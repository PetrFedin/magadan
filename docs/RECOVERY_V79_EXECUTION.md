# V7.9 source recovery execution

**Current status: SOURCE_IMPORT_BLOCKED / PRODUCTION_HOLD.** The original V7.9 ZIP and bundle are visible in the project Library but raw-byte materialization returned an access-path error; connected Google Drive search was empty and the authorized desktop is offline. They have **not** been unpacked or published.

## Prepared and tested

- `tools/import_v79_snapshot.py` is published on this recovery branch and read back from GitHub.
- 10 offline fixture tests ran successfully in the current execution environment, including ZIP path traversal, symlink, .env, high-confidence secrets, file presence, migration numbering, case collisions, and Git bundle import.
- These tests **do not validate the actual archive**, do not certify the full source, and are not GitHub Actions CI.

## Recovery steps (on an authorized machine)

1. Obtain the actual `HydroKontur_Magadan_V7_9_GitHub_Ready.zip` or `HydroKontur_Magadan_V7_9_Local_Git_Baseline.bundle` from the project's Library or offline backup.
2. Use a clean, private, isolated machine with Python 3.13 and Git. Do not run arbitrary scripts inside the archive before checking its contents.
3. Run: `python tools/import_v79_snapshot.py /absolute/source/V79.zip --destination /absolute/staging/v79` (destination must not exist; its parent must exist).
4. Review `SOURCE_RECOVERY_MANIFEST.json` and scan every source file with a dedicated secret scanner, license review and security tooling. The script's regexes are only a first line of defense.
5. Confirm every required source is present and consistent. Compare against earlier release inventory and never overwrite historical SQL migrations.
6. Run the source's Python/JS test suites and full authorized browser E2E. Native PostgreSQL 17 RLS and external-grid model checks require independently provisioned evidence.
7. Publish to a new integration branch, open a Draft PR, and inspect actual GitHub Actions results on one SHA. Require independent review before merging.

## Non-negotiable gap

The tools directory is **NOT the HydroKontur application**. Missing `server/hydro_api/main.py` and the rest of the original source tree still block completion of Issue #1. No production infrastructure was touched.
