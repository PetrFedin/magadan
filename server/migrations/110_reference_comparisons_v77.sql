-- V7.7 candidate for an EMPTY, isolated PostgreSQL 17 acceptance database.
-- DO NOT MARK NATIVE PASS until tests_v71/test_postgres_native.py runs with real PG17.
-- This is a record of UNATTESTED lab comparisons, not a certified engineering report.
-- PostgreSQL requires an exact unique composite key for the tenant-scoped FK below.
-- The existing (org_id,id) key does not qualify for (org_id,asset_id,id).
ALTER TABLE public.study_runs
  ADD CONSTRAINT study_runs_tenant_asset_identity_v77 UNIQUE (org_id,asset_id,id);
CREATE TABLE public.grid_reference_comparisons_v77 (
    id varchar PRIMARY KEY,
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    asset_id varchar NOT NULL,
    study_id varchar NOT NULL,
    source_input_sha256 varchar(64) NOT NULL,
    submission json NOT NULL,
    submission_sha256 varchar(64) NOT NULL,
    report json NOT NULL,
    report_sha256 varchar(64) NOT NULL,
    engine_sha256 varchar(64) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL,
    CONSTRAINT ref_v77_org_id UNIQUE (org_id,id),
    CONSTRAINT ref_v77_deduplicate UNIQUE (org_id,study_id,submission_sha256),
    CONSTRAINT ref_v77_asset_fk FOREIGN KEY(org_id,asset_id) REFERENCES public.assets(org_id,id),
    CONSTRAINT ref_v77_source_fk FOREIGN KEY(org_id,asset_id,study_id)
        REFERENCES public.study_runs(org_id,asset_id,id),
    CONSTRAINT ref_v77_sha_format CHECK (
        source_input_sha256 ~ '^[0-9a-f]{64}$' AND submission_sha256 ~ '^[0-9a-f]{64}$'
        AND report_sha256 ~ '^[0-9a-f]{64}$' AND engine_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ref_v77_lab_scope CHECK (
        submission::jsonb->>'scope'='SYNTHETIC_UNATTESTED_REFERENCE_ONLY'
        AND report::jsonb->>'status' IN
           ('LAB_NUMERICAL_MATCH_UNATTESTED','LAB_NUMERICAL_MISMATCH_UNATTESTED')
        AND report::jsonb->>'source_claim_trusted'='false'
        AND report::jsonb->>'external_solver_execution_verified'='false'
        AND report::jsonb->>'independent_engineering_accepted'='false'
        AND report::jsonb->>'industrial_approval_eligible'='false'),
    CONSTRAINT ref_v77_max_payload CHECK (
        octet_length(submission::text)<=128000 AND octet_length(report::text)<=330000)
);
ALTER TABLE public.grid_reference_comparisons_v77 OWNER TO hk_owner;
ALTER TABLE public.grid_reference_comparisons_v77 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grid_reference_comparisons_v77 FORCE ROW LEVEL SECURITY;
CREATE POLICY ref_v77_owner ON public.grid_reference_comparisons_v77 TO hk_owner
    USING(true) WITH CHECK(true);
CREATE POLICY ref_v77_select ON public.grid_reference_comparisons_v77 FOR SELECT TO hk_app
    USING (hk_security.allowed(org_id));
CREATE POLICY ref_v77_insert ON public.grid_reference_comparisons_v77 FOR INSERT TO hk_app
    WITH CHECK (hk_security.allowed(org_id,ARRAY['engineer']::text[])
        AND created_by=hk_security.actor());
GRANT SELECT, INSERT ON public.grid_reference_comparisons_v77 TO hk_app;
CREATE INDEX ref_v77_org_created ON public.grid_reference_comparisons_v77(org_id,created_at DESC);

CREATE FUNCTION hk_private.validate_grid_reference_v77() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE src record;
BEGIN
    SELECT s.module,s.case_payload,s.input_sha256,s.asset_id,a.classification INTO src
    FROM public.study_runs s JOIN public.assets a ON (a.id=s.asset_id AND a.org_id=s.org_id)
    WHERE s.org_id=NEW.org_id AND s.id=NEW.study_id;
    IF NOT FOUND OR src.asset_id<>NEW.asset_id OR src.classification<>'LAB_REFERENCE'
       OR src.module<>'gridloss' OR src.case_payload::jsonb->>'model_kind'<>'radial_ac_v73'
       OR src.input_sha256<>NEW.source_input_sha256 THEN
      RAISE EXCEPTION 'REFERENCE_SOURCE_NOT_LAB_GRID_OR_TENANT_MISMATCH' USING ERRCODE='23514';
    END IF;
    IF NEW.submission::jsonb->>'claimed_tool' IS NULL
       OR NEW.submission::jsonb->>'case_sha256' IS NULL
       OR NEW.report::jsonb->>'status' NOT IN
          ('LAB_NUMERICAL_MATCH_UNATTESTED','LAB_NUMERICAL_MISMATCH_UNATTESTED') THEN
      RAISE EXCEPTION 'REFERENCE_REQUIRED_FIELDS_MISSING' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_grid_reference_v77() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.validate_grid_reference_v77() FROM PUBLIC;
CREATE TRIGGER ref_v77_validate BEFORE INSERT ON public.grid_reference_comparisons_v77
    FOR EACH ROW EXECUTE FUNCTION hk_private.validate_grid_reference_v77();
CREATE TRIGGER ref_v77_immutable BEFORE UPDATE OR DELETE ON public.grid_reference_comparisons_v77
    FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER ref_v77_audit AFTER INSERT ON public.grid_reference_comparisons_v77
    FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- No FK or UPDATE to public.initiatives; reference matches cannot approve investment.
