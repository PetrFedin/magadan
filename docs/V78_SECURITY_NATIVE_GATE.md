# V7.8 Security / PostgreSQL 17 native acceptance - mandatory HOLD

## Actual current status

- Prepared SQL migrations `001` through `120`; the new V7.8 migration has ONLY been inspected statically.
- Native PostgreSQL binaries, the psycopg driver and a dedicated acceptance database are NOT available in the current development runtime.
- Enterprise identity provider, independent compliant external WORM archival storage and owner-permitted field data are absent.
- Therefore PostgreSQL RLS, event concurrency/atomicity, recovery, real external audit, and actual external independent power-flow solver must NOT be marked PASS.

## Controlled deployment requirements

1. Use an isolated PostgreSQL 17 acceptance database on an approved host, separate secrets; no production, SCADA or RusHydro endpoint access.
2. Verify each historical SQL migration SHA-256, apply in sequence 001,010,020,030,040,050,060,070,080,090,100,110,120. Historical versions are frozen; schema builder must refuse overwrites.
3. The app role must not own schema, must have no BYPASSRLS, and must have SELECT/INSERT only on approved tables. Use `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`; explicitly verify pg_catalog and grants.
4. Test no-token/no-context SELECT/INSERT, org A vs org B, forged organization ID and forged GUC, expired sessions, revoked membership, pool connection reuse after rollback, and competing requests on the same benefit key.
5. Ensure `grid_annual_dossiers_v78` is append-only; attempt UPDATE/DELETE, TRUNCATE, direct superuser access path review, and invalid foreign-key combinations; verify audit insert trigger and hash chain.
6. Repeat 2 concurrent writers with identical programme-WBS and with different benefit keys, and 2 concurrent legacy/new-module claims on same physical benefit. The cross-table inter-module check is NOT YET guaranteed atomic: this must be fixed using a single authoritative global benefit ledger with unique physical identity BEFORE production.
7. Test point-in-time database backup/restore, signed audit receipts and receipt retention, and loss of service midway through financial write. Under failure, do not report a successful approval.
8. Exercise OIDC PKCE, MFA, authorization/role mapping, secrets rotation, independent audit-reader rights, key revocation and break-glass logging under enterprise controls.
9. Reject user-supplied file contents as instructions; validate MIME/content, cap sizes and isolate document storage; run static dependency and secret scans.
10. Have owner-appointed security review, lawful data processing review and independent engineering sign-off before changing `production_ready` away from FALSE.

## Native-only testing protocol

From server working directory, with real dedicated test-only configuration:

```
HYDRO_NATIVE_TESTS_REQUIRED=1 HYDRO_NATIVE_CONFIG=/path/to/approved-native.json \
  python -m pytest -q tests_v71/test_postgres_native.py
```

No configuration or driver => `NATIVE_ACCEPTANCE_BLOCKED` (nonzero exit). This is the correct result. Static SQL tests and SQLite cannot replace native proof.

## Read-only PostgreSQL role/policy audit on an actual database (NOT executed here)

```
SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c WHERE c.relname='grid_annual_dossiers_v78';
SELECT schemaname,tablename,policyname,roles,cmd,qual,with_check
FROM pg_policies WHERE tablename='grid_annual_dossiers_v78';
SELECT rolname,rolsuper,rolbypassrls FROM pg_roles
WHERE rolname IN ('hk_app','hk_owner','hk_exporter','hk_authenticator');
```

Expected predicates and policy names must be independently reviewed, not assumed from a migration text file. A failed assertion keeps PRODUCTION HOLD.

## Source reference
PostgreSQL 17 documentation: https://www.postgresql.org/docs/17/ddl-rowsecurity.html . Formal RLS semantics include owner/superuser bypass and the option FORCE RLS. Do not rely solely on tenant `org_id` supplied by the browser.
