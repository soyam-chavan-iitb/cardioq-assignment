# CardioQ Heart Score — Methodology Note

**Author**: Swayam (IIT Bombay) | **Role under evaluation**: Product Development Intern, CardioQ.ai
**Submitted to**: Capt. Indra Kumar Jha, Founder & CEO, Ziffytech Digital Healthcare
**Build window**: 48-hour AI-augmented sprint

---

## 1. Problem statement

Build a working prototype of a CardioQ Heart Score engine: a single application
that takes a patient's clinical inputs, runs three globally validated risk
algorithms (Framingham 2008, ESC SCORE2 2021, AHA PREVENT 2023) in parallel,
and returns one unified, explainable Heart Score on a 0–100 scale, with a
risk band, top contributing factors, and an exportable report.

This document describes the methodological choices behind the engine and
is intended to be read alongside the source code in this repository.

---

## 2. The three sub-models

| Model | Year | Outcome predicted | Validation age range | Inputs (base model) |
|---|---|---|---|---|
| Framingham General CVD | 2008 | Composite CVD: coronary death, MI, coronary insufficiency, angina, ischemic/hemorrhagic stroke, TIA, PAD, HF | 30–74 | Age, sex, total chol, HDL, SBP (treated/untreated), smoker, diabetes |
| SCORE2 / SCORE2-OP | 2021 | Fatal + non-fatal CVD (MI, stroke, CV death) | 40–69 / 70–89 | Age, sex, smoker, SBP, total chol, HDL, regional calibration |
| AHA PREVENT (base) | 2023 | 10-yr ASCVD (MI + stroke) | 30–79 | Age, sex, total chol, HDL, SBP, BP-tx, statin, diabetes, smoker, BMI, eGFR |

The three models were selected by the assignment brief; they are the most
recent and most clinically endorsed in their respective regulatory
jurisdictions (US, EU, AHA-revised US).

A note on outcome heterogeneity that we make explicit rather than hide:
Framingham predicts a broader CVD composite (it includes heart failure and
TIA, which the others don't). SCORE2 includes both fatal and non-fatal CVD
mortality. PREVENT's primary 10-year output is ASCVD-only (the heart-failure
component is modelled separately). When we average the three, we are
*approximately* combining three different predictions of "the same broad
underlying risk", which is defensible at this prototype stage but a known
limitation for clinical use.

## 3. Coefficient sourcing and verification

A key concern was that AI recall of recent equation coefficients can be
unreliable. The assignment brief instructed: "*we expect you to verify by
reading the paper, not just trust Claude's recall.*" We followed this
strictly:

- **Framingham 2008 coefficients** were taken directly from the [Framingham
  Heart Study's official risk-function page](https://www.framinghamheartstudy.org/fhs-risk-functions/cardiovascular-disease-10-year-risk/),
  which publishes the regression coefficients, baseline survival, and the
  centring constant. We then verified the implementation by hand-tracing one
  case (61F, TC 180, HDL 47, SBP 124, no other risks): LP = 26.4390,
  LP − μ = 0.2459, risk = 1 − 0.95012^exp(0.2459) = 6.32%, which matches the
  test fixture exactly.

- **SCORE2 + SCORE2-OP coefficients** (sex-specific Cox terms, baseline
  survivals 0.9605/0.9776/0.7576/0.8082, and regional recalibration
  constants `scale1`/`scale2` for all 4 regions × 2 sexes × 2 age bands)
  were sourced from the SCORE2 supplementary material, as transcribed in
  the open-source `RiskScorescvd` R package
  (github.com/dvicencio/RiskScorescvd, file `11_SCORE2_func.R`). We then
  verified the implementation against the SCORE2 paper's own abstract,
  which states the 10-year risk for a 50-year-old smoker with SBP 140
  mmHg, total chol 5.5 mmol/L, HDL 1.3 mmol/L: men 5.9% (low region) /
  14.0% (very-high), women 4.2% / 13.7%. **Our engine reproduces all four
  values exactly.**

- **PREVENT coefficients** for the 10-year base model (23 features × 5
  outcomes × 2 sexes = 230 betas, of which we use the 46 ASCVD-relevant
  ones) were extracted directly from the open-source `preventr` R package
  (github.com/martingmayer/preventr) by loading its `sysdata.rda` binary in
  R and exporting the coefficient matrix. The `preventr` author cites
  Khan 2024 Supplementary Table S25 as the source. We then verified the
  implementation against the published reference example: female age 50,
  SBP 160 (on BP-treatment), total chol 200 mg/dL, HDL 45 mg/dL, no
  statin, diabetic, non-smoker, eGFR 90, BMI 35 → expected 9.2%, our
  engine returns 9.20%, agreement at 4 decimal places.

In all three cases, **we wrote the engine ourselves in pure Python**
(no R bridge, no compiled binary dependency, no API calls) — the
above sources were used to obtain numerical values that we then encoded
into our own modules with our own input validation, error handling,
spline transformations, and explainability layers.

## 4. Heart Score normalisation

The single most consequential design choice in this engine is how to map
three different 10-year risk percentages (with different outcome
definitions) into one 0–100 number. We rejected three tempting shortcuts:

- **Average the percentages directly.** Wrong: a 10% Framingham CVD risk
  and a 10% PREVENT-ASCVD risk represent different underlying probabilities,
  so arithmetic-averaging hides the disagreement.
- **Take the maximum.** Conservative but loses information. A 30%
  Framingham + 5% PREVENT + 5% SCORE2 average would produce 30% under this
  rule, which over-weights one model.
- **Train a regression to map our three inputs to one number.** The brief
  forbids ML training, and we wouldn't have the labelled outcome data
  anyway.

The chosen approach maps each percentage to a 0–100 sub-score using *that
algorithm's own published clinical risk-band thresholds* with linear
interpolation inside each band, then takes a weighted average.

| Algorithm | 0–20 | 20–40 | 40–60 | 60–80 | 80–100 |
|---|---|---|---|---|---|
| Framingham | <5% | 5–10% | 10–20% | 20–30% | >30% |
| SCORE2 | <5% | 5–10% | 10–20% | 20–30% | >30% |
| PREVENT | <5% | 5–7.5% | 7.5–10% | 10–20% | >20% |

The bands for Framingham and SCORE2 are the 5/10/20/30% breakpoints used
clinically for low / borderline / moderate / high / very-high risk
classification. PREVENT's bands follow the AHA/ACC 2026 lipid guidelines,
which set 5% / 7.5% / 10% / 20% as the meaningful thresholds for
lipid-lowering therapy decisions.

This approach has three properties we like:
1. We don't pretend to out-statistics the algorithms; we use each one's
   own calibration.
2. The bands are clinically validated decision thresholds, not arbitrary
   numbers.
3. The mapping is monotone and continuous, so small input changes produce
   small score changes.

**Sub-model weights**:
- Framingham: 0.35
- PREVENT: 0.35
- SCORE2: 0.30

PREVENT is slightly favoured for being the most recent (2023) and for
incorporating kidney function and BMI. SCORE2 is mildly down-weighted
because India is not in its original 4-region calibration and we therefore
default to the "high-risk" region as a proxy (see §6 below). Framingham
remains weighted alongside PREVENT because it is the most thoroughly
validated of the three across decades and populations, even though it is
the oldest.

The final 0–100 score maps to a five-tier risk band:

| Score | Band |
|---|---|
| 0–19  | Low |
| 20–39 | Borderline |
| 40–59 | Moderate |
| 60–79 | High |
| 80–100 | Very High |

## 5. Explainability layer (top contributing factors)

For each sub-model we compute the per-factor contribution to the linear
predictor, evaluated as the deviation from a matched "optimal reference
patient" of the same age and sex (TC 170 mg/dL, HDL 60 mg/dL, SBP 110
mmHg, BMI 25, eGFR 90, no diabetes/smoking/medication). We then:

1. Normalise each model's contributions by the sum of absolute
   contributions (so a small-coefficient model can't be drowned out by a
   large-coefficient model).
2. Sum across models, harmonising names where the same underlying factor
   appears under different labels (e.g. Framingham's "Total cholesterol"
   and PREVENT's "Non-HDL cholesterol" both roll up into "Cholesterol
   (lipids)").
3. Rank by descending contribution and return the top three positive
   drivers.

Output: a ranked list of human-readable factor names with relative
weights, surfaced in the UI and in the JSON export.

## 6. Missing-data handling

The brief required handling a profile with missing cholesterol. Our policy:

- **Framingham** runs only if age 30–74 and lipid + SBP inputs are present.
  Lipid imputation is not attempted — Framingham *requires* TC and HDL.
- **SCORE2 / SCORE2-OP** runs only if age 40–89.
- **PREVENT** requires BMI and eGFR. If either is missing, PREVENT is
  skipped.

When any sub-model is skipped, the surviving sub-models are re-weighted
proportionally so the weights still sum to 1. The skipped models are
flagged in the result `notes` and shown in the UI so the user can see
exactly what fed into the score and what didn't. This is preferable to
silent imputation.

## 7. Indian-population considerations and limitations

A few honest caveats:

- **SCORE2 has no India-specific calibration.** SCORE2 publishes
  recalibration constants for four European risk regions only. India's
  cardiovascular epidemiology more closely resembles the "high" region (CV
  mortality between 150–300 per 100,000, prevalence of premature ASCVD
  comparable to Eastern Europe), so we default the SCORE2 region selector
  to "high" — but the user can override this. A SCORE2 Asia-Pacific
  variant exists (Hageman 2024) but is not yet implemented here; this is
  a clear next-iteration improvement.

- **PREVENT was developed and validated in US data.** The AHA explicitly
  flags this in its FAQ. PREVENT may over- or under-estimate risk in
  South Asian populations, who are known to have higher ASCVD risk at any
  given LDL level than the populations PREVENT was trained on.

- **Framingham notoriously over-estimates** in non-Anglo-Saxon
  populations. Several studies (e.g., D'Agostino 2001 internal
  validation; subsequent Indian validation studies) have shown it can
  over-predict by 30–60% in South Asian cohorts. Recalibration to Indian
  data is a known need.

- **None of the three include South-Asian-specific risk enhancers**
  (e.g. coronary calcium imaging, family history of premature CVD,
  Lipoprotein(a)). The 2019 ACC/AHA primary prevention guideline lists
  South Asian ancestry itself as a risk-enhancing factor, which our
  current engine does not surface.

The unified Heart Score is therefore best interpreted as a *triangulated
educational estimate*, not a clinical decision-making tool. The risk band
should be considered indicative, particularly for Indian patients. Any
real CardioQ.ai product release would need (a) recalibration on Indian
cohort data, (b) integration of South-Asian-specific enhancers, and
(c) regulatory pathway compliance.

## 8. What I would build next given two more weeks

1. **Indian recalibration.** Re-fit the regional constants of SCORE2 to
   Indian cohort data (e.g. INTERHEART India arm, LUCAS, or similar) so
   the engine produces locally-calibrated risk rather than European
   "high-region" approximation.
2. **South Asian risk enhancers.** Add Lp(a), family history, and either
   CAC or CIMT imaging as optional inputs, with a documented uplift on
   the unified score.
3. **Lifetime risk view (PREVENT 30-year).** PREVENT's 30-year equations
   are already in the same supplementary material; surfacing them would
   enable the "what does my risk look like at 65?" conversation that
   younger patients find more motivating than 10-year numbers.
4. **EHR integration via FHIR.** Plumb in an ingestion path that accepts
   a FHIR Bundle and extracts the 10-12 inputs automatically.
5. **Auditability.** Store all calculations with a hash of the inputs,
   the engine version, and the reference papers used, so a clinician can
   later reproduce what the patient saw on a given date.
6. **BMI/weight-loss as a quantified counterfactual.** Currently we don't
   surface a BMI scenario because BMI isn't a predictor in any of the
   three sub-models for the ASCVD outcome (it only enters PREVENT's
   separate HF model). A defensible enhancement would be to model weight
   loss as also raising HDL and lowering SBP using published effect
   sizes (e.g. ~4 mmHg SBP per 5kg lost), then run the counterfactual
   through the same engine — but this requires its own validation and
   explicit user-facing caveats.

> **Note**: counterfactual "what if" scenarios for smoking, blood pressure,
> HDL, and statin initiation are already implemented in this prototype
> (see `counterfactual_scenarios()` in `heart_score.py` and the
> "What if this patient changed something?" panel in the UI).
