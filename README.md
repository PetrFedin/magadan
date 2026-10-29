> **Актуальная разработка: [V7.6](README_V76.md). Статус LAB PASS / PRODUCTION HOLD; настоящих данных объектов Магаданской области, PostgreSQL RLS-приёмки или промышленного допуска нет.**

# HydroKontur 360 - Magadan: V7.2 laboratory release

**Release date:** 2026-10-23. **Industrial status: HOLD.**

This package continues the V7.1 server. Six product lanes now share a synthetic-only authenticated case execution, immutable source/result hashing, engine-source pinning and retrievable scenario comparisons. V7.1's independently reviewed grid calculation and staged investment approval remain separate; *a V7.2 study cannot be promoted as production investment evidence*.

## Delivered

- `server/hydro_api/studies.py`: six strict domain-scoped synthetic engines.
- `server/hydro_api/studies_api.py`: tenant/role-aware API and reproducibility routes.
- `server/hydro_api/storage.py`: append-only `study_runs` table for the SQLite laboratory.
- `server/migrations/060_studies_v72.sql`: pending native PostgreSQL study schema, FORCE RLS, composite-tenant FK, append-only and automated audit.
- `server/ui/`: server-served workbench with six-domain research panel and examples.
- `server/tests_v72/`: domain, HTTP security, audit, reproduction and schema contract tests.
- `docs/`: architecture, Magadan site pilot data requirements, capital economics, WBS/regulatory scope, release roadmap and OpenAPI.
- `artifacts_v72/`: exact test logs, failure evidence, independent static UI screenshots and acceptance report.

## Tested facts in this artifact

See `artifacts_v72/acceptance_summary.json` and the raw tests. Only synthetic data has been processed. The server tests are HTTP requests through FastAPI TestClient; they do **not** establish production network interoperability. The React/JS V6 tests belong to its prior standalone laboratory.

Real Chromium localhost E2E is **BLOCKED_BY_ADMINISTRATOR** in this environment; separate inline static layout QA passed at 1440, 768 and 375 px. Neither screenshot nor static JS syntax check is an authenticated HTTP E2E pass.

Native PostgreSQL 17 RLS execution is **NOT DONE**. With native acceptance required, the suite failed closed because a dedicated PostgreSQL configuration does not exist. PostgreSQL migration 060 and native tests are delivered but not validated on a database.

## Run the synthetic lab locally

1. Create a Python environment and install `server/requirements.txt` and, when using V7.1 OIDC/Postgres features, its additional requirements. Use approved package sources.
2. Export two different random secrets (>= 32 characters each): `HYDRO_JWT_SECRET`, `HYDRO_AUDIT_SECRET`.
3. Set `HYDRO_PROFILE=legacy_lab` and an isolated local SQLite `HYDRO_DATABASE_URL`. Never point the demo seeder to customer or historical production databases.
4. Set `HYDRO_ALLOW_DEMO_SEED=YES`; run `PYTHONPATH=server python -m hydro_api.seed_lab` on an EMPTY demo database. Credentials are randomly created and shown once.
5. Start `PYTHONPATH=server uvicorn hydro_api.asgi:app --host 127.0.0.1 --port 8000` and open `/lab`.
6. The new section 06 provides six modules. Examples are explicitly marked synthetic and cannot be submitted as genuine field data.

The laboratory uses local password login only for controlled testing. Corporate IdP must use the separate `postgres_lab` configuration, approved certificates and real MFA policy after acceptance. Do not expose the legacy laboratory to a public network.

## Verification commands

```
PYTHONPATH=server pytest -q server/tests server/tests_v71 server/tests_v72 \
 --ignore=server/tests/test_browser.py \
 --ignore=server/tests_v71/test_postgres_native.py
cd v6-client && node --test tests/domain.test.mjs tests/assurance.test.mjs
```

PostgreSQL acceptance must be run only in a fresh isolated database with the explicit `HYDRO_NATIVE_TESTS_REQUIRED=1` contract; see `docs/V72_RELEASE_ROADMAP.md`. An unsupported or unreachable database is a blocker, not a successful SQL check.

## Module ownership and extension

| Lane | Server-authored synthetic study | Pending verified industrial model |
| --- | --- | --- |
| HydroForecast | Historical forecast scoring | Basin hydrological forecast and real calibration |
| CascadeEconomics | Two-reservoir time-step balance | Real operating rules, water routing and constraints |
| TurbineReliability | Robust vibration anomaly | Validated condition monitoring and repair economics |
| GridLoss Planner | Two-bus AC benchmark | Real multi-bus Magadan feeder reference validation |
| HeatNet Economics | Lumped thermal balance | Calibrated thermohydraulic network model |
| HydroCAPEX | Small constrained investment portfolio | ERP, contract/budget/BOQ and post-investment audit |

## Release exclusions and provenance

No GitHub repo, corporate database, public deployment, actual RusHydro project, grid equipment or SCADA systems were changed. No third-party engineering acceptance, real asset consent, real-world savings or grant award is implied by laboratory test success.

Detailed source log: `docs/V72_MASTER_SYSTEM_DESIGN.md`, `docs/V72_MAGADAN_PILOT_CARDS.md`, `docs/V72_FINANCE_AND_CONSTRUCTION.md`, `docs/V72_ACCEPTANCE_PROTOCOL.md`, `docs/V72_RELEASE_ROADMAP.md`.
