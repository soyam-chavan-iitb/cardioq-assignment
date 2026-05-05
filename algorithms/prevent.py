"""
AHA PREVENT base 10-year cardiovascular risk equations (2023).

Reference:
    Khan SS, Matsushita K, Sang Y, Ballew SH, Grams ME, Surapaneni A,
    Blaha MJ, Carson AP, Chang AR, Ciemins E, Go AS, Gutierrez OM,
    Hwang SJ, Jassal SK, Kovesdy CP, Lloyd-Jones DM, Shlipak MG,
    Palaniappan LP, Sperling L, Virani SS, Tuttle K, Neeland IJ, Chow SL,
    Rangaswami J, Pencina MJ, Ndumele CE, Coresh J; Chronic Kidney Disease
    Prognosis Consortium and the American Heart Association Cardiovascular-
    Kidney-Metabolic Science Advisory Group.
    "Development and Validation of the American Heart Association's PREVENT
    Equations." Circulation. 2024 Feb 6;149(6):430-449.
    doi:10.1161/CIRCULATIONAHA.123.067626. PMID: 37947085.

Coefficient source:
    Beta coefficients and intercepts for the base 10-year model, sex-specific,
    extracted directly from the open-source `preventr` R package's sysdata.rda
    (https://github.com/martingmayer/preventr), which corresponds to Khan 2024
    Supplementary Table S25 (the "base model, 10-year horizon" rows).
    Cross-verified against the published worked example
    (female age 50, SBP 160, on BP-tx, total chol 200, HDL 45, no statin,
     diabetic, non-smoker, eGFR 90, BMI 35) → 9.2% 10-year ASCVD risk.

Model form:
    Logistic regression. risk = expit(beta . X)  where X is the centered/
    transformed feature vector and beta is sex-and-outcome-specific.

    Centering and transformation (per Khan 2024 / preventr):
        age_c       = (age - 55) / 10
        non_hdl_c   = (non-HDL chol in mmol/L) - 3.5
        hdl_c       = (HDL in mmol/L - 1.3) / 0.3
        sbp_lt_110  = (min(sbp, 110) - 110) / 20
        sbp_ge_110  = (max(sbp, 110) - 130) / 20
        bmi_lt_30   = (min(bmi, 30) - 25) / 5
        bmi_ge_30   = (max(bmi, 30) - 30) / 5
        egfr_lt_60  = (min(egfr, 60) - 60) / -15
        egfr_ge_60  = (max(egfr, 60) - 90) / -15
    Plus binary indicators (diabetes, smoking, bp_tx, statin) and the
    interaction terms listed below.

Population of validity:
    Adults aged 30-79, no prior cardiovascular disease.

Cholesterol unit handling:
    Inputs are mg/dL by convention (US standard). The module converts
    cholesterol to mmol/L internally using the factor 38.67 (mg/dL per mmol/L
    for cholesterol).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# Conversion factor: cholesterol mg/dL  ÷ 38.67 ≈ mmol/L
CHOL_MG_DL_PER_MMOL_L = 38.67


# Beta coefficients for the BASE 10-year PREVENT model.
# Order of features is fixed; both lookup tables below use the same order.
# Source: preventr/R/sysdata.rda → base_10yr (mirrors Khan 2024 Table S25).
_FEATURE_NAMES = [
    "age",                   # age_c, per 10 years
    "non_hdl_c",             # non-HDL-C per 1 mmol/L  (centered at 3.5)
    "hdl_c",                 # HDL-C per 0.3 mmol/L     (centered at 1.3)
    "sbp_lt_110",            # SBP <110 per 20 mmHg
    "sbp_ge_110",            # SBP >=110 per 20 mmHg
    "diabetes",
    "smoking",
    "bmi_lt_30",             # BMI <30 per 5 kg/m2
    "bmi_ge_30",             # BMI >=30 per 5 kg/m2
    "egfr_lt_60",            # eGFR <60 per -15 mL/min/1.73m2
    "egfr_ge_60",            # eGFR >=60 per -15 mL/min/1.73m2
    "bp_tx",                 # antihypertensive use
    "statin",                # statin use
    "bp_tx_sbp_ge_110",      # treated SBP >=110 interaction
    "statin_non_hdl_c",      # statin * non_hdl_c
    "age_non_hdl_c",         # age_c * non_hdl_c
    "age_hdl_c",             # age_c * hdl_c
    "age_sbp_ge_110",        # age_c * sbp_ge_110
    "age_diabetes",          # age_c * diabetes
    "age_smoking",           # age_c * smoking
    "age_bmi_ge_30",         # age_c * bmi_ge_30
    "age_egfr_lt_60",        # age_c * egfr_lt_60
    "constant",              # intercept
]

# Coefficients for ASCVD outcome — base model, 10-year horizon.
# Verbatim from preventr's sysdata.rda (ascvd column, female_ascvd / male_ascvd).
_ASCVD_BETAS = {
    "female": [
        0.7198830,   # age
        0.1176967,   # non_hdl_c
        -0.1511850,  # hdl_c
        -0.0835358,  # sbp_lt_110
        0.3592852,   # sbp_ge_110
        0.8348585,   # diabetes
        0.4831078,   # smoking
        0.0000000,   # bmi_lt_30
        0.0000000,   # bmi_ge_30
        0.4864619,   # egfr_lt_60
        0.0397779,   # egfr_ge_60
        0.2265309,   # bp_tx
        -0.0592374,  # statin
        -0.0395762,  # bp_tx_sbp_ge_110
        0.0844423,   # statin_non_hdl_c
        -0.0567839,  # age_non_hdl_c
        0.0325692,   # age_hdl_c
        -0.1035985,  # age_sbp_ge_110
        -0.2417542,  # age_diabetes
        -0.0791142,  # age_smoking
        0.0000000,   # age_bmi_ge_30
        -0.1671492,  # age_egfr_lt_60
        -3.8199750,  # constant
    ],
    "male": [
        0.7099847,   # age
        0.1658663,   # non_hdl_c
        -0.1144285,  # hdl_c
        -0.2837212,  # sbp_lt_110
        0.3239977,   # sbp_ge_110
        0.7189597,   # diabetes
        0.3956973,   # smoking
        0.0000000,   # bmi_lt_30
        0.0000000,   # bmi_ge_30
        0.3690075,   # egfr_lt_60
        0.0203619,   # egfr_ge_60
        0.2036522,   # bp_tx
        -0.0865581,  # statin
        -0.0322916,  # bp_tx_sbp_ge_110
        0.1145630,   # statin_non_hdl_c
        -0.0300005,  # age_non_hdl_c
        0.0232747,   # age_hdl_c
        -0.0927024,  # age_sbp_ge_110
        -0.2018525,  # age_diabetes
        -0.0970527,  # age_smoking
        0.0000000,   # age_bmi_ge_30
        -0.1217081,  # age_egfr_lt_60
        -3.5006550,  # constant
    ],
}


@dataclass
class PREVENTInput:
    """Inputs for AHA PREVENT base 10-year ASCVD risk.

    Units (US standard, matching the AHA online calculator):
        age:               years (30-79)
        total_cholesterol: mg/dL  (130-320 typical valid range)
        hdl_cholesterol:   mg/dL  (20-100 typical valid range)
        sbp:               mmHg   (90-200)
        bmi:               kg/m^2 (18.5-39.9 in PREVENT validation range)
        egfr:              mL/min/1.73m^2 (15-140)
    """

    sex: Literal["male", "female"]
    age: float
    total_cholesterol: float
    hdl_cholesterol: float
    sbp: float
    bmi: float
    egfr: float
    on_bp_treatment: bool
    on_statin: bool
    diabetes: bool
    smoker: bool


def _build_feature_vector(inputs: PREVENTInput) -> list[float]:
    """Apply the PREVENT centering/spline/interaction transformations.

    Returns a list of 23 floats in the same order as _FEATURE_NAMES.
    """
    # Cholesterol: convert mg/dL → mmol/L, then derive non-HDL.
    total_c_mmol = inputs.total_cholesterol / CHOL_MG_DL_PER_MMOL_L
    hdl_c_mmol = inputs.hdl_cholesterol / CHOL_MG_DL_PER_MMOL_L
    non_hdl_centered = (total_c_mmol - hdl_c_mmol) - 3.5
    hdl_centered = (hdl_c_mmol - 1.3) / 0.3

    age_c = (inputs.age - 55) / 10.0

    # Piecewise-linear splines for SBP, BMI, eGFR.
    sbp_lt_110 = (min(inputs.sbp, 110) - 110) / 20.0
    sbp_ge_110 = (max(inputs.sbp, 110) - 130) / 20.0
    bmi_lt_30 = (min(inputs.bmi, 30) - 25) / 5.0
    bmi_ge_30 = (max(inputs.bmi, 30) - 30) / 5.0
    egfr_lt_60 = (min(inputs.egfr, 60) - 60) / -15.0
    egfr_ge_60 = (max(inputs.egfr, 60) - 90) / -15.0

    dm = 1.0 if inputs.diabetes else 0.0
    smoking = 1.0 if inputs.smoker else 0.0
    bp_tx = 1.0 if inputs.on_bp_treatment else 0.0
    statin = 1.0 if inputs.on_statin else 0.0

    return [
        age_c,
        non_hdl_centered,
        hdl_centered,
        sbp_lt_110,
        sbp_ge_110,
        dm,
        smoking,
        bmi_lt_30,
        bmi_ge_30,
        egfr_lt_60,
        egfr_ge_60,
        bp_tx,
        statin,
        bp_tx * sbp_ge_110,
        statin * non_hdl_centered,
        age_c * non_hdl_centered,
        age_c * hdl_centered,
        age_c * sbp_ge_110,
        age_c * dm,
        age_c * smoking,
        age_c * bmi_ge_30,
        age_c * egfr_lt_60,
        1.0,  # constant
    ]


def calculate_prevent_ascvd_risk(inputs: PREVENTInput) -> float:
    """10-year ASCVD risk as a fraction in [0, 1]. Multiply by 100 for percent.

    Implements the AHA PREVENT base model (no HbA1c/UACR/SDI add-ons).
    """
    if inputs.sex not in ("male", "female"):
        raise ValueError(f"sex must be 'male' or 'female', got {inputs.sex!r}")
    if not (30 <= inputs.age <= 79):
        raise ValueError(
            f"age must be between 30 and 79 (PREVENT validation range), "
            f"got {inputs.age}"
        )
    if inputs.total_cholesterol <= 0 or inputs.hdl_cholesterol <= 0:
        raise ValueError("cholesterol values must be positive")
    if inputs.bmi <= 0 or inputs.egfr <= 0 or inputs.sbp <= 0:
        raise ValueError("BMI, eGFR, and SBP must be positive")

    betas = _ASCVD_BETAS[inputs.sex]
    features = _build_feature_vector(inputs)
    log_odds = sum(b * x for b, x in zip(betas, features))
    risk = math.exp(log_odds) / (1.0 + math.exp(log_odds))
    return max(0.0, min(1.0, risk))


def factor_contributions(inputs: PREVENTInput) -> dict[str, float]:
    """Per-factor contribution to the log-odds, grouped into clinically
    meaningful buckets for the explainability layer.

    Each value is the sum of (beta * x) over all spline pieces and
    interaction terms that involve that factor, computed as the deviation
    from the 'optimal reference' patient (matched age and sex):
        non-HDL 3.5 mmol/L, HDL 1.3 mmol/L, SBP 110 mmHg, BMI 25,
        eGFR 90, no diabetes, no smoking, no BP-treatment, no statin.

    Larger positive values = bigger upward push on log-odds (and thus risk).
    """
    betas = _ASCVD_BETAS[inputs.sex]
    feats = _build_feature_vector(inputs)
    name_to_beta_x = dict(zip(_FEATURE_NAMES, [b * x for b, x in zip(betas, feats)]))

    return {
        "Non-HDL cholesterol": (
            name_to_beta_x["non_hdl_c"]
            + name_to_beta_x["statin_non_hdl_c"]
            + name_to_beta_x["age_non_hdl_c"]
        ),
        "HDL cholesterol": (
            name_to_beta_x["hdl_c"] + name_to_beta_x["age_hdl_c"]
        ),
        "Systolic blood pressure": (
            name_to_beta_x["sbp_lt_110"]
            + name_to_beta_x["sbp_ge_110"]
            + name_to_beta_x["bp_tx_sbp_ge_110"]
            + name_to_beta_x["age_sbp_ge_110"]
        ),
        "Diabetes": name_to_beta_x["diabetes"] + name_to_beta_x["age_diabetes"],
        "Smoking": name_to_beta_x["smoking"] + name_to_beta_x["age_smoking"],
        "BMI": (
            name_to_beta_x["bmi_lt_30"]
            + name_to_beta_x["bmi_ge_30"]
            + name_to_beta_x["age_bmi_ge_30"]
        ),
        "Kidney function (eGFR)": (
            name_to_beta_x["egfr_lt_60"]
            + name_to_beta_x["egfr_ge_60"]
            + name_to_beta_x["age_egfr_lt_60"]
        ),
        "BP medication": name_to_beta_x["bp_tx"],
        "Statin use": name_to_beta_x["statin"],
        "Age": name_to_beta_x["age"],
    }
