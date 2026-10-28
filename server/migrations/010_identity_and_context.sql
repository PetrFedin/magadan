-- Fresh, dedicated HydroKontur database only. Run after 001_schema.sql.
-- Bootstrap connection only; never use hk_owner or a superuser as the API role.
CREATE SCHEMA hk_auth AUTHORIZATION hk_owner;
CREATE SCHEMA hk_private AUTHORIZATION hk_owner;
CREATE SCHEMA hk_security AUTHORIZATION hk_owner;
CREATE SCHEMA hk_crypto AUTHORIZATION hk_owner;
CREATE EXTENSION pgcrypto WITH SCHEMA hk_crypto;
GRANT USAGE ON SCHEMA hk_crypto TO hk_owner;
CREATE TABLE hk_private.secrets (purpose text PRIMARY KEY, secret bytea NOT NULL);
INSERT INTO hk_private.secrets VALUES ('context', hk_crypto.gen_random_bytes(32)), ('audit', hk_crypto.gen_random_bytes(32));
ALTER TABLE hk_private.secrets OWNER TO hk_owner;

CREATE TABLE hk_auth.identities (
 id text PRIMARY KEY, issuer text NOT NULL, subject text NOT NULL,
 user_id text NOT NULL REFERENCES public.users(id), UNIQUE (issuer, subject)
);
CREATE TABLE hk_auth.oidc_transactions (
 state_hash varchar(64) PRIMARY KEY, binding_hash varchar(64) NOT NULL,
 nonce text NOT NULL, verifier text NOT NULL, expires_at bigint NOT NULL, consumed boolean NOT NULL DEFAULT false
);
CREATE TABLE hk_auth.sessions (
 token_hash varchar(64) PRIMARY KEY, user_id text NOT NULL REFERENCES public.users(id),
 token_version bigint NOT NULL, issuer text NOT NULL, subject text NOT NULL,
 auth_time bigint NOT NULL, acr text NOT NULL, csrf_hash varchar(64) NOT NULL,
 expires_at bigint NOT NULL, revoked boolean NOT NULL DEFAULT false
);
CREATE INDEX session_user_idx ON hk_auth.sessions(user_id);
ALTER TABLE hk_auth.identities OWNER TO hk_owner;
ALTER TABLE hk_auth.oidc_transactions OWNER TO hk_owner;
ALTER TABLE hk_auth.sessions OWNER TO hk_owner;
GRANT USAGE ON SCHEMA hk_auth TO hk_authenticator;
GRANT SELECT ON hk_auth.identities TO hk_authenticator;
GRANT SELECT, INSERT, UPDATE ON hk_auth.oidc_transactions, hk_auth.sessions TO hk_authenticator;
GRANT SELECT (id, active, token_version) ON public.users TO hk_authenticator;

CREATE FUNCTION hk_security.bind_session(p_token text, p_org text DEFAULT '')
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_hash text; v_user text; v_payload text; v_sig text; v_key bytea;
BEGIN
 IF length(p_token) NOT BETWEEN 32 AND 256 THEN RAISE EXCEPTION 'INVALID_SESSION' USING ERRCODE='28000'; END IF;
 v_hash := encode(hk_crypto.digest(convert_to(p_token,'UTF8'),'sha256'),'hex');
 SELECT s.user_id INTO v_user FROM hk_auth.sessions s JOIN public.users u ON u.id=s.user_id
 WHERE s.token_hash=v_hash AND NOT s.revoked AND s.expires_at>extract(epoch FROM clock_timestamp())
 AND u.active AND u.token_version=s.token_version;
 IF v_user IS NULL THEN RAISE EXCEPTION 'INVALID_SESSION' USING ERRCODE='28000'; END IF;
 IF coalesce(p_org,'')<>'' AND NOT EXISTS (
  SELECT 1 FROM public.memberships m WHERE m.user_id=v_user AND m.org_id=p_org AND m.active
 ) THEN RAISE EXCEPTION 'TENANT_NOT_ACCESSIBLE' USING ERRCODE='42501'; END IF;
 SELECT secret INTO v_key FROM hk_private.secrets WHERE purpose='context';
 v_payload := jsonb_build_array(v_user,coalesce(p_org,''),v_hash,txid_current(),pg_backend_pid())::text;
 v_sig := encode(hk_crypto.hmac(convert_to(v_payload,'UTF8'),v_key,'sha256'),'hex');
 PERFORM set_config('hk.actor',v_user,true);
 PERFORM set_config('hk.org',coalesce(p_org,''),true);
 PERFORM set_config('hk.session_hash',v_hash,true);
 PERFORM set_config('hk.signature',v_sig,true);
 RETURN v_user;
END $$;
ALTER FUNCTION hk_security.bind_session(text,text) OWNER TO hk_owner;

CREATE FUNCTION hk_security.context() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_actor text; v_org text; v_hash text; v_sig text; v_payload text; v_expected text; v_key bytea; s record;
BEGIN
 v_actor:=nullif(current_setting('hk.actor',true),'');
 v_org:=coalesce(current_setting('hk.org',true),'');
 v_hash:=nullif(current_setting('hk.session_hash',true),'');
 v_sig:=nullif(current_setting('hk.signature',true),'');
 IF v_actor IS NULL OR v_hash IS NULL OR v_sig IS NULL THEN RETURN '{}'::jsonb; END IF;
 SELECT secret INTO v_key FROM hk_private.secrets WHERE purpose='context';
 v_payload:=jsonb_build_array(v_actor,v_org,v_hash,txid_current(),pg_backend_pid())::text;
 v_expected:=encode(hk_crypto.hmac(convert_to(v_payload,'UTF8'),v_key,'sha256'),'hex');
 IF v_sig<>v_expected THEN RETURN '{}'::jsonb; END IF;
 SELECT x.auth_time,x.acr INTO s FROM hk_auth.sessions x JOIN public.users u ON u.id=x.user_id
 WHERE x.token_hash=v_hash AND x.user_id=v_actor AND NOT x.revoked
 AND x.expires_at>extract(epoch FROM statement_timestamp()) AND u.active AND x.token_version=u.token_version;
 IF NOT FOUND THEN RETURN '{}'::jsonb; END IF;
 RETURN jsonb_build_object('user_id',v_actor,'org_id',v_org,'auth_time',s.auth_time,'acr',s.acr);
END $$;
ALTER FUNCTION hk_security.context() OWNER TO hk_owner;

CREATE FUNCTION hk_security.actor() RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
AS $$ SELECT hk_security.context()->>'user_id' $$;
ALTER FUNCTION hk_security.actor() OWNER TO hk_owner;
CREATE FUNCTION hk_security.allowed(p_org text,p_roles text[] DEFAULT NULL) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce((hk_security.context()->>'org_id')=p_org,false) AND EXISTS (
  SELECT 1 FROM public.memberships m WHERE m.org_id=p_org AND m.user_id=hk_security.actor() AND m.active
  AND (p_roles IS NULL OR m.role=ANY(p_roles))
 )
$$;
ALTER FUNCTION hk_security.allowed(text,text[]) OWNER TO hk_owner;
GRANT USAGE ON SCHEMA hk_security TO hk_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_security FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA hk_security TO hk_app;
