# HYDROKONTUR 360 / MAGADAN — V8.0

## Release scope

This build extends V7.9 with **canonical physical boundary identity** for laboratory benefit reservations and a **non-certified M&V quality diagnostic**. Source code does not connect to RusHydro production systems. No actual energy savings, grant award or field-ready engineering status is claimed.

### Working improvements
- `meter_boundaries_v8`, `boundary_assets_v8`, `boundary_conflicts_v8`: append-only scopes and alias mapping, identical/contained/explicitly overlapping boundaries; graph frozen after first benefit reservation.
- Existing V7.9 benefit SQL trigger upgraded: duplicate physical effect blocked even when `asset_id` differs; cross-family electricity/risk overlap groups and boundary quantity mismatch; if a graph exists, unmapped assets cannot reserve an effect.
- New API: `/v8/meta/boundary-readiness`, `/v8/orgs/{org_id}/meter-boundaries`, `/boundary-asset-assignments`, `/boundary-overlaps`, `/boundary-audit`.
- New M&V quality diagnostic: joint load-temperature support, chronological holdout error, residual bias/lag correlation, descriptive error envelope. **Not** a confidence interval, causality conclusion, or certified field savings.
- UI section 14 uses the real API; both section 13 and 14 now sit inside the authentication-protected `#lab` container (previous V7.9 structural weakness corrected).
- PostgreSQL 17 SQL candidate `150_boundary_graph_v8.sql` with default-deny graph authoring, RLS and per-tenant/family transaction lock on benefit insertion. SQL not applied; native status BLOCKED.

## Local laboratory commands

```sh
PYTHONPATH=server pytest -q server/tests_v8
PYTHONPATH=server python scripts/reproduce_v8.py
node --check server/ui/ui.js
cd v6-client && npm test
```

Full regression evidence is in `artifacts_v8/`. Python and JS testing excludes unperformed native PostgreSQL and real-browser E2E. This release includes candidate SQL but does **not** automatically provision any database, deploy an application or make external changes.

## Technical documentation
- `docs/V8_MASTER_ARCHITECTURE_RU.md`
- `docs/V8_MAGADAN_PILOT_AND_INVESTMENT_RU.md`
- `docs/V8_SECURITY_NATIVE_GATES_RU.md`
- `docs/V8_EXECUTION_ROADMAP_RU.md`

## Production HOLD
- Actual Postgres17 RLS execution, conflict/locks under PG and restoration test unavailable.
- Actual corporate SSO/MFA, independent archive, reference pandapower/OpenDSS and field permits unavailable.
- Cross-organisation physical benefit reconciliation and legacy dossier backfill not implemented.
- Meter boundary graph is immutable and conservative; future production requires time-versioned asset graphs and a controlled amendment process.
- M&V input is synthetic. No baseline meters, independent engineer, causality review, regulated cost valuation or physical object has been verified.
