"""
CardioQ Heart Score — Streamlit application.

Runs at: streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st

from heart_score import PatientInput, calculate_heart_score, counterfactual_scenarios


# --- Visual helpers -----------------------------------------------------------
# Risk-band colour palette used by both the gauge and the comparison chart.
# Chosen to be reasonably colour-blind friendly (avoid pure red/green
# adjacency; use orange in the middle).
BAND_COLORS = {
    "Low":        "#1a9850",   # green
    "Borderline": "#a6d96a",   # light green
    "Moderate":   "#fdae61",   # orange
    "High":       "#f46d43",   # red-orange
    "Very High":  "#d73027",   # deep red
}


def _risk_gauge(score: float, band: str) -> go.Figure:
    """Semicircular gauge showing the patient's 0-100 score with the five
    risk bands colour-coded as background segments."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100", "font": {"size": 36}},
            domain={"x": [0, 1], "y": [0, 1]},
            title={
                "text": f"<b>{band}</b>",
                "font": {"size": 22, "color": BAND_COLORS.get(band, "#333")},
            },
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickvals": [0, 20, 40, 60, 80, 100],
                    "tickwidth": 1,
                    "tickcolor": "#666",
                },
                "bar": {"color": "rgba(0,0,0,0.0)"},  # invisible — we use threshold
                "bgcolor": "white",
                "borderwidth": 1,
                "bordercolor": "#cccccc",
                "steps": [
                    {"range": [0, 20],   "color": BAND_COLORS["Low"]},
                    {"range": [20, 40],  "color": BAND_COLORS["Borderline"]},
                    {"range": [40, 60],  "color": BAND_COLORS["Moderate"]},
                    {"range": [60, 80],  "color": BAND_COLORS["High"]},
                    {"range": [80, 100], "color": BAND_COLORS["Very High"]},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 5},
                    "thickness": 0.85,
                    "value": score,
                },
            },
        )
    )
    fig.update_layout(
        height=280,
        margin={"t": 60, "b": 10, "l": 30, "r": 30},
        font={"family": "system-ui, -apple-system, sans-serif"},
    )
    return fig


def _algorithm_comparison_chart(sub_risks_percent: dict[str, float | None]) -> go.Figure | None:
    """Horizontal bar chart comparing the 10-year risk % from each
    sub-model that ran. Reference lines mark clinical decision thresholds
    (5%, 10%, 20%) so divergence between algorithms is visible at a glance."""
    pretty = {
        "framingham": "Framingham 2008<br><span style='font-size:10px;color:#888'>general CVD</span>",
        "score2":     "SCORE2 / OP<br><span style='font-size:10px;color:#888'>fatal+non-fatal CVD</span>",
        "prevent":    "AHA PREVENT<br><span style='font-size:10px;color:#888'>10-yr ASCVD</span>",
    }
    names, values, hover_texts = [], [], []
    for key, pct in sub_risks_percent.items():
        if pct is None:
            continue
        names.append(pretty[key])
        values.append(pct)
        hover_texts.append(f"{pct:.2f}%")

    if not values:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker={"color": "#3b82f6", "line": {"color": "#1e40af", "width": 1}},
            text=[f"{v:.1f}%" for v in values],
            textposition="outside",
            hovertext=hover_texts,
            hoverinfo="text+y",
        )
    )

    # Clinical decision thresholds.
    threshold_meta = [
        (5,  "5% — borderline"),
        (10, "10% — high"),
        (20, "20% — very high"),
    ]
    x_max = max(max(values) * 1.25, 25)
    for x, label in threshold_meta:
        if x <= x_max:
            fig.add_vline(
                x=x, line={"color": "#999", "dash": "dash", "width": 1},
                annotation_text=label, annotation_position="top",
                annotation_font_size=10, annotation_font_color="#666",
            )

    fig.update_layout(
        height=240,
        margin={"t": 30, "b": 40, "l": 10, "r": 30},
        xaxis={"title": "10-year risk (%)", "range": [0, x_max], "gridcolor": "#eee"},
        yaxis={"title": "", "automargin": True},
        plot_bgcolor="white",
        showlegend=False,
        font={"family": "system-ui, -apple-system, sans-serif"},
    )
    return fig


# --- Page config --------------------------------------------------------------
st.set_page_config(
    page_title="CardioQ Heart Score",
    page_icon="❤️",
    layout="centered",
)

DISCLAIMER = (
    "**Disclaimer.** This tool is for educational evaluation only and is **not** "
    "a diagnostic or clinical decision-making tool. It does not replace "
    "clinical judgement. Inputs and outputs are not stored. Do not use real "
    "patient data without appropriate authorisation."
)


# --- Header -------------------------------------------------------------------
st.title("❤️ CardioQ Heart Score")
st.caption(
    "Educational prototype combining Framingham 2008, ESC SCORE2 (2021), "
    "and AHA PREVENT (2023) into a single 0–100 unified score."
)
st.info(DISCLAIMER, icon="ℹ️")


# --- Patient input form -------------------------------------------------------
with st.form("patient_form"):
    st.subheader("Patient inputs")

    c1, c2 = st.columns(2)
    with c1:
        sex = st.selectbox("Sex", ["female", "male"], index=0)
        age = st.number_input("Age (years)", min_value=20, max_value=95, value=55)
        total_chol = st.number_input(
            "Total cholesterol (mg/dL)", min_value=100, max_value=400, value=200
        )
        hdl = st.number_input(
            "HDL cholesterol (mg/dL)", min_value=15, max_value=120, value=50
        )
        sbp = st.number_input(
            "Systolic blood pressure (mmHg)", min_value=80, max_value=220, value=135
        )

    with c2:
        on_bp_tx = st.checkbox("On blood pressure medication", value=False)
        smoker = st.checkbox("Current smoker", value=False)
        diabetes = st.checkbox("Diabetes (Type 2)", value=False)
        on_statin = st.checkbox("On statin therapy", value=False)
        score2_region = st.selectbox(
            "SCORE2 risk region",
            options=["high", "low", "moderate", "very_high"],
            index=0,
            help=(
                "SCORE2 was calibrated for four European regions. India is not in "
                "the original calibration; 'high' is the closest available proxy."
            ),
        )

    st.markdown("**Optional inputs (improve PREVENT estimate)**")
    c3, c4 = st.columns(2)
    with c3:
        provide_bmi = st.checkbox("Provide BMI", value=True)
        bmi = st.number_input(
            "BMI (kg/m²)",
            min_value=15.0, max_value=50.0, value=27.0, step=0.1,
            disabled=not provide_bmi,
        )
    with c4:
        provide_egfr = st.checkbox("Provide eGFR", value=True)
        egfr = st.number_input(
            "eGFR (mL/min/1.73m²)",
            min_value=10, max_value=150, value=85,
            disabled=not provide_egfr,
        )

    submitted = st.form_submit_button("Calculate Heart Score", type="primary")


# --- Run engine on submit -----------------------------------------------------
if submitted:
    patient = PatientInput(
        sex=sex,                                  # type: ignore[arg-type]
        age=float(age),
        total_cholesterol=float(total_chol),
        hdl_cholesterol=float(hdl),
        sbp=float(sbp),
        on_bp_treatment=on_bp_tx,
        smoker=smoker,
        diabetes=diabetes,
        on_statin=on_statin,
        bmi=float(bmi) if provide_bmi else None,
        egfr=float(egfr) if provide_egfr else None,
        score2_risk_region=score2_region,         # type: ignore[arg-type]
    )

    result = calculate_heart_score(patient)

    # --- Headline -------------------------------------------------------------
    st.divider()
    st.subheader("Result")
    st.plotly_chart(_risk_gauge(result.heart_score, result.risk_band),
                    use_container_width=True, config={"displayModeBar": False})

    # Plain-language summary
    st.markdown("### What this means")
    st.write(result.plain_language_summary())

    # --- Per-algorithm breakdown ---------------------------------------------
    st.markdown("### Per-algorithm 10-year risk")
    chart = _algorithm_comparison_chart(result.sub_risks_percent)
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption(
            "Note: the three algorithms predict slightly different outcomes "
            "(general CVD vs fatal+non-fatal CVD vs ASCVD-only), so visible "
            "divergence is expected — see METHODOLOGY.md §2."
        )

    breakdown_rows = []
    pretty_names = {
        "framingham": "Framingham 2008 (general CVD)",
        "score2": "SCORE2 / SCORE2-OP (fatal+non-fatal CVD)",
        "prevent": "AHA PREVENT (10-yr ASCVD)",
    }
    for key, pct in result.sub_risks_percent.items():
        if pct is None:
            breakdown_rows.append(
                {"Algorithm": pretty_names[key], "10-yr risk": "skipped",
                 "Sub-score (0–100)": "—",
                 "Weight in fusion": "0%"}
            )
        else:
            w = result.weights_used.get(key, 0)
            breakdown_rows.append({
                "Algorithm": pretty_names[key],
                "10-yr risk": f"{pct:.2f}%",
                "Sub-score (0–100)": f"{result.sub_scores.get(key, 0):.1f}",
                "Weight in fusion": f"{w*100:.0f}%",
            })
    st.table(breakdown_rows)

    # --- Top contributing factors --------------------------------------------
    if result.top_factors:
        st.markdown("### Top contributing factors")
        st.write(
            "Factors pushing this patient's risk *upward* the most, ranked by "
            "their normalised contribution across the sub-models that ran:"
        )
        for i, (name, contribution) in enumerate(result.top_factors, start=1):
            st.markdown(f"**{i}. {name}**  &nbsp; *(relative weight: {contribution:.2f})*")

    # --- Counterfactual "what if" view --------------------------------------
    scenarios = counterfactual_scenarios(patient, result)
    if scenarios:
        st.markdown("### What if this patient changed something?")
        st.caption(
            "Each scenario re-runs all three risk algorithms with one factor "
            "modified. Ranked by largest score reduction. Does not capture "
            "compounding effects of multiple changes."
        )
        for cf in scenarios:
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{cf.label}**")
                st.caption(cf.rationale)
            with cols[1]:
                st.metric(
                    "New score",
                    f"{cf.new_score:.1f}",
                    delta=f"{cf.score_delta:+.1f}",
                    delta_color="inverse",  # negative delta is good (green)
                )
            with cols[2]:
                st.markdown(f"**New band**\n\n{cf.new_band}")
            with cols[3]:
                # Visual progress bar of score reduction
                pct_reduction = abs(cf.score_delta) / max(result.heart_score, 1)
                st.markdown(f"**Reduction**\n\n{pct_reduction*100:.0f}%")
            st.divider()

    # --- Notes ---------------------------------------------------------------
    if result.notes:
        with st.expander("Notes about this calculation"):
            for note in result.notes:
                st.markdown(f"- {note}")

    # --- JSON export ---------------------------------------------------------
    st.divider()
    st.markdown("### Export")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": "CardioQ Heart Score prototype v0.1",
        "inputs": {
            "sex": sex, "age": age,
            "total_cholesterol_mg_dl": total_chol,
            "hdl_cholesterol_mg_dl": hdl,
            "sbp_mmhg": sbp,
            "on_bp_treatment": on_bp_tx,
            "smoker": smoker, "diabetes": diabetes, "on_statin": on_statin,
            "bmi": bmi if provide_bmi else None,
            "egfr": egfr if provide_egfr else None,
            "score2_risk_region": score2_region,
        },
        "outputs": {
            "heart_score": result.heart_score,
            "risk_band": result.risk_band,
            "ten_year_risks_percent": result.sub_risks_percent,
            "sub_scores": result.sub_scores,
            "weights_used": result.weights_used,
            "top_factors": [{"factor": n, "relative_weight": round(c, 3)}
                            for n, c in result.top_factors],
            "counterfactuals": [
                {
                    "scenario": cf.label,
                    "rationale": cf.rationale,
                    "new_heart_score": cf.new_score,
                    "score_delta": round(cf.score_delta, 1),
                    "new_risk_band": cf.new_band,
                }
                for cf in scenarios
            ],
            "notes": result.notes,
        },
        "disclaimer": (
            "Educational use only. Not a clinical or diagnostic tool. "
            "Discuss any health concerns with a qualified clinician."
        ),
        "references": {
            "framingham": ("D'Agostino RB Sr et al. Circulation. 2008 Feb 12;"
                           "117(6):743-53. PMID:18212285"),
            "score2": ("SCORE2 working group. Eur Heart J. 2021 Jul 1;"
                       "42(25):2439-2454. PMID:34120177"),
            "prevent": ("Khan SS et al. Circulation. 2024 Feb 6;149(6):430-449. "
                        "PMID:37947085"),
        },
    }
    json_payload = json.dumps(report, indent=2)
    st.download_button(
        "Download report (JSON)",
        data=json_payload,
        file_name=f"cardioq_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
    )

    with st.expander("Preview JSON report"):
        st.code(json_payload, language="json")


# --- Footer -------------------------------------------------------------------
st.divider()
st.caption(
    "Built as an educational prototype. Algorithms implemented from published "
    "papers and verified against their own reference cases. See "
    "METHODOLOGY.md and PROMPTS.md in the repo for full transparency."
)
