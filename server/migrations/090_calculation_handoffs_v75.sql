-- V7.5 CANDIDATE: never executed in this release; dedicated blank PostgreSQL 17 ONLY.
-- Requires migrations 001..080 and hk_private/hk_security trusted functions.
-- No record from this table can authorize engineering/financial/SCADA actions.
CREATE TABLE public.research_handoffs (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL REFERENCES public.organizations(id),
 asset_id varchar NOT NULL REFERENCES public.assets(id),
 kind varchar(40) NOT NULL,
 left_study_id varchar NOT NULL,
 right_study_id varchar,
 programme_id varchar,
 input_payload json NOT NULL,
 input_sha256 varchar(64) NOT NULL,
 snapshot json NOT NULL,
 snapshot_sha256 varchar(64) NOT NULL,
 engine_sha256 varchar(64) NOT NULL,
 created_by varchar NOT NULL REFERENCES public.users(id),
 created_at timestamptz NOT NULL,
 CONSTRAINT handoff_tenant_id UNIQUE (org_id,id),
 CONSTRAINT handoff_org_kind_unique UNIQUE (org_id,kind,input_sha256),
 CONSTRAINT handoff_left_fk FOREIGN KEY (org_id,left_study_id) REFERENCES public.study_runs(org_id,id),
 CONSTRAINT handoff_right_fk FOREIGN KEY (org_id,right_study_id) REFERENCES public.study_runs(org_id,id),
 CONSTRAINT handoff_programme_fk FOREIGN KEY (org_id,programme_id) REFERENCES public.research_programmes(org_id,id),
 CONSTRAINT handoff_kind_check CHECK(kind IN ('forecast_to_cascade','turbine_to_maintenance')),
 CONSTRAINT handoff_left_and_right_check CHECK(
   (kind='forecast_to_cascade' AND right_study_id IS NOT NULL AND right_study_id<>left_study_id)
   OR (kind='turbine_to_maintenance' AND right_study_id IS NULL)),
 CONSTRAINT handoff_synthetic_only_check CHECK (
   snapshot::jsonb->>'version'='7.5-LAB'
   AND snapshot::jsonb->>'status'='RESEARCH_ONLY_NO_INDUSTRIAL_APPROVAL'
   AND snapshot::jsonb->>'industrial_approval_eligible'='false'
   AND input_payload::jsonb->>'version'='7.5-LAB'
   AND input_payload::jsonb->>'research_only'='true'
 ),
 CONSTRAINT handoff_payload_budget_check CHECK (
   octet_length(snapshot::text)<=350000 AND octet_length(input_payload::text)<=130000
 ),
 CONSTRAINT handoff_sha_format CHECK (
   input_sha256 ~ '^[a-f0-9]{64}$' AND snapshot_sha256 ~ '^[a-f0-9]{64}$'
   AND engine_sha256 ~ '^[a-f0-9]{64}$')
);
ALTER TABLE public.research_handoffs OWNER TO hk_owner;
ALTER TABLE public.research_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_handoffs FORCE ROW LEVEL SECURITY;
CREATE POLICY owner_read_write ON public.research_handoffs TO hk_owner USING(true) WITH CHECK(true);
CREATE POLICY application_select ON public.research_handoffs FOR SELECT TO hk_app USING(hk_security.allowed(org_id));
CREATE POLICY application_insert ON public.research_handoffs FOR INSERT TO hk_app
 WITH CHECK(hk_security.allowed(org_id,ARRAY['engineer']::text[]) AND created_by=hk_security.actor());
GRANT SELECT, INSERT ON public.research_handoffs TO hk_app;
CREATE INDEX handoff_org_time_idx ON public.research_handoffs (org_id,created_at DESC);
CREATE INDEX handoff_org_source_idx ON public.research_handoffs (org_id,left_study_id);

-- This trigger is not an engineering sign-off. It only rejects malformed / cross-asset connections.
CREATE FUNCTION hk_private.validate_handoff_v75() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE src1 record; src2 record; a record;
BEGIN
 SELECT org_id,asset_id,module,source_ref,scenario_group INTO src1
 FROM public.study_runs WHERE org_id=NEW.org_id AND id=NEW.left_study_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'HANDOFF_SOURCE_MISSING' USING ERRCODE='23514'; END IF;
 SELECT org_id,classification INTO a FROM public.assets WHERE id=NEW.asset_id AND org_id=NEW.org_id;
 IF NOT FOUND OR a.classification<>'LAB_REFERENCE' OR src1.asset_id<>NEW.asset_id
    OR src1.source_ref NOT LIKE 'SYNTHETIC-%' THEN
  RAISE EXCEPTION 'HANDOFF_SOURCE_NOT_LAB_ASSET' USING ERRCODE='23514'; END IF;
 IF NEW.kind='forecast_to_cascade' THEN
  SELECT org_id,asset_id,module,source_ref,scenario_group INTO src2
   FROM public.study_runs WHERE org_id=NEW.org_id AND id=NEW.right_study_id;
  IF NOT FOUND OR src1.module<>'hydroforecast' OR src2.module<>'cascade'
     OR src2.asset_id<>NEW.asset_id OR src1.scenario_group IS DISTINCT FROM src2.scenario_group
     OR src2.source_ref NOT LIKE 'SYNTHETIC-%' THEN
   RAISE EXCEPTION 'FORECAST_CASCADE_SOURCE_MISMATCH' USING ERRCODE='23514'; END IF;
 ELSE
  IF src1.module<>'turbine' OR NEW.right_study_id IS NOT NULL THEN
   RAISE EXCEPTION 'MAINTENANCE_SOURCE_MISMATCH' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.programme_id IS NOT NULL THEN
  IF NOT EXISTS(SELECT 1 FROM public.research_programme_studies
       WHERE org_id=NEW.org_id AND programme_id=NEW.programme_id AND study_id=NEW.left_study_id)
   OR (NEW.right_study_id IS NOT NULL AND NOT EXISTS(
       SELECT 1 FROM public.research_programme_studies
       WHERE org_id=NEW.org_id AND programme_id=NEW.programme_id AND study_id=NEW.right_study_id)) THEN
   RAISE EXCEPTION 'HANDOFF_SOURCES_NOT_IN_PROGRAMME' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_handoff_v75() OWNER TO hk_owner;
CREATE TRIGGER validate_handoff_sources BEFORE INSERT ON public.research_handoffs
 FOR EACH ROW EXECUTE FUNCTION hk_private.validate_handoff_v75();
CREATE TRIGGER prevent_mutation BEFORE UPDATE OR DELETE ON public.research_handoffs
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER record_research_audit AFTER INSERT ON public.research_handoffs
 FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
REVOKE ALL ON FUNCTION hk_private.validate_handoff_v75() FROM PUBLIC;
-- There is deliberately NO FK to public.initiatives / approved investments.
