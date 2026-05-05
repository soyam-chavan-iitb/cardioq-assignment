"""
Framingham General Cardiovascular Disease Risk Score (10-year) — Lipids model.

Reference:
    D'Agostino RB Sr, Vasan RS, Pencina MJ, Wolf PA, Cobain M, Massaro JM,
    Kannel WB. General cardiovascular risk profile for use in primary care:
    the Framingham Heart Study. Circulation. 2008 Feb 12;117(6):743-53.
    doi:10.1161/CIRCULATIONAHA.107.699579. PMID: 18212285.

Coefficients verified against the official Framingham Heart Study risk
function page:
    https://www.framinghamheartstudy.org/fhs-risk-functions/cardiovascular-disease-10-year-risk/

The 10-year CVD risk is computed as:
    risk = 1 - S0(10) ** exp(LP - mean_LP)

where LP is the linear predictor (sum of beta * x for each predictor),
S0(10) is the baseline 10-year survival, and mean_LP is the population mean
of the linear predictor (also called the "centering constant").

Outcome predicted: any first CVD event (coronary death, MI, coronary
insufficiency, angina, ischemic stroke, hemorrhagic stroke, TIA, peripheral
artery disease, heart failure) within 10 years.

Population of validity: 30-74 years old, no prior CVD.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# Sex-specific regression coefficients (Lipids model, primary table).
# Source: Framingham Heart Study site, Regression Coefficients and Hazard
# Ratios — Primary Model.
_COEFFS = {
    "male": {
        "S0_10": 0.88936,
        "mean_LP": 23.9802,
        "log_age": 3.06117,
        "log_tc": 1.12370,
        "log_hdl": -0.93263,
        "log_sbp_untreated": 1.93303,
        "log_sbp_treated": 1.99881,
        "smoker": 0.65451,
        "diabetes": 0.57367,
    },
    "female": {
        "S0_10": 0.95012,
        "mean_LP": 26.1931,
        "log_age": 2.32888,
        "log_tc": 1.20904,
        "log_hdl": -0.70833,
        "log_sbp_untreated": 2.76157,
        "log_sbp_treated": 2.82263,
        "smoker": 0.52873,
        "diabetes": 0.69154,
    },
}


@dataclass
class FraminghamInput:
    """Inputs for the Framingham 2008 General CVD risk score (Lipids model).

    Units:
        age: years (30-74 supported by the model)
        total_cholesterol: mg/dL
        hdl_cholesterol: mg/dL
        sbp: systolic blood pressure in mmHg
        on_bp_treatment: True if currently on antihypertensive medication
        smoker: current smoker (Yes/No)
        diabetes: physician diagnosis of diabetes (Yes/No)
    """

    sex: Literal["male", "female"]
    age: float
    total_cholesterol: float
    hdl_cholesterol: float
    sbp: float
    on_bp_treatment: bool
    smoker: bool
    diabetes: bool


def calculate_framingham_risk(inputs: FraminghamInput) -> float:
    """Return 10-year general CVD risk as a fraction in [0, 1].

    Multiply by 100 to get percent.
    """
    if inputs.sex not in ("male", "female"):
        raise ValueError(f"sex must be 'male' or 'female', got {inputs.sex!r}")
    if inputs.age <= 0:
        raise ValueError("age must be positive")
    if inputs.total_cholesterol <= 0 or inputs.hdl_cholesterol <= 0:
        raise ValueError("cholesterol values must be positive")
    if inputs.sbp <= 0:
        raise ValueError("SBP must be positive")

    c = _COEFFS[inputs.sex]

    # Build the linear predictor exactly as published.
    log_sbp_term = (
        c["log_sbp_treated"] if inputs.on_bp_treatment else c["log_sbp_untreated"]
    ) * math.log(inputs.sbp)

    lp = (
        c["log_age"] * math.log(inputs.age)
        + c["log_tc"] * math.log(inputs.total_cholesterol)
        + c["log_hdl"] * math.log(inputs.hdl_cholesterol)
        + log_sbp_term
        + c["smoker"] * (1 if inputs.smoker else 0)
        + c["diabetes"] * (1 if inputs.diabetes else 0)
    )

    risk = 1.0 - c["S0_10"] ** math.exp(lp - c["mean_LP"])
    # Clamp for numerical safety; values should already lie in [0, 1].
    return max(0.0, min(1.0, risk))


def factor_contributions(inputs: FraminghamInput) -> dict[str, float]:
    """Return the contribution of each input to the linear predictor,
    expressed as (beta * x - beta * x_at_optimal_reference).

    Used by the explainability layer to identify top drivers of risk.
    Larger positive values = bigger upward push on risk.
    """
    c = _COEFFS[inputs.sex]

    # Optimal reference values (population-healthy person, same sex/age):
    #   total chol 170 mg/dL, HDL 60 mg/dL, SBP 110 mmHg untreated,
    #   non-smoker, no diabetes. Age is held at the patient's own age
    #   so it doesn't dominate as a "modifiable factor".
    contrib = {
        "Total cholesterol": c["log_tc"] * (
            math.log(inputs.total_cholesterol) - math.log(170)
        ),
        "HDL cholesterol": c["log_hdl"] * (
            math.log(inputs.hdl_cholesterol) - math.log(60)
        ),
        "Systolic blood pressure": (
            (c["log_sbp_treated"] if inputs.on_bp_treatment else c["log_sbp_untreated"])
            * math.log(inputs.sbp)
            - c["log_sbp_untreated"] * math.log(110)
        ),
        "Smoking": c["smoker"] * (1 if inputs.smoker else 0),
        "Diabetes": c["diabetes"] * (1 if inputs.diabetes else 0),
        "Age": c["log_age"] * (math.log(inputs.age) - math.log(50)),
    }
    return contrib
