"""Static/schema tests: do not count these as actual RLS enforcement tests."""
from pathlib import Path
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from hydro_api.storage import Base

ROOT=Path(__file__).resolve().parents[1]/'migrations'

def test_timestamp_is_bigint_for_postgresql():
    ddl=str(CreateTable(Base.metadata.tables['audit_events']).compile(dialect=postgresql.dialect()))
    assert 'timestamp_ms BIGINT NOT NULL' in ddl


def test_every_current_table_has_force_rls_statement():
    ddl="\n".join(p.read_text() for p in sorted(ROOT.glob("[0-9]*.sql")))
    for name in Base.metadata.tables:
        assert f'ALTER TABLE public.{name} FORCE ROW LEVEL SECURITY;' in ddl


def test_runtime_role_cannot_create_or_bypass():
    ddl=(ROOT/'001_schema.sql').read_text()
    assert 'hk_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS' in ddl
    assert 'REVOKE CREATE ON SCHEMA public FROM PUBLIC' in ddl


def test_context_is_transaction_bound_not_plain_org():
    sql=(ROOT/'010_identity_and_context.sql').read_text()
    for term in ['txid_current()', 'pg_backend_pid()', 'hk_crypto.hmac', 's.expires_at', 'u.token_version=s.token_version']:
        assert term in sql
    assert "set_config('hk.signature',v_sig,true)" in sql


def test_composite_links_and_single_review_present():
    sql=(ROOT/'020_rls_and_links.sql').read_text()
    assert 'FOREIGN KEY(org_id,asset_id,model_id)' in sql
    assert 'FOREIGN KEY(org_id,asset_id,evidence_id)' in sql
    assert 'FOREIGN KEY(org_id,asset_id,run_id)' in sql
    assert 'UNIQUE(org_id,evidence_id)' in sql


def test_outbox_is_created_with_event_and_not_editable_by_app():
    sql=(ROOT/'030_audit_and_workflow.sql').read_text()
    assert 'INSERT INTO public.audit_outbox' in sql
    assert 'FOR UPDATE' in sql
    assert 'SKIP LOCKED' not in sql # queue claim belongs to the worker, not append trigger
    assert 'GRANT UPDATE' in sql and 'TO hk_exporter' in sql
    assert 'GRANT UPDATE ON public.audit_outbox TO hk_app' not in sql


def test_local_receipt_not_production_policy():
    sql=(ROOT/'040_seal_policy.sql').read_text()
    assert 'require_compliance boolean NOT NULL DEFAULT true' in sql
    assert "IS DISTINCT FROM 'COMPLIANCE'" in sql


def test_database_requires_authenticated_external_receipt():
    sql=(ROOT/'050_receipt_authenticity.sql').read_text()
    for fragment in ('hk_crypto.hmac','UNAUTHENTICATED_AUDIT_RECEIPT',"body->'sealed_event' IS DISTINCT FROM env",'BEFORE INSERT ON public.audit_receipts'):
        assert fragment in sql
