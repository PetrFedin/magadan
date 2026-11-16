# HydroKontur 360 - V7.8: actual executable acceptance report

**Run date:** 2026-10-25. **System:** isolated laboratory only, simulated inputs. **Conclusion:** LAB PASS FOR ENUMERATED TESTS; INDUSTRIAL PRODUCTION HOLD.

## Completed tests after final code changes

| Group | Test result | Evidence log |
|---|---|---|
| Original V7.1 + V7.2 server | 83 passed, 1 native PostgreSQL skipped, 1 browser E2E deselected | `final_replay_group_a.log` |
| V7.3 + V7.4 + V7.5 + V7.6 modules | 88 passed | `final_replay_group_b.log` |
| V7.7 + V7.8 + original V7 server | 70 passed | `final_replay_group_c.log` |
| New V7.8 only | 18 passed, 1 native PostgreSQL skipped | `final_tests_v78.log` |
| Legacy JavaScript | 63 passed | `final_js.log` |
| Synthetic radial KCL/AC stress | 64 synthetic cases accepted, same solver with second numerical check | `final_stress64.log` |
| Independent arithmetic from stored annual cashflow rows | all low/base/high scenarios recomputed within RUB 0.05 | `showcase_trace_v78.json` |
| Static HTML layout | 1440/768/375 px no horizontal overflow, 140 unique IDs and no missing JS bindings | `layout_metrics.json`, screenshot PNGs |
| FastAPI OpenAPI | 70 documented operations (5 new V7.8 endpoints), syntax and compilation passed | `docs/openapi_v78.json` |
| Native PostgreSQL mandatory required run | **FAILED AS INTENDED** with `NATIVE_ACCEPTANCE_BLOCKED`, code 2, no PostgreSQL configuration | `pg_native_required.log` |
| Real third-party electrical solver | **NOT RUN**: pandapower unavailable | install/check log |

**Correct nonduplicative total:** 83 + 88 + 70 = **241 Python passes**. The isolated V7.8 18 passes are a subset of that total, not an additional 18. The 64 synthetic physics stress cases and 63 JavaScript tests are separate from Python unit count. The native test module added after baseline passes **was skipped**, so neither native skip represents RLS acceptance.

## Numerical sample and second calculation

Physical loss base 2.399290916 MWh vs alternative 1.349564646 MWh for a single 144-hour study cycle, difference 1.049726270 MWh. Synthetic WBS totals RUB 2,300,000 in 2027-2029.

Year 2030: 7,200 modeled hours; physical saved 52,486.313499 kWh, synthetic avoided cost RUB 216,251.40, OPEX delta RUB 100,000.

Year 2031: 7,200 modeled hours; savings 49,861.997824 kWh (retention 0.95), gross RUB 255,300.83, OPEX delta RUB 120,000.

All NPV are NEGATIVE at nominal 12% and the documented year-end convention: low RUB -1,753,573.76; base RUB -1,668,884.89; high RUB -1,584,196.03. No approved tariffs and no approved project; no project rate of return is claimed.

RUB cashflows recalculated independently from year rows using high precision Decimal, maximum absolute pre-rounding discrepancy against serialized NPV of less than RUB 0.005. This verifies arithmetic, not underlying prices, engineering assumptions or actual savings.

Physical stress with deterministic seed 20261023, 64 cases: maximum active power-balance residual 9.210714051732794e-11 MW; maximum reactive residual 1.3733757464251538e-10 MVAr; maximum second-method voltage difference 3.277416044233312e-09 V. This is numerical consistency in a limited balanced radial model and NOT independent external solver acceptance.

## What release does NOT prove

- Physical model correctness on real Magadan Oblast electricity networks, hydrological basins or heat networks.
- External pandapower/OpenDSS/RastrWin calculation on the same case.
- Operational reliability, dispatch permissions, grid protection, N-1 safety, construction permits, actual supplier prices, northern logistics or lawful tariff accounting.
- PostgreSQL native RLS enforcement or cross-module atomic anti-double-counting under concurrent writes.
- Corporate OIDC/MFA, external WORM-backed independent audit, backup/restore in authorized customer infrastructure.
- Real asset-owner agreements, licensed/authorized data, independent qualified engineer, financing, grants or post-construction benefits.
- Authenticated browser E2E through a real running server; only static Chromium responsive layout was inspected.

Every unresolved P0 item keeps `production_ready = false` and `industrial_approval_eligible = false`.

## Delivery integrity checks

Code syntax compiled, UI JS syntax checked, historical migration files remain frozen against generator overwrites, new migration 120 only inspected statically. ZIP file integrity and per-file SHA256 manifest will be verified in the delivery procedure. All instructions for native acceptance are test-only and must not touch live customer assets.
