-- V7.3 proposed PostgreSQL migration. DO NOT MARK ACCEPTED until native PG17 tests pass.
-- Only synthetic field-invalidating studies. No relation to investment approvals.
CREATE TABLE public.grid_economic_dossiers (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL REFERENCES public.organizations(id),
 asset_id varchar NOT NULL,
 baseline_run_id varchar NOT NULL,
 proposed_run_id varchar NOT NULL,
 benefit_key varchar(100) NOT NULL,
 finance_input json NOT NULL,
 result json NOT NULL,
 result_sha256 varchar(64) NOT NULL,
 pinned_engine_sha256 varchar(64) NOT NULL,
 created_by varchar NOT NULL REFERENCES public.users(id),
 created_at timestamptz NOT NULL,
 CONSTRAINT grid_dossier_tenant_id UNIQUE(org_id,id),
 CONSTRAINT grid_dossier_unique_effect_key UNIQUE(org_id,benefit_key),
 CONSTRAINT grid_dossier_unique_pair UNIQUE(org_id,baseline_run_id,proposed_run_id),
 CONSTRAINT grid_dossier_distinct_scenarios CHECK(baseline_run_id<>proposed_run_id),
 CONSTRAINT grid_dossier_synthetic_finance_only CHECK(
   finance_input::jsonb->>'scope'='SYNTHETIC_NOT_A_TARIFF'),
 CONSTRAINT grid_dossier_research_status_only CHECK(
   result::jsonb->>'status'='SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL'
   AND result::jsonb #>> '{economic_result,industrial_investment_eligible}'='false'),
 CONSTRAINT grid_dossier_org_asset FOREIGN KEY(org_id,asset_id) REFERENCES public.assets(org_id,id),
 CONSTRAINT grid_dossier_baseline_tenant FOREIGN KEY(org_id,baseline_run_id) REFERENCES public.study_runs(org_id,id),
 CONSTRAINT grid_dossier_proposed_tenant FOREIGN KEY(org_id,proposed_run_id) REFERENCES public.study_runs(org_id,id)
);
ALTER TABLE public.grid_economic_dossiers OWNER TO hk_owner;
CREATE INDEX grid_dossier_asset_index ON public.grid_economic_dossiers(org_id,asset_id,created_at);
ALTER TABLE public.grid_economic_dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grid_economic_dossiers FORCE ROW LEVEL SECURITY;
CREATE POLICY grid_dossier_owner ON public.grid_economic_dossiers TO hk_owner USING(true) WITH CHECK(true);
CREATE POLICY grid_dossier_select ON public.grid_economic_dossiers FOR SELECT TO hk_app
 USING (hk_security.allowed(org_id));
CREATE POLICY grid_dossier_insert ON public.grid_economic_dossiers FOR INSERT TO hk_app
 WITH CHECK (
   hk_security.allowed(org_id,ARRAY['economist']::text[]) AND created_by=hk_security.actor()
   AND EXISTS (SELECT 1 FROM public.assets a WHERE a.id=grid_economic_dossiers.asset_id
      AND a.org_id=grid_economic_dossiers.org_id AND a.classification='LAB_REFERENCE')
   AND EXISTS (SELECT 1 FROM public.study_runs s WHERE s.id=grid_economic_dossiers.baseline_run_id
      AND s.org_id=grid_economic_dossiers.org_id AND s.asset_id=grid_economic_dossiers.asset_id
      AND s.module='gridloss' AND (s.case_payload::jsonb->>'model_kind')='radial_ac_v73')
   AND EXISTS (SELECT 1 FROM public.study_runs s WHERE s.id=grid_economic_dossiers.proposed_run_id
      AND s.org_id=grid_economic_dossiers.org_id AND s.asset_id=grid_economic_dossiers.asset_id
      AND s.module='gridloss' AND (s.case_payload::jsonb->>'model_kind')='radial_ac_v73')
 );
GRANT SELECT,INSERT ON public.grid_economic_dossiers TO hk_app;
CREATE TRIGGER grid_dossier_immutable BEFORE UPDATE OR DELETE ON public.grid_economic_dossiers
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER grid_dossier_auto_audit AFTER INSERT ON public.grid_economic_dossiers
 FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- No FK, view or grant from grid_economic_dossiers to public.initiatives.
