"""SQL source checks only; NOT native PG RLS acceptance."""
from pathlib import Path
from hydro_api.storage import Base
ROOT=Path(__file__).parents[1]

def test_handoff_migration_contains_multitenant_rls_and_immutable_triggers():
    sql=(ROOT/'migrations'/'090_calculation_handoffs_v75.sql').read_text()
    for text in ('CREATE TABLE public.research_handoffs',
       'ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY',
       'hk_security.allowed(org_id,ARRAY',
       'created_by=hk_security.actor()',
       'FOREIGN KEY (org_id,left_study_id)',
       'FOREIGN KEY (org_id,right_study_id)',
       'FOREIGN KEY (org_id,programme_id)',
       'HANDOFF_SOURCES_NOT_IN_PROGRAMME',
       'hand_offs_are_not_used_this_is_sentinel' if False else 'validate_handoff_sources',
       'hk_private.audit_business_change()',
       'hk_private.reject_mutation()',
       'industrial_approval_eligible',
       'created_at timestamptz'):
        assert text in sql,text
    assert 'REFERENCES public.initiatives' not in sql
    assert 'GRANT UPDATE' not in sql and 'GRANT DELETE' not in sql
    assert 'research_handoffs' in Base.metadata.tables

def test_sql_native_acceptance_has_explicit_blocking_status():
    code=(ROOT/'tests_v71'/'test_postgres_native.py').read_text()
    assert 'NATIVE_ACCEPTANCE_BLOCKED' in code
    assert 'test_v75_handoff_isolation_and_append_only' in code
