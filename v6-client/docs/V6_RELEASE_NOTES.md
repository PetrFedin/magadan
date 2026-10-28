# HYDROKONTUR 360 -- MAGADAN V6 (20 October 2026)

## What really changed
- New `src/assurance.mjs` defines quality/traceability/feasibility checks, not a plant solver.
- 34 new assurance tests complement the 29 tests in V5: 63/63 passed.
- Six existing domain modules and seven-stage decision flow preserved.
- Browser QA: 6 modules, 7 workflow transitions, 8 assurance interactions, no JS errors; desktop and mobile at 375 px tested.
- 108 proposed requirements, 48 data dictionary definitions, 15 planned APIs, 12 RACI activity mappings and 6 candidate Magadan pilot perimeters.
- 29 workbook tabs, including 21 preserved V5 tabs and 8 new V6 tabs. 234 formula cells evaluated without reported calculation errors.
- A synthetic eight-year electricity loss intervention produces NPV about RUB 17.702 million under explicit invented input assumptions. This is NOT an empirical finding or forecast for any RusHydro asset.
- The Word/PDF technical specification is in English for engineering teams with a Russian cover and regional context.

## Release gates
**Production HOLD.** Browser role selection is not real authentication. LocalStorage is neither confidential nor authoritative. The existing event-hash chain is not a server-anchored immutable ledger. New assurance checks are a separate local demonstration screen, not a mandatory server-side gate on all decision transitions. Real flow, network and hydraulic solvers are not connected. No institutional access to asset data or industrial infrastructure has been obtained.

## Minimum next increment
1. Legally identify candidate data owner and select one Magadan object with enough reliable data.
2. Implement a restricted server API with actual identity, tenant scope and independent audit anchoring.
3. Bind dataset/model/constraint evidence receipts to workflow transition validation; reject any missing signed engineering approvals.
4. Integrate one independently validated engineering calculation and agreed control baseline.
5. Run independent verification and finance reconciliation before claiming ROI or presenting as an approved pilot.

## Comparison references
- ISO 55001:2024 official source: https://www.iso.org/standard/83054.html
- Asset-management decision value summary: https://committee.iso.org/sites/tc251/home/projects/published/iso-55001.html
- HEC-ResSim: https://www.hec.usace.army.mil/software/hec-ressim/features.aspx
- Heat network ZuluThermo: https://politerm.com/zuluthermo/webhelp/index.html
- Oracle Primavera baseline, actuals and forecast: https://docs.oracle.com/en/industries/construction-engineering/primavera-unifier/26/managers/cashflow-10298240a.html
- Russian project documentation Gov Decree 87 (current consolidator): https://www.consultant.ru/document/cons_doc_LAW_75048/

These competitor and regulatory sources provide context only; their appearance does not mean our laboratory has equivalent certified features or Russian compliance.
