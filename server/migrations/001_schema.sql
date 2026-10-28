-- Dedicated empty database. Role passwords must be set out-of-band by bootstrap.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public') THEN
  RAISE EXCEPTION 'REFUSE_NONEMPTY_DATABASE'; END IF;
END $$;
CREATE ROLE hk_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_authenticator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hk_exporter LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO hk_app,hk_authenticator,hk_exporter,hk_owner;


CREATE TABLE organizations (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	audit_seq INTEGER NOT NULL, 
	audit_tip VARCHAR NOT NULL, 
	PRIMARY KEY (id)
)

;
ALTER TABLE public.organizations OWNER TO hk_owner;

CREATE TABLE users (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash TEXT NOT NULL, 
	active BOOLEAN NOT NULL, 
	token_version INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

;
ALTER TABLE public.users OWNER TO hk_owner;
CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE assets (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	classification VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id)
)

;
ALTER TABLE public.assets OWNER TO hk_owner;
CREATE INDEX ix_assets_org_id ON assets (org_id);

CREATE TABLE audit_events (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	seq INTEGER NOT NULL, 
	actor_id VARCHAR NOT NULL, 
	event_type VARCHAR NOT NULL, 
	object_type VARCHAR NOT NULL, 
	object_id VARCHAR NOT NULL, 
	payload JSON NOT NULL, 
	previous_hash VARCHAR(64) NOT NULL, 
	event_hash VARCHAR(64) NOT NULL, 
	timestamp_ms BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_seq UNIQUE (org_id, seq), 
	FOREIGN KEY(org_id) REFERENCES organizations (id)
)

;
ALTER TABLE public.audit_events OWNER TO hk_owner;
CREATE INDEX ix_audit_events_org_id ON audit_events (org_id);

CREATE TABLE memberships (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_user UNIQUE (org_id, user_id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;
ALTER TABLE public.memberships OWNER TO hk_owner;
CREATE INDEX ix_memberships_user_id ON memberships (user_id);
CREATE INDEX ix_memberships_org_id ON memberships (org_id);

CREATE TABLE evidence (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	asset_id VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	source_ref VARCHAR NOT NULL, 
	payload JSON NOT NULL, 
	content_sha256 VARCHAR(64) NOT NULL, 
	created_by VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;
ALTER TABLE public.evidence OWNER TO hk_owner;
CREATE INDEX ix_evidence_org_id ON evidence (org_id);

CREATE TABLE model_versions (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	asset_id VARCHAR NOT NULL, 
	algorithm VARCHAR NOT NULL, 
	params JSON NOT NULL, 
	content_sha256 VARCHAR(64) NOT NULL, 
	created_by VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;
ALTER TABLE public.model_versions OWNER TO hk_owner;
CREATE INDEX ix_model_versions_org_id ON model_versions (org_id);

CREATE TABLE calculation_runs (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	asset_id VARCHAR NOT NULL, 
	model_id VARCHAR NOT NULL, 
	evidence_id VARCHAR NOT NULL, 
	input_sha256 VARCHAR(64) NOT NULL, 
	result_sha256 VARCHAR(64) NOT NULL, 
	result JSON NOT NULL, 
	created_by VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id), 
	FOREIGN KEY(model_id) REFERENCES model_versions (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;
ALTER TABLE public.calculation_runs OWNER TO hk_owner;
CREATE INDEX ix_calculation_runs_org_id ON calculation_runs (org_id);

CREATE TABLE evidence_reviews (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	evidence_id VARCHAR NOT NULL, 
	actor_id VARCHAR NOT NULL, 
	accepted BOOLEAN NOT NULL, 
	note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
ALTER TABLE public.evidence_reviews OWNER TO hk_owner;
CREATE INDEX ix_evidence_reviews_org_id ON evidence_reviews (org_id);

CREATE TABLE model_reviews (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	model_id VARCHAR NOT NULL, 
	actor_id VARCHAR NOT NULL, 
	accepted BOOLEAN NOT NULL, 
	note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(model_id) REFERENCES model_versions (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
ALTER TABLE public.model_reviews OWNER TO hk_owner;
CREATE INDEX ix_model_reviews_org_id ON model_reviews (org_id);

CREATE TABLE initiatives (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	asset_id VARCHAR NOT NULL, 
	run_id VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	effect_key VARCHAR NOT NULL, 
	state VARCHAR NOT NULL, 
	revision INTEGER NOT NULL, 
	created_by VARCHAR NOT NULL, 
	engineer_approver VARCHAR, 
	finance_approver VARCHAR, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_effect UNIQUE (org_id, effect_key), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(asset_id) REFERENCES assets (id), 
	FOREIGN KEY(run_id) REFERENCES calculation_runs (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;
ALTER TABLE public.initiatives OWNER TO hk_owner;
CREATE INDEX ix_initiatives_org_id ON initiatives (org_id);

CREATE TABLE initiative_evidence (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	initiative_id VARCHAR NOT NULL, 
	evidence_id VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_initiative_evidence UNIQUE (initiative_id, evidence_id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(initiative_id) REFERENCES initiatives (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id)
)

;
ALTER TABLE public.initiative_evidence OWNER TO hk_owner;
CREATE INDEX ix_initiative_evidence_org_id ON initiative_evidence (org_id);

CREATE TABLE transitions (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	initiative_id VARCHAR NOT NULL, 
	from_state VARCHAR NOT NULL, 
	to_state VARCHAR NOT NULL, 
	revision INTEGER NOT NULL, 
	actor_id VARCHAR NOT NULL, 
	audit_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES organizations (id), 
	FOREIGN KEY(initiative_id) REFERENCES initiatives (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
ALTER TABLE public.transitions OWNER TO hk_owner;
CREATE INDEX ix_transitions_org_id ON transitions (org_id);
