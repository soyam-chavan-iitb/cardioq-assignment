"""
Unit tests for SCORE2 / SCORE2-OP.

Primary reference test cases come directly from the SCORE2 paper abstract:

    For a 50-year-old SMOKER with SBP 140 mmHg, total chol 5.5 mmol/L,
    HDL 1.3 mmol/L:
        Men:    low-risk region: 5.9%   very high-risk region: 14.0%
        Women:  low-risk region: 4.2%   very high-risk region: 13.7%
"""

import math
import pytest

from algorithms.score2 import SCORE2Input, calculate_score2_risk, factor_contributions

# Convert the paper's mmol/L test values to mg/dL for our API.
TC_5_5 = 5.5 * 38.67   # ≈ 212.7 mg/dL
HDL_1_3 = 1.3 * 38.67  # ≈ 50.3  mg/dL


def test_paper_reference_male_50_low_region():
    """SCORE2 paper abstract: 50-yr male smoker → 5.9% in low-risk region."""
    inputs = SCORE2Input(
        sex="male", age=50,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=True, diabetes=False,
        risk_region="low",
    )
    risk = calculate_score2_risk(inputs)
    assert math.isclose(risk, 0.059, abs_tol=0.005), (
        f"Expected ~5.9%, got {risk*100:.2f}%"
    )


def test_paper_reference_male_50_very_high_region():
    """SCORE2 paper abstract: 50-yr male smoker → 14.0% in very-high region."""
    inputs = SCORE2Input(
        sex="male", age=50,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=True, diabetes=False,
        risk_region="very_high",
    )
    risk = calculate_score2_risk(inputs)
    assert math.isclose(risk, 0.140, abs_tol=0.010), (
        f"Expected ~14.0%, got {risk*100:.2f}%"
    )


def test_paper_reference_female_50_low_region():
    """SCORE2 paper abstract: 50-yr female smoker → 4.2% in low-risk region."""
    inputs = SCORE2Input(
        sex="female", age=50,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=True, diabetes=False,
        risk_region="low",
    )
    risk = calculate_score2_risk(inputs)
    assert math.isclose(risk, 0.042, abs_tol=0.005), (
        f"Expected ~4.2%, got {risk*100:.2f}%"
    )


def test_paper_reference_female_50_very_high_region():
    """SCORE2 paper abstract: 50-yr female smoker → 13.7% in very-high region."""
    inputs = SCORE2Input(
        sex="female", age=50,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=True, diabetes=False,
        risk_region="very_high",
    )
    risk = calculate_score2_risk(inputs)
    assert math.isclose(risk, 0.137, abs_tol=0.010), (
        f"Expected ~13.7%, got {risk*100:.2f}%"
    )


def test_score2_op_path_used_for_age_70_plus():
    """For age >= 70, SCORE2-OP should be used. Sanity check: a 75-year-old
    woman in the high-risk region with mild risk factors should give a
    plausible figure (5-25% range)."""
    inputs = SCORE2Input(
        sex="female", age=75,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=False, diabetes=False,
        risk_region="high",
    )
    risk = calculate_score2_risk(inputs)
    assert 0.05 <= risk <= 0.30, f"OP risk plausibility check failed: {risk*100:.2f}%"


def test_high_region_ranks_above_low():
    """Same patient, low region < high region risk. Sanity check on
    recalibration direction."""
    base = dict(
        sex="male", age=55,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, smoker=False, diabetes=False,
    )
    risk_low = calculate_score2_risk(SCORE2Input(risk_region="low", **base))
    risk_high = calculate_score2_risk(SCORE2Input(risk_region="high", **base))
    assert risk_high > risk_low


def test_smoking_increases_score2_risk():
    base = dict(
        sex="male", age=55,
        total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
        sbp=140, diabetes=False, risk_region="high",
    )
    no_smoke = calculate_score2_risk(SCORE2Input(smoker=False, **base))
    smoke = calculate_score2_risk(SCORE2Input(smoker=True, **base))
    assert smoke > no_smoke


def test_age_out_of_range():
    with pytest.raises(ValueError):
        calculate_score2_risk(SCORE2Input(
            sex="male", age=35,  # below 40 lower bound for SCORE2
            total_cholesterol=TC_5_5, hdl_cholesterol=HDL_1_3,
            sbp=140, smoker=False, diabetes=False,
            risk_region="high",
        ))
