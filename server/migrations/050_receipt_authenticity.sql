-- Exporter credentials alone must not be sufficient to forge external sealing.
-- This key is shared only by the audit receiver and this protected DB function.
-- It is NOT the transport bearer secret, OIDC key, or ordinary API secret.
INSERT INTO hk_private.secrets(purpose,secret) VALUES('receipt',hk_crypto.gen_random_bytes(32));
CREATE FUNCTION hk_private.verify_receipt_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE k bytea; raw bytea; body jsonb; e record; env jsonb; expected text;
BEGIN
 SELECT secret INTO k FROM hk_private.secrets WHERE purpose='receipt';
 raw:=decode(NEW.receipt->'db_attestation'->>'payload_b64','base64');
 expected:=encode(hk_crypto.hmac(raw,k,'sha256'),'hex');
 IF expected IS NULL OR expected IS DISTINCT FROM NEW.receipt->'db_attestation'->>'mac' THEN
  RAISE EXCEPTION 'UNAUTHENTICATED_AUDIT_RECEIPT' USING ERRCODE='23514'; END IF;
 body:=convert_from(raw,'UTF8')::jsonb;
 IF body IS DISTINCT FROM NEW.receipt->'receipt' THEN RAISE EXCEPTION 'RECEIPT_BODY_MISMATCH' USING ERRCODE='23514'; END IF;
 SELECT * INTO e FROM public.audit_events WHERE id=NEW.event_id AND org_id=NEW.org_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_EVENT_NOT_FOUND' USING ERRCODE='23503'; END IF;
 env:=jsonb_build_object('schema_version','hk-audit-v1','event_id',e.id,'org_id',e.org_id,'seq',e.seq,
  'event_hash',e.event_hash,'previous_hash',e.previous_hash,'actor_id',e.actor_id,'event_type',e.event_type,
  'object_type',e.object_type,'object_id',e.object_id,'payload',e.payload::jsonb,'timestamp_ms',e.timestamp_ms);
 IF body->'sealed_event' IS DISTINCT FROM env OR body->>'event_id' IS DISTINCT FROM e.id
 OR body->>'org_id' IS DISTINCT FROM e.org_id OR body->>'event_hash' IS DISTINCT FROM e.event_hash
 OR NEW.event_hash IS DISTINCT FROM e.event_hash OR NEW.envelope_sha256 IS DISTINCT FROM body->>'envelope_sha256'
 OR body->>'retention_mode' IS NULL OR body->>'retention_mode' NOT IN ('COMPLIANCE','LAB_FILE')
 OR body->>'version_id' IS NULL OR body->>'object_key' IS NULL OR body->>'retention_until' IS NULL
 THEN RAISE EXCEPTION 'RECEIPT_BINDING_MISMATCH' USING ERRCODE='23514'; END IF;
 IF (body->>'retention_until')::timestamptz<=clock_timestamp() THEN
  RAISE EXCEPTION 'RECEIPT_RETENTION_EXPIRED' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION hk_private.verify_receipt_insert() OWNER TO hk_owner;
CREATE TRIGGER authenticated_receipt BEFORE INSERT ON public.audit_receipts FOR EACH ROW EXECUTE FUNCTION hk_private.verify_receipt_insert();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_private FROM PUBLIC;
