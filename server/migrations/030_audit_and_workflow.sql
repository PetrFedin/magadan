CREATE TABLE public.audit_outbox (
 event_id text PRIMARY KEY REFERENCES public.audit_events(id), org_id text NOT NULL,
 seq integer NOT NULL, attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(), delivered_at timestamptz,
 last_error_code text, UNIQUE(org_id, seq)
);
CREATE TABLE public.audit_receipts (
 event_id text PRIMARY KEY REFERENCES public.audit_events(id), org_id text NOT NULL,
 event_hash text NOT NULL, envelope_sha256 text NOT NULL, receipt jsonb NOT NULL,
 received_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.audit_outbox OWNER TO hk_owner;
ALTER TABLE public.audit_receipts OWNER TO hk_owner;
ALTER TABLE public.audit_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE public.audit_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY outbox_owner ON public.audit_outbox TO hk_owner USING (true) WITH CHECK (true);
CREATE POLICY receipt_owner ON public.audit_receipts TO hk_owner USING (true) WITH CHECK (true);
CREATE POLICY outbox_read ON public.audit_outbox FOR SELECT TO hk_app USING(hk_security.allowed(org_id));
CREATE POLICY receipt_read ON public.audit_receipts FOR SELECT TO hk_app USING(hk_security.allowed(org_id));
CREATE POLICY outbox_exporter ON public.audit_outbox TO hk_exporter USING(true) WITH CHECK(true);
CREATE POLICY receipts_exporter ON public.audit_receipts TO hk_exporter USING(true) WITH CHECK(true);
CREATE POLICY events_exporter ON public.audit_events FOR SELECT TO hk_exporter USING(true);
GRANT SELECT ON public.audit_events,public.audit_outbox,public.audit_receipts TO hk_exporter;
GRANT UPDATE(attempts,available_at,delivered_at,last_error_code) ON public.audit_outbox TO hk_exporter;
GRANT INSERT ON public.audit_receipts TO hk_exporter;
GRANT SELECT ON public.audit_outbox,public.audit_receipts TO hk_app;

CREATE FUNCTION hk_security.append_audit(p_org text,p_event text,p_type text,p_id text,p_payload jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE o record; v_actor text; v_data jsonb; v_hash text; v_key bytea; v_id text; v_ms bigint;
BEGIN
 v_actor:=hk_security.actor();
 IF NOT hk_security.allowed(p_org) THEN RAISE EXCEPTION 'AUDIT_CONTEXT_REQUIRED' USING ERRCODE='42501'; END IF;
 SELECT audit_seq,audit_tip INTO o FROM public.organizations WHERE id=p_org FOR UPDATE;
 SELECT secret INTO v_key FROM hk_private.secrets WHERE purpose='audit';
 v_ms:=floor(extract(epoch FROM clock_timestamp())*1000);
 v_id:=gen_random_uuid()::text;
 v_data:=jsonb_build_object('org_id',p_org,'seq',o.audit_seq+1,'actor_id',v_actor,
  'event_type',p_event,'object_type',p_type,'object_id',p_id,'payload',p_payload,
  'previous_hash',o.audit_tip,'timestamp_ms',v_ms);
 v_hash:=encode(hk_crypto.hmac(convert_to(v_data::text,'UTF8'),v_key,'sha256'),'hex');
 INSERT INTO public.audit_events(id,org_id,seq,actor_id,event_type,object_type,object_id,payload,previous_hash,event_hash,timestamp_ms)
 VALUES(v_id,p_org,o.audit_seq+1,v_actor,p_event,p_type,p_id,p_payload,o.audit_tip,v_hash,v_ms);
 UPDATE public.organizations SET audit_seq=o.audit_seq+1,audit_tip=v_hash WHERE id=p_org;
 INSERT INTO public.audit_outbox(event_id,org_id,seq) VALUES(v_id,p_org,o.audit_seq+1);
 RETURN v_hash;
END $$;
ALTER FUNCTION hk_security.append_audit(text,text,text,text,jsonb) OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_security.append_audit(text,text,text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hk_security.append_audit(text,text,text,text,jsonb) TO hk_app;

CREATE FUNCTION hk_private.audit_business_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_org text; v_row jsonb;
BEGIN
 v_row:=to_jsonb(NEW);v_org:=v_row->>'org_id';
 PERFORM hk_security.append_audit(v_org,lower(TG_OP),TG_TABLE_NAME,v_row->>'id',
  jsonb_build_object('row_sha256',encode(hk_crypto.digest(convert_to(v_row::text,'UTF8'),'sha256'),'hex'),
    'revision',v_row->'revision','state',v_row->'state'));
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.audit_business_change() OWNER TO hk_owner;

CREATE FUNCTION hk_private.reject_mutation() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY' USING ERRCODE='42501'; END $$;
ALTER FUNCTION hk_private.reject_mutation() OWNER TO hk_owner;

CREATE FUNCTION hk_security.verify_audit(p_org text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e record; o record; v_seq integer:=0; v_prev text:='GENESIS'; v_key bytea; d jsonb; h text;
BEGIN
 IF NOT hk_security.allowed(p_org,ARRAY['auditor','admin']) THEN RAISE EXCEPTION 'FORBIDDEN' USING ERRCODE='42501'; END IF;
 SELECT secret INTO v_key FROM hk_private.secrets WHERE purpose='audit';
 FOR e IN SELECT * FROM public.audit_events WHERE org_id=p_org ORDER BY seq LOOP
  v_seq:=v_seq+1;
  d:=jsonb_build_object('org_id',e.org_id,'seq',e.seq,'actor_id',e.actor_id,'event_type',e.event_type,
   'object_type',e.object_type,'object_id',e.object_id,'payload',e.payload::jsonb,'previous_hash',e.previous_hash,'timestamp_ms',e.timestamp_ms);
  h:=encode(hk_crypto.hmac(convert_to(d::text,'UTF8'),v_key,'sha256'),'hex');
  IF e.seq<>v_seq OR e.previous_hash<>v_prev OR e.event_hash<>h THEN
   RETURN jsonb_build_object('valid',false,'checked',v_seq-1,'reason','CHAIN_INTEGRITY_FAILURE'); END IF;
  v_prev:=e.event_hash;
 END LOOP;
 SELECT audit_seq,audit_tip INTO o FROM public.organizations WHERE id=p_org;
 RETURN jsonb_build_object('valid',o.audit_seq=v_seq AND o.audit_tip=v_prev,'checked',v_seq,'tip',v_prev,
  'property','PostgreSQL HMAC chain; external receipts are a separate assurance property');
END $$;
ALTER FUNCTION hk_security.verify_audit(text) OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_security.verify_audit(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hk_security.verify_audit(text) TO hk_app;

-- State and evidence gates are repeated in the database to resist direct SQL bypass.
CREATE FUNCTION hk_private.guard_transition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_actor text; v_next text; v_role text; v_kind text;
BEGIN
 IF ROW(NEW.id,NEW.org_id,NEW.asset_id,NEW.run_id,NEW.title,NEW.effect_key,NEW.created_by)
    IS DISTINCT FROM ROW(OLD.id,OLD.org_id,OLD.asset_id,OLD.run_id,OLD.title,OLD.effect_key,OLD.created_by) THEN
  RAISE EXCEPTION 'IMMUTABLE_BASELINE' USING ERRCODE='42501'; END IF;
 v_actor:=hk_security.actor();
 SELECT n,r,k INTO v_next,v_role,v_kind FROM (VALUES
 ('draft','engineering_review','engineer',NULL::text),
 ('engineering_review','financial_review','engineer','engineering_report'),
 ('financial_review','approval_pending','economist','financial_report'),
 ('approval_pending','approved','manager','approval_memo'),
 ('approved','in_execution','manager',NULL::text),
 ('in_execution','verification_pending','engineer','execution_proof'),
 ('verification_pending','verified','auditor','outcome_report')) AS w(s,n,r,k) WHERE s=OLD.state;
 IF v_next IS NULL OR NEW.state<>v_next OR NEW.revision<>OLD.revision+1 THEN
  RAISE EXCEPTION 'INVALID_OR_STALE_TRANSITION' USING ERRCODE='40001'; END IF;
 IF NOT hk_security.allowed(NEW.org_id,ARRAY[v_role]) THEN RAISE EXCEPTION 'ROLE_DENIED' USING ERRCODE='42501'; END IF;
 IF OLD.state='engineering_review' AND v_actor=OLD.created_by THEN RAISE EXCEPTION 'SELF_REVIEW' USING ERRCODE='42501'; END IF;
 IF OLD.state='financial_review' AND v_actor IN (OLD.created_by,OLD.engineer_approver) THEN RAISE EXCEPTION 'SELF_REVIEW' USING ERRCODE='42501'; END IF;
 IF OLD.state='approval_pending' AND v_actor IN (OLD.created_by,OLD.engineer_approver,OLD.finance_approver) THEN RAISE EXCEPTION 'SELF_REVIEW' USING ERRCODE='42501'; END IF;
 IF OLD.state='verification_pending' AND (v_actor=OLD.created_by OR EXISTS(
  SELECT 1 FROM public.initiative_evidence l JOIN public.evidence e ON e.id=l.evidence_id AND e.org_id=l.org_id
  WHERE l.initiative_id=OLD.id AND l.org_id=OLD.org_id AND e.kind='outcome_report' AND e.created_by=v_actor
 )) THEN RAISE EXCEPTION 'SELF_VERIFICATION' USING ERRCODE='42501'; END IF;
 IF v_kind IS NOT NULL AND NOT EXISTS(
  SELECT 1 FROM public.initiative_evidence l JOIN public.evidence e ON e.id=l.evidence_id AND e.org_id=l.org_id
   JOIN public.evidence_reviews r ON r.evidence_id=e.id AND r.org_id=e.org_id
  WHERE l.initiative_id=OLD.id AND l.org_id=OLD.org_id AND e.asset_id=OLD.asset_id AND e.kind=v_kind
    AND r.accepted AND r.actor_id<>e.created_by
    AND (v_kind NOT IN ('engineering_report','financial_report','outcome_report') OR e.payload->>'run_id'=OLD.run_id)
 ) THEN RAISE EXCEPTION 'EVIDENCE_GATE' USING ERRCODE='23514'; END IF;
 IF NEW.engineer_approver IS DISTINCT FROM
    (CASE WHEN OLD.state='engineering_review' THEN v_actor ELSE OLD.engineer_approver END)
 OR NEW.finance_approver IS DISTINCT FROM
    (CASE WHEN OLD.state='financial_review' THEN v_actor ELSE OLD.finance_approver END)
 THEN RAISE EXCEPTION 'APPROVER_FORGERY' USING ERRCODE='42501'; END IF;
 -- Prior records must have an external receipt before approval, execution or closure.
 IF OLD.state IN ('approval_pending','approved','verification_pending') AND EXISTS(
  SELECT 1 FROM public.audit_outbox q WHERE q.org_id=OLD.org_id AND q.delivered_at IS NULL
 ) THEN RAISE EXCEPTION 'AUDIT_SEAL_REQUIRED' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.guard_transition() OWNER TO hk_owner;
CREATE TRIGGER initiative_guard BEFORE UPDATE ON public.initiatives FOR EACH ROW EXECUTE FUNCTION hk_private.guard_transition();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['evidence','evidence_reviews','model_versions','model_reviews','calculation_runs','initiative_evidence','transitions','audit_events','audit_receipts'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['assets','evidence','evidence_reviews','model_versions','model_reviews','calculation_runs','initiatives','initiative_evidence','transitions'] LOOP
  EXECUTE format('CREATE TRIGGER automatic_audit AFTER INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change()',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_private FROM PUBLIC;
