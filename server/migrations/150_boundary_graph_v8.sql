-- V8.0 CANDIDATE FOR EMPTY ISOLATED PostgreSQL 17 ACCEPTANCE DATABASE.
-- NOT applied, NOT certified. No raw metering access, no savings recognition.
-- Graph additions intentionally DBA-only on PG; hk_app has SELECT only until
-- independent review of issuer authorization, provenance, RLS and concurrency.

CREATE TABLE public.meter_boundaries_v8 (
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    id varchar(100) NOT NULL,
    parent_id varchar(100),
    quantity_class varchar(35) NOT NULL,
    source_ref varchar(160) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(org_id,id),
    FOREIGN KEY(org_id,parent_id) REFERENCES public.meter_boundaries_v8(org_id,id),
    CHECK(quantity_class IN ('ELECTRIC_ENERGY','HEAT_ENERGY','EQUIPMENT_MAINTENANCE','FINANCIAL_PROCESS')),
    CHECK(id ~ '^SYNTHETIC-[A-Za-z0-9_-]{7,80}$'),
    CHECK(source_ref ~ '^SYNTHETIC-[A-Za-z0-9_-]{12,120}$'),
    CHECK(parent_id IS DISTINCT FROM id)
);
CREATE TABLE public.boundary_assets_v8 (
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    asset_id varchar NOT NULL,
    boundary_id varchar(100) NOT NULL,
    evidence_ref varchar(160) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    PRIMARY KEY(org_id,asset_id),
    FOREIGN KEY(org_id,asset_id) REFERENCES public.assets(org_id,id),
    FOREIGN KEY(org_id,boundary_id) REFERENCES public.meter_boundaries_v8(org_id,id),
    CHECK(evidence_ref ~ '^SYNTHETIC-[A-Za-z0-9_-]{12,120}$')
);
CREATE TABLE public.boundary_conflicts_v8 (
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    left_id varchar(100) NOT NULL,
    right_id varchar(100) NOT NULL,
    reason varchar(50) NOT NULL,
    PRIMARY KEY(org_id,left_id,right_id),
    FOREIGN KEY(org_id,left_id) REFERENCES public.meter_boundaries_v8(org_id,id),
    FOREIGN KEY(org_id,right_id) REFERENCES public.meter_boundaries_v8(org_id,id)
);
CREATE INDEX boundary_assets_v8_by_boundary ON public.boundary_assets_v8(org_id,boundary_id);
CREATE INDEX boundary_conflicts_v8_reverse ON public.boundary_conflicts_v8(org_id,right_id,left_id);
ALTER TABLE public.meter_boundaries_v8 OWNER TO hk_owner;
ALTER TABLE public.boundary_assets_v8 OWNER TO hk_owner;
ALTER TABLE public.boundary_conflicts_v8 OWNER TO hk_owner;

ALTER TABLE public.meter_boundaries_v8 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meter_boundaries_v8 FORCE ROW LEVEL SECURITY;
ALTER TABLE public.boundary_assets_v8 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.boundary_assets_v8 FORCE ROW LEVEL SECURITY;
ALTER TABLE public.boundary_conflicts_v8 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.boundary_conflicts_v8 FORCE ROW LEVEL SECURITY;
CREATE POLICY boundary_v8_owner ON public.meter_boundaries_v8 TO hk_owner USING(true) WITH CHECK(true);
CREATE POLICY boundary_v8_app_read ON public.meter_boundaries_v8 FOR SELECT TO hk_app USING (hk_security.allowed(org_id));
CREATE POLICY boundaryasset_v8_owner ON public.boundary_assets_v8 TO hk_owner USING(true) WITH CHECK(true);
CREATE POLICY boundaryasset_v8_app_read ON public.boundary_assets_v8 FOR SELECT TO hk_app USING (hk_security.allowed(org_id));
CREATE POLICY conflict_v8_owner ON public.boundary_conflicts_v8 TO hk_owner USING(true) WITH CHECK(true);
CREATE POLICY conflict_v8_app_read ON public.boundary_conflicts_v8 FOR SELECT TO hk_app USING (hk_security.allowed(org_id));
REVOKE ALL ON TABLE public.meter_boundaries_v8,public.boundary_assets_v8,public.boundary_conflicts_v8 FROM PUBLIC,hk_app;
GRANT SELECT ON public.meter_boundaries_v8,public.boundary_assets_v8,public.boundary_conflicts_v8 TO hk_app;
-- Intentionally NO INSERT/UPDATE/DELETE grants for hk_app on graph tables.

CREATE FUNCTION hk_private.reject_boundary_graph_mutation_v8() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
  RAISE EXCEPTION 'APPEND_ONLY_BOUNDARY_GRAPH_V8' USING ERRCODE='23514';
END $$;
ALTER FUNCTION hk_private.reject_boundary_graph_mutation_v8() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.reject_boundary_graph_mutation_v8() FROM PUBLIC;

CREATE FUNCTION hk_private.freeze_boundary_after_claim_v8() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
  IF EXISTS(SELECT 1 FROM public.benefit_reservations_v79
       WHERE org_id=NEW.org_id) THEN
     RAISE EXCEPTION 'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION hk_private.freeze_boundary_after_claim_v8() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.freeze_boundary_after_claim_v8() FROM PUBLIC;

CREATE TRIGGER boundary_v8_immutable BEFORE UPDATE OR DELETE ON public.meter_boundaries_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_boundary_graph_mutation_v8();
CREATE TRIGGER assignment_v8_immutable BEFORE UPDATE OR DELETE ON public.boundary_assets_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_boundary_graph_mutation_v8();
CREATE TRIGGER conflict_v8_immutable BEFORE UPDATE OR DELETE ON public.boundary_conflicts_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.reject_boundary_graph_mutation_v8();
CREATE TRIGGER boundary_v8_freeze BEFORE INSERT ON public.meter_boundaries_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.freeze_boundary_after_claim_v8();
CREATE TRIGGER assignment_v8_freeze BEFORE INSERT ON public.boundary_assets_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.freeze_boundary_after_claim_v8();
CREATE TRIGGER conflict_v8_freeze BEFORE INSERT ON public.boundary_conflicts_v8
 FOR EACH ROW EXECUTE FUNCTION hk_private.freeze_boundary_after_claim_v8();

-- PG runtime registry is allowed to INSERT V7.9 synthetic reservations, but
-- must serialize transactions competing across DIFFERENT assets/alias keys.
-- This trigger takes a per-tenant physical benefit category advisory lock.
CREATE FUNCTION hk_private.guard_benefit_boundary_v8() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g text; assigned_class text;
BEGIN
  g:= CASE
    WHEN NEW.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE') THEN 'ELECTRIC_ENERGY'
    WHEN NEW.family='HEAT_ENERGY_COST' THEN 'HEAT_ENERGY'
    WHEN NEW.family IN ('MAINTENANCE_COST','RELIABILITY_RISK') THEN 'EQUIPMENT_MAINTENANCE'
    ELSE 'FINANCIAL_PROCESS' END;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(NEW.org_id||':'||g,0));
  SELECT b.quantity_class INTO assigned_class FROM public.boundary_assets_v8 a
    JOIN public.meter_boundaries_v8 b ON b.org_id=a.org_id AND b.id=a.boundary_id
    WHERE a.org_id=NEW.org_id AND a.asset_id=NEW.asset_id;
  IF EXISTS(SELECT 1 FROM public.meter_boundaries_v8 WHERE org_id=NEW.org_id)
    AND NOT EXISTS(SELECT 1 FROM public.boundary_assets_v8
                   WHERE org_id=NEW.org_id AND asset_id=NEW.asset_id) THEN
     RAISE EXCEPTION 'UNMAPPED_PHYSICAL_SCOPE_CANNOT_RESERVE' USING ERRCODE='23514';
  END IF;
  IF assigned_class IS NOT NULL AND assigned_class<>g THEN
     RAISE EXCEPTION 'BOUNDARY_QUANTITY_CLASS_MISMATCH' USING ERRCODE='23514';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.benefit_reservations_v79 x
    WHERE x.org_id=NEW.org_id AND x.start_year<=NEW.end_year AND x.end_year>=NEW.start_year
    AND (x.family=NEW.family
      OR (x.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE')
          AND NEW.family IN ('ELECTRIC_ENERGY_COST','GENERATION_VALUE'))
      OR (x.family IN ('MAINTENANCE_COST','RELIABILITY_RISK')
          AND NEW.family IN ('MAINTENANCE_COST','RELIABILITY_RISK')))
    AND (x.asset_id=NEW.asset_id OR EXISTS (
      SELECT 1 FROM public.boundary_conflicts_v8 c
      JOIN public.boundary_assets_v8 a ON a.org_id=c.org_id AND a.boundary_id=c.left_id
      JOIN public.boundary_assets_v8 b ON b.org_id=c.org_id AND b.boundary_id=c.right_id
      WHERE c.org_id=NEW.org_id AND a.asset_id=NEW.asset_id AND b.asset_id=x.asset_id
    ))
  ) THEN
    RAISE EXCEPTION 'BENEFIT_BOUNDARY_PERIOD_OVERLAP' USING ERRCODE='23P01';
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION hk_private.guard_benefit_boundary_v8() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.guard_benefit_boundary_v8() FROM PUBLIC;
CREATE TRIGGER guard_benefit_boundary_v8 BEFORE INSERT ON public.benefit_reservations_v79
 FOR EACH ROW EXECUTE FUNCTION hk_private.guard_benefit_boundary_v8();

-- PG V8 boundary authoring is intentionally HOLD. A separate authenticated
-- and auditable DBA-only procedure plus concurrency native QA is required.
-- DO NOT substitute this SQL candidate for completed PostgreSQL acceptance.
