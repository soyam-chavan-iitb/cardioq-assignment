"""
Unit tests for the AHA PREVENT base 10-year ASCVD risk implementation.

Primary reference test case is the worked example documented in the preventr
R package (mirrors Khan 2024 Supplementary Table S25):

    age=50, sex=female, sbp=160, on bp_tx, total_c=200 mg/dL, hdl=45 mg/dL,
    no statin, diabetic, non-smoker, eGFR=90, BMI=35
    → 10-year ASCVD risk = 9.2% (0.092)
"""

import math
import pytest

from algorithms.prevent import (
    PREVENTInput,
    calculate_prevent_ascvd_risk,
    factor_contributions,
)


def test_published_reference_case_female_50():
    """Khan 2024 / preventr documented example: expected 9.2% ASCVD."""
    inputs = PREVENTInput(
        sex="female", age=50,
        total_cholesterol=200, hdl_cholesterol=45,
        sbp=160, bmi=35, egfr=90,
        on_bp_treatment=True, on_statin=False,
        diabetes=True, smoker=False,
    )
    risk = calculate_prevent_ascvd_risk(inputs)
    # The R preventr package returns 0.092 (rounded to 3 dp);
    # we should agree to within 0.5 percentage points.
    assert math.isclose(risk, 0.092, abs_tol=0.005), (
        f"Expected ~9.2%, got {risk*100:.2f}%"
    )


def test_optimal_30_year_old_very_low_risk():
    """A 30-year-old with optimal vitals should have very low ASCVD risk."""
    inputs = PREVENTInput(
        sex="female", age=30,
        total_cholesterol=170, hdl_cholesterol=60,
        sbp=110, bmi=23, egfr=100,
        on_bp_treatment=False, on_statin=False,
        diabetes=False, smoker=False,
    )
    risk = calculate_prevent_ascvd_risk(inputs)
    assert risk < 0.005, f"Expected <0.5% risk, got {risk*100:.3f}%"


def test_high_risk_70_year_old_man():
    """An older man with multiple risk factors should land in clearly
    high-risk band (>15%)."""
    inputs = PREVENTInput(
        sex="male", age=70,
        total_cholesterol=240, hdl_cholesterol=35,
        sbp=160, bmi=32, egfr=55,
        on_bp_treatment=True, on_statin=False,
        diabetes=True, smoker=True,
    )
    risk = calculate_prevent_ascvd_risk(inputs)
    assert risk > 0.20, f"Expected high risk (>20%), got {risk*100:.2f}%"


def test_smoking_increases_risk():
    """Holding everything else equal, smoking must increase ASCVD risk."""
    base = dict(
        sex="male", age=55,
        total_cholesterol=200, hdl_cholesterol=50,
        sbp=130, bmi=27, egfr=85,
        on_bp_treatment=False, on_statin=False,
        diabetes=False,
    )
    risk_no_smoke = calculate_prevent_ascvd_risk(PREVENTInput(smoker=False, **base))
    risk_smoker = calculate_prevent_ascvd_risk(PREVENTInput(smoker=True, **base))
    assert risk_smoker > risk_no_smoke


def test_factor_contributions_smoker_positive():
    """Smoking factor contribution should be positive for a smoker, zero
    for a non-smoker."""
    base = dict(
        sex="male", age=55,
        total_cholesterol=200, hdl_cholesterol=50,
        sbp=130, bmi=27, egfr=85,
        on_bp_treatment=False, on_statin=False,
        diabetes=False,
    )
    smoker = factor_contributions(PREVENTInput(smoker=True, **base))
    non_smoker = factor_contributions(PREVENTInput(smoker=False, **base))
    assert smoker["Smoking"] > 0
    assert non_smoker["Smoking"] == 0


def test_age_out_of_range():
    with pytest.raises(ValueError):
        calculate_prevent_ascvd_risk(
            PREVENTInput(
                sex="male", age=25,  # below 30 lower bound
                total_cholesterol=200, hdl_cholesterol=50,
                sbp=130, bmi=27, egfr=85,
                on_bp_treatment=False, on_statin=False,
                diabetes=False, smoker=False,
            )
        )
