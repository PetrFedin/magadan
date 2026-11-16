-- V7.4 unaccepted PostgreSQL candidate. NEVER apply to a production database.
-- Dependencies: 001..070; dedicated empty PostgreSQL 17 laboratory database only.
-- These are SYNTHETIC research collections, NOT investment approvals or engineering acceptance.

CREATE TABLE public.research_programmes (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL REFERENCES public.organizations(id),
 reference_code varchar(80) NOT NULL,
 title varchar(180) NOT NULL,
 purpose text NOT NULL,
 capital_input json,
 snapshot json NOT NULL,
 snapshot_sha256 varchar(64) NOT NULL,
 created_by varchar NOT NULL REFERENCES public.users(id),
 created_at timestamptz NOT NULL,
 CONSTRAINT research_programmes_org_id UNIQUE(org_id,id),
 CONSTRAINT research_programmes_org_reference UNIQUE(org_id,reference_code),
 CONSTRAINT research_programme_lab_scope CHECK (
   snapshot::jsonb->>'release'='7.4-LAB_ONLY'
   AND snapshot::jsonb #>> '{screening,scope}'='SYNTHETIC_MAGADAN_RESEARCH_ONLY'
   AND snapshot::jsonb->>'cannot_be_used_for_field_approval'='true'
   AND (capital_input IS NULL OR capital_input::jsonb->>'tax_basis'='EXCL_VAT_SYNTHETIC')
 ),
 CONSTRAINT research_programme_snapshot_size CHECK(octet_length(snapshot::text)<=350000)
);

CREATE TABLE public.research_programme_studies (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL,
 programme_id varchar NOT NULL,
 study_id varchar NOT NULL,
 CONSTRAINT research_programme_study_unique UNIQUE(org_id,programme_id,study_id),
 CONSTRAINT research_programme_study_parent FOREIGN KEY(org_id,programme_id)
  REFERENCES public.research_programmes(org_id,id),
 CONSTRAINT research_programme_study_source FOREIGN KEY(org_id,study_id)
  REFERENCES public.study_runs(org_id,id)
);

CREATE TABLE public.research_programme_finance (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL,
 programme_id varchar NOT NULL,
 dossier_id varchar NOT NULL,
 CONSTRAINT research_programme_finance_unique UNIQUE(org_id,programme_id,dossier_id),
 CONSTRAINT research_programme_finance_parent FOREIGN KEY(org_id,programme_id)
  REFERENCES public.research_programmes(org_id,id),
 CONSTRAINT research_programme_finance_source FOREIGN KEY(org_id,dossier_id)
  REFERENCES public.grid_economic_dossiers(org_id,id)
);

CREATE TABLE public.research_programme_links (
 id varchar PRIMARY KEY,
 org_id varchar NOT NULL,
 programme_id varchar NOT NULL,
 from_study_id varchar NOT NULL,
 to_study_id varchar NOT NULL,
 relationship varchar(70) NOT NULL,
 CONSTRAINT research_programme_link_unique UNIQUE(org_id,programme_id,from_study_id,to_study_id,relationship),
 CONSTRAINT research_programme_link_from FOREIGN KEY(org_id,programme_id,from_study_id)
  REFERENCES public.research_programme_studies(org_id,programme_id,study_id),
 CONSTRAINT research_programme_link_to FOREIGN KEY(org_id,programme_id,to_study_id)
  REFERENCES public.research_programme_studies(org_id,programme_id,study_id),
 CONSTRAINT research_programme_link_no_self CHECK(from_study_id<>to_study_id),
 CONSTRAINT research_programme_link_type CHECK(relationship IN (
   'forecast_context_for_cascade','cascade_context_for_capex','diagnostics_context_for_capex',
   'grid_context_for_capex','heat_context_for_capex'))
);

-- Reject semantic-link spoofing even by a direct hk_app INSERT bypassing HTTP validation.
CREATE FUNCTION hk_private.validate_research_link() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE l record; r record;
BEGIN
 SELECT module,scenario_group INTO l FROM public.study_runs
  WHERE id=NEW.from_study_id AND org_id=NEW.org_id;
 SELECT module,scenario_group INTO r FROM public.study_runs
  WHERE id=NEW.to_study_id AND org_id=NEW.org_id;
 IF l.module IS NULL OR r.module IS NULL OR l.scenario_group IS DISTINCT FROM r.scenario_group THEN
  RAISE EXCEPTION 'UNTRUSTED_CROSS_DOMAIN_SOURCE' USING ERRCODE='23514'; END IF;
 IF NOT (
  (NEW.relationship='forecast_context_for_cascade' AND l.module='hydroforecast' AND r.module='cascade') OR
  (NEW.relationship='cascade_context_for_capex' AND l.module='cascade' AND r.module='hydrocapex') OR
  (NEW.relationship='diagnostics_context_for_capex' AND l.module='turbine' AND r.module='hydrocapex') OR
  (NEW.relationship='grid_context_for_capex' AND l.module='gridloss' AND r.module='hydrocapex') OR
  (NEW.relationship='heat_context_for_capex' AND l.module='heatnet' AND r.module='hydrocapex')
 ) THEN RAISE EXCEPTION 'INCORRECT_SEMANTIC_DIRECTION' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_research_link() OWNER TO hk_owner;

-- Finance memo may only refer to two calculations included in the same research programme.
CREATE FUNCTION hk_private.validate_research_finance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE d record;
BEGIN
 SELECT baseline_run_id,proposed_run_id INTO d FROM public.grid_economic_dossiers
 WHERE id=NEW.dossier_id AND org_id=NEW.org_id;
 IF NOT FOUND OR NOT EXISTS(
  SELECT 1 FROM public.research_programme_studies WHERE org_id=NEW.org_id
   AND programme_id=NEW.programme_id AND study_id=d.baseline_run_id
 ) OR NOT EXISTS(
  SELECT 1 FROM public.research_programme_studies WHERE org_id=NEW.org_id
   AND programme_id=NEW.programme_id AND study_id=d.proposed_run_id
 ) THEN RAISE EXCEPTION 'UNPINNED_FINANCIAL_STUDY_PAIR' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_research_finance() OWNER TO hk_owner;

ALTER TABLE public.research_programmes OWNER TO hk_owner;
ALTER TABLE public.research_programme_studies OWNER TO hk_owner;
ALTER TABLE public.research_programme_finance OWNER TO hk_owner;
ALTER TABLE public.research_programme_links OWNER TO hk_owner;

ALTER TABLE public.research_programmes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_programmes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_studies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_studies FORCE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_finance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_finance FORCE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_programme_links FORCE ROW LEVEL SECURITY;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY[
 'research_programmes','research_programme_studies',
 'research_programme_finance','research_programme_links'] LOOP
  EXECUTE format('CREATE POLICY owner_read_write ON public.%I TO hk_owner USING(true) WITH CHECK(true)',t);
  EXECUTE format('CREATE POLICY application_select ON public.%I FOR SELECT TO hk_app USING(hk_security.allowed(org_id))',t);
  IF t='research_programmes' THEN
   EXECUTE format('CREATE POLICY application_insert ON public.%I FOR INSERT TO hk_app WITH CHECK(hk_security.allowed(org_id,ARRAY[''economist'']::text[]) AND created_by=hk_security.actor())',t);
  ELSE
   EXECUTE format('CREATE POLICY application_insert ON public.%I FOR INSERT TO hk_app WITH CHECK(hk_security.allowed(org_id,ARRAY[''economist'']::text[]))',t);
  END IF;
  EXECUTE format('GRANT SELECT,INSERT ON public.%I TO hk_app',t);
  EXECUTE format('CREATE TRIGGER prevent_mutation BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation()',t);
  EXECUTE format('CREATE TRIGGER record_research_audit AFTER INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change()',t);
 END LOOP;
END $$;
CREATE INDEX research_programme_org_created ON public.research_programmes(org_id,created_at DESC);
CREATE TRIGGER check_research_link BEFORE INSERT ON public.research_programme_links
 FOR EACH ROW EXECUTE FUNCTION hk_private.validate_research_link();
CREATE TRIGGER check_research_finance BEFORE INSERT ON public.research_programme_finance
 FOR EACH ROW EXECUTE FUNCTION hk_private.validate_research_finance();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_private FROM PUBLIC;
-- No grants or foreign keys from research_programmes to public.initiatives.
