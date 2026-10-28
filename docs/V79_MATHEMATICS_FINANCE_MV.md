# V7.9 - mathematics, economics and measurement-verification methodology

All output in this file is a **synthetic mathematical demonstration**. It is NOT utility billing data, a certified M&V estimate, actual tariffs, audited costs, grid operation advice, or a real ROI projection for Magadan.

## 1. Why a loss model is insufficient for financial attribution

For a feeder and a load window `w`:

\[
P_{loss,w} = \sum_{lines\ i} \frac{3 |I_{i,w}|^2 R_i}{10^6}\quad\text{MW}
\]

The base and alternative must share the same source voltage, topology, bus loads, time windows and demand boundary; only a technically documented intervention parameter changes. The V7.8 engine computes signed differences in kWh for each year, checks measured/modelled hours, adds year-specific *hypothetical* avoided supply costs, then subtracts WBS CAPEX and delta-OPEX to produce scenario NPV. This calculation remains `SYNTHETIC_SINGLE_MEASURE_ONLY` and is not a tariff model.

\[
\Delta E_{w,y} = \big(P^{base}_{loss,w}-P^{alt}_{loss,w}\big) h_w n_y 1000 f_y,
\qquad B_y = \sum_w \Delta E_{w,y} c_{w,y}.
\]

\[
NPV_s=\sum_y \frac{k_s B_y - OPEX_y-CAPEX_y}{(1+r)^{y-y_0}}.
\]

`f_y`, `k_s` and all costs are assumptions unless supported by actual records. Negative NPV does not negate mandatory safety projects. Project choices must be constrained by law/operational safety before economic comparison.

## 2. The new benefit *reservation* is not a booked financial effect

One reservation has a fixed organization, source, physical asset, benefit family and reporting years. `org + asset + family + overlapping period` may occur only once. Identical source references cannot be reused even under different family strings.

- `GRID_ANNUAL_V78`: optional gross Rb valuation sourced from the report's base-scenario yearly cashflow rows for the precise requested years. This is GROSS hypothetical avoided-cost, not net NPV or actual cash.
- `MAINTENANCE_HANDOFF_V75`: no numeric benefit inferred. Diagnostic anomaly and repair-option costs do not prove avoided failures or monetary savings.
- `PROGRAMME_V74`: heat energy source for a pinned heatnet study; no certified monetary effect.
- `ASSURANCE_V76`: decision-process study; no certified financial value.

Old V7.3 and V7.6 source reports remain outside this new registry until backfill. A public dashboard must not sum these reports with V7.9 reservations. Cross-company double counting, subcontractor pass-through and shared site boundaries require separate consolidation logic.

## 3. Counterfactual after commissioning - the V7.9 OLS laboratory

It is impossible to directly measure an unobserved counterfactual. IPMVP estimates saving by comparing pre/post measurements adjusted for changed operating conditions and the defined measurement boundary. The tool's first research method uses an hourly loss-rate model:

\[
\hat \ell_t=\beta_0+\beta_1(p_t/10)+\beta_2(p_t/10)^2+\beta_3(T_t/30),
\]

where `p` is delivered demand in MW, `T` is mean ambient temperature in Celsius, and `loss_kwh/duration_hours` is the observed loss rate (kW). The scale factors improve numerical conditioning; coefficients are not physical line constants. This is an *exploratory statistical model*, not an approved physical loss model.

- Fit by least squares **only** to the first 75% of the chronologically ordered pre-commissioning data, requiring at least 24 points for training and 8 pre-commissioning holdout points.
- Evaluate residual MAE, RMSE and bias on the remaining pre-commissioning holdout. A good holdout score does not establish causality.
- Reject non-full-rank design or condition number > 10 million.
- Reject post-period load or temperature outside the original TRAIN support; no unlabelled extrapolation.
- Reject overlap in measurement intervals, missing timezones, source availability after the allowed boundary, duplicated timestamps and NaN/Boolean measurements.
- Estimate for *observed synthetic* post-project windows only. There is no annualization, no preemptive recognition of future benefits and no invented confidence interval.

For post windows with durations `h_t`:

\[
E^{counterfactual}_{post}=\sum_{t\in post}\hat\ell_t h_t,
\quad E^{observed}_{post}=\sum_{t\in post}\ell_t^{observed} h_t,
\]

\[
\Delta E_{modelled}=E^{counterfactual}_{post}-E^{observed}_{post}.
\]

This difference is signed. If it is negative, the instrument must NOT silently clip it to zero. Values are synthetic and `benefit_recognition_eligible=false` regardless of sign.

### Known statistical deficiencies (explicit blockers)

- OLS assumes stable coefficients and does not adjust for serial correlation, heteroscedasticity or meter calibration error.
- The 75/25 split is a research convention, not an accepted industrial holdout design.
- The difference between modelled baseline and post data is not automatically attributable to the investment: non-routine adjustments, confounders, plant changes and reporting errors require independent study.
- No independent third-party interval estimate, normalized uncertainty budget, quality-of-fit acceptance threshold or engineering M&V plan has been agreed.
- This laboratory does NOT use real Magadan load, weather, meters or contracted costs.

## 4. Reproducible synthetic end-to-end result

Run `PYTHONPATH=server python scripts/reproduce_v79.py`.

The script creates a temporary isolated SQLite database and three synthetic user roles. It saves a synthetic turbine study and maintenance handoff; reserves a nonmonetary maintenance family benefit; verifies that a duplicate is rejected with HTTP 409; creates a post-project screen on 48 baseline and 12 post synthetic observations; verifies audit replay and local HMAC chain.

The actual synthetic signed difference and its report SHA-256 are written in `artifacts_v79/showcase_trace_v79.json`. No observed real saving is asserted.

## 5. How to build an admissible real M&V process later

1. Sign a measurement boundary map: asset IDs, supply points, instruments, calibration records, affected and unaffected energy streams.
2. Approve a baseline observation period covering appropriate load/season conditions with a data-quality report.
3. Approve an adjustment model **before** final post-project verification; agree on routine and non-routine adjustment methods.
4. Record the exact installation, commissioning and stabilization dates and any temporary operating constraints.
5. Collect post-project data independently; measure the reliability of meters and missing data.
6. Report counterfactual uncertainty and sensitivity, use appropriately specified temporal validation, and control multiple measures sharing a boundary.
7. Have the engineering and financial owner sign separate technical and valuation conclusions. Do not multiply kWh by a retail tariff without a justified avoided-cost basis.
8. Only after verified physical effect and accepted cost treatment should a **new separately authorized** accounting workflow recognize a financial outcome. V7.9 has no such workflow.

Reference: EVO IPMVP https://evo-world.org/en/products-services-mainmenu-en/protocols/ipmvp
