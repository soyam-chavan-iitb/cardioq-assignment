"""
Unit tests for the Framingham 2008 General CVD risk score implementation.

Reference test cases use the published worked examples in
D'Agostino et al. 2008 (Circulation 117:743-753, Figure 2 / Appendix).
"""

import math
import pytest

from algorithms.framingham import (
    FraminghamInput,
    calculate_framingham_risk,
    factor_contributions,
)


def test_formula_matches_manual_trace():
    """Direct sanity check of the formula evaluation.

    For a 61-year-old woman, TC=180, HDL=47, SBP=124 (untreated),
    non-smoker, no diabetes, the linear predictor evaluates to:
        LP = 2.32888*ln(61) + 1.20904*ln(180) - 0.70833*ln(47)
             + 2.76157*ln(124)
           = 9.5736 + 6.2787 - 2.7271 + 13.3138  = 26.4390
        LP - mean_LP = 26.4390 - 26.1931 = 0.2459
        risk = 1 - 0.95012 ** exp(0.2459) = 0.0632  (6.32%)
    This protects against accidental coefficient regressions.
    """
    inputs = FraminghamInput(
        sex="female", age=61,
        total_cholesterol=180, hdl_cholesterol=47,
        sbp=124, on_bp_treatment=False,
        smoker=False, diabetes=False,
    )
    risk = calculate_framingham_risk(inputs)
    assert math.isclose(risk, 0.0632, abs_tol=0.001), (
        f"Expected ~6.32%, got {risk*100:.2f}%"
    )


def test_man_smoker_high_risk():
    """A 55-year-old male smoker with diabetes and unfavourable lipids
    should land in a clearly elevated risk band (>20%)."""
    inputs = FraminghamInput(
        sex="male",
        age=55,
        total_cholesterol=240,
        hdl_cholesterol=35,
        sbp=150,
        on_bp_treatment=True,
        smoker=True,
        diabetes=True,
    )
    risk = calculate_framingham_risk(inputs)
    assert risk > 0.30, f"Expected high risk (>30%), got {risk*100:.2f}%"


def test_healthy_young_woman_low_risk():
    """A 30-year-old healthy non-smoker, no diabetes, optimal vitals should
    have very low (<2%) 10-year CVD risk."""
    inputs = FraminghamInput(
        sex="female",
        age=30,
        total_cholesterol=170,
        hdl_cholesterol=60,
        sbp=110,
        on_bp_treatment=False,
        smoker=False,
        diabetes=False,
    )
    risk = calculate_framingham_risk(inputs)
    assert risk < 0.02, f"Expected very low risk (<2%), got {risk*100:.2f}%"


def test_treatment_increases_apparent_risk():
    """Within the model, a treated patient at the same SBP carries slightly
    higher risk than an untreated patient — this captures the 'why are they
    on treatment' selection effect baked into the coefficients."""
    base = dict(
        sex="male",
        age=55,
        total_cholesterol=200,
        hdl_cholesterol=50,
        sbp=140,
        smoker=False,
        diabetes=False,
    )
    risk_untreated = calculate_framingham_risk(
        FraminghamInput(on_bp_treatment=False, **base)
    )
    risk_treated = calculate_framingham_risk(
        FraminghamInput(on_bp_treatment=True, **base)
    )
    assert risk_treated > risk_untreated


def test_smoking_contribution_positive():
    """For a smoker, the smoking factor contribution should be positive
    (it pushes risk up); for a non-smoker, it should be exactly zero."""
    smoker = FraminghamInput(
        sex="male", age=50, total_cholesterol=200, hdl_cholesterol=50,
        sbp=130, on_bp_treatment=False, smoker=True, diabetes=False,
    )
    non_smoker = FraminghamInput(
        sex="male", age=50, total_cholesterol=200, hdl_cholesterol=50,
        sbp=130, on_bp_treatment=False, smoker=False, diabetes=False,
    )
    assert factor_contributions(smoker)["Smoking"] > 0
    assert factor_contributions(non_smoker)["Smoking"] == 0


def test_input_validation():
    with pytest.raises(ValueError):
        calculate_framingham_risk(
            FraminghamInput(
                sex="other",  # type: ignore[arg-type]
                age=50, total_cholesterol=200, hdl_cholesterol=50,
                sbp=130, on_bp_treatment=False, smoker=False, diabetes=False,
            )
        )
    with pytest.raises(ValueError):
        calculate_framingham_risk(
            FraminghamInput(
                sex="male", age=-1, total_cholesterol=200, hdl_cholesterol=50,
                sbp=130, on_bp_treatment=False, smoker=False, diabetes=False,
            )
        )
