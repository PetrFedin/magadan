# V7.1 controlled laboratory runbook

NOT EXECUTED HERE: native PostgreSQL setup below. Do not use production credentials or a corporate database. The checked-in GitHub workflow is a draft local file, not a published or executed workflow.

## A. Inspect and test existing code

Use a new virtual environment, then `pip install -r server/requirements-v71.txt`. For UI browser testing Playwright and an authorized Chromium runtime are additional requirements. In this build environment they could not navigate to the app because of an administrative restriction.

```
PYTHONPATH=server pytest -q server/tests/test_server.py server/tests/test_reproduction.py
PYTHONPATH=server pytest -q server/tests_v71 --ignore=server/tests_v71/test_postgres_native.py
(cd v6-client && node --test tests/*.test.mjs)
```

If a runner imposes short command timeouts, run the documented modules in separate processes and preserve each JUnit/exit status. Do not count an incomplete or killed process as a completed passing suite. Final evidence here is the partitioned local_server_a/b and local_components reports, not superseded broad-run logs.

## B. Create a dedicated native PostgreSQL 17 acceptance database

Use an operator-approved EMPTY test database whose name starts with hydrokontur_v71_. No script creates/drops a corporate database. Obtain the actual server and Python psycopg through your approved package process. Put test secrets outside the repository.

```
export HYDRO_PG_ADMIN_URL='postgresql://TEST_BOOTSTRAP:SECRET@127.0.0.1:5432/hydrokontur_v71_acceptance'
python scripts/bootstrap_native.py --out /tmp/hydro-native-credentials.json
export HYDRO_NATIVE_CONFIG=/tmp/hydro-native-credentials.json
export HYDRO_NATIVE_TESTS_REQUIRED=1
PYTHONPATH=server pytest -q server/tests_v71/test_postgres_native.py --junitxml=/tmp/native-junit.xml
```

Bootstrap refuses a nonempty database and refuses overwriting the output credential file. It applies 001,010,020,030,040,050, creates narrow runtime roles and writes random test passwords with mode 0600. Owner/security-key material is never printed. Roles exist cluster-wide: use a fresh dedicated cluster or have the operator review conflicts; do not force-drop existing roles. No native syntax or runtime success is claimed until the command above finishes with a complete test report.

The native suite contains a deliberate LAB_FILE exception test to exercise the workflow with real PostgreSQL transactions. It temporarily sets require_compliance=false only in the disposable acceptance database and restores it in finally. This does NOT certify WORM. Do not run that suite against a production database, and do not parallelize it with pytest-xdist.

Do not migrate V7 SQLite by copying a file into PostgreSQL. Inventory counts and hashes, preserve the original export and chain as historical evidence, map types, load into staging, validate composite links, then create an explicitly documented import event. Rehashing old events and presenting them as the original chain is forbidden. This release contains fresh-database migrations, NOT a production data-conversion tool.

## C. Register identity with the actual corporate owner

The owner must supply approved issuer/discovery origin, registered client ID and credentials if required, exact HTTPS callback, CA trust and corporate assurance values. Provision (issuer,sub)->user and reviewed memberships through an administrative process; no email-based self-signup exists. This process and real corporate MFA have not been performed.

Copy .env.example into a secret-managed environment outside git. Fill actual app/auth DSNs from separate credentials. JWT/AUDIT legacy keys must remain distinct random values even though OIDC is used; do not reuse IdP, audit receiver or database receipt keys.

```
export HYDRO_PROFILE=postgres_lab
PYTHONPATH=server uvicorn hydro_api.asgi:app --host 127.0.0.1 --port 8081 --no-access-log
```

Terminate HTTPS at an approved proxy. Configure precise origin, trusted forwarding rules, body limits, rate limits, CA trust and logging that does not record tokens/codes/verifiers. The production profile intentionally refuses startup pending external acceptance. Global IdP logout, SCIM/JIT provisioning, back-channel logout and a separate auth service are NOT implemented.

## D. Configure independent audit

Generate an Ed25519 keypair in the receiver's secret store. Pin its public key in the exporter. Provision the database receipt MAC key only to the receiver and protected DB function, never to the exporter. The transport bearer secret is a THIRD distinct credential. Key rotation/rollover acceptance is pending.

Local development, different process/directory (not WORM):

```
python scripts/run_audit.py receiver --mode lab --host 127.0.0.1 --port 8091
python scripts/run_audit.py export-once --mode lab
```

The exporter reads HYDRO_EXPORT_DATABASE_URL; the receiver needs HYDRO_AUDIT_SIGNING_KEY_FILE and HYDRO_AUDIT_DATABASE_MAC_FILE; both read HYDRO_AUDIT_TRANSPORT_SECRET_FILE. The exporter receives only HYDRO_AUDIT_PUBLIC_KEY_FILE. All paths are mounted secret files. No real keys are in this archive.

For an owner-approved, tested object store, select `--mode compliance` with an explicit HTTPS endpoint, preconfigured versioned Object Lock bucket and minimum-permission provider credentials. Receiver HTTP must be behind approved TLS/transport protection. Do not create storage, choose retention or incur cloud spend automatically.

Acceptance must attempt overwrite, version-specific delete, retention shortening and downgrade under writer and administrator roles, verify a pinned version after retries/restart, and test receiver failure and backlog. Verify actual native DB rejection of an unauthenticated receipt. S3 SDK mocks are not substitutes for these storage experiments. No WORM service was accessed here.

## E. Backup, rollback and incident response (pending drills)

Before a real pilot, perform backup plus restore to a second empty isolated database, compare row counts/hashes, audit heads, receipts, memberships and RLS catalogs, and re-run cross-tenant/reproduction tests. Exercise point-in-time recovery without deleting externally sealed evidence. No successful restore/RPO/RTO is claimed in this build.

On invalid receipt or chain mismatch: freeze protected approvals, retain the pending event and prior snapshots, notify the designated security/records owner, investigate before replay. Never edit old evidence or delete a failing event to clear the gate. Revocation of API/auth/export credentials is separate from IdP/key revocation. Real incident owners and escalation channels are not yet appointed.

## F. Mandatory external gates

Native SQL tests completed; identity owner signs actual SSO/MFA acceptance; records/security owner signs storage retention acceptance; independent engineer signs method/benchmark acceptance; data owner authorizes the actual Magadan study dataset. Until all relevant gates are met, this is a laboratory development package.
