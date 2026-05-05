# CardioQ Heart Score (Educational Prototype)

A 0–100 unified cardiovascular risk score that combines three globally
validated algorithms — Framingham 2008, ESC SCORE2 (2021), and AHA PREVENT
(2023) — into a single, explainable Heart Score with risk band, top
contributing factors, and downloadable JSON report.

Built as a 48-hour AI-augmented build sprint for the CardioQ.ai Product
Development Intern role at Ziffytech Digital Healthcare.

> ⚠️ **Educational use only.** This is not a clinical or diagnostic tool.
> Do not use real patient data. Discuss health questions with a qualified
> clinician.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/<your-handle>/cardioq-heart-score.git
cd cardioq-heart-score

# 2. Install
pip install -r requirements.txt

# 3. Run tests (28 tests, all should pass)
pytest -v

# 4. Launch the Streamlit app
streamlit run app.py
```

A live deployment is also available (see hosting section in the email).

---

## What's in this repo

```
cardioq/
├── app.py                  # Streamlit UI (D1)
├── heart_score.py          # Fusion engine: percent → 0-100 → band → factors
├── algorithms/
│   ├── framingham.py       # D'Agostino 2008 General CVD risk
│   ├── score2.py           # SCORE2 (40-69) + SCORE2-OP (70+) with regional recal
│   └── prevent.py          # AHA PREVENT base 10-yr ASCVD
├── tests/                  # 28 unit tests (all passing)
│   ├── test_framingham.py
│   ├── test_score2.py
│   ├── test_prevent.py
│   └── test_heart_score.py
├── METHODOLOGY.md          # 3-5 page methodology note (D2)
├── PROMPTS.md              # AI prompt log (D3)
├── README.md               # this file
└── requirements.txt
```

---

## Validation against published reference cases

Each algorithm was implemented from primary sources and unit-tested against
the worked examples published in those sources.

| Algorithm | Reference test | Source | Pass |
|---|---|---|---|
| Framingham 2008 | 61F, TC180, HDL47, SBP124 → 6.32% | Manual trace from FHS site coefficients | ✅ |
| SCORE2 (M50, low region) | smoker, SBP140, TC5.5, HDL1.3 → 5.9% | SCORE2 paper abstract | ✅ |
| SCORE2 (M50, very-high region) | same → 14.0% | SCORE2 paper abstract | ✅ |
| SCORE2 (F50, low region) | same → 4.2% | SCORE2 paper abstract | ✅ |
| SCORE2 (F50, very-high region) | same → 13.7% | SCORE2 paper abstract | ✅ |
| PREVENT (F50) | full reference profile → 9.2% | preventr R package docs (Khan 2024) | ✅ |

Plus 22 additional tests covering edge cases, missing-data handling, and
the 5 patient profiles specified in the assignment brief.

---

## Heart Score methodology in one paragraph

Each sub-model returns a 10-year cardiovascular risk percentage. Each
percentage is mapped to a 0–100 sub-score using *that algorithm's own
published clinical risk-band thresholds* with linear interpolation. The
three sub-scores are combined as a weighted average (Framingham 0.35,
PREVENT 0.35, SCORE2 0.30) and mapped to a 5-tier risk band (Low,
Borderline, Moderate, High, Very High). When an algorithm can't run
(age outside its validation range, or PREVENT-required inputs missing),
the surviving algorithms are re-weighted proportionally so the result is
still defensible. The UI also surfaces **counterfactual "what if" scenarios** —
e.g. "if you quit smoking, your score would drop from 88.9 to 80.4" —
ranked by largest score reduction. Full justification, including the
known limitation that the three algorithms predict slightly different
outcomes, is in [METHODOLOGY.md](METHODOLOGY.md).

---

## Citations

- D'Agostino RB Sr, et al. General cardiovascular risk profile for use in
  primary care: the Framingham Heart Study. *Circulation*. 2008
  Feb 12;117(6):743-53. PMID: 18212285.
- SCORE2 working group and ESC Cardiovascular Risk Collaboration. SCORE2
  risk prediction algorithms: new models to estimate 10-year risk of CVD
  in Europe. *Eur Heart J*. 2021;42(25):2439-2454. PMID: 34120177.
- SCORE2-OP working group. *Eur Heart J*. 2021;42(25):2455-2467.
  PMID: 34120185.
- Khan SS, et al. Development and Validation of the American Heart
  Association's PREVENT Equations. *Circulation*. 2024
  Feb 6;149(6):430-449. PMID: 37947085.

Coefficient sourcing notes are in [METHODOLOGY.md](METHODOLOGY.md).

---

## License

MIT (see LICENSE).
