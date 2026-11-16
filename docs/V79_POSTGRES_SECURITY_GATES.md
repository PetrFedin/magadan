# V7.9 - native PostgreSQL 17, identity, WORM and event protection acceptance

**STATUS: NOT ACCEPTED.** This is an execution checklist, not proof that migrations were applied.

## 1. Dedicated temporary environment

Use a newly provisioned PostgreSQL 17 installation on an isolated non-production host. Do NOT connect tests to any RusHydro or Magadan operating system. A project DBA must provide dedicated credentials for the one-time migration setup and two separately constrained runtime roles (`hk_app`, `hk_authenticator`, and an audit exporter).

Before schema work: verify `SELECT version();`, expected database, blank public schema, installed extension permission and no production connections. Refuse nonempty DB or unknown role mappings.

Apply migrations in monotonic order: `001,010,020,030,040,050,060,070,080,090,100,110,120,130,140`. Snapshot schema and migration hashes; never edit historical migrations to fix later changes; introduce 150+ for repairs.

## 2. Privilege and native Row-Level Security tests

Test using constrained runtime credentials, not the owner or DBA user:

- Without valid server-created transaction context: SELECT returns no tenant rows; INSERT rejected.
- Context with fabricated tenant ID/session, copied across pooled connections or expired/revoked user: rejected.
- Incorrect organization cross JOIN in a nested research/finance subquery: rejected.
- `hk_app` cannot update/delete/truncate immutable research, benefit or M&V tables, disable triggers, change policies, set owner role or bypass RLS.
- Concurrent collision: two transactions registering same `org_id / asset_id / family / overlapping year range` yield exactly one COMMIT and one exclusion violation; no double effect.
- Nonoverlapping years and independent physical boundaries are handled only as specifically authorized; overlapping physical boundaries under different asset IDs remain a separate consolidation risk.
- Direct SQL INSERT with fabricated `source_id`, altered source SHA, nonLAB asset or unsupported source type is rejected by native triggers.
- Verify grants and `SECURITY DEFINER` search paths; no untrusted caller can invoke privileged functions directly to circumvent policy.
- Verify PostgreSQL exception reporting and connection state after rollback; no stale RLS session context may leak via pool reuse.

### Native prerequisites

```
HYDRO_NATIVE_TESTS_REQUIRED=1 PYTHONPATH=server python -m pytest -q server/tests_v71/test_postgres_native.py
```

The exact test requires a separate configured PG instance, bootstrap account and role permissions. Running this with no PG MUST fail with `NATIVE_ACCEPTANCE_BLOCKED`; never report its tests as PASS.

## 3. Legacy benefit migration - blocker to official aggregation

`GRID_ANNUAL_V78`, `MAINTENANCE_HANDOFF_V75`, `PROGRAMME_V74` and `ASSURANCE_V76` remain source databases; earlier economic dossiers may also exist without a V7.9 reservation.

- Dry run a migration in a separate DB. Classify every historical report by asset, physical boundary, effect family, reporting period, source hash and source data lineage.
- Quarantine conflicting records, duplicates, canceled proposals, rolled-up parent/child effects, unmetered estimates and cross-company pass-throughs.
- Resolve physical boundary allocation as a human-approved policy; default to conservative rejection, not guessed allocation.
- Only after a verified backfill set all source-creation endpoints to mandatory reservation, and all dashboards to read the exclusive registry.
- Withhold all official organization-wide savings totals until reconciliation is independently reviewed and signed.

## 4. Corporate identity and audit

- Register a real OIDC client with company-approved provider and TLS, validate issuer/audience/nonce/state/PKCE; do not trust email domain for role authorization. Test MFA policy, removal from enterprise directory, access revocation during an in-flight operation, session expiry and CSRF.
- Configure an external append-only / retention-enforced store operated independently from the business application; verify specific object version, signed receipt, key provenance and retention policy. Test duplicate delivery, lost response, exporter retry, DB rollback, clock skew, key rotation, restoration and permanent retention controls.
- Record audit evidence in the same DB transaction as the business action. Only declare it externally sealed upon cryptographically checked, issuer-scoped receipt.
- Verify PITR and restore of DB with RLS policies, users, receipts, event sequence and key dependencies. Recovery pass must reexecute a preserved financial/engineering calculation and verify its hashes.

## 5. Current negative result

The development container does not provide PostgreSQL executable/utility or a dedicated PG17 server. The mandatory acceptance attempt failed at collection with `NATIVE_ACCEPTANCE_BLOCKED` and is recorded in `artifacts_v79/postgres_native_attempt.txt`. SQL migration candidates 130/140 were only text/contract checked. This does not satisfy any industrial security gate.

Official references: https://www.postgresql.org/docs/17/ddl-rowsecurity.html and https://www.postgresql.org/docs/17/ddl-constraints.html.
