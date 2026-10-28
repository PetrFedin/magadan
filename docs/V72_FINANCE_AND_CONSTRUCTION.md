# HydroKontur 360 Magadan | Finance, engineering and capital construction integration

Status: target design; NOT an approved technical design or construction estimate.

## 1. Three economic perspectives must remain distinct

**Corporate finance:** actual changes in revenue, operating costs, investment expenditures, working capital, taxes and financing as permitted by the relevant financial rules.

**Engineering outcome:** reduced technical losses, higher forecast accuracy, earlier verified anomaly detection, validated asset availability. An engineering improvement is not automatically a corporate cashflow.

**Regional/public value:** energy reliability, social infrastructure resilience, environmental and supply continuity; do not mechanically add non-monetary values to corporate NPV.

## 2. Baseline and attribution

Each proposed intervention requires a pre-registered baseline, common scenarios, consistent topology and asset condition, financing horizon, physical quantity units, inflation/tariff treatment, independent approver and a planned post-action comparison. The same grid-loss benefit identified by GridLoss and evaluated by HydroCAPEX counts once, using organization + benefit key + agreed physical origin. Labour hours saved are not automatically realized payroll savings.

## 3. Financial equation contract

Year-zero investment and annual cashflows:

`NPV = -CAPEX_0 + sum((cash_benefit_t - incremental_opex_t - CAPEX_t) / (1 + r)^t, t=1..T)`.

Use Decimal and explicit currency RUB; r is a stated assumption with independent discount-rate authorization. Nominal flows require nominal rates; real flows require real rates. Tax, tariff, subsidies and benefits of avoided energy are not double counted. Portfolio NPV is valid only for comparable baseline assumptions and independent/correctly adjusted interacting effects.

V7.2 `hydrocapex` runs a SMALL brute-force synthetic portfolio (12 projects maximum); it does not estimate construction bills of quantity, external supplier prices, taxes or actual RusHydro investment returns. A negative-NPV mandatory safety project cannot be silently discarded in favour of a profitable nonmandatory project.

## 4. Engineering to project workflow

1. Capture the verified physical issue and current baseline.
2. Specify acceptable no-action and remedial alternatives where legally permissible.
3. Agree design, geotechnical, environmental, power-system and water-use constraints.
4. Select feasibility study method and quality of engineering evidence.
5. Define WBS/CBS and owner-signed Bill of Quantities, priced line by line.
6. Analyze Magadan-specific logistics, staffing, seasonal work windows and climate/geocryology where site-specific investigations confirm applicability.
7. Register design permissions, expert reviews and construction authorizations required for that particular project.
8. Coordinate budget, financing, contracts, 3-way match and physical progress.
9. Track BIM / project change logs; issue a new cost baseline when approved.
10. Verify commissioning and independently evaluate realized engineering and financial results.

## 5. WBS/CBS minimum fields

`project_id, work_package_id, asset_id, legal_owner, design_revision, boq_revision, work_type, quantity, unit, price_source, unit_price_rub, planned_delivery, actual_delivery, contractual_obligation, approved_change_ref, applied_index, document_ref, authorization_state, safety_critical, environmental_constraint, audit_reference`.

No fabricated kilometers of line, excavation volume, pipe diameter or construction cost is permitted. These come from surveying, design documents and official estimates.

## 6. Regulatory applicability register

Legal review should start from: Russia Town Planning Code, Government Decrees 87 and 145 (as applicable), Federal Laws 117-FZ (hydraulic structures), 35-FZ (electricity), 190-FZ (heat), 261-FZ (energy efficiency), 187-FZ (critical information infrastructure), environmental and water laws, current applicable SP and GOST standards and the Magadan regional energy-efficiency program. A named law is not proof that every provision applies to every candidate site. A site-specific register requires clause, current edition, regulated entity, trigger, authority, evidence, status, approver and date.

## 7. Rights and acceptance

RusHydro group participation, municipality participation and subcontractor access cannot be inferred from a corporate-level discussion. Each site/data owner must approve access. The system's simulated manager approval cannot substitute for board, technical authority, procurement or government approvals.

## 8. Funding boundary

Separate research and engineering software grants from construction financing, regulated capital works, O&M and future procurement. A scenario budget is not an approved offer, award or grant entitlement. Funding can be recognized only after binding conditions and appropriate approvals are verified.
