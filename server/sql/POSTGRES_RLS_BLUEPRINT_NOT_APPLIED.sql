-- SECURITY DESIGN ONLY. THIS SCRIPT HAS NOT BEEN EXECUTED AGAINST POSTGRESQL.
-- DO NOT APPLY WITHOUT REVIEW BY DBA/SECURITY AND TESTING AGAINST A STAGING DB.
-- V7 refuses postgres connection until transaction-scoped tenant bind and RLS are verified.
-- RLS security relies on a non-superuser app role WITHOUT BYPASSRLS or table ownership;
-- configuration variables must be set from VERIFIED auth membership server-side.
-- Do NOT use user-provided header or org_id as authority.
-- App runtime must execute one DB transaction per request and:
--   BEGIN;
--   SELECT set_config('app.tenant_id', :verified_org, true);
--   SELECT set_config('app.actor_id', :verified_sub, true);
--   ... SQL ...;
--   COMMIT;
-- Pool check-in must clean all state, and negative tests must verify isolation.
-- Global user authentication should be isolated from tenant service account.

BEGIN;
DO $$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'memberships','assets','evidence','evidence_reviews','model_versions',
    'model_reviews','calculation_runs','initiatives','initiative_evidence',
    'transitions','audit_events']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tbl);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tbl);
    EXECUTE format('CREATE POLICY tenant_scope ON %I USING (org_id = nullif(current_setting(''app.tenant_id'',true),'''')) WITH CHECK (org_id = nullif(current_setting(''app.tenant_id'',true),''''))',tbl);
  END LOOP;
END $$;
-- For real event protection, audit inserts must happen through a reviewed,
-- separately privileged SECURITY DEFINER append-only function.
CREATE OR REPLACE FUNCTION reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'AUDIT_APPEND_ONLY';
END $$;
DROP TRIGGER IF EXISTS protect_audit ON audit_events;
CREATE TRIGGER protect_audit BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
COMMIT;
-- Mandatory before any production claim: tests for pool reuse, empty context,
-- wrong context, cross-tenant direct SQL, malicious actor, privileged role,
-- immutable audit, HMAC key separation, external write-once anchor and recovery.
