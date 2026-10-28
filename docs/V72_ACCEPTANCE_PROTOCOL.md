# V7.2 Acceptance and QA record

The release is a **synthetic laboratory**, not a field-deployed Magadan product. The full set of native PostgreSQL checks is REQUIRED for a database security green status, but has not run in the current runtime. The OIDC integration uses a simulated issuer, and the audit receiver does not establish actual corporate WORM compliance.

## Reproducible commands

From project root with installed server requirements:

```
PYTHONPATH=server pytest -q server/tests server/tests_v71 server/tests_v72 \
  --ignore=server/tests/test_browser.py \
  --ignore=server/tests_v71/test_postgres_native.py
cd v6-client && node --test tests/domain.test.mjs tests/assurance.test.mjs
```

Native acceptance in a separate empty database (requires PostgreSQL 17, psycopg, explicit administrator-approved test database) must include `060_studies_v72.sql` after V7.1 migrations, the tests in `test_postgres_native.py`, data ownership checks and hard-failure on a missing database. Never run native acceptance against operational or pre-existing database.

## Security negative tests

- Cross-tenant study creation returns not found, and read by a different tenant returns not found.
- Viewer cannot create studies; only economist can create HydroCAPEX studies.
- Real-looking source references are rejected from the synthetic endpoint.
- Synthetic study IDs cannot be used to create investment initiatives.
- Append-only SQLite lab storage rejects normal UPDATE of a study.
- PostgreSQL intended checks include deny-without-context, signed session context, transaction rebinding and direct SQL tamper resistance, not yet executed.

## Scientific negative tests

- Future availability timestamps cannot leak into forecast training.
- Naive timestamps, duplicate observations and invalid intervals reject.
- Mass/energy balance constraints flag infeasible cascade scenarios.
- Turbine load comparability is required; constant baseline cannot yield a meaningful risk score.
- Thermal calculations preserve units and assumptions.
- Repeated benefit IDs, cyclic project dependencies and insufficient budgets reject or return infeasible portfolio.
- Nonfinite and oversized inputs fail validation, rather than returning misleading zeros.
- Results can be re-run only with the pinned engine source and identical case.

## Field evidence blockers

- No actual Magadan feeder measurements, topology or site-approved data rights.
- No independent professional electrical engineering signoff or third-party solver benchmark.
- No corporate SSO/MFA acceptance or RLS execution on real PostgreSQL.
- No externally locked, third-party verified retention.
- No browser network E2E due administrator blocking localhost access in this environment.
- No action permitted on SCADA, power dispatch or process control systems.

## Authorization and regulatory conditions

Require documented identity and membership, least privilege, independent review and concrete decision power in the operator's existing regulatory and procurement framework. Source: PostgreSQL RLS 17 and OWASP Authorization guidance. Any final field claim requires evidence beyond synthetic input hashes and scripted assertions.
