"""
ESC SCORE2 and SCORE2-OP 10-year cardiovascular disease risk equations.

References:
    SCORE2 working group and ESC Cardiovascular Risk Collaboration. SCORE2
    risk prediction algorithms: new models to estimate 10-year risk of
    cardiovascular disease in Europe. Eur Heart J. 2021 Jul 1;42(25):2439-2454.
    doi:10.1093/eurheartj/ehab309. PMID: 34120177.

    SCORE2-OP working group and ESC Cardiovascular Risk Collaboration.
    SCORE2-OP risk prediction algorithms: estimating incident cardiovascular
    event risk in older persons in four geographical risk regions.
    Eur Heart J. 2021 Jul 1;42(25):2455-2467. doi:10.1093/eurheartj/ehab312.
    PMID: 34120185.

Coefficient source:
    Cox-regression coefficients and regional recalibration constants
    (scale1, scale2) sourced from the SCORE2 supplementary material
    (page 9), as transcribed in the open-source `RiskScorescvd` R package
    (https://github.com/dvicencio/RiskScorescvd, file 11_SCORE2_func.R).

Outcome:
    10-year risk of fatal AND non-fatal cardiovascular disease (CVD).
    Note this differs from Framingham (general CVD, broader composite) and
    from PREVENT (ASCVD-only). The fusion logic in heart_score.py
    acknowledges this difference.

Population of validity:
    Adults aged 40-89, no prior CVD or diabetes (though diabetes was kept
    in the model for recalibration; setting diabetes=0 for non-diabetics
    works correctly).

Risk regions:
    SCORE2 was calibrated for four geographical European regions based on
    standardised CVD mortality rates: Low / Moderate / High / Very high.
    India is NOT in the original calibration. Per discussion in
    METHODOLOGY.md, this engine defaults to the "High" risk region for
    Indian patients as the closest available proxy, with the caveat that
    India-specific recalibration does not yet exist for SCORE2.

Cholesterol units:
    SCORE2 uses mmol/L internally. Inputs are accepted in mg/dL (US
    convention) and converted using the factor 38.67 for total/HDL
    cholesterol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

CHOL_MG_DL_PER_MMOL_L = 38.67

RiskRegion = Literal["low", "moderate", "high", "very_high"]

# Regional recalibration constants for individuals aged 40-69 (SCORE2).
# Format: (scale1, scale2) per (region, sex).
# Source: SCORE2 supplementary material; values cross-verified against the
# RiskScorescvd R package implementation.
_SCORE2_SCALES_UNDER_70 = {
    ("low", "male"):       (-0.5699,  0.7476),
    ("low", "female"):     (-0.7380,  0.7019),
    ("moderate", "male"):  (-0.1565,  0.8009),
    ("moderate", "female"):(-0.3143,  0.7701),
    ("high", "male"):      ( 0.3207,  0.9360),
    ("high", "female"):    ( 0.5710,  0.9369),
    ("very_high", "male"): ( 0.5836,  0.8294),
    ("very_high", "female"):(0.9412,  0.8329),
}

# Regional recalibration constants for SCORE2-OP (age 70+).
_SCORE2_SCALES_70_PLUS = {
    ("low", "male"):       (-0.34,    1.19),
    ("low", "female"):     (-0.52,    1.01),
    ("moderate", "male"):  ( 0.01,    1.25),
    ("moderate", "female"):(-0.10,    1.10),
    ("high", "male"):      ( 0.08,    1.15),
    ("high", "female"):    ( 0.38,    1.09),
    ("very_high", "male"): ( 0.05,    0.70),
    ("very_high", "female"):(0.38,    0.69),
}


@dataclass
class SCORE2Input:
    """Inputs for SCORE2 / SCORE2-OP.

    Units:
        age:               years (40-89)
        total_cholesterol: mg/dL
        hdl_cholesterol:   mg/dL
        sbp:               mmHg
        smoker / diabetes: bool
    """

    sex: Literal["male", "female"]
    age: float
    total_cholesterol: float
    hdl_cholesterol: float
    sbp: float
    smoker: bool
    diabetes: bool
    risk_region: RiskRegion = "high"


def _score2_under_70(inputs: SCORE2Input) -> float:
    """SCORE2 linear predictor + baseline survival, age 40-69.

    Returns the un-recalibrated 10-year risk (caller applies regional scaling).
    """
    age = inputs.age
    smoker = 1 if inputs.smoker else 0
    diabetes = 1 if inputs.diabetes else 0
    total_chol = inputs.total_cholesterol / CHOL_MG_DL_PER_MMOL_L  # → mmol/L
    hdl = inputs.hdl_cholesterol / CHOL_MG_DL_PER_MMOL_L

    age_term = (age - 60) / 5
    sbp_term = (inputs.sbp - 120) / 20
    chol_term = (total_chol - 6) / 1
    hdl_term = (hdl - 1.3) / 0.5

    if inputs.sex == "male":
        lp = (
            0.3742 * age_term
            + 0.6012 * smoker
            + 0.2777 * sbp_term
            + 0.6457 * diabetes
            + 0.1458 * chol_term
            + (-0.2698) * hdl_term
            + (-0.0755) * age_term * smoker
            + (-0.0255) * age_term * sbp_term
            + (-0.0281) * age_term * chol_term
            + 0.0426 * age_term * hdl_term
            + (-0.0983) * age_term * diabetes
        )
        baseline_survival = 0.9605
    else:  # female
        lp = (
            0.4648 * age_term
            + 0.7744 * smoker
            + 0.3131 * sbp_term
            + 0.8096 * diabetes
            + 0.1002 * chol_term
            + (-0.2606) * hdl_term
            + (-0.1088) * age_term * smoker
            + (-0.0277) * age_term * sbp_term
            + (-0.0226) * age_term * chol_term
            + 0.0613 * age_term * hdl_term
            + (-0.1272) * age_term * diabetes
        )
        baseline_survival = 0.9776

    return 1.0 - baseline_survival ** math.exp(lp)


def _score2_op(inputs: SCORE2Input) -> float:
    """SCORE2-OP linear predictor + baseline survival, age 70+.

    Returns the un-recalibrated 10-year risk.
    """
    age = inputs.age
    smoker = 1 if inputs.smoker else 0
    diabetes = 1 if inputs.diabetes else 0
    total_chol = inputs.total_cholesterol / CHOL_MG_DL_PER_MMOL_L
    hdl = inputs.hdl_cholesterol / CHOL_MG_DL_PER_MMOL_L

    age_term = age - 73           # OP centers age at 73, not 60
    sbp_term = inputs.sbp - 150
    chol_term = total_chol - 6
    hdl_term = hdl - 1.4

    if inputs.sex == "male":
        lp = (
            0.0634 * age_term
            + 0.4245 * diabetes
            + 0.3524 * smoker
            + 0.0094 * sbp_term
            + 0.0850 * chol_term
            + (-0.3564) * hdl_term
            + (-0.0174) * age_term * diabetes
            + (-0.0247) * age_term * smoker
            + (-0.0005) * age_term * sbp_term
            + 0.0073 * age_term * chol_term
            + 0.0091 * age_term * hdl_term
        )
        # Note: SCORE2-OP centers the LP using a published correction term
        # before applying the baseline survival.
        return 1.0 - 0.7576 ** math.exp(lp - 0.0929)
    else:  # female
        lp = (
            0.0789 * age_term
            + 0.6010 * diabetes
            + 0.4921 * smoker
            + 0.0102 * sbp_term
            + 0.0605 * chol_term
            + (-0.3040) * hdl_term
            + (-0.0107) * age_term * diabetes
            + (-0.0255) * age_term * smoker
            + (-0.0004) * age_term * sbp_term
            + (-0.0009) * age_term * chol_term
            + 0.0154 * age_term * hdl_term
        )
        return 1.0 - 0.8082 ** math.exp(lp - 0.229)


def calculate_score2_risk(inputs: SCORE2Input) -> float:
    """SCORE2 / SCORE2-OP 10-year risk of fatal+non-fatal CVD as a fraction.

    Selects the SCORE2 (age 40-69) or SCORE2-OP (age 70+) sub-model based on
    age, computes the un-recalibrated risk, then applies the region-specific
    Gompertz-style recalibration:
        recalibrated = 1 - exp(-exp(scale1 + scale2 * log(-log(1 - raw))))
    """
    if inputs.sex not in ("male", "female"):
        raise ValueError(f"sex must be 'male' or 'female', got {inputs.sex!r}")
    if inputs.risk_region not in ("low", "moderate", "high", "very_high"):
        raise ValueError(f"unknown risk region: {inputs.risk_region!r}")
    if not (40 <= inputs.age <= 89):
        raise ValueError(
            f"age must be between 40 and 89 (SCORE2 validation range), "
            f"got {inputs.age}"
        )

    if inputs.age < 70:
        raw_risk = _score2_under_70(inputs)
        scale1, scale2 = _SCORE2_SCALES_UNDER_70[(inputs.risk_region, inputs.sex)]
    else:
        raw_risk = _score2_op(inputs)
        scale1, scale2 = _SCORE2_SCALES_70_PLUS[(inputs.risk_region, inputs.sex)]

    # Avoid log of 1 or 0 numerically.
    raw_risk = max(min(raw_risk, 1 - 1e-9), 1e-9)
    recalibrated = 1.0 - math.exp(
        -math.exp(scale1 + scale2 * math.log(-math.log(1.0 - raw_risk)))
    )
    return max(0.0, min(1.0, recalibrated))


def factor_contributions(inputs: SCORE2Input) -> dict[str, float]:
    """Per-factor contribution to the linear predictor, for the explainability
    layer. Computed as deviation from the optimal-reference patient (matched
    age + sex, with the model-defined "centered" reference values for SBP,
    chol, HDL, no diabetes, no smoking).

    Note: SCORE2 doesn't separately model BP-treatment status as a predictor
    (unlike Framingham/PREVENT), so that factor isn't surfaced here.
    """
    smoker = 1 if inputs.smoker else 0
    diabetes = 1 if inputs.diabetes else 0
    total_chol = inputs.total_cholesterol / CHOL_MG_DL_PER_MMOL_L
    hdl = inputs.hdl_cholesterol / CHOL_MG_DL_PER_MMOL_L

    if inputs.age < 70:
        age_term = (inputs.age - 60) / 5
        sbp_term = (inputs.sbp - 120) / 20
        chol_term = (total_chol - 6) / 1
        hdl_term = (hdl - 1.3) / 0.5
        if inputs.sex == "male":
            return {
                "Smoking": 0.6012 * smoker + (-0.0755) * age_term * smoker,
                "Systolic blood pressure": (
                    0.2777 * sbp_term + (-0.0255) * age_term * sbp_term
                ),
                "Diabetes": 0.6457 * diabetes + (-0.0983) * age_term * diabetes,
                "Total cholesterol": (
                    0.1458 * chol_term + (-0.0281) * age_term * chol_term
                ),
                "HDL cholesterol": (
                    -0.2698 * hdl_term + 0.0426 * age_term * hdl_term
                ),
                "Age": 0.3742 * age_term,
            }
        else:
            return {
                "Smoking": 0.7744 * smoker + (-0.1088) * age_term * smoker,
                "Systolic blood pressure": (
                    0.3131 * sbp_term + (-0.0277) * age_term * sbp_term
                ),
                "Diabetes": 0.8096 * diabetes + (-0.1272) * age_term * diabetes,
                "Total cholesterol": (
                    0.1002 * chol_term + (-0.0226) * age_term * chol_term
                ),
                "HDL cholesterol": (
                    -0.2606 * hdl_term + 0.0613 * age_term * hdl_term
                ),
                "Age": 0.4648 * age_term,
            }
    else:
        # SCORE2-OP contributions
        age_term = inputs.age - 73
        sbp_term = inputs.sbp - 150
        chol_term = total_chol - 6
        hdl_term = hdl - 1.4
        if inputs.sex == "male":
            return {
                "Smoking": 0.3524 * smoker + (-0.0247) * age_term * smoker,
                "Systolic blood pressure": (
                    0.0094 * sbp_term + (-0.0005) * age_term * sbp_term
                ),
                "Diabetes": 0.4245 * diabetes + (-0.0174) * age_term * diabetes,
                "Total cholesterol": (
                    0.0850 * chol_term + 0.0073 * age_term * chol_term
                ),
                "HDL cholesterol": (
                    -0.3564 * hdl_term + 0.0091 * age_term * hdl_term
                ),
                "Age": 0.0634 * age_term,
            }
        else:
            return {
                "Smoking": 0.4921 * smoker + (-0.0255) * age_term * smoker,
                "Systolic blood pressure": (
                    0.0102 * sbp_term + (-0.0004) * age_term * sbp_term
                ),
                "Diabetes": 0.6010 * diabetes + (-0.0107) * age_term * diabetes,
                "Total cholesterol": (
                    0.0605 * chol_term + (-0.0009) * age_term * chol_term
                ),
                "HDL cholesterol": (
                    -0.3040 * hdl_term + 0.0154 * age_term * hdl_term
                ),
                "Age": 0.0789 * age_term,
            }
