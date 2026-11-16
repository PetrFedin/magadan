-- V7.9 SQL CANDIDATE. Dedicated EMPTY PostgreSQL 17 acceptance DB ONLY.
-- No industrial savings or corporate permissions may be inferred from application.
-- btree_gist enables atomic EXCLUDE across tenant, measurement boundary, family, period.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE public.benefit_reservations_v79 (
    id varchar PRIMARY KEY,
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    asset_id varchar NOT NULL,
    family varchar(50) NOT NULL,
    start_year integer NOT NULL,
    end_year integer NOT NULL,
    source_kind varchar(50) NOT NULL,
    source_id varchar(120) NOT NULL,
    source_sha256 varchar(64) NOT NULL,
    source_fingerprint varchar(64) NOT NULL,
    measurement_plan_ref varchar(160) NOT NULL,
    measurement_boundary_description text NOT NULL,
    comparison_normalization text NOT NULL,
    lab_estimated_gross_rub varchar(80),
    reservation_sha256 varchar(64) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_benefit_v79_org_id UNIQUE(org_id,id),
    CONSTRAINT uq_benefit_v79_single_source UNIQUE(org_id,source_kind,source_id),
    CONSTRAINT uq_benefit_v79_source_fingerprint UNIQUE(org_id,source_fingerprint),
    CONSTRAINT benefit_v79_asset_fk FOREIGN KEY(org_id,asset_id)
        REFERENCES public.assets(org_id,id),
    CONSTRAINT benefit_v79_valid_family CHECK (family IN (
        'ELECTRIC_ENERGY_COST','HEAT_ENERGY_COST','MAINTENANCE_COST',
        'GENERATION_VALUE','CAPEX_COST','DECISION_PROCESS','RELIABILITY_RISK')),
    CONSTRAINT benefit_v79_source_kind CHECK (source_kind IN (
        'GRID_ANNUAL_V78','ASSURANCE_V76','MAINTENANCE_HANDOFF_V75','PROGRAMME_V74')),
    CONSTRAINT benefit_v79_valid_period CHECK(
        start_year >= 2026 AND end_year <= 2050
        AND end_year >= start_year AND end_year - start_year <= 20),
    CONSTRAINT benefit_v79_only_synthetic CHECK(
        measurement_plan_ref LIKE 'SYNTHETIC-%'
        AND char_length(measurement_boundary_description) >= 40
        AND char_length(comparison_normalization) >= 60),
    CONSTRAINT benefit_v79_hashes CHECK (
        source_sha256 ~ '^[a-f0-9]{64}$'
        AND source_fingerprint ~ '^[a-f0-9]{64}$'
        AND reservation_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT benefit_v79_no_claim_promotion CHECK (
        lab_estimated_gross_rub IS NULL OR
        lab_estimated_gross_rub ~ '^-?[0-9]{1,32}\.[0-9]{2}$'),
    CONSTRAINT benefit_v79_no_boundary_overlap EXCLUDE USING gist(
        org_id WITH =,asset_id WITH =,family WITH =,
        int4range(start_year,end_year + 1,'[)') WITH &&
    )
);
ALTER TABLE public.benefit_reservations_v79 OWNER TO hk_owner;
ALTER TABLE public.benefit_reservations_v79 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.benefit_reservations_v79 FORCE ROW LEVEL SECURITY;
CREATE POLICY benefit_v79_owner ON public.benefit_reservations_v79 TO hk_owner
    USING(true) WITH CHECK(true);
CREATE POLICY benefit_v79_select ON public.benefit_reservations_v79 FOR SELECT TO hk_app
    USING(hk_security.allowed(org_id));
CREATE POLICY benefit_v79_insert ON public.benefit_reservations_v79 FOR INSERT TO hk_app
    WITH CHECK(hk_security.allowed(org_id,ARRAY['economist']::text[])
      AND created_by=hk_security.actor());
GRANT SELECT,INSERT ON public.benefit_reservations_v79 TO hk_app;
CREATE INDEX benefit_v79_org_period ON public.benefit_reservations_v79(org_id,start_year,end_year);

CREATE FUNCTION hk_private.validate_benefit_v79() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE source_asset varchar; source_hash varchar; source_kind varchar; srcjson jsonb;
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.assets WHERE org_id=NEW.org_id
         AND id=NEW.asset_id AND classification='LAB_REFERENCE') THEN
        RAISE EXCEPTION 'REAL_ASSET_EXCLUDED' USING ERRCODE='23514';
    END IF;
    IF NEW.source_kind='GRID_ANNUAL_V78' THEN
        SELECT asset_id,report_sha256,report::jsonb INTO source_asset,source_hash,srcjson
        FROM public.grid_annual_dossiers_v78 WHERE org_id=NEW.org_id AND id=NEW.source_id;
        IF NOT FOUND OR NEW.family<>'ELECTRIC_ENERGY_COST'
          OR srcjson->>'industrial_approval_eligible' IS DISTINCT FROM 'false' THEN
          RAISE EXCEPTION 'GRID_SOURCE_NOT_LAB' USING ERRCODE='23514'; END IF;
    ELSIF NEW.source_kind='MAINTENANCE_HANDOFF_V75' THEN
        SELECT asset_id,snapshot_sha256,kind INTO source_asset,source_hash,source_kind
        FROM public.research_handoffs WHERE org_id=NEW.org_id AND id=NEW.source_id;
        IF NOT FOUND OR NEW.family<>'MAINTENANCE_COST' OR source_kind<>'turbine_to_maintenance' THEN
          RAISE EXCEPTION 'MAINTENANCE_SOURCE_NOT_LAB' USING ERRCODE='23514'; END IF;
    ELSIF NEW.source_kind='PROGRAMME_V74' THEN
        SELECT snapshot_sha256,snapshot::jsonb INTO source_hash,srcjson
        FROM public.research_programmes WHERE org_id=NEW.org_id AND id=NEW.source_id;
        IF NOT FOUND OR NEW.family<>'HEAT_ENERGY_COST'
           OR jsonb_array_length(COALESCE(srcjson->'heat_screenings','[]'::jsonb))=0
           OR NOT EXISTS(SELECT 1 FROM public.research_programme_studies p
             JOIN public.study_runs s ON s.id=p.study_id AND s.org_id=p.org_id
             WHERE p.org_id=NEW.org_id AND p.programme_id=NEW.source_id
               AND s.asset_id=NEW.asset_id AND s.module='heatnet') THEN
          RAISE EXCEPTION 'HEAT_SOURCE_NOT_LAB' USING ERRCODE='23514'; END IF;
        source_asset:=NEW.asset_id;
    ELSIF NEW.source_kind='ASSURANCE_V76' THEN
        SELECT snapshot_sha256,programme_id,snapshot::jsonb
        INTO source_hash,source_kind,srcjson FROM public.assurance_packs_v76
        WHERE org_id=NEW.org_id AND id=NEW.source_id;
        IF NOT FOUND OR NEW.family<>'DECISION_PROCESS'
           OR srcjson->>'industrial_approval_eligible' IS DISTINCT FROM 'false'
           OR NOT EXISTS (SELECT 1 FROM public.research_programme_studies p
             JOIN public.study_runs s ON s.id=p.study_id AND s.org_id=p.org_id
             WHERE p.org_id=NEW.org_id AND p.programme_id=source_kind
               AND s.asset_id=NEW.asset_id) THEN
          RAISE EXCEPTION 'ASSURANCE_SOURCE_NOT_LAB' USING ERRCODE='23514'; END IF;
        source_asset:=NEW.asset_id;
    ELSE
        RAISE EXCEPTION 'UNKNOWN_SOURCE_KIND' USING ERRCODE='23514';
    END IF;
    IF source_asset IS DISTINCT FROM NEW.asset_id
       OR source_hash IS DISTINCT FROM NEW.source_sha256 THEN
      RAISE EXCEPTION 'SOURCE_HASH_OR_ASSET_MISMATCH' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_benefit_v79() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.validate_benefit_v79() FROM PUBLIC;
CREATE TRIGGER benefit_v79_validate BEFORE INSERT ON public.benefit_reservations_v79
    FOR EACH ROW EXECUTE FUNCTION hk_private.validate_benefit_v79();
CREATE TRIGGER benefit_v79_immutable BEFORE UPDATE OR DELETE ON public.benefit_reservations_v79
    FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER benefit_v79_audit AFTER INSERT ON public.benefit_reservations_v79
    FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- The same source/asset/family MAY appear in older tables as historical unregistered
-- dossier. Migration/backfill and cross-version automated reservations are NOT complete.
