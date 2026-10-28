# HydroKontur 360 - Magadan V7.8: mathematical, engineering and economic specification

**Classification:** SYNTHETIC LABORATORY RESEARCH, not an approved engineering design, grid model, capital estimate or RusHydro report. The names Magadan and RusHydro describe prospective pilots, not customer access or endorsement.

## 1. Architectural rule: one traceable calculation chain

Verified synthetic input -> reproducible engineering solve -> matched intervention -> annual load-window aggregation -> approved-for-LAB-only WBS -> nominal annual cashflows -> NPV scenarios -> independent arithmetic replay -> immutable laboratory dossier -> separate subject-matter sign-off (NOT YET AVAILABLE).

Every calculation records organization, asset, engineering source IDs, source input/result/algorithm checksums, research programme revision and WBS, cost assumptions and their origin, financial-engine hash and reference year. Editing the model code deliberately invalidates earlier reproduction until it is explicitly versioned and requalified.

The database and API strictly limit this flow to `LAB_REFERENCE` assets. A report may NEVER be attached to a real grid investment approval, permit, procurement decision or grid automation action. Real asset data and tariff treatment are outside the accepted scope.

## 2. Physical model: synthetic balanced radial three-phase PQ network

The legacy V7.3 solver, used as the **source** for V7.8, is a connected tree with a slack bus `SOURCE` and up to 16 study nodes. Every node has line impedance per phase R+jX (ohms), nonnegative active/reactive load P and Q, and a current limit. Time-window `scale` affects node loads. Voltage is nominal line-to-line kilovolts.

For each static load window, per-phase source voltage is `V0 = 1000 * V_LL_kV / sqrt(3)` volts. For node i: `S_i = scale * (P_i + j Q_i) * 1e6 / 3` VA per phase; `I_load_i = conjugate(S_i / V_i)`; `I_branch_i = I_load_i + sum(I_branch_children)`; `V_i = V_parent - Z_i * I_branch_i`.

An iterative backward/forward sweep solves these equations; a separately initialized nonlinear nodal-Kirchhoff root computes a numerical cross-check (NOT an independent commercial power-flow application). `P_loss_i = 3 * |I_branch_i|^2 * R_i / 1e6` MW. Reactive loss is `Q_loss_i = 3 * |I_branch_i|^2 * X_i / 1e6` MVAr. Sending power minus receiving aggregate load equals losses to the solver's numerical tolerance. Voltages and current limits are checked for each window.

This model excludes phase unbalance, zero-sequence current, neutral, harmonics, distributed generation, storage, tap changers, nonlinear devices, protection, N-1 contingencies, actual switching, SCADA and calibrated as-built asset data. It cannot independently demonstrate real network safety or capacity.

## 3. Baseline versus intervention: strict physical invariance

`physical_comparability(base, alternative)` requires same source voltage, minimum voltage criterion, reference identity, exact tree connectivity, identical node set, identical node loads, identical time-window names/scales/durations. Only branch impedance and ampacity may change. If no engineering property changes, the pair is rejected. The alternative must satisfy test current/voltage limits; limitations of the baseline remain explicitly visible.

Each engineering source is replayed before financial valuation and its input/result SHA-256 and algorithm hash checked. If two cases differ in load or period, a difference in total energy losses cannot be treated as the economic result of the proposed action.

This deliberately conservative invariant set is NOT a full technical design comparison. A genuine reconstruction may require new topology, devices and network reliability models; in that case a separate validated comparison methodology must be authorized instead of relaxing the synthetic rule.

## 4. Physical energy savings for each window and year

For load window w: `E_base_w = P_loss_base_w * H_w` (MWh per synthetic cycle), `E_alt_w = P_loss_alt_w * H_w` (MWh). For year y with C_y repeated cycles and explicitly assumed retention fraction f_y:

`E_saved_y,w [kWh] = (E_base_w - E_alt_w) [MWh] * 1,000 * C_y * f_y`.

Savings may be negative. The API preserves the sign and therefore reports an *increase* in cost if the intervention worsens the physical loss result. A synthetic retained-savings factor is neither a probability nor a measured degradation curve.

`H_model_y = C_y * sum_w H_w`. Validate `H_model_y <= 8,760`, or `<= 8,784` for leap years; otherwise hard reject. If `H_model_y < calendar hours`, flag `PARTIAL_YEAR_NO_EXTRAPOLATION` and do not monetize missing hours. Having 7,200 modeled hours does not imply full-year loss savings.

For a specific load window the modeled technical loss ratio is `P_loss / (P_delivered + P_loss)` with matching units. This is NOT the audited electricity loss of a region or any legal/tariff reporting percentage.

The model checks year-by-year that every engineering window has exactly one assigned synthetic economic avoided-cost rate; no substitute average or zero fills are allowed.

## 5. Value of avoided energy and costs - explicit regulatory boundary

Each cost assumption `c_y,w` is in synthetic RUB/kWh. `GrossAvoided_y = sum_w E_saved_y,w * c_y,w` RUB. It is NOT an energy tariff and is not automatically a net cash inflow in a regulated utility. Real monetization requires verified marginal avoided generation or procurement cost, approved methodology and consistent regulatory treatment.

An optional additional OPEX may be positive or negative, explicitly stated in RUB per year. Costs and saving rates are in nominal prices and discounted with a nominal rate. This does not yet model VAT, profits tax, depreciation, financing, grant receipts, tariff pass-through, tax liabilities or inflation from external sources. Those modules require actual customer accounting and legal review.

Three scenarios are *not probability-weighted forecasts*: `low/base/high` are ordered synthetic multipliers between 0 and 3 applied only to gross avoided cost. Capex and additional OPEX remain fixed within this scenario, so no Monte Carlo distribution, confidence interval or VaR is implied. Price and physical uncertainty are not independently probabilistically calibrated.

## 6. Capital: one intervention and one exclusively attributed WBS

Capital comes exclusively from the linked research programme's `CapitalScreen`, not from a free input box. WBS lines contain code, class (`survey`, `design`, `equipment`, `civil_works`, `logistics`, `commissioning`, `other`), year, quantity, unit, synthetic unit price, price-reference ID and predecessor IDs. Cycles, absent predecessors and duplicate codes are forbidden. Contingency specified both as a percent and separate line is forbidden.

`CAPEX_y = sum_i (q_i * p_i) * (1 + contingency_pct / 100)` for lines in year y. It is checked against the declared annual RUB budget cap; a breach remains visible in output and is never transformed into financing approval. Required `commissioning` line must be present; first-year operational savings are permitted only strictly AFTER the last commissioning year and all planned capital works. Any missing design, environmental, survey or project stages must be listed as missing, not silently assumed to exist.

This WBS is a **screening exercise**, NOT a cost estimate by design engineer, contractor, licensed estimator, independent geotechnical expert, regional index or current budget classification. Northern transport, permafrost, geology, seismic design, seasonal windows and cost escalation require separately sourced evidence.

## 7. Nominal annual cashflows, convention and reproducible NPV

For each year y (construction years have Gross=0), for synthetic scenario s:

`NetCF_y,s = GrossAvoided_y * scenario_factor_s - AdditionalOPEX_y - WBS_CAPEX_y`.

`PV_y,s = NetCF_y,s / (1 + r_nominal)^(y - anchor_year)`, with **all cashflows at year end**, discount anchor **31 December of anchor year**, `anchor_year < first CAPEX year` and `anchor_year < first full service year`.

`NPV_s = sum_y PV_y,s`, with PV of gross, OPEX and CAPEX disclosed independently. Both nominal parameters and anchor year are recorded. Discounted payback is only the first relevant year-end with positive cumulative PV, if any; otherwise it is null. IRR is not reported because changing signs can produce multiple roots, and it is inappropriate to present a spurious single return number.

`break_even_extra_gross_multiplier = max(0, PV(OPEX + CAPEX)/PV(Gross_s))` when `PV(Gross_s) > 0`. This is a **multiplier on the gross value of the given scenario**, not a regulatory tariff or a forecast of fuel prices. It is undefined when gross PV is zero or negative.

Decimal arithmetic is used for currency and a second calculation independently reconstructs NPV from each row of saved year-end cashflows. The executable reference checks absolute discrepancy <= RUB 0.05, allowing explicit 2-decimal per-row reporting. Independent internal arithmetic checking does not establish empirical validity of assumptions.

## 8. Reproducible SYNTHETIC sample with years 2027-2031

Baseline: 20 kV balanced radial feeder with three loads, window `normal` 120 hours and `winter_peak` 24 hours. Proposed single change: resistance of one modeled branch 0.25 to 0.13 ohm per phase; loads, topology, voltage and windows stay unchanged.

Baseline 144-hour window cycle: **2.399290916 MWh** calculated technical losses. Proposed cycle: **1.349564646 MWh**. Difference: **1.049726270 MWh per cycle**.

2027 WBS survey RUB 300,000, 2028 equipment RUB 1,500,000, 2029 commissioning RUB 500,000. Total synthetic pre-tax CAPEX = RUB **2,300,000**. Service begins only in 2030.

For 2030 and 2031, 50 cycles/year = 7,200 modeled hours (no extrapolation to 8,760). 2030 avoided-cost assumptions normal 3 RUB/kWh and peak 8 RUB/kWh; 2031 normal 4 and peak 9. Additional annual OPEX 100,000 and 120,000 RUB. 2031 retained savings factor = 0.95. Price factors low=0.7, base=1.0, high=1.3. Nominal discount rate 12%, anchor 2026 year end.

NPV low = **RUB -1,753,573.76**; base = **RUB -1,668,884.89**; high = **RUB -1,584,196.03**. Both physical loss reduction and NEGATIVE NPVs are retained. This is a deliberately NON-viable synthetic example, not an investment recommendation to RusHydro. See `artifacts_v78/showcase_trace_v78.json` for full intermediate rows and SHA-256.

## 9. Mathematical programme across all six products

| Product | Mathematical variables and equations | Verification | Field blockers |
|---|---|---|---|
| HydroForecast | hydrographs Q(t), snow/precipitation forcings, MAE, RMSE, bias, probabilistic CRPS and interval coverage | forward-only temporal backtesting, no future data | licensed historic observations, gauging, hydrologist sign-off |
| CascadeEconomics | water continuity V(t+1)=V(t)+(Qin-Qout)*dt; station P=rho*g*Q*H*eta; lag/routing | mass balance at every step and constraint membership | approved water-use rules, volume/head curves, reservoir calibration |
| TurbineReliability | signals by comparable mode, deviations, failure labels, expected cost conditional on *calibrated* probability | independent fault adjudication, precision, false alarm/asset/year | asset failure history, repairs, expert labeling, no fabricated probabilities |
| GridLoss Planner | AC nodal KCL, line complex impedance, three-phase I2R, voltage and thermal constraints | separate numerical KCL root, external professional solver PENDING | as-built topology, meter calibration, independent power-flow validation |
| HeatNet Economics | thermal Qdot=m_dot*c_p*(T1-T2), hydraulic mass conservation, network loss and pump cost | calibrated pressure/temperature/flow against certified observations | pipeline drawings, actual nodes, sensors, professional thermohydraulics |
| HydroCAPEX | WBS q*p, year-end DCF, budget caps, project precedence, option exclusion, no double-counting | independent recalculation and post-project M&V | contractual prices, permits, invoices, tariff methodology, accepted financing |

No module is permitted to issue control commands to SCADA, grid protection, reservoirs, pumps or industrial devices. Modules must report their own uncertainty, assumptions and the explicit scope of validity. No synthetic number is a verified indicator of an actual Magadan facility.

## 10. Software numerical checks, access controls and open issues

- Access: server-side authentication and membership per tenant; in SQLite tests records are also append-only. PostgreSQL RLS SQL is prepared but **not natively executed**.
- Integrity: original source study, engine, programme revision, financial input, WBS, scenario output pinned by SHA-256; auditor replay actually recomputes physical and financial results.
- Single-measure exclusivity: one programme WBS may not be assigned to a second V7.8 dossier; sequential legacy module duplicate checks exist. **Cross-table concurrent uniqueness is NOT yet atomic.** A global benefit ledger and PostgreSQL contention tests are P0.
- Provenance: demo rates have `SYNTHETIC-*` references, never represent a tariff, supplier offer or approved cost norm.
- Security: real corporate OIDC/MFA, WORM immutable archive, native PostgreSQL RLS, backup-restore, key rotation and independent penetration test are NOT completed.
- Engineering: third-party solver and field comparison, N-1, reliability indices, tariff audit, climate/permafrost design and independent engineer certification are NOT completed.
- Outcome: no industrial project, grant decision, structural engineering drawing, permit or project financing is approved.

## 11. External reference requirements for acceptance

A proper grid pilot needs: owner's written permission, approved and revision-controlled one-line diagram, measured impedances, transformer and switch configurations, time-stamped actual load/energy inputs, metering quality report, line thermal limits, base/proposed network definitions, certified independent solver execution output, formal tolerances, reviewer independence and signed comparison protocol.

For Magadan: separate agreements with the asset owner and all suppliers of protected data; do not assume consent from RusHydro covers other utilities. As-built topology and legally necessary permits cannot be deduced from published maps.

For financial acceptance: actual avoided supply cost by period, regulated/nonregulated treatment, accepted inflation and discount conventions, priced and independently checked WBS and northern logistics, taxation/financing, baseline counterfactual, uncertainty and a post-implementation M&V protocol. A positive NPV without these facts is not a funding approval.
