"""
CardioQ Heart Score (0-100) fusion engine.

Combines the three sub-models (Framingham, SCORE2, PREVENT) into a single
0-100 unified Heart Score with a clinical risk band and the top contributing
factors.

Methodology (see METHODOLOGY.md for full justification):

1. Each sub-model returns a 10-year cardiovascular risk percentage.
2. Each percentage is mapped to a 0-100 sub-score using the *algorithm's
   own published risk-band thresholds* with linear interpolation inside each
   band. This ensures we don't mix incompatible numerical scales.
3. The three sub-scores are combined as a weighted average:
        Framingham : 0.35
        PREVENT    : 0.35
        SCORE2     : 0.30
   PREVENT is slightly favoured for being the most recent and including
   kidney/metabolic predictors. SCORE2 is mildly down-weighted because it
   was calibrated on European populations and there is no India-specific
   recalibration; we still include it for triangulation.
4. The unified Heart Score is mapped to a risk band:
        0  -  20  → Low
        20 -  40  → Borderline
        40 -  60  → Moderate
        60 -  80  → High
        80 - 100  → Very High
5. Top contributing factors are identified by aggregating per-factor
   contributions across all three sub-models (factors that affect more
   than one model are summed across them).

Important caveat (also stated in methodology):
    The three algorithms predict slightly different outcomes (general CVD,
    fatal+nonfatal CVD, ASCVD-only). Averaging them is an approximation; we
    name this limitation explicitly rather than hide it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from algorithms.framingham import (
    FraminghamInput,
    calculate_framingham_risk,
    factor_contributions as framingham_factors,
)
from algorithms.score2 import (
    SCORE2Input,
    calculate_score2_risk,
    factor_contributions as score2_factors,
    RiskRegion,
)
from algorithms.prevent import (
    PREVENTInput,
    calculate_prevent_ascvd_risk,
    factor_contributions as prevent_factors,
)

# Weights for the three sub-models in the weighted average.
WEIGHTS = {
    "framingham": 0.35,
    "prevent":    0.35,
    "score2":     0.30,
}

# Risk-band thresholds (10-year %) used to map each algorithm's raw output
# to a 0-100 sub-score with linear interpolation within each band.
#   - Framingham general CVD: <5 / 5-10 / 10-20 / 20-30 / >30
#   - SCORE2:                <5 / 5-10 / 10-20 / 20-30 / >30  (same buckets
#                            for simplicity and consistency; the ESC's own
#                            age-stratified thresholds are surfaced via the
#                            risk_region in the SCORE2 module)
#   - PREVENT ASCVD:         <5 / 5-7.5 / 7.5-10 / 10-20 / >20  (per AHA
#                            guideline thresholds for statin decisions)
_BAND_EDGES = {
    "framingham": [(0.0, 0), (5.0, 20), (10.0, 40), (20.0, 60), (30.0, 80), (60.0, 100)],
    "score2":     [(0.0, 0), (5.0, 20), (10.0, 40), (20.0, 60), (30.0, 80), (60.0, 100)],
    "prevent":    [(0.0, 0), (5.0, 20), (7.5, 40), (10.0, 60), (20.0, 80), (50.0, 100)],
}


def _percent_to_subscore(risk_percent: float, model_key: str) -> float:
    """Map a 10-year risk % to a 0-100 sub-score using the model's own band
    edges, with linear interpolation inside each band."""
    edges = _BAND_EDGES[model_key]
    if risk_percent <= edges[0][0]:
        return float(edges[0][1])
    if risk_percent >= edges[-1][0]:
        return float(edges[-1][1])
    for (x0, y0), (x1, y1) in zip(edges, edges[1:]):
        if x0 <= risk_percent <= x1:
            return y0 + (y1 - y0) * (risk_percent - x0) / (x1 - x0)
    return float(edges[-1][1])  # defensive fallback


def _classify_band(score: float) -> str:
    if score < 20:
        return "Low"
    if score < 40:
        return "Borderline"
    if score < 60:
        return "Moderate"
    if score < 80:
        return "High"
    return "Very High"


@dataclass
class PatientInput:
    """The unified patient input form. Inputs cover the union of variables
    needed by Framingham, SCORE2, and PREVENT.

    Missing-data rule: BMI/eGFR are required for PREVENT. If they are None,
    PREVENT is skipped and the remaining two algorithms are re-weighted
    proportionally.
    """

    sex: Literal["male", "female"]
    age: float                      # years
    total_cholesterol: float        # mg/dL
    hdl_cholesterol: float          # mg/dL
    sbp: float                      # mmHg
    on_bp_treatment: bool
    smoker: bool
    diabetes: bool
    on_statin: bool = False
    bmi: float | None = None        # kg/m^2  — needed for PREVENT
    egfr: float | None = None       # mL/min/1.73 m2 — needed for PREVENT
    score2_risk_region: RiskRegion = "high"  # India default → "high"


@dataclass
class HeartScoreResult:
    heart_score: float
    risk_band: str
    sub_scores: dict[str, float] = field(default_factory=dict)
    sub_risks_percent: dict[str, float | None] = field(default_factory=dict)
    weights_used: dict[str, float] = field(default_factory=dict)
    top_factors: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def plain_language_summary(self) -> str:
        """One-paragraph patient-facing summary."""
        risk = self.heart_score
        framings = []
        for k, v in self.sub_risks_percent.items():
            if v is not None:
                framings.append(f"{k.capitalize()}: {v:.1f}%")
        ten_yr_estimates = ", ".join(framings)
        top_three = ", ".join(name for name, _ in self.top_factors[:3])
        return (
            f"Your unified CardioQ Heart Score is {risk:.0f} out of 100, "
            f"placing you in the '{self.risk_band}' risk band over the next "
            f"10 years. Three globally validated algorithms each estimated "
            f"your individual 10-year risk: {ten_yr_estimates}. The factors "
            f"contributing most to your current score are: {top_three}. "
            f"This is an educational estimate, not a clinical diagnosis — "
            f"please discuss your full picture with a qualified clinician."
        )


def _aggregate_top_factors(
    framingham_contribs: dict[str, float],
    score2_contribs: dict[str, float],
    prevent_contribs: dict[str, float],
    n: int = 3,
) -> list[tuple[str, float]]:
    """Sum per-factor contributions across the three sub-models and return
    the top-n factors driving risk upward.

    Each sub-model's contributions are first normalized so their magnitudes
    are comparable (divide by the sum of absolute contributions in that
    model). Then we sum per factor name and rank by descending contribution.
    """

    def normalize(contribs: dict[str, float]) -> dict[str, float]:
        magnitude = sum(abs(v) for v in contribs.values())
        if magnitude == 0:
            return {k: 0.0 for k in contribs}
        return {k: v / magnitude for k, v in contribs.items()}

    aggregated: dict[str, float] = defaultdict(float)
    for source in (framingham_contribs, score2_contribs, prevent_contribs):
        if not source:
            continue
        for k, v in normalize(source).items():
            # Light name harmonisation across models so e.g. "Total cholesterol"
            # and "Non-HDL cholesterol" are not double-counted.
            key = k
            if k in ("Total cholesterol", "Non-HDL cholesterol"):
                key = "Cholesterol (lipids)"
            elif k == "Kidney function (eGFR)":
                key = "Kidney function"
            aggregated[key] += v

    # Rank by contribution descending. Negative values mean the factor is
    # protective for this patient; we want the top *upward* drivers.
    ranked = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
    # Filter out factors with non-positive contribution before slicing top-n.
    positive = [(k, v) for k, v in ranked if v > 0]
    return positive[:n]


def calculate_heart_score(patient: PatientInput) -> HeartScoreResult:
    """Run all three sub-models, fuse to a 0-100 score, return a result
    object with full transparency on what fed in."""

    notes: list[str] = []

    # ---- Framingham (always runs; valid 30-74) ----
    fram_risk: float | None
    fram_factors: dict[str, float] = {}
    if 30 <= patient.age <= 74:
        fram_inputs = FraminghamInput(
            sex=patient.sex, age=patient.age,
            total_cholesterol=patient.total_cholesterol,
            hdl_cholesterol=patient.hdl_cholesterol,
            sbp=patient.sbp, on_bp_treatment=patient.on_bp_treatment,
            smoker=patient.smoker, diabetes=patient.diabetes,
        )
        fram_risk = calculate_framingham_risk(fram_inputs)
        fram_factors = framingham_factors(fram_inputs)
    else:
        fram_risk = None
        notes.append("Framingham skipped: age outside the 30-74 validation range.")

    # ---- SCORE2 / SCORE2-OP (40-89) ----
    score2_risk: float | None
    s2_factors: dict[str, float] = {}
    if 40 <= patient.age <= 89:
        s2_inputs = SCORE2Input(
            sex=patient.sex, age=patient.age,
            total_cholesterol=patient.total_cholesterol,
            hdl_cholesterol=patient.hdl_cholesterol,
            sbp=patient.sbp,
            smoker=patient.smoker, diabetes=patient.diabetes,
            risk_region=patient.score2_risk_region,
        )
        score2_risk = calculate_score2_risk(s2_inputs)
        s2_factors = score2_factors(s2_inputs)
    else:
        score2_risk = None
        notes.append("SCORE2 skipped: age outside the 40-89 validation range.")

    # ---- PREVENT (30-79; needs BMI and eGFR) ----
    prev_risk: float | None
    p_factors: dict[str, float] = {}
    if patient.bmi is None or patient.egfr is None:
        prev_risk = None
        notes.append(
            "PREVENT skipped: BMI and/or eGFR not provided. PREVENT is "
            "the only sub-model that needs kidney function and BMI."
        )
    elif not (30 <= patient.age <= 79):
        prev_risk = None
        notes.append("PREVENT skipped: age outside the 30-79 validation range.")
    else:
        p_inputs = PREVENTInput(
            sex=patient.sex, age=patient.age,
            total_cholesterol=patient.total_cholesterol,
            hdl_cholesterol=patient.hdl_cholesterol,
            sbp=patient.sbp, bmi=patient.bmi, egfr=patient.egfr,
            on_bp_treatment=patient.on_bp_treatment,
            on_statin=patient.on_statin,
            diabetes=patient.diabetes, smoker=patient.smoker,
        )
        prev_risk = calculate_prevent_ascvd_risk(p_inputs)
        p_factors = prevent_factors(p_inputs)

    # ---- Fuse ----
    sub_risks_pct = {
        "framingham": fram_risk * 100 if fram_risk is not None else None,
        "score2":     score2_risk * 100 if score2_risk is not None else None,
        "prevent":    prev_risk * 100 if prev_risk is not None else None,
    }

    sub_scores: dict[str, float] = {}
    for key, pct in sub_risks_pct.items():
        if pct is not None:
            sub_scores[key] = _percent_to_subscore(pct, key)

    if not sub_scores:
        # No algorithm could run — return a defensive zero with a clear note.
        return HeartScoreResult(
            heart_score=0.0, risk_band="Unable to estimate",
            sub_scores={}, sub_risks_percent=sub_risks_pct,
            weights_used={}, top_factors=[],
            notes=notes + [
                "No risk algorithm could run for this patient profile. "
                "Please review the inputs and validity ranges."
            ],
        )

    # Re-weight surviving algorithms so weights still sum to 1.
    total_weight = sum(WEIGHTS[k] for k in sub_scores)
    used_weights = {k: WEIGHTS[k] / total_weight for k in sub_scores}

    heart_score = sum(used_weights[k] * sub_scores[k] for k in sub_scores)

    top_factors = _aggregate_top_factors(fram_factors, s2_factors, p_factors)

    return HeartScoreResult(
        heart_score=round(heart_score, 1),
        risk_band=_classify_band(heart_score),
        sub_scores={k: round(v, 1) for k, v in sub_scores.items()},
        sub_risks_percent=sub_risks_pct,
        weights_used=used_weights,
        top_factors=top_factors,
        notes=notes,
    )


# -----------------------------------------------------------------------------
# Counterfactual ("what-if") view
# -----------------------------------------------------------------------------

@dataclass
class Counterfactual:
    """A single 'what if you changed X' scenario.

    Attributes:
        label:           Short user-facing description.
        rationale:       Clinical justification for why we suggest this change.
        new_score:       The recomputed Heart Score under the modified inputs.
        score_delta:     new_score - current_score (negative = risk reduction).
        new_band:        The new risk band.
    """
    label: str
    rationale: str
    new_score: float
    score_delta: float
    new_band: str


def _modified_patient(patient: PatientInput, **overrides) -> PatientInput:
    """Return a copy of `patient` with the named fields overridden."""
    from dataclasses import replace
    return replace(patient, **overrides)


def counterfactual_scenarios(
    patient: PatientInput,
    current_result: HeartScoreResult,
    max_scenarios: int = 4,
) -> list[Counterfactual]:
    """Compute 'what if' scenarios for the modifiable risk factors that are
    currently elevated for this patient.

    We only suggest scenarios that (a) apply to the patient (no point telling
    a non-smoker to quit) and (b) target factors clinical guidelines actually
    treat as modifiable in primary prevention.

    Returns up to `max_scenarios` scenarios ranked by score reduction.
    """
    candidates: list[Counterfactual] = []

    def _make(label: str, rationale: str, **overrides) -> Counterfactual | None:
        modified = _modified_patient(patient, **overrides)
        new_result = calculate_heart_score(modified)
        delta = new_result.heart_score - current_result.heart_score
        # Only surface scenarios that actually reduce risk by a non-trivial
        # margin (avoid noise from float rounding).
        if delta >= -0.5:
            return None
        return Counterfactual(
            label=label,
            rationale=rationale,
            new_score=new_result.heart_score,
            score_delta=delta,
            new_band=new_result.risk_band,
        )

    # 1) Smoking — single largest modifiable factor in any risk model.
    if patient.smoker:
        cf = _make(
            label="If you quit smoking",
            rationale=(
                "Smoking cessation is the single largest modifiable risk "
                "reduction in primary prevention; risk drops materially "
                "within 1–2 years."
            ),
            smoker=False,
        )
        if cf:
            candidates.append(cf)

    # 2) Systolic BP — if elevated above guideline target.
    if patient.sbp > 130:
        target = 120
        cf = _make(
            label=f"If your systolic BP dropped to {target} mmHg",
            rationale=(
                "Lowering SBP toward the AHA 2025 hypertension target "
                "(<130 mmHg, ideally 120) is consistently the second largest "
                "modifiable lever after smoking."
            ),
            sbp=float(target),
        )
        if cf:
            candidates.append(cf)

    # 3) HDL cholesterol — if low.
    if patient.hdl_cholesterol < 50:
        target_hdl = 60
        cf = _make(
            label=f"If your HDL rose to {target_hdl} mg/dL",
            rationale=(
                "HDL is a protective factor in all three sub-models. "
                "Aerobic exercise and weight loss raise HDL by 5–15 mg/dL "
                "in most patients."
            ),
            hdl_cholesterol=float(target_hdl),
        )
        if cf:
            candidates.append(cf)

    # 4) Total cholesterol — if high enough that statin therapy is reasonable.
    if patient.total_cholesterol > 220 and not patient.on_statin:
        target_total = 180
        cf = _make(
            label=f"If you started a statin (total cholesterol → {target_total} mg/dL)",
            rationale=(
                "Moderate-intensity statin therapy typically reduces total "
                "cholesterol by 25–35%. Recommended for 10-yr ASCVD risk ≥5% "
                "per AHA 2026 lipid guidelines."
            ),
            total_cholesterol=float(target_total),
            on_statin=True,
        )
        if cf:
            candidates.append(cf)

    # Note on BMI: we deliberately do NOT include a BMI counterfactual.
    # BMI is not a predictor in Framingham (Lipids model), SCORE2, or
    # PREVENT-ASCVD (its coefficient is 0 in the base ASCVD equations; BMI
    # only enters PREVENT's separate heart-failure model, which we don't use
    # in this unified score). Suggesting weight loss as a "what if" would be
    # clinically reasonable but the model can't quantify the benefit, so we
    # don't surface it rather than mislead. Documented in METHODOLOGY §7.

    # Rank by largest absolute risk reduction (most negative delta first).
    candidates.sort(key=lambda c: c.score_delta)
    return candidates[:max_scenarios]
