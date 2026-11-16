-- V7.8 CANDIDATE ONLY: apply after 001..110 on a dedicated EMPTY PostgreSQL 17 acceptance database.
-- DO NOT mark the migration PASS without its native execution and negative security tests.
-- This is RESEARCH for one synthetic single-measure feeder WBS, NOT a construction authorization.
CREATE TABLE public.grid_annual_dossiers_v78 (
    id varchar PRIMARY KEY,
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    asset_id varchar NOT NULL,
    programme_id varchar NOT NULL,
    baseline_run_id varchar NOT NULL,
    proposed_run_id varchar NOT NULL,
    benefit_key varchar(100) NOT NULL,
    source_bundle_sha256 varchar(64) NOT NULL,
    finance_input json NOT NULL,
    input_sha256 varchar(64) NOT NULL,
    report json NOT NULL,
    report_sha256 varchar(64) NOT NULL,
    engine_sha256 varchar(64) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL,
    CONSTRAINT grid_dcf_v78_org_id UNIQUE(org_id,id),
    CONSTRAINT grid_dcf_v78_unique_wbs_single_measure UNIQUE(org_id,programme_id),
    CONSTRAINT grid_dcf_v78_unique_effect UNIQUE(org_id,benefit_key),
    CONSTRAINT grid_dcf_v78_unique_pair UNIQUE(org_id,baseline_run_id,proposed_run_id),
    CONSTRAINT grid_dcf_v78_asset_fk FOREIGN KEY(org_id,asset_id) REFERENCES public.assets(org_id,id),
    CONSTRAINT grid_dcf_v78_programme_fk FOREIGN KEY(org_id,programme_id)
         REFERENCES public.research_programmes(org_id,id),
    CONSTRAINT grid_dcf_v78_base_fk FOREIGN KEY(org_id,baseline_run_id)
         REFERENCES public.study_runs(org_id,id),
    CONSTRAINT grid_dcf_v78_alt_fk FOREIGN KEY(org_id,proposed_run_id)
         REFERENCES public.study_runs(org_id,id),
    CONSTRAINT grid_dcf_v78_sha_valid CHECK (
        source_bundle_sha256 ~ '^[a-f0-9]{64}$'
        AND input_sha256 ~ '^[a-f0-9]{64}$'
        AND report_sha256 ~ '^[a-f0-9]{64}$'
        AND engine_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT grid_dcf_v78_research_only CHECK (
        baseline_run_id<>proposed_run_id
        AND finance_input::jsonb #>> '{parameters,scope}' IS NOT DISTINCT FROM 'SYNTHETIC_SINGLE_INTERVENTION_NO_TARIFF'
        AND finance_input::jsonb->>'programme_id' IS NOT DISTINCT FROM programme_id
        AND finance_input::jsonb->>'baseline_run_id' IS NOT DISTINCT FROM baseline_run_id
        AND finance_input::jsonb->>'proposed_run_id' IS NOT DISTINCT FROM proposed_run_id
        AND finance_input::jsonb #>> '{parameters,benefit_key}' IS NOT DISTINCT FROM benefit_key
        AND report::jsonb->>'scope' IS NOT DISTINCT FROM 'SYNTHETIC_SINGLE_MEASURE_ONLY'
        AND report::jsonb->>'benefit_key' IS NOT DISTINCT FROM benefit_key
        AND report::jsonb->>'industrial_approval_eligible' IS NOT DISTINCT FROM 'false'
        AND report::jsonb->>'independent_engineering_accepted' IS NOT DISTINCT FROM 'false'
        AND report::jsonb->>'source_is_not_third_party_attested' IS NOT DISTINCT FROM 'true'),
    CONSTRAINT grid_dcf_v78_payload_limit CHECK(
        octet_length(finance_input::text)<=110000 AND octet_length(report::text)<=1050000)
);
ALTER TABLE public.grid_annual_dossiers_v78 OWNER TO hk_owner;
ALTER TABLE public.grid_annual_dossiers_v78 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grid_annual_dossiers_v78 FORCE ROW LEVEL SECURITY;
CREATE POLICY grid_dcf_v78_owner ON public.grid_annual_dossiers_v78 TO hk_owner
    USING (true) WITH CHECK (true);
CREATE POLICY grid_dcf_v78_select ON public.grid_annual_dossiers_v78 FOR SELECT TO hk_app
    USING(hk_security.allowed(org_id));
CREATE POLICY grid_dcf_v78_insert ON public.grid_annual_dossiers_v78 FOR INSERT TO hk_app
    WITH CHECK(hk_security.allowed(org_id,ARRAY['economist']::text[])
      AND created_by=hk_security.actor());
GRANT SELECT, INSERT ON public.grid_annual_dossiers_v78 TO hk_app;
CREATE INDEX grid_dcf_v78_org_created ON public.grid_annual_dossiers_v78(org_id,created_at DESC);

CREATE FUNCTION hk_private.validate_grid_dcf_v78() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE p record; b record; a record; memberships bigint;
BEGIN
  SELECT capital_input,snapshot,snapshot_sha256 INTO p
    FROM public.research_programmes
   WHERE org_id=NEW.org_id AND id=NEW.programme_id;
  IF NOT FOUND OR p.capital_input IS NULL OR
     p.snapshot::jsonb->>'cannot_be_used_for_field_approval' IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'RESEARCH_ONLY_SINGLE_MEASURE_WBS_MISSING' USING ERRCODE='23514';
  END IF;
  IF COALESCE(jsonb_array_length(p.snapshot::jsonb->'study_ids'),0)<>2
     OR NOT COALESCE(p.snapshot::jsonb->'study_ids' @> jsonb_build_array(NEW.baseline_run_id,NEW.proposed_run_id),false)
     OR p.snapshot::jsonb->'financial_dossier_ids' IS DISTINCT FROM '[]'::jsonb
     OR p.snapshot::jsonb->'heat_screenings' IS DISTINCT FROM '[]'::jsonb
     OR p.snapshot::jsonb->'links' IS DISTINCT FROM '[]'::jsonb THEN
    RAISE EXCEPTION 'PROGRAMME_MULTIPLE_INTERVENTIONS_OR_PAIR_DRIFT' USING ERRCODE='23514';
  END IF;
  SELECT count(*) INTO memberships FROM public.research_programme_studies s
   WHERE s.org_id=NEW.org_id AND s.programme_id=NEW.programme_id
     AND s.study_id IN (NEW.baseline_run_id,NEW.proposed_run_id);
  IF memberships<>2 THEN
    RAISE EXCEPTION 'PROGRAMME_LINKS_MISSING' USING ERRCODE='23514';
  END IF;
  SELECT module,asset_id,scenario_group,case_payload,source_ref INTO b
    FROM public.study_runs WHERE org_id=NEW.org_id AND id=NEW.baseline_run_id;
  SELECT module,asset_id,scenario_group,case_payload,source_ref INTO a
    FROM public.study_runs WHERE org_id=NEW.org_id AND id=NEW.proposed_run_id;
  IF b.module IS DISTINCT FROM 'gridloss' OR a.module IS DISTINCT FROM 'gridloss'
     OR b.asset_id IS DISTINCT FROM NEW.asset_id OR a.asset_id IS DISTINCT FROM NEW.asset_id
     OR b.scenario_group IS DISTINCT FROM a.scenario_group
     OR b.case_payload::jsonb->>'model_kind' IS DISTINCT FROM 'radial_ac_v73'
     OR a.case_payload::jsonb->>'model_kind' IS DISTINCT FROM 'radial_ac_v73'
     OR b.source_ref NOT LIKE 'SYNTHETIC-%' OR a.source_ref NOT LIKE 'SYNTHETIC-%' THEN
    RAISE EXCEPTION 'ENGINEERING_SOURCES_NOT_COMPARABLE' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.assets WHERE org_id=NEW.org_id AND id=NEW.asset_id
                 AND classification='LAB_REFERENCE') THEN
    RAISE EXCEPTION 'REAL_ASSET_EXCLUDED' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_grid_dcf_v78() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.validate_grid_dcf_v78() FROM PUBLIC;
CREATE TRIGGER grid_dcf_v78_validate BEFORE INSERT ON public.grid_annual_dossiers_v78
    FOR EACH ROW EXECUTE FUNCTION hk_private.validate_grid_dcf_v78();
CREATE TRIGGER grid_dcf_v78_immutable BEFORE UPDATE OR DELETE ON public.grid_annual_dossiers_v78
    FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER grid_dcf_v78_audit AFTER INSERT ON public.grid_annual_dossiers_v78
    FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- Deliberately no authorization to update or delete these records.
