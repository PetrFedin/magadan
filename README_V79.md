# HYDROKONTUR 360 / MAGADAN - V7.9 evidence and benefits laboratory

**Release 2026-10-25. LAB ONLY / PRODUCTION HOLD.** This version extends the full V7.8 tree without modifying any RusHydro production system, GitHub repository or actual utility measurements.

## New working features

1. Tenant-scoped, source-version-pinned **synthetic benefit reservation registry** for electric energy, heat energy, maintenance and decision-process evidence. A duplicate source or overlapping year interval for same organization/asset/benefit family is atomically rejected by SQLite. Real corporate benefit recognition is NOT provided.
2. Synthetic post-intervention **measurement normalization research**. Chronological baseline 75/25 training/holdout, separate pre/post source availability, full time window boundary controls, load/temperature support and minimum design rank; signed differences in kWh, NEVER recognized actual savings or money.
3. HTTP routes, server-side roles, lab asset validation, original study replay for maintenance, model-hash pinning, append-only records, HMAC local audit, auditor replay.
4. Full UI section 13 with reserve / audit / M&V research actions and explicit non-field status. JS syntax and DOM ID correspondence checked; actual browser E2E and responsive visuals NOT accepted because the local Chromium is blocked by environment policy.
5. Candidate PostgreSQL17 migrations `130_benefit_ledger_v79.sql`, `140_measurement_screen_v79.sql` with RLS, exclusion and immutable audit design. These files have NOT been applied or executed on PG.

## How to run locally (isolated laboratory only)

Start from the project root using an isolated Python environment, pinned dependencies as per prior README, secret variables and a fresh SQLite lab database; never reuse production secrets or records.

```
PYTHONPATH=server python -m pytest -q server/tests_v79
PYTHONPATH=server python scripts/reproduce_v79.py
cd v6-client && npm test
```

For all prior regression groups, see `artifacts_v79/TEST_REPORT_V79.md`. For a dedicated PostgreSQL acceptance, see `docs/V79_POSTGRES_SECURITY_GATES.md`: a real PostgreSQL17 instance and scoped test credentials are prerequisites. Without them the native gate must STOP with `NATIVE_ACCEPTANCE_BLOCKED`.

### Example API routes

- `POST/GET /v79/orgs/{org_id}/benefit-reservations`, `GET /.../{id}`, `POST /.../{id}/reproduce`.
- `POST/GET /v79/orgs/{org_id}/measurement-screens`, `GET /.../{id}`, `POST /.../{id}/reproduce`.
- `GET /v79/meta/readiness` and `/v79/meta/measurement-readiness`.

For exact schemas use `docs/openapi_v79.json`.

## Evidence documents

- `docs/V79_MASTER_ARCHITECTURE.md` - architecture and domain threat model.
- `docs/V79_MATHEMATICS_FINANCE_MV.md` - formulas, temporal and uncertainty caveats.
- `docs/V79_POSTGRES_SECURITY_GATES.md` - native PG17/RLS / IdP / WORM / restore acceptance.
- `docs/V79_MAGADAN_DATA_REQUEST_AND_RACI.md` - six pilot requests, responsibility and permissions.
- `docs/V8_SIX_PRODUCTS_ENGINEERING_PLAN.md` - complete V8 technical programme roadmap.
- `artifacts_v79/showcase_trace_v79.json` - real executed HTTP trace on synthetic data; includes hashes and audit outcomes.
- `artifacts_v79/acceptance_summary.json`, `TEST_REPORT_V79.md` - executed, not-executed and blocked evidence.

## Absolute limits

- The laboratory does not include real Magadan operational telemetry, owner permission, independent engineering signoff, certified measurement and verification, approved tariffs or corporate finance.
- PostgreSQL 17 native RLS/concurrency, external Object Lock/WORM, corporate SSO/MFA and third-party pandapower/OpenDSS are NOT validated.
- Prior V7.3/V7.6/V7.8 dossiers remain outside the new benefit registry. Never add them to V7.9 reservations as a corporate savings total. Across distinct assets a shared physical metering boundary could still be counted twice until a canonical boundary graph is implemented.
- Local SQLite audit is tamper-evident under normal DB operations but not independent immutable archival storage.
- Synthetic signed post-project difference is a research statistic, NOT a saved, tariff-valued, realized or authorized economic result.
