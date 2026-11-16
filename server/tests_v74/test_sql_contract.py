"""Static migration checking. These tests are NOT native PostgreSQL acceptance."""
from pathlib import Path
from hydro_api.storage import Base
ROOT=Path(__file__).parents[1]

def test_proposed_pg_rls_is_strict_but_unexecuted():
    sql=(ROOT/'migrations'/'080_research_programme_v74.sql').read_text()
    for key in ('ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY',
        'FOREIGN KEY(org_id,study_id)',
        'FOREIGN KEY(org_id,programme_id,from_study_id)',
        'FOREIGN KEY(org_id,programme_id,to_study_id)',
        'hk_security.allowed(org_id,ARRAY',
        'created_by varchar',
        'hk_private.audit_business_change()',
        'hk_private.reject_mutation()',
        'validate_research_link',
        'validate_research_finance',
        'SYNTHETIC_MAGADAN_RESEARCH_ONLY',
        'cannot_be_used_for_field_approval'):
        assert key in sql,key
    assert 'REFERENCES public.initiatives' not in sql
    assert 'UPDATE public.initiatives' not in sql
    for table in ('research_programmes','research_programme_studies',
                  'research_programme_finance','research_programme_links'):
        assert table in Base.metadata.tables
