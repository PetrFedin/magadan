CREATE TABLE hk_private.policy (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 require_compliance boolean NOT NULL DEFAULT true,
 fresh_auth_seconds integer NOT NULL DEFAULT 600 CHECK(fresh_auth_seconds BETWEEN 60 AND 3600)
);
ALTER TABLE hk_private.policy OWNER TO hk_owner;
INSERT INTO hk_private.policy(singleton,require_compliance) VALUES(true,true);

CREATE FUNCTION hk_security.audit_ready(p_org text) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE strict boolean;
BEGIN
 IF NOT hk_security.allowed(p_org) THEN RETURN false; END IF;
 SELECT require_compliance INTO strict FROM hk_private.policy WHERE singleton;
 RETURN EXISTS(SELECT 1 FROM public.audit_events WHERE org_id=p_org) AND NOT EXISTS (
  SELECT 1 FROM public.audit_events e LEFT JOIN public.audit_outbox q ON q.event_id=e.id
  LEFT JOIN public.audit_receipts r ON r.event_id=e.id
  WHERE e.org_id=p_org AND (q.delivered_at IS NULL OR r.event_id IS NULL OR r.event_hash<>e.event_hash
    OR (strict AND (r.receipt->'receipt'->>'retention_mode') IS DISTINCT FROM 'COMPLIANCE')
    OR (r.receipt->'receipt'->>'retention_until')::timestamptz<=statement_timestamp())
 );
END $$;
ALTER FUNCTION hk_security.audit_ready(text) OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_security.audit_ready(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hk_security.audit_ready(text) TO hk_app;

CREATE FUNCTION hk_private.guard_external_seal() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE fresh integer;
BEGIN
 IF OLD.state IN ('approval_pending','approved','verification_pending') THEN
  SELECT fresh_auth_seconds INTO fresh FROM hk_private.policy WHERE singleton;
  IF coalesce((hk_security.context()->>'auth_time')::bigint,0)<extract(epoch FROM clock_timestamp())-fresh THEN
    RAISE EXCEPTION 'FRESH_AUTHENTICATION_REQUIRED' USING ERRCODE='28000'; END IF;
  IF NOT hk_security.audit_ready(OLD.org_id) THEN RAISE EXCEPTION 'EXTERNAL_SEAL_REQUIRED' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.guard_external_seal() OWNER TO hk_owner;
CREATE TRIGGER external_seal_guard BEFORE UPDATE ON public.initiatives FOR EACH ROW EXECUTE FUNCTION hk_private.guard_external_seal();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_private FROM PUBLIC;
