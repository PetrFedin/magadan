-- V7.9 SQL CANDIDATE; dedicated EMPTY PostgreSQL 17 acceptance DB ONLY.
-- Simulated post-project counterfactual; no field savings, tariffs or investment approval.
CREATE TABLE public.measurement_screens_v79 (
    id varchar PRIMARY KEY,
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    asset_id varchar NOT NULL,
    input_payload json NOT NULL,
    input_sha256 varchar(64) NOT NULL,
    report json NOT NULL,
    report_sha256 varchar(64) NOT NULL,
    engine_sha256 varchar(64) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_mv_v79_org_id UNIQUE(org_id,id),
    CONSTRAINT uq_mv_v79_repeat UNIQUE(org_id,input_sha256),
    CONSTRAINT mv_v79_asset_fk FOREIGN KEY(org_id,asset_id)
      REFERENCES public.assets(org_id,id),
    CONSTRAINT mv_v79_hashes CHECK(
      input_sha256 ~ '^[a-f0-9]{64}$' AND report_sha256 ~ '^[a-f0-9]{64}$'
      AND engine_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT mv_v79_research_only CHECK(
      input_payload::jsonb->>'asset_id' IS NOT DISTINCT FROM asset_id
      AND input_payload::jsonb->>'scope' IS NOT DISTINCT FROM 'SYNTHETIC_MV_RESEARCH_NO_REALIZED_SAVINGS'
      AND report::jsonb->>'verified_actual_savings' IS NOT DISTINCT FROM 'false'
      AND report::jsonb->>'benefit_recognition_eligible' IS NOT DISTINCT FROM 'false'
      AND report::jsonb->>'industrial_approval_eligible' IS NOT DISTINCT FROM 'false'
      AND report::jsonb->>'status' IS NOT DISTINCT FROM 'SYNTHETIC_COUNTERFACTUAL_RESEARCH_ONLY'),
    CONSTRAINT mv_v79_payload_size CHECK(
      octet_length(input_payload::text)<=180000 AND octet_length(report::text)<=1500000)
);
ALTER TABLE public.measurement_screens_v79 OWNER TO hk_owner;
ALTER TABLE public.measurement_screens_v79 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.measurement_screens_v79 FORCE ROW LEVEL SECURITY;
CREATE POLICY mv_v79_owner ON public.measurement_screens_v79 TO hk_owner
    USING(true) WITH CHECK(true);
CREATE POLICY mv_v79_select ON public.measurement_screens_v79 FOR SELECT TO hk_app
    USING(hk_security.allowed(org_id));
CREATE POLICY mv_v79_insert ON public.measurement_screens_v79 FOR INSERT TO hk_app
    WITH CHECK(hk_security.allowed(org_id,ARRAY['engineer','economist']::text[])
      AND created_by=hk_security.actor());
GRANT SELECT,INSERT ON public.measurement_screens_v79 TO hk_app;
CREATE INDEX mv_v79_org_created ON public.measurement_screens_v79(org_id,created_at DESC);
CREATE FUNCTION hk_private.mv_v79_asset_gate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.assets WHERE org_id=NEW.org_id
        AND id=NEW.asset_id AND classification='LAB_REFERENCE') THEN
      RAISE EXCEPTION 'NON_LAB_MV_ASSET' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
ALTER FUNCTION hk_private.mv_v79_asset_gate() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.mv_v79_asset_gate() FROM PUBLIC;
CREATE TRIGGER mv_v79_validate BEFORE INSERT ON public.measurement_screens_v79
  FOR EACH ROW EXECUTE FUNCTION hk_private.mv_v79_asset_gate();
CREATE TRIGGER mv_v79_immutable BEFORE UPDATE OR DELETE ON public.measurement_screens_v79
  FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER mv_v79_audit AFTER INSERT ON public.measurement_screens_v79
  FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
