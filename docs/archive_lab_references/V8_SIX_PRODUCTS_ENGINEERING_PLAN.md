> **АРХИВНЫЙ ИСТОЧНИК:** извлечённый текст из библиотеки проекта, а не проверенный исходник GitHub. Утверждения об исторических испытаниях НЕ проверены на текущем SHA репозитория. PRODUCTION HOLD. Перенесено 28.10.2026.

# HYDROKONTUR 360 / MAGADAN - V8 end-to-end engineering programme specification

**Issue:** 2026-10-25. **Classification:** DESIGN / laboratory research. No RusHydro acceptance; no municipal/industrial access; no approval of operating regimes, construction or grant funding. The six candidate pilots are not contracts.

## A. Common operating contract

Every product must produce an `EngineeringEvidenceBundle` with the following fields and validation responsibilities:

| Group | Minimum fields and tests | Responsible signoff |
| --- | --- | --- |
| Owner and object | legal owner/operating organization, scope/asset_id, real vs laboratory classification, access agreement, authorized data custodian | Legal and asset owner |
| Source | hash, custody, origin, observation/availability timestamps, calibration, unit, accepted revision | Data steward + metrology specialist |
| Geometry and physics | topology/basin graph/thermal graph/equipment hierarchy, parameter uncertainty, limits | Profile engineer |
| Engine | code/container SHA-256, algorithm release, solver numerical tolerances, installed dependencies | Computational methods owner |
| Baseline | agreed status quo or no-project scenario, independent replay, same boundary and weather/load/operations | Engineering reviewer |
| Alternatives | technically permissible interventions, explicit changed variables, cost/schedule commitments, safety gate | Owner engineering authority |
| Financial | avoided-cost basis, OPEX delta, WBS/CBS, year-by-year CAPEX, tax/tariff policy, discount rate, double-benefit-control | Financial reviewer |
| Post-implementation | commissioning and acceptance dates, meter traceability, independent M&V plan, actual data, uncertainty, residual risks | Independent expert and operating owner |
| Decision | RACI, documentation revision, approver, approval date, authorization scope, permanent audit | Authorized investment body |

**No research bundle may be upgraded to a field-approved bundle by changing a boolean.** New version, signed evidence and separate decision authorization are mandatory.

## B. HydroForecast (Kolym basin) - RFQ and validation

- Object: one agreed catchment in Kolym hydro basin; candidate only, owner to determine actual boundaries.
- Required: gauge discharge/level time series; station timestamps and correction revisions; meteorological forcings and their *availability at forecast issue*; snow and freeze data where available; basin DEM, area and land cover, hydrological boundaries, upstream influences.
- Model portfolio: existing owner baseline, naive seasonal benchmark, physical water-balance candidate and optional statistically calibrated residual model. Never fit and test on the same historical dates.
- Physics: `dS/dt = P + inflow - ET - outlet - losses` with consistent m3/second and m3/storage conversion; quantify missing mass-balance terms rather than silently ignoring them.
- Predictions: agreed lead times, unique issue timestamp, `(Q10,Q50,Q90)` only if coverage is calibrated (otherwise label as scenarios, not quantiles), ensemble identifiers, inputs hash.
- QA: blocked future-information leak; coverage by hydrological regime; MAE/RMSE/bias vs baseline, interval reliability score; discharge extremes with independent hydro review.
- V8 output: versioned forecast package that CascadeEconomics consumes via explicitly approved `catchment_id, time_step_s, q_m3_s, units, issue_at, available_at, source_sha` contract.
- Blockers: signed gauge data authorization, reference predictions, independent hydrologist acceptance.

## C. CascadeEconomics (Kolyma + Ust-Srednekan) - planning research

- Objects: Kolym cascade facilities as *candidate* nodes, not actual operational data.
- Inputs: surveyed stage/storage curves, tailwater level, head loss/efficiency curves by turbine, reservoir constraints, environmental obligations, dispatch/inflow history, hydrological forecast provenance, maintenance lockouts.
- Mass-balance each step: `S[t+1] = S[t] + (Qin[t] - Qturbine[t] - Qspill[t] - Qother[t])*dt` with correct upstream routing lag and spill flows. Two-step delay or linear reservoir are **research approximations**, not approved river routing.
- Hydropower: `P = rho*g*Q*H*eta` at actual operational head and measured machine map; rated power and availability limits mandatory.
- Optimization objective: compare permissible options under a pre-agreed economic accounting method; **hard** hydrotechnical, ecological and dispatch restrictions take priority over any price signal.
- QA: mass-balance residual by interval, routing nonnegativity, boundary violations, zero/peak flow, missing gauges, independent ResSim or owner-calibrated model comparison.
- Output: scenario set with all active constraints, uncertainty bands, result delta, policy decisions and engineering review.
- Blockers: applicable water-management rules, reservoir and turbine maps, regulatory/owner consent.

## D. TurbineReliability (Kolyma units) - condition to action

- Objects: agreed unit(s) on one cascade station, not entire fleet by assumption.
- Required: sensor unit/calibration, sensor placement, vibration spectra, temperature and operating points, machine rebuild history, defect coding, work orders, inspections, repairs, serviceable spares and logistics.
- Anomaly != defect != failure. Define observed event, engineering hypothesis, expert-confirmed defect, action, result as separate entities. Rare failures do not justify an uncalibrated probability.
- Models: regime-stratified baselines, change-point diagnostics, event-time cross-validation, event provenance. Record false alarms per machine-hour, sensitivity to reviewed defects and lead time.
- Repair choice: alternatives `inspection/repair/replace/defer(if permissible)` with disaggregated costs `parts+work+transport+planned outage+expected consequence(if legitimately calibrated)`; do not count hypothetical avoided failures as real savings.
- Integrations: EAM/CMMS work order evidence linked to HydroCAPEX decision, external engineer signs intervention merits.
- QA: regime leakage, timestamp leakage, wrong asset/organization, spare availability, impossible schedule, independent failure label and repair ROI.
- Output: technical action candidate with rationale and bounded loss scenarios; no automatic dispatch or turbine commands.

## E. GridLoss Planner - primary Magadan candidate

- Pilot: one bounded feeder with owner-approved, legally accessible topology and synchronized load/meter intervals.
- Required: buses and branches, R/X and transformer data, phase assumptions, voltage base, switch positions by date, meters, losses/energy boundaries, time-of-use demand, line thermal limits and revision history.
- Lab physics: for symmetrical 3-phase line `Ploss(W)=3*|I|^2*R` with proper phase units. Field: independent multi-bus AC load flow including relevant regulator/transformer, reactive power and network configuration; phase unbalance when material.
- Require signed exported input case and independent solver execution evidence (version/hash, power-flow convergence, independent node/branch values). A reuploaded in-house result is NOT independent validation.
- Economics: `DeltaE[kWh] = sum_windows (Ploss_base-Ploss_alt)[MW]*h*1000`; future yearly profiles must be justified. Avoided-cost price is a recognized incremental cost, not retail tariff by default; include commissioning date, CAPEX WBS, changed OPEX, tax and nominal/real consistency.
- Field M&V: meter calibration, missingness, topology changes, before/after normalization and confounding plan preapproved; independent engineer verifies performance and operator signs intervention.
- Acceptance: external solver agreement by pre-agreed tolerances; source model quality, cost and input lineage; output does not violate operational grid limits.

## F. HeatNet Economics - hydraulic + economic twin

- Pilot: one owner-agreed thermal segment, and document inter-operator exchange rights if heat producer and network operator differ.
- Inputs: topology, DN/pipes/material/insulation, age, supply/return routes, pump curves, heat exchange stations, pressures, flow, temperature, ambient conditions, equipment efficiency, meter calibration, outage history.
- Physics: `Qdot = mdot*cp*(Ts-Tr)` with mass flow units; hydraulic network equations and heat-transfer losses calibrated against actual permitted measurements; power calculation alone is not a hydraulic solver.
- Scenario baseline: compare identical outside temperature, heat demand, metering boundaries, pressure constraints. Post-project savings must adjust for heating-degree-days and customer mix with agreed methodology.
- Economics: separate thermal energy saved, pump electricity saved, cash expenditures avoided, repair effects, tariff/regulated accounting. Do not double count fuel and the same sold heat energy.
- Reference: professional thermohydraulic model (e.g. owner-approved ZuluThermo or alternative); independent heat engineer acceptance before business use.
- Output: verified candidate heat-network investment with technical constraints, construction drawings and actual efficiency evidence.

## G. HydroCAPEX - engineering-to-investment execution

- Financial project object must keep immutable `technical_need -> baseline -> alternatives -> selected solution -> permits -> WBS/CBS -> contracts -> execution -> verified result` chain.
- WBS: object and year, quantity, priced unit, rate provenance, transport cost, taxes, contingency separately, dependencies, actual contractor confirmations.
- Valuation: `NPV = sum_y (Benefits_y - incremental OPEX_y - CAPEX_y)/(1+r)^(y-y0)`. IRR and ROI only where cashflow shape makes these meaningful; mandatory safety projects assessed for least-cost compliant solution, not discarded for negative NPV.
- Portfolio: binding budget by year, optional/mandatory alternatives, exclusive choices, site dependencies, construction seasons, risk, workforce, procurement lead time and governance.
- Magadan North Logistics: seasonally constrained access, verified routes/quotes and actual permitted construction windows; geographic generalizations cannot substitute for site-specific surveys.
- Construction: survey reports, design brief, feasibility, design/expert approvals as applicable, detailed design, procurement, construction supervision, as-builts, commissioning and lawful acceptance. A CAD map is not a working drawing.
- Finance source: corporate ERP/EPM remains authoritative unless explicitly approved otherwise. HydroCAPEX performs the narrower engineering-origin/proof role and never silently writes to actual corporate budget without an approved integration.

## H. Cross-module and security boundary - V8 deliverables

### Must exist as concrete versioned API contracts

- `ForecastRelease -> CascadeScenario`: temporal `m3/s` rates and uncertainty; physical mapping to approved basin boundary.
- `ConditionEvent -> RepairAlternative`: verified asset node, event label confidence, downtime, logistics/CMMS work-order route.
- `NetworkModel -> EngineeringOption -> AnnualCashflows`: topology, load support, per-window loss energy and cost.
- `ThermalModel -> EngineeringOption -> AnnualCashflows`: hydraulic and weather-normalized validity.
- `All EngineeringOptions -> Portfolio`: unique physical effect identity + time boundary, frozen costs and WBS, authority to make decision.
- `ProjectExecution -> OutcomeVerification`: commissioned installed version, data after acceptance and independent M&V.

### Security and audit gates

1. PostgreSQL 17 database exclusively dedicated to testing; deterministic migrations 001-140; no overwrite of previous migration; correct table privileges; `FORCE RLS`; test owners and bypass privileges; session pooling, concurrent creation and role revocation.
2. Corporate OIDC with real IdP + MFA, approved access mapping and immediate removal tests; exact client TLS and secret rotation.
3. External audit outbox, signed object-version receipts and independent retention enforcement; test read-after-write, retry, duplicate receipt and key rotation.
4. Data classification and physical segregation of SCADA/operational environments; no command or dispatch endpoints in lab or prod analysis until separately regulated/approved scope.
5. Independent engineering solver and mathematical tolerance report, reproducible build/container SHA and source evidence; human expert signature.
6. Read-only pilot with real field measurements after lawful permission; no operational control.
7. No official dashboard ever aggregates old financial claims plus new lab benefit reservations until complete backfill, reconciliation and scoped boundary conflicts are proven closed.

## I. Proposed acceptance milestones G0 to G9

| Gate | Minimum deliverables | NO-GO reason |
| --- | --- | --- |
| G0 | Owner/engineering sponsor and data rights | No signed authorization |
| G1 | Asset boundary, provenance, data quality and time | No valid source or broken chronology |
| G2 | Physical model validated on independent baseline | No numerical convergence/verified geometry |
| G3 | Inter-module transfer calibration | Volume, units, timestamps or asset mismatch |
| G4 | Scenario and restrictions check | Any hard safety or legal rule violated |
| G5 | Signed engineering alternative with no hidden change | Unsupported cost or unrealistic scheduling |
| G6 | Financial and tax/tariff valuation | Double benefit, no independent assumptions, unsupported rates |
| G7 | Approved designs, legal/permit pathway, funding | Missing required permissions |
| G8 | Verified implementation and operation | Incomplete acceptance, meter calibration or commissioning |
| G9 | Independently accepted M&V and benefit recognition | Baseline mismatch, confounding, no external attestation |

## J. Existing scope and explicit nonclaims

- V7.9 LAB has a synthetic benefit reservation ledger and synthetic post-project M&V. It does NOT field-verify six independent models.
- No Magadan real feeder, catchment, turbine, TPP or municipal heat network approved; no data/ownership contract; no grant funded.
- PostgreSQL RLS, a real enterprise IdP, real WORM storage and any independent industry power flow validation remain UNACCEPTED.
- The laboratory 13th UI section is new; an actual browser E2E acceptance remains open.

## Source orientation (confirm current applicability prior to field decisions)

- PostgreSQL 17 row security: https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- EVO IPMVP: https://evo-world.org/en/products-services-mainmenu-en/protocols/ipmvp
- Deltares Wflow: https://deltares.github.io/Wflow.jl/
- U.S. Army Corps HEC-ResSim: https://www.hec.usace.army.mil/software/hec-ressim/
- pandapower power flow: https://pandapower.readthedocs.io/en/stable/powerflow.html
- Russian Civil Planning Code, applicable construction and hydraulic safety law: verify controlling edition and project-specific applicability with the licensed technical/legal designer.
