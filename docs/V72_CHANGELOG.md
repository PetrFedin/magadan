# V7.2 change log (relative to V7.1)

- Added six strict exploratory synthetic engines (`studies.py`): retrospective forecast scoring, two-stage reservoir balance, operating-point MAD deviation, existing independent-check AC grid solver, simplified heat transfer, bounded Decimal CAPEX portfolio optimizer.
- Added new tenant-scoped `v72` study routes for create/list/read/reproduce/compare and public Pydantic JSON schema introspection.
- Added immutable `study_runs` SQLAlchemy table, SQLite append-only triggers, and a separate native PostgreSQL migration 060 specifying force RLS, cross-tenant FK constraints and transactional audit hooks (UNAPPLIED).
- Added a new six-product research workspace to the existing server-served UI; existing V7 reviewed grid-to-investment workflow not weakened.
- Added 26 V7.2 scientific and HTTP tests and 2 SQL migration structure tests; current full non-browser test suite 119 Python tests and 63 legacy Node tests PASS.
- Added a denial test that prevents a study ID from being used as a certified `calculation_run` in a V7 investment initiative.
- Added non-finite JSON rejection, monetary magnitude guard, future-data leakage guard, model provenance checks and explicit comparison caveats.
- Added Magadan-first pilot and engineering/finance/regulatory dossiers, structured feature register, OpenAPI snapshot, input examples, versioned QA evidence and go/no-go script.
- Corrected native acceptance GitHub workflow to use a new V7.2-prefixed dedicated database and include synthetic regression steps; workflow is prepared locally and NOT uploaded or run.
- Live browser HTTP E2E blocked by Chromium administrator policy; separate static visual QA passed at 1440/768/375 px. No production data, deployment or independent industrial model verification.
