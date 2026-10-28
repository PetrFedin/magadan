# HydroKontur 360 - Magadan | Six site-oriented pilot dossiers

Research candidates ONLY. No owner or operator has authorized access or endorsed the proposals. All units, values and site identities in code demonstrations are synthetic.

## HF-01 HydroForecast: Kolyma basin hydrological uncertainty

**Decision:** Do competing forecast methods provide additional decision value over the operator-approved baseline on periods not seen in calibration?

**Need:** Legally obtained and timestamped hydrometeorological observations, actual flows, reservoir releases, forecast issue history, data-quality lineage, operator restrictions, GIS basin boundaries.

**Engineering work:** Reconstruct historical publication timelines; compare historical incumbent forecasts with a transparent simple baseline; validate probabilistic coverage for different hydrological regimes, seasons and horizons. Keep measured release, calculated inflow and local runoff conceptually distinct.

**Economic mechanism:** Improvement in admissible generation/investment decisions. Never attribute hydrological variability or two-module double-counted benefits to model quality.

**Current code:** Hindcast scoring, future-data guard, interval coverage, WAPE undefined handling. NO operational basin forecast or signed hydrologist approval.

**Gate:** Independent hydrologist signs dataset, forecast issue/availability history and pre-registered error criteria. No automatic reservoir control.

## CE-02 CascadeEconomics: two-stage Kolyma cascade research

**Decision:** What is the range of economic consequences for admissible water/asset scenarios under unchanged water management and technical constraints?

**Need:** Verified level-volume curves, actual hydropower performance curves, permitted releases, environmental requirements, headwater/tailwater levels, repair availability, operator and dispatcher rules.

**Engineering work:** Multi-period water routing, turbine efficiency maps, stochastic scenarios, bound verification, zero violation gate; independently reproduce selected cases with established solver or engineering team.

**Economic mechanism:** Incremental attributable effect of choosing a feasible option; reserve/reliability effects evaluated separately.

**Current code:** Two idealized reservoirs, instantaneous upstream delivery, hydro power approximation and range checks. NOT a regulated cascade model.

**Gate:** Data owner and water engineer attest curves, restrictions and limits before any financial comparison.

## TR-03 TurbineReliability: Kolyma generation unit diagnostics

**Decision:** Which observed trends warrant verified inspection and which actual interventions are cost-effective without weakening planned safety maintenance?

**Need:** Equipment hierarchy, measured signals and operating loads, sensor placement/calibration, failures and root-cause records, maintenance events and spare inventory, OEM technical restrictions.

**Engineering work:** Normal-operating comparability, anomalous shift detection, signed evidence for a defect, expert review, false alert measurement per machine-year, diagnostic lead time by event class.

**Economic mechanism:** Verified avoidable inspections/maintenance costs, expected downtime losses only if probabilities have been calibrated; northern freight and crew availability as sourced inputs.

**Current code:** Robust synthetic MAD indicator with no failure probability; no certified alarm thresholds.

**Gate:** OEM/plant engineer signs dataset/event taxonomy and independent test. Never issue trip/restart commands.

## GL-04 GridLoss Planner: bounded authorized Magadan distribution circuit

**Decision:** Can an independently checked engineering study isolate technical losses and rank legally admissible remedial measures against actual cost and network constraints?

**Need:** Authorized single-line diagram and version, line and transformer parameters, input and output meters and time synchronization, demand profiles, operating conditions, reference solver and applicable loss methodology.

**Engineering work:** Start with loss/balance reconciliation, then multi-bus AC model and model calibration. Distinguish technical losses, metering uncertainties and unexplained residuals; do not label residuals theft.

**Economic mechanism:** Verified loss reduction multiplied by operator-relevant marginal avoided cost, less incremental OPEX and approved CAPEX, discounted consistently. Exact scenario attribution and no double counting.

**Current code:** Synthetic two-bus AC with independent closed-form power flow cross-check. External engineering signoff and actual Magadan feeder data absent.

**Gate:** Professional engineer compares identical topology, inputs and results against approved tool before pilot. Conduct no switching/operational commands.

## HN-05 HeatNet Economics: bounded Magadan heating segment

**Decision:** Which measured discrepancy can be explained by calibrated network physics, and which interventions are technically and financially justified?

**Need:** Verified heat-network topology and ownership, pipe/material/isolation parameters, temperatures, flow, heat meter calibration, pump characteristics, consumption and weather normalization, tariff/treatment methodology.

**Engineering work:** Independent hydraulic solver parity, stationary and peak load scenarios, explicit safety and social-service reliability constraints, post-project validation in comparable climate windows.

**Economic mechanism:** Actual cost reductions from fuel/pump power/maintenance without multiplying physical savings into multiple cashflow buckets.

**Current code:** Simplified steady-state heat delivery and linearized UA loss. NOT a calibrated hydraulic or transient model.

**Gate:** Heat-network owner and technical specialist independently sign the model and meters.

## HC-06 HydroCAPEX: regional energy investment dossiers

**Decision:** Under a limited budget, mandatory reliability works, project dependencies and available resources, which combinations of technically valid options have a clear decision record?

**Need:** Verified asset need, real bill of quantities, actual fiscal and legal owner, engineering alternatives, approvals, procurement rules, WBS/CBS, operating costs, discounting rules, tariffs and funding contracts.

**Engineering work:** Link from a signed study and issue to its specific investment candidate; construction dependency map; phased cashflows; project revision tracking; post-completion effect verification.

**Economic mechanism:** Better capital allocation and lower project lifecycle cost while preserving all mandatory safety investments. A signed NPV is not a construction authorization.

**Current code:** Decimal portfolio NPV and 12-project synthetic enumerator with budgets, dependencies and exclusivity. No real permitting, BIM4D, contractor price integration or finance ERP binding.

**Gate:** Technical authority and finance sponsor confirm mandatory status, unit prices, allowable discounting/valuation and cost baseline.

## Cross-project operational requirements

- Every output carries organization, asset, model revision, input SHA-256, result SHA-256 and execution provenance.
- An engineer can reject a source; rejected data must not enter production-authorized decisions.
- Legal and security ownership is checked separately for each participating organization.
- No cross-owner automatic sharing of operational data.
- Every claimed monetary gain maps to an authoritative post-action baseline comparison and a unique benefit claim for that organization.
- Scientific publications, grants or commercial materials must distinguish synthetic algorithm checks from actual industrial performance results.
