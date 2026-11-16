# HYDROKONTUR 360 V7.9 - actually executed test report

**Status:** LAB PASS for the targeted Python, inherited JavaScript and synthetic HTTP chain; native PostgreSQL, external solver, corporate IdP/WORM, actual Magadan data and browser E2E are UNACCEPTED.

## 1. Test groups executed

| Group | Test command | Result | Evidence |
| --- | --- | --- | --- |
| V7.1-7.4 API/domain | `PYTHONPATH=server python -m pytest -q server/tests_v71 server/tests_v72 server/tests_v73 server/tests_v74 --ignore=server/tests_v71/test_postgres_native.py` | 132 pass | `pytest_group_a.txt` |
| V7.5-7.6 API/domain | `PYTHONPATH=server python -m pytest -q server/tests_v75 server/tests_v76` | 40 pass | `pytest_group_b.txt` |
| V7.7-7.9 API/domain including temporal edge cases | `PYTHONPATH=server python -m pytest -q server/tests_v77 server/tests_v78 server/tests_v79 --ignore=server/tests_v78/test_postgres_native_v78.py` | 58 pass | `pytest_group_c_final.txt` |
| Legacy server | `PYTHONPATH=server python -m pytest -q server/tests --ignore=server/tests/test_browser.py` | 35 pass | `pytest_legacy.txt` |
| Inherited JavaScript | `npm test` in `v6-client` | 63 pass | `node_legacy.txt` |
| New temporal edge tests (after original groups) | `PYTHONPATH=server python -m pytest -q server/tests_v79/test_measurement.py` | 12 pass, including 3 new | `pytest_v79_temporal_final.txt` |
| Synthetic end-to-end API chain | `PYTHONPATH=server python scripts/reproduce_v79.py` | passed | `showcase_cli.txt` and `showcase_trace_v79.json` |
| Native PG17 mandatory suite | `HYDRO_NATIVE_TESTS_REQUIRED=1 ...test_postgres_native.py` | **BLOCKED / error at collection**, no test executed | `postgres_native_attempt.txt` |
| Live browser E2E and visual 375/768/1440 | Chromium refused navigation even to static file | **NOT ACCEPTED** | `browser_visual_attempt.txt` |

Aggregate successful Python test count: **132 + 40 + 58 + 35 = 265**. The additional targeted 12-test run overlaps the 58-test group and is NOT counted again. **This is an aggregation of separately completed groups**, not a claim that one full test invocation ran to completion. The blocked PG suite is EXCLUDED from pass counts.

## 2. Specific negative cases successfully checked

- JWT role/tenant and asset boundary; unauthorized actor -> forbidden/not found.
- Concurrent claim collision: two requests on same tenant/asset/family/year -> only one creates, other conflict 409.
- Duplicate benefit source with different description -> conflict.
- Wrong source kind/family, missing source or changed original calculation -> rejected.
- Maintenance source: original turbine input and engine re-executed before accepting registration.
- Lab study cannot become a field-realized benefit via mutable state.
- Measurement: missing timezone, duplicate/overlapping periods, future baseline leakage, unidentifiable polynomial design, post extrapolation, Boolean input, post observation outside the report boundary, baseline window crossing commissioning, observation available before interval end.
- Auditor replay of stored M&V math, source/engine hash mismatch, append-only update/delete rejection, HMAC local audit verification.

## 3. Synthetic end-to-end result

- One turbine study and maintenance numerical handoff were created using HTTP API in a temporary SQLite database with separate engineer/economist/auditor users.
- A MAINTENANCE_COST *reservation* was inserted (zero booked saving).
- Same claim retried -> HTTP 409.
- 48 synthetic pre readings, 12 synthetic post readings -> signed normalized difference in the run trace (~13.191738 kWh), for sampled windows only. NO annualization and NO actual savings recognition.
- Independent audit user re-ran original computation, checked stored hashes; local HMAC audit chain verified.
- `actual_savings_confirmed=false`, `postgresql_native_rls_passed=false`, `external_worm_attestation=false`, `industrial_approval_eligible=false`.

## 4. Unclosed risks

1. PostgreSQL 17 migrations 001-140 and RLS not executed; no production authorization.
2. Earlier economic reports not automatically registered in global ledger, so cross-version aggregate reporting prohibited.
3. Different asset IDs can refer to same physical metering boundary without currently being caught. Need canonical asset/boundary graph and consolidated ownership.
4. A scenario replay and statistical M&V are not independent calibrated engineering evidence.
5. Corporate IdP/MFA, external retention-enforced archive and real field data absent.
6. Actual live browser/interactive E2E not accepted even though JS syntax and static binding audit passed.
7. Reference third-party electrical solver execution and qualified independent expert assessment not done.

## 5. External methodological anchors

PostgreSQL RLS: https://www.postgresql.org/docs/17/ddl-rowsecurity.html

Measurement and Verification: https://evo-world.org/en/products-services-mainmenu-en/protocols/ipmvp
