-- V8.1 LAB-ONLY correctness fix for V8 physical-boundary / benefit concurrency.
-- ADDITIVE migration: DO NOT rewrite historical 150_boundary_graph_v8.sql.
-- Run ONLY on dedicated EMPTY / ISOLATED PostgreSQL 17 acceptance environments.
-- NOT industrial approval, not field data, not certified saving.
--
-- Security defect: the V8 boundary insert freeze predicate and benefit insert
-- used DIFFERENT serialization. If concurrent, either could read a snapshot
-- prior to the other's uncommitted INSERT. A post-claim graph change was possible.
--
-- Both triggers now acquire the SAME per-org transaction-scoped advisory lock
-- BEFORE checking the counterparty. All graph mutation and reservation writers
-- MUST use READ COMMITTED; stronger snapshots are rejected until separately
-- proven correct. In PostgreSQL READ COMMITTED, the SELECT after an acquired
-- lock observes the other transaction's committed rows.
--
-- This is a SQL CANDIDATE. Native concurrent PG17 proof is required before
-- claiming the invariant is enforced. An authorized SQL role may still need
-- independent physical-source attestation and separate corporate identity.
CREATE OR REPLACE FUNCTION hk_private.freeze_boundary_after_claim_v8() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'V81_GRAPH_CLAIM_REQUIRES_READ_COMMITTED' USING ERRCODE='25000';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('hk:v81:boundary-claim:org:' || NEW.org_id, 0));
  IF EXISTS(SELECT 1 FROM public.benefit_reservations_v79
       WHERE org_id=NEW.org_id) THEN
     RAISE EXCEPTION 'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
ALTER FUNCTION hk_private.freeze_boundary_after_claim_v8() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.freeze_boundary_after_claim_v8() FROM PUBLIC;

CREATE OR REPLACE FUNCTION hk_private.guard_benefit_boundary_v8() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g text; assigned_class text;
BEGIN
  IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'V81_GRAPH_CLAIM_REQUIRES_READ_COMMITTED' USING ERRCODE='25000';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('hk:v81:boundary-claim:org:' || NEW.org_id, 0));
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
