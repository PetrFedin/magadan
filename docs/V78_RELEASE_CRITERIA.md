# V7.8 Release criteria, risks and next engineering gates

## V7.8 acceptance predicates

- LAB_PASSED requires successful unit regression, deterministic synthetic arithmetic and no missing window/source identifiers, input/engine hash replay, negative checks, append-only test, user/asset segregation. PASSED.
- LIMITED_UI_STATIC_QA requires no overflow on 375/768/1440 and no broken static DOM IDs. PASSED.
- PG_NATIVE_RLS_ACCEPTED requires real PostgreSQL17, roles, permissions, transaction-bounded signed sessions, RLS with and without context, immutable tables, concurrency tests, backup/restore. NOT PASSED.
- INDEPENDENT_PHYSICS_REFERENCE requires owner-authorized as-built, field measurements, external professional solver on identical case, fixed tolerance and independent engineer. NOT PASSED.
- INVESTMENT_DOSSIER_ACCEPTED requires verified beneficial counterfactual, accepted financial rules, signed WBS and permit path, field measurement verification and owner approval. NOT PASSED.

## Severity order for next release

P0-1 dedicated native PG acceptance and ACID global benefit registry (currently only sequential in-module/legacy checks). 
P0-2 enterprise identity and external immutable evidence chain with restore and tamper exercises.
P0-3 measured owner-approved feeder study, independent solver, time-aligned reference data and fixed comparison tolerances.
P0-4 full field tariff/avoided-cost basis, registered construction quantities and actual WBS from competent engineering.
P1-1 full load profile covering all hours of a real year or explicit empirically justified selection/weighting, never naive extrapolation.
P1-2 feeder switching, transformer modeling, losses at reactive/voltage constraints, N-1 and operational reliability.
P1-3 equipment condition model built on labeled historic failure and repair events, with uncertainty and independent validation.
P1-4 hydrological forecasts with time-based hindcast, hydrodynamic routing and approved constraints for specific Kolyma reservoir operation.
P1-5 thermohydraulic calibration with meter uncertainties and pipeline heat-loss cost methodology.
P1-6 WBS -> executed contract -> invoice -> commissioning -> field measured savings; legal and environmental approval registry for Magadan.
P2-1 customer-approved company-wide rollout to other regions after positive pilot evidence; no assumed market leadership or unique technology claims.

## Leading operational KPIs for development

- Calculation availability: percent of runs with validated source metadata and bounded solver residual, not merely HTTP success.
- Scenario reproducibility: percent of hash-pinned runs with exact replay from accepted executable environment.
- Document completeness: signed input provenance + independent engineering + reviewed finance + permitted implementation.
- Financial reconciliations: zero unsupported double benefit claims and full cost/benefit year mapping.
- Security: zero demonstrated cross-tenant data leaks in native PG and genuine independent audit evidence, verified through negative tests.
- Field value: difference between expected and factually measured avoided cost after controlling for changing loads, season, asset state and pricing.

These are acceptance *metrics*, not measured performance statistics of RusHydro or Magadan Oblast.
