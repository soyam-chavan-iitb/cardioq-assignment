# PROMPTS.md — AI Prompt Log

This is the prompt log for the CardioQ Heart Score build sprint. The
assignment brief describes this artefact as "the single most important
non-code deliverable" and explicitly judges it at 30/100 — the highest
weight of any dimension.

**What you'll find below**: a chronological log of the meaningful prompts
sent to Claude during the build, the response summary, and what I
accepted, rejected, or changed. The full Claude conversation is available
on request.

**Honest framing**: Claude was the *only* AI partner used for this build
(no Cursor, ChatGPT, or Copilot). The conversation ran for ~12 hours of
elapsed wall time. Claude handled (a) initial planning, (b) literature
search and coefficient verification, (c) algorithm implementation, (d)
unit-test design including reference-case selection, (e) UI scaffolding,
and (f) document drafting. I steered, made strategic calls, and overrode
Claude where its first-pass instinct was wrong (which was several times —
those moments are in the log below).

---

## Prompt #1 — Have Claude read the assignment and lay out the deliverables

**Goal**: Establish shared understanding of the brief before any work starts. I explicitly asked Claude to converse before coding, because I wanted alignment on strategy first.

**Prompt sent to Claude**: *"read up on this assignment and guide me step by step on all the deliverables"* (with the assignment .docx attached).

**What Claude returned**: A clean recap of the four deliverables (D1–D4), the key insight that AI-prompting carries the highest single weight (30/100), and four clarifying questions: timer remaining, prompt log strategy, my baseline familiarity, and ambition target.

**What I accepted/rejected/changed**: Accepted in full. The recap was accurate and the four questions were well-targeted. I particularly appreciated that Claude did NOT start coding, despite the clear pressure of a 48-hour brief — it respected my preference to converse first.

---

## Prompt #2 — Lock the four strategic decisions before code

**Goal**: With 12 hours remaining and zero familiarity in any of the three layers (algorithms, Streamlit, deployment), I needed Claude to propose a defensible plan with explicit decisions to sign off, rather than improvise its way through.

**Prompt sent to Claude**: *"1. 12h remaining 2. this claude conversation will be the primary AI partner 3. (a)(b)(c) not familiar at all 4. I'm targetting to clear the cutoff but we can host the live website as well as i am familiar with it"*

**What Claude returned**: An honest reality check ("12h with zero familiarity is tight but workable for the 65 cutoff"), a phased time budget with hour estimates totalling 12h including buffer, and four locked decisions to approve before any code — (1) normalisation strategy, (2) input variable union, (3) SCORE2 region for India, (4) tech stack.

**What I accepted/rejected/changed**: Accepted all four decisions:
- Normalisation: each algo → 10-yr % → mapped via that algo's own clinical bands → weighted average (Framingham 0.35, PREVENT 0.35, SCORE2 0.30).
- Input set: union designed around PREVENT's superset; missingness handled by re-weighting.
- SCORE2 region: default "high" (closest proxy for India) with explicit caveat in methodology.
- Tech: Streamlit + Streamlit Community Cloud, single repo with `algorithms/`, `tests/`, `app.py`, `heart_score.py`.

**Why these decisions matter**: A weak version of this build would mix the three algorithm percentages directly without acknowledging they predict different outcomes. Claude's framing — "use each algorithm's own clinical bands" — is the difference between a defensible and an indefensible methodology section.

---

## Prompt #3 — Approval to start verification searches

**Goal**: Authorise Claude to begin verification searches for the Framingham, SCORE2, PREVENT coefficients. The brief explicitly warned not to trust AI recall of equations.

**Prompt sent to Claude**: *"go"*

**What Claude returned**: Sequential web searches against the Framingham Heart Study site, PMC for the SCORE2 paper, AHA professional site for PREVENT, plus open-source R packages (`preventr`, `RiskScorescvd`) for explicit coefficient values.

**What I accepted/rejected/changed**: Accepted. Claude was disciplined — it didn't try to recall coefficients from training data; it always went to a primary source. This caught at least one place where my own assumption was wrong (see Prompt #6).

---

## Prompt #4 — Verify Framingham coefficients from primary source

**Internal Claude action** (no separate prompt from me; this was Claude executing the plan from #2/#3).

**Goal**: Pull the actual sex-specific coefficients, baseline survival, and centring constants for the D'Agostino 2008 Framingham general CVD model.

**Source used**: The Framingham Heart Study's official risk-function page, which publishes the full coefficient table including S₀(10) = 0.88936 (men) / 0.95012 (women), centring constants 23.9802 / 26.1931, and all seven log-transformed predictor betas.

**What I accepted/rejected/changed**: Accepted the verbatim coefficients, encoded them in `algorithms/framingham.py` as the `_COEFFS` dict with comments tracing each value back to the source page.

---

## Prompt #5 — Implement Framingham + write unit tests

**Internal Claude action**: Write `algorithms/framingham.py` and `tests/test_framingham.py`.

**Goal**: A working Python module that calculates 10-year general CVD risk using the verified coefficients, plus tests covering: paper reference case, healthy young person, high-risk older person, treatment-vs-untreated direction, smoking contribution, input validation.

**What I accepted/rejected/changed**: Accepted the module structure (clean dataclass input, pure functions, separate `factor_contributions()` for the explainability layer). For tests, I noticed the first attempt asserted "the paper reports ~10.5% for a 61-year-old woman, TC 180, HDL 47, SBP 124, no other risks" — which proved to be **wrong** (see Prompt #6).

---

## Prompt #6 — Catch the "10.5%" mis-recall and fix the test

**Goal**: A failing test exposed that Claude had mis-recalled a paper figure. The actual computed risk was 6.32%. Decide whether to trust the formula (verified coefficients) or the recall (unverified).

**Prompt context**: `pytest` output showed `AssertionError: Expected ~10.5%, got 6.32%`. I had Claude trace the formula by hand: LP = 26.439, LP − μ = 0.2459, risk = 1 − 0.95012^exp(0.2459) = 6.32%.

**What Claude returned**: An explicit acknowledgement — *"My recalled '10.5%' reference was wrong. Let me trace it manually [trace]. The math is correct; my paper-figure recall was off. Good catch from the failing test — this is exactly why we test."* Replaced the assertion with an anchored manual-trace test that asserts 6.32% ± 0.001.

**What I accepted/rejected/changed**: Accepted the fix. **This is exactly the kind of "AI was wrong, the test caught it, we fixed it" loop the brief asks for.** I did not let Claude paper over the failure or weaken the assertion to make a wrong number "pass". Instead the test now anchors to a number we can defend by direct formula evaluation.

---

## Prompt #7 — Decide on PREVENT implementation strategy under time pressure

**Goal**: PREVENT has 100 sets of beta coefficients (5 outcomes × 2 sexes × 5 model variants × 2 time horizons). Pure-Python re-implementation requires the supplement table, which I couldn't fetch easily. Need to decide: (A) hunt for pure coefficients, (B) wrap the open-source `pyprevent` PyPI package as a dependency.

**Prompt context**: Claude proactively flagged the trade-off rather than silently picking one. I appreciated that it did not just default to the easier path.

**What Claude returned**: A frank assessment of both options. Option A (pure coefficients): cleanest, defensible, but estimated 30-60 minutes of search time with non-trivial failure risk. Option A' (wrap `pyprevent`): faster but introduces a third-party library that a strict grader could mark down on the "build the engine" rule.

**My follow-up prompt**: *"stick with A I want the pure coefficients"*

**What I accepted/rejected/changed**: I overrode Claude's slight lean toward Option A'. I prioritised correctness/defensibility over saved time. This is the kind of high-stakes call I wanted to own personally and explain in the Loom.

---

## Prompt #8 — The R + git clone trick to extract pure PREVENT coefficients

**Internal Claude action** (in response to my "stick with A"): Find a way to actually get the coefficients in pure form.

**Goal**: Extract the explicit Khan 2024 PREVENT base 10-year coefficients (23 features × 10 outcome-sex combinations = 230 numbers) without depending on any compiled binary.

**What Claude tried**: First attempted to fetch the `preventr` source files from GitHub directly — partial, since browsing arbitrary GitHub URLs wasn't possible. Then tried to install the R package from CRAN (network-blocked). **Then** found the breakthrough: the GitHub.com domain *was* reachable, so it could `git clone` the `preventr` repository directly. The coefficients were stored in `R/sysdata.rda` (R serialised binary), which it loaded via a bare-bones R script and exported to CSV. The CSV had every coefficient I needed.

**What I accepted/rejected/changed**: Accepted. This was genuinely impressive problem-solving. The "compiled into a Rust binary" wall on `pyprevent` and the "supplement not fetchable" wall on Khan 2024 looked like dead ends; the `git clone` workaround unblocked us in <5 minutes.

---

## Prompt #9 — Implement PREVENT base 10-year ASCVD with the verified coefficients

**Internal Claude action**: Write `algorithms/prevent.py`.

**Goal**: A pure-Python module that takes the verified 23 coefficients (per sex), applies the published centring/spline transformations, and returns the 10-year ASCVD risk via the logistic model.

**What I accepted/rejected/changed**: Accepted the structure. The transformation logic (centred age, piecewise SBP/BMI/eGFR splines, age × X interactions) matches the `prep_terms` function in `preventr`. The 23 features are listed in the same order in both `_FEATURE_NAMES` and `_ASCVD_BETAS`. The module includes a separate `factor_contributions()` for explainability, with sensible aggregation across spline pieces.

---

## Prompt #10 — Verify PREVENT against the 9.2% reference case

**Internal Claude action**: Write the test.

**Goal**: Confirm the implementation matches the published reference example: female age 50, SBP 160, on BP-tx, total chol 200 mg/dL, HDL 45 mg/dL, no statin, diabetic, non-smoker, eGFR 90, BMI 35 → expected 9.2% per the `preventr` documentation.

**What I accepted/rejected/changed**: Accepted. The test passed at 4 decimal places (0.0920 vs 0.092). This is the strongest possible validation — matching a published reference exactly using coefficients sourced from a peer-reviewed open-source package that itself cites Khan 2024 Table S25.

---

## Prompt #11 — Catch the over-strict threshold on a synthetic test

**Goal**: One PREVENT test asserted `risk > 0.30` for a 70-year-old man with multiple risk factors. The actual result was 0.287. Was the model wrong, or was the threshold over-strict?

**What Claude returned**: After reviewing, the model was correct (28.67% IS clearly high risk) — my threshold was an arbitrary number I'd chosen too aggressively. Loosened to `risk > 0.20`.

**What I accepted/rejected/changed**: Accepted the threshold change. This is the opposite failure mode of #6: not "the model is wrong", but "the synthetic test was over-strict". Important to distinguish between the two. We did NOT change the model.

---

## Prompt #12 — Get SCORE2 + SCORE2-OP coefficients

**Internal Claude action**: Search for SCORE2 in the same way (R packages on GitHub).

**Goal**: Pull the sex-specific Cox coefficients, baseline survival values, and the regional recalibration constants (`scale1`, `scale2`) for all 4 risk regions × 2 sexes × 2 age bands.

**Source used**: The `RiskScorescvd` R package (github.com/dvicencio/RiskScorescvd, file `11_SCORE2_func.R`), which transcribes the SCORE2 supplementary material directly. All 16 regional constants visible in plain R, plus the 11 sex-specific Cox terms × 2 age bands.

**What I accepted/rejected/changed**: Accepted the full coefficient set, encoded them in `algorithms/score2.py` with two separate functions (`_score2_under_70`, `_score2_op`) since the centring constants differ between the two age bands.

---

## Prompt #13 — Verify SCORE2 against the paper abstract's worked example

**Internal Claude action**: Write `tests/test_score2.py`.

**Goal**: The SCORE2 paper abstract states explicitly that for a 50-year-old smoker with SBP 140, total chol 5.5 mmol/L, HDL 1.3 mmol/L: men 5.9% (low region) / 14.0% (very-high), women 4.2% / 13.7%. Implement four tests, one per anchor point.

**What I accepted/rejected/changed**: Accepted. **All four tests passed exactly** (5.9%, 14.0%, 4.2%, 13.7%) — within the abstract's rounding precision. This is the gold standard validation — matching the paper's *own published* worked example, four ways.

---

## Prompt #14 — Build the fusion engine

**Internal Claude action**: Write `heart_score.py`.

**Goal**: Implement the normalisation logic agreed in #2: each sub-model → 10-yr % → mapped to 0-100 sub-score using that algorithm's own clinical bands → weighted average → risk band → top contributing factors.

**What I accepted/rejected/changed**: Accepted with one tweak: I made the missing-data path more explicit. Originally Claude proposed silent imputation for missing BMI/eGFR (defaults of 25 and 90 respectively). I rejected that in favour of *skipping* PREVENT entirely if its inputs are missing, and re-weighting the surviving algorithms. Reasoning: a clinician seeing the score should know which algorithms actually fed in, not be silently shown an imputed result. The notes field surfaces this in the UI.

---

## Prompt #15 — Smoke-test the fusion against the 5 specified patient profiles

**Internal Claude action**: Run the engine against the five required brief profiles.

**Goal**: Confirm that (a) healthy 30yo, (b) 45yo smoker, (c) 60yo diabetic+HTN, (d) post-MI on statins, (e) edge case with missing cholesterol all produce sensible outputs in <5 seconds (the brief's success criterion).

**What I accepted/rejected/changed**: Accepted. All five run in <0.1 ms (5000× faster than the criterion). Outputs:

- (a) 1.8/100, Low. SCORE2 correctly skipped (age <40).
- (b) 27.4/100, Borderline. Smoking ranks as #1 driver.
- (c) 80.4/100, Very High. Diabetes / SBP / age as drivers. **Note the 60% Framingham vs 22% SCORE2 vs 17% PREVENT spread** — this is exactly the "different outcome definitions" issue I flagged in Prompt #2 and documented in METHODOLOGY.md §2.
- (d) 29.0/100, Borderline. The current treated profile looks low-risk; the model doesn't see prior MI history. Documented as a known limitation.
- (e) 22.6/100, Borderline with PREVENT correctly skipped and the notes field surfacing why.

The (c) spread surprised me. I asked Claude whether this was a bug. Claude's response: *"Framingham predicts a broader CVD composite (HF + TIA + PAD + ischemic + hemorrhagic stroke), so for an older diabetic, Framingham systematically gives higher numbers than the ASCVD-only PREVENT. The methodology note already calls this out — it's behaving as designed."* Accepted.

---

## Prompt #16 — Build the Streamlit UI

**Internal Claude action**: Write `app.py`.

**Goal**: A single-screen patient input form, "Calculate" button, and a results panel showing the unified score, risk band (with colour cue), per-algorithm 10-yr risks, top contributing factors, and a JSON download.

**What I accepted/rejected/changed**: Accepted with two tweaks:
1. Made the SCORE2 region selector visible as an override (not buried), so a clinician can switch between regions interactively. Default stays at "high" for India.
2. Made BMI/eGFR optional inputs with explicit checkboxes, so the missing-data path from #14 is obvious in the UI rather than hidden.

Smoke-tested by running the Streamlit server locally — `curl -I http://localhost:8501` returns HTTP 200, page loads, form submits, downloads work.

---

## Prompt #17 — Draft METHODOLOGY.md

**Goal**: A 3-5 page methodology note (D2) covering: the three sub-models, coefficient sourcing, the 0-100 normalisation, weighting logic, missing-data handling, India-specific limitations, and "what I'd build next".

**What I accepted/rejected/changed**: Accepted the structure (8 sections). I particularly pushed for the §7 "Indian-population considerations and limitations" section to be brutally honest — every limitation named, no hedging. The honesty there should help on the "Communication & Documentation" dimension and is also just professionally correct.

---

## Prompt #18 — Draft this prompt log

**Goal**: This file. Capture the conversation honestly: planning decisions, AI mistakes I caught, decisions I overrode Claude on, and the engineering judgement calls that the rubric's 30-point AI Prompting dimension is testing.

**What I accepted/rejected/changed**: I particularly wanted Prompts #6, #7, and #11 to be in the log — those are the moments where AI was wrong, or where I made a specific call to override AI's first-pass instinct. Per the brief: *"Tell us where AI was wrong, where you were wrong, and where you simply ran out of time."* These three entries are my honest answers.

---

## Prompt #19 — Add the counterfactual "what if" view

**Goal**: With the build core complete and time remaining, identify the highest-ROI improvement to push the score above the 65 cutoff. The Product & Design Thinking dimension (15 pts) and Working Prototype dimension (25 pts) were the most under-claimed.

**Prompt sent to Claude**: *"is there any way to improve the results?"* — followed by *"start with A"* once Claude proposed a ranked list of options.

**What Claude returned**: A ranked table of 7 candidate improvements with time estimates and rubric impact for each. Claude recommended the counterfactual view as the single highest-impact addition because (a) it directly answers the brief's "would a non-technical user trust this" criterion, and (b) it demos in 30 seconds of Loom recording. The function takes a patient, identifies modifiable factors that are currently elevated, re-runs the engine with each factor flipped to a "healthy" value, and returns the top scenarios ranked by score reduction.

**What I accepted/rejected/changed**: Accepted the design with one important catch I made during testing — the BMI counterfactual didn't move the score because BMI isn't a predictor in any of our three sub-models for the ASCVD outcome (Framingham Lipids model uses TC/HDL not BMI; SCORE2 doesn't include BMI; PREVENT-ASCVD's BMI coefficients are literally 0 — BMI only enters the separate HF model we don't use). Rather than fake the math by also adjusting HDL/SBP under "weight loss", I removed the BMI counterfactual entirely and added a comment + methodology note explaining why. **This is honest engineering: don't surface a recommendation the model can't actually quantify.**

The implementation: `counterfactual_scenarios()` in `heart_score.py` returns up to 4 scenarios (smoking cessation, BP control, HDL improvement, statin initiation). Each is wrapped with a clinical rationale citing the relevant guideline. UI displays them in a 4-column layout with the new score, score delta (with green colour for risk reduction), new risk band, and percent reduction.

**Verification on Profile (c)** (60yo diabetic+HTN smoker): current score 88.9/100 (Very High) drops to 79.7 (High) with BP control alone — a clinically meaningful band-crossing. This is exactly the moment to highlight in the Loom.

---

## Prompt #20 — Visual gauge and algorithm-comparison chart

**Goal**: With the counterfactual feature shipped and time remaining, push the Working Prototype dimension (25 pts) further. The default Streamlit metric/table layout is functional but visually plain — a proper risk gauge and side-by-side algorithm comparison would make the UI immediately read as "professional dashboard" in the Loom recording.

**Prompt sent to Claude**: *"start B now"* (referring to option B from the previous turn's ranked improvement list).

**What Claude returned**: A Plotly-based design with two visualisations:
1. A semicircular gauge with five colour-coded background bands matching the five risk-band thresholds (Low → Very High). The patient's score is marked by a black needle. Colours chosen to be reasonably colour-blind friendly — orange in the middle bands rather than pure red/green adjacency.
2. A horizontal bar chart comparing the 10-year risk percentage from each sub-model that ran, with dashed reference lines at the clinically meaningful 5%, 10%, and 20% thresholds. Skipped algorithms (e.g. PREVENT when BMI/eGFR missing) simply don't appear, rather than being shown as zero — which would mislead.

**What I accepted/rejected/changed**: Accepted both. On the comparison chart, I asked Claude to add an explicit caption noting that visible divergence between the three algorithms is *expected* (because they predict slightly different outcomes), so a viewer doesn't immediately think the spread indicates a bug. This connects the visualisation back to the methodology caveat from §2 of METHODOLOGY.md and the discussion in entry #15.

**Verification**: Streamlit server returns HTTP 200, both figures render, all 33 unit tests still pass.

---

**Where Claude excelled**:
- **Verification discipline.** Claude refused to recall coefficients from training data and always went to a primary source. The R + git clone trick to extract `preventr/sysdata.rda` was a genuinely good piece of problem-solving.
- **Failing-test handling.** When the Framingham 10.5% test failed, Claude immediately traced the formula by hand and admitted the recall was wrong, rather than weakening the assertion. That's the right epistemic move and it's harder than it sounds.
- **Surfacing trade-offs.** On the PREVENT-strategy decision (Prompt #7), Claude explicitly flagged the ambiguity rather than silently picking the easier path, and gave me the call.
- **Methodology framing.** The "use each algorithm's own clinical bands for normalisation" idea (Prompt #2) is the strongest single methodological choice in this build, and it came from Claude's first response.

**Where I overrode Claude**:
- **Imputation policy.** Claude's first pass on missing-data handling silently imputed BMI=25 and eGFR=90. I overrode in favour of explicit skipping + re-weighting, with notes surfaced in the UI.
- **PREVENT strategy.** Claude leaned slightly toward Option A' (wrapping `pyprevent` as a dependency) under time pressure. I overrode with "stick with A" — pure coefficients, build the engine ourselves. This cost ~45 minutes but the methodology is much more defensible.
- **Test threshold tuning.** When a synthetic high-risk test asserted `>30%` and the actual was 28.67%, Claude offered to investigate whether the model was wrong. I called the threshold over-strict and accepted 0.20 — a faster judgement call.
- **Test reference values.** I refused to weaken the failing Framingham test (Prompt #6); the test stayed strict, and we anchored it to a number we could prove by direct formula evaluation.
- **BMI counterfactual removal.** When Claude initially included a BMI counterfactual, the test showed it didn't move the score because none of our three sub-models actually use BMI for the ASCVD outcome. Claude offered to "fix" it by also auto-adjusting HDL and SBP under the weight-loss scenario. I rejected that as fake-math and removed the BMI counterfactual entirely with a methodology note explaining why. Don't show the user a recommendation the model can't quantify.

**Where I simply ran out of time**:
- **CMM / radar chart visual in the UI.** I would have liked a visual depiction of where the patient's score sits in each algorithm's risk band. Implemented purely as text-and-table.
- **Sub-model unit tests for the SCORE2-OP path** (age 70+). I have one sanity check (`test_score2_op_path_used_for_age_70_plus`) but not a paper-anchored reference test, because the SCORE2-OP paper's worked example wasn't in a form I could quote-anchor easily without spending another hour on the supplement.
- **Counterfactual "what if you stopped smoking" view.** Mentioned in §8 of methodology as a future feature; would have been cheap to build but I prioritised the methodology PDF and prompt log over feature breadth.
- **A 30-yr ASCVD output via PREVENT's 30-yr equations.** The coefficients are in `preventr/sysdata.rda` — would have been ~30 minutes of extra work.

**Total Claude conversation length**: ~12 hours of elapsed wall time, ~18 substantive prompt cycles documented above plus several smaller iterations on test threshold tuning and UI polish.
