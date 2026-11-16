# HydroKontur 360 - Magadan - V7.8 engineering and financial laboratory

**Release classification: LABORATORY / SYNTHETIC INPUTS ONLY; PRODUCTION HOLD.** This is a continuation of the verified V7.7 source tree, not a RusHydro release, grant approval, Magadan infrastructure survey, or field acceptance.

## What V7.8 adds

1. Window- and year-specific physical loss reduction -> synthetic valued energy -> commissioning-gated annual cashflows -> 3 NPVs.
2. Detailed feeder baseline/alternative checks and independent in-code numerical KCL verification retained from V7.3.
3. WBS as the **single** capex source with budget and predecessor checks; no second manual capex number; first benefit after commissioning.
4. Partial annual profiles preserved as partial, no unobserved hours monetized. Actual tariffs and customer financial data are not invented.
5. Immutable SQLite lab dossier with tenant-scoped server endpoints, replay of source models, checksums and a no-industrial-approval state.
6. PostgreSQL 17 candidate migration `120_grid_annual_dcf_v78.sql` (NOT EXECUTED); `FORCE RLS`, composite foreign keys, audit trigger, append-only protection.
7. Frozen historical migration builder: refuses mutation of migrations 001/020; preview is allowed in a separate folder.
8. Twelfth web UI section for selecting and replaying annual grid financial screening; static QA at desktop/tablet/mobile widths.
9. 5 new HTTP endpoints, OpenAPI with **70 operations**, and test-backed reproducible synthetic example with NEGATIVE NPV.

## Suggested local installation and lab tests

From repository root with dependencies installed in an ISOLATED local environment:

```
python -m pip install -r server/requirements.txt
PYTHONPATH=server python -m pytest -q server/tests_v78 server/tests_v77
PYTHONPATH=server python -m pytest -q server/tests_v71 server/tests_v72 --ignore=server/tests_v71/test_postgres_native.py
PYTHONPATH=server python -m pytest -q server/tests_v73 server/tests_v74 server/tests_v75 server/tests_v76
PYTHONPATH=server python -m pytest -q server/tests --ignore=server/tests/test_browser.py
cd v6-client && npm test
```

The full Python suite includes Argon2 workload and can be slow in constrained environments; log **each completed group** independently. A merely timed-out aggregate is NOT a PASS.

### Reproducible synthetic accounting example

```
PYTHONPATH=server python scripts/reproduce_case_v78.py
```

Outputs: `artifacts_v78/showcase_trace_v78.json`, `artifacts_v78/CALCULATION_WALKTHROUGH_V78_RU.md`. It recomputes annual discounted net cashflows independently from the serialized individual rows and fails when discrepancies exceed five kopecks.

### Deliberately failing mandatory native security gate

```
HYDRO_NATIVE_TESTS_REQUIRED=1 PYTHONPATH=server \
  python -m pytest -q server/tests_v71/test_postgres_native.py
```

Without a **dedicated PostgreSQL 17 acceptance database and credentials**, this must exit with `NATIVE_ACCEPTANCE_BLOCKED`. SQLite or static SQL search does not satisfy this test. The `scripts/bootstrap_native.py` fixture refuses nonempty databases. Do not direct native scripts at production.

## API

```
GET  /v78/meta/readiness
POST /v78/orgs/{org_id}/grid-annual-dossiers
GET  /v78/orgs/{org_id}/grid-annual-dossiers
GET  /v78/orgs/{org_id}/grid-annual-dossiers/{item_id}
POST /v78/orgs/{org_id}/grid-annual-dossiers/{item_id}/reproduce
```

Economist creates; auditor reproduces; the read path is tenant scoped and recomputes. A lab financing report cannot be used as a V7 approved industrial initiative.

## Key evidence

- `docs/V78_MATHEMATICS_ENGINE_AND_FINANCE.md` - full equations, numerical limits, finance and six-product model matrix.
- `docs/V78_MAGADAN_FIELD_PILOT_AND_APPROVAL.md` - six prospective pilot data requests and G0-G8 acceptance.
- `docs/V78_SECURITY_NATIVE_GATE.md` - mandatory PostgreSQL/SSO/WORM and double-counting closure.
- `docs/V78_REQUIREMENTS_AND_EVIDENCE.csv` - 33 traceable requirements with true status.
- `docs/openapi_v78.json` - generated from FastAPI (70 operations).
- `artifacts_v78/TEST_REPORT_V78.md` - pass/fail and open native gates.
- `artifacts_v78/showcase_trace_v78.json` - actual synthetic source and calculation evidence.
- `artifacts_v78/v78-grid-economics-{1440,768,375}.png` - static screenshots, not live authenticated browser E2E.

## Known P0 issues that must remain open

- PostgreSQL 17 native RLS, concurrent write tests, backup/recovery, authoritative cross-table benefit lock.
- Corporate SSO/MFA, independent WORM and external signed audit receipt acceptance.
- Actual independent third-party power-flow solver (pandapower/OpenDSS/RastrWin3) comparison.
- Asset owner permissions, Magadan actual feeder telemetry, engineering drawings, signed expert report.
- Legal/regulatory tariff valuation, tax/VAT, procurement, field engineering, commissioning and post-project M&V.

All reports must continue to state `industrial_approval_eligible: false`. No SCADA, equipment control or construction authorization is provided.
