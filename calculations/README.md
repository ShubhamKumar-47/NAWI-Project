# NAWI Automated Metrological Calculation Engine

The **NAWI Automated Metrological Calculation Engine** is a high-precision, version-controlled calculation service layer implementing the testing and verification requirements of **OIML Recommendation R 76-1:2006 (Non-automatic weighing instruments)** and **EN 45501:2015**.

---

## 1. Architecture Overview

Calculation formulas and compliance determinations are isolated inside `calculations/services/` and never directly in `views.py`.

```
calculations/
├── apps.py                  # Django App Configuration
├── models.py                # CalculationRecord model for audit & traceability
├── views.py                 # Views for Calculation Results Page
├── urls.py                  # Routing for calculation results and recalculations
├── tests.py                 # Automated unit and integration test suite
└── services/
    ├── __init__.py          # Unified service layer interface
    ├── tolerance_rules.py   # Configurable, version-controlled OIML R 76 tolerance tables
    ├── validation.py        # Metrological parameter and observation validators
    ├── error_calculation.py  # Precision arithmetic (Python Decimal) and error formulas
    ├── weighing_performance.py # Weighing Performance Test Service (§A.4.4 / §3.5 Table 1)
    ├── repeatability.py     # Repeatability Test Service (§A.4.10 / §3.6.1)
    ├── eccentricity.py      # Eccentricity Test Service (§A.4.7 / §3.6.2)
    ├── zero_tests.py        # Zero-Setting & Tracking Test Service (§A.4.1 – §A.4.3)
    ├── discrimination.py    # Discrimination Test Service (§A.4.8 / §3.8)
    ├── tare.py              # Tare Weighing Test Service (§A.4.6 / §3.5.3)
    └── coordinator.py       # Session calculation orchestrator & DB persistence
```

---

## 2. Normative OIML R 76 References & Formulas

| Procedure | OIML R 76-1 Clause | Standard Formula / Evaluation | Permissible Error Rule |
| :--- | :--- | :--- | :--- |
| **Weighing Performance** | §A.4.4 & §3.5 Table 1 | \(E = I - L\)<br>Turning point: \(E = (I + 0.5d - \Delta L) - L\) | Table 1 by Accuracy Class & Load in \(e\):<br>\(\pm 0.5e\), \(\pm 1.0e\), \(\pm 1.5e\) (initial)<br>\(\pm 1.0e\), \(\pm 2.0e\), \(\pm 3.0e\) (service) |
| **Repeatability** | §A.4.10 & §3.6.1 | Range \(R = I_{max} - I_{min}\) across \(\ge 3\) successive weighings | Range \(R \le \|MPE\|\) for the nominal load applied |
| **Eccentricity** | §A.4.7 & §3.6.2 | \(E_i = I_i - L\) across 5 receptor locations (Centre + 4 quadrants) | Error at each position \(\|E_i\| \le MPE\) for the test load applied |
| **Zero-Setting** | §A.4.1 – §A.4.3 | Turning point: \(E_0 = I + 0.5d - \Delta L\)<br>Direct: \(E_0 = I\) | Maximum zero error \(\|E_0\| \le 0.25e\)<br>(or \(\le 0.5d\) with auxiliary device) |
| **Discrimination** | §A.4.8 & §3.8 | Observed change \(\Delta I = I_2 - I_1\) when extra load \(\Delta L \approx 1.4d\) is added | Indicator response \(\Delta I \ge 1.0d\) |
| **Tare Weighing** | §A.4.6 & §3.5.3.4 | Net error \(E_{net} = I_{net} - (I_{gross} - L_{tare})\) | Net error \(\|E_{net}\| \le MPE\) for the net indication value |

---

## 3. Metrological Integrity Principles

1. **High-Precision Decimal Arithmetic:** All computations employ Python `Decimal`. Intermediate values are never prematurely rounded. Display formatting is strictly separated from internal calculation precision.
2. **Version-Controlled Rules:** Every calculation specifies the standard edition (e.g. `OIML R 76-1:2006`) and rule version (e.g. `R76-2006-v1.0`).
3. **Unconfigured Rule Safeguard:** If an unrecognized edition, accuracy class, or out-of-range load is supplied, the engine flags `is_rule_configured = False` and sets `comparison_result = NOT_EVALUATED`. It never invents arbitrary tolerances.
4. **Audit Traceability:** Each calculation output is persisted to `CalculationRecord` in the database, retaining foreign keys to the original measurement observation, raw input snapshots, computed metadata, and metrologist identity.
5. **Human-Readable Explanations:** Every point includes a step-by-step mathematical breakdown showing load in \(e\), applicable Table 1 range, MPE limit, comparison math, and the final verdict.

---

## 4. Web Interface

The calculation results page is accessible at:
```
/calculations/<session_uuid>/
```
Features:
- Summary KPI cards: Total Evaluated, Compliant Points (PASS), Tolerance Exceeded (FAIL), Overall Session Status.
- Grouped sections for each applicable test procedure.
- Table displaying: Reference Load, Indicated Reading, Calculated Error, Applicable MPE, Comparison Result, Result Badge, and Expandable Explanation.
- One-click **"Recalculate All Procedures"** button for operators and lab administrators.

