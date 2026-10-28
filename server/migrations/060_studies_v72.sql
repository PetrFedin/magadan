-- Apply to a dedicated lab database after all V7.1 migrations.
-- Server-produced records only. No acceptance/approval from these studies.
CREATE TABLE public.study_runs (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL REFERENCES public.organizations(id),
 asset_id varchar NOT NULL,
 module varchar(40) NOT NULL,
 source_ref varchar(220) NOT NULL,
 scenario_group varchar(100) NOT NULL,
 case_payload json NOT NULL,
 input_sha256 varchar(64) NOT NULL,
 result json NOT NULL,
 result_sha256 varchar(64) NOT NULL,
 engine_sha256 varchar(64) NOT NULL,
 created_by varchar NOT NULL REFERENCES public.users(id),
 created_at timestamptz NOT NULL,
 CONSTRAINT study_runs_tenant_id UNIQUE(org_id,id),
 CONSTRAINT study_runs_tenant_asset FOREIGN KEY (org_id,asset_id)
    REFERENCES public.assets(org_id,id),
 CONSTRAINT study_source_synthetic CHECK (source_ref LIKE 'SYNTHETIC-%'),
 CONSTRAINT study_module_valid CHECK (module IN ('hydroforecast','cascade','turbine','gridloss','heatnet','hydrocapex'))
);
ALTER TABLE public.study_runs OWNER TO hk_owner;
CREATE INDEX study_runs_org_asset ON public.study_runs(org_id,asset_id,module);
ALTER TABLE public.study_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.study_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY study_runs_owner ON public.study_runs TO hk_owner USING (true) WITH CHECK(true);
CREATE POLICY study_runs_read ON public.study_runs FOR SELECT TO hk_app
 USING (hk_security.allowed(org_id));
CREATE POLICY study_runs_insert ON public.study_runs FOR INSERT TO hk_app
 WITH CHECK (
   hk_security.allowed(org_id, CASE WHEN module='hydrocapex' THEN ARRAY['economist']::text[] ELSE ARRAY['engineer']::text[] END)
   AND created_by=hk_security.actor()
 );
GRANT SELECT, INSERT ON public.study_runs TO hk_app;
CREATE TRIGGER study_runs_immutable BEFORE UPDATE OR DELETE ON public.study_runs
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER study_runs_audit AFTER INSERT ON public.study_runs
 FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- We deliberately DO NOT allow study runs to bind to industrial initiatives.
