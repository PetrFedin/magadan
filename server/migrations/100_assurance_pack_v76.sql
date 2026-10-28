-- V7.6 CANDIDATE FOR A NEW EMPTY PostgreSQL 17 TEST CLUSTER.
-- Not executed or native accepted in this session. Apply strictly after 001..090.
-- This table NEVER authorizes construction, dispatch, SCADA or financial disbursements.
CREATE TABLE public.assurance_packs_v76 (
    id varchar PRIMARY KEY,
    org_id varchar NOT NULL REFERENCES public.organizations(id),
    programme_id varchar NOT NULL,
    reference_code varchar(100) NOT NULL,
    benefit_key varchar(100) NOT NULL,
    source_bundle_sha256 varchar(64) NOT NULL,
    input_payload json NOT NULL,
    input_sha256 varchar(64) NOT NULL,
    snapshot json NOT NULL,
    snapshot_sha256 varchar(64) NOT NULL,
    engine_sha256 varchar(64) NOT NULL,
    created_by varchar NOT NULL REFERENCES public.users(id),
    created_at timestamptz NOT NULL,
    CONSTRAINT assurance_tenant_id_v76 UNIQUE (org_id,id),
    CONSTRAINT assurance_reference_v76 UNIQUE (org_id,reference_code),
    CONSTRAINT assurance_benefit_v76 UNIQUE (org_id,benefit_key),
    CONSTRAINT assurance_bundle_v76 UNIQUE (org_id,programme_id,source_bundle_sha256),
    CONSTRAINT assurance_parent_fk_v76 FOREIGN KEY (org_id,programme_id)
        REFERENCES public.research_programmes(org_id,id),
    CONSTRAINT assurance_synthetic_status_v76 CHECK (
        snapshot::jsonb->>'release'='7.6-LAB'
        AND snapshot::jsonb->>'status'='RESEARCH_REVIEW_ONLY_NOT_AN_APPROVED_INVESTMENT'
        AND snapshot::jsonb->>'industrial_approval_eligible'='false'
        AND input_payload::jsonb->>'scope'='SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'
        AND snapshot::jsonb->>'org_id'=org_id
        AND snapshot::jsonb->>'programme_id'=programme_id
        AND snapshot::jsonb->>'reference_code'=reference_code
        AND snapshot::jsonb->>'source_bundle_sha256'=source_bundle_sha256
        AND input_payload::jsonb->>'programme_id'=programme_id
        AND input_payload::jsonb->>'reference_code'=reference_code
        AND input_payload::jsonb #>> '{finance,benefit_key}'=benefit_key
    ),
    CONSTRAINT assurance_sha_format_v76 CHECK (
        input_sha256 ~ '^[a-f0-9]{64}$'
        AND snapshot_sha256 ~ '^[a-f0-9]{64}$'
        AND engine_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT assurance_size_bound_v76 CHECK (
        octet_length(snapshot::text)<=375000 AND octet_length(input_payload::text)<=75000)
);
ALTER TABLE public.assurance_packs_v76 OWNER TO hk_owner;
ALTER TABLE public.assurance_packs_v76 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assurance_packs_v76 FORCE ROW LEVEL SECURITY;
CREATE POLICY assurance_owner_v76 ON public.assurance_packs_v76 TO hk_owner
    USING(true) WITH CHECK(true);
CREATE POLICY assurance_read_v76 ON public.assurance_packs_v76 FOR SELECT TO hk_app
    USING(hk_security.allowed(org_id));
CREATE POLICY assurance_insert_v76 ON public.assurance_packs_v76 FOR INSERT TO hk_app
    WITH CHECK(hk_security.allowed(org_id,ARRAY['economist']::text[]) AND created_by=hk_security.actor());
GRANT SELECT, INSERT ON public.assurance_packs_v76 TO hk_app;
CREATE INDEX assurance_org_created_v76 ON public.assurance_packs_v76(org_id,created_at DESC);

-- SECURITY DEFINER trigger is an additional cross-record check, not substitute for service replay.
CREATE FUNCTION hk_private.validate_assurance_v76() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE parent record; h_id text;
BEGIN
    SELECT org_id,capital_input,snapshot,snapshot_sha256 INTO parent
    FROM public.research_programmes
    WHERE org_id=NEW.org_id AND id=NEW.programme_id;
    IF NOT FOUND OR parent.capital_input IS NULL THEN
        RAISE EXCEPTION 'ASSURANCE_MISSING_PARENT_WBS' USING ERRCODE='23514';
    END IF;
    IF parent.snapshot::jsonb->>'cannot_be_used_for_field_approval' IS DISTINCT FROM 'true'
       OR parent.snapshot::jsonb->>'capital' IS NULL
       OR NEW.snapshot::jsonb->>'programme_sha256' IS DISTINCT FROM parent.snapshot_sha256 THEN
        RAISE EXCEPTION 'ASSURANCE_PARENT_VERSION_OR_SCOPE_INVALID' USING ERRCODE='23514';
    END IF;
    FOR h_id IN SELECT jsonb_array_elements_text(NEW.input_payload::jsonb->'handoff_ids') LOOP
        IF NOT EXISTS(SELECT 1 FROM public.research_handoffs h
                      WHERE h.org_id=NEW.org_id AND h.id=h_id AND h.programme_id=NEW.programme_id
                        AND h.snapshot::jsonb->>'industrial_approval_eligible'='false') THEN
            RAISE EXCEPTION 'ASSURANCE_UNVERIFIED_HANDOFF_SOURCE' USING ERRCODE='23514';
        END IF;
    END LOOP;
    IF jsonb_array_length(NEW.input_payload::jsonb->'handoff_ids')<1 THEN
        RAISE EXCEPTION 'ASSURANCE_SOURCES_REQUIRED' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
ALTER FUNCTION hk_private.validate_assurance_v76() OWNER TO hk_owner;
REVOKE ALL ON FUNCTION hk_private.validate_assurance_v76() FROM PUBLIC;
CREATE TRIGGER assurance_validate_parent_v76 BEFORE INSERT ON public.assurance_packs_v76
  FOR EACH ROW EXECUTE FUNCTION hk_private.validate_assurance_v76();
CREATE TRIGGER assurance_prevent_mutation_v76 BEFORE UPDATE OR DELETE ON public.assurance_packs_v76
  FOR EACH ROW EXECUTE FUNCTION hk_private.reject_mutation();
CREATE TRIGGER assurance_audit_insert_v76 AFTER INSERT ON public.assurance_packs_v76
  FOR EACH ROW EXECUTE FUNCTION hk_private.audit_business_change();
-- No INSERT/UPDATE/DELETE from this table to public.initiatives: deliberately no approval bridge.
