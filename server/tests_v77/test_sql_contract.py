"""SQL structure checks are NOT native PostgreSQL execution."""
from pathlib import Path
from hydro_api.storage import Base

ROOT=Path(__file__).parents[1]

def test_v77_sql_requires_tenant_and_unattested_flags():
    text=(ROOT/'migrations'/'110_reference_comparisons_v77.sql').read_text()
    for term in ('CREATE TABLE public.grid_reference_comparisons_v77',
                 'FOREIGN KEY(org_id,asset_id,study_id)',
                 'ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY',
                 "ARRAY['engineer']::text[]",'created_by=hk_security.actor()',
                 'LAB_NUMERICAL_MATCH_UNATTESTED','industrial_approval_eligible',
                 'external_solver_execution_verified',
                 'hk_private.reject_mutation()', 'hk_private.audit_business_change()'):
        assert term in text,term
    assert 'GRANT UPDATE' not in text and 'GRANT DELETE' not in text
    assert 'INSERT INTO public.initiatives' not in text
    assert 'grid_reference_comparisons_v77' in Base.metadata.tables


def test_last_migration_and_actual_native_gate():
    scripts=sorted((ROOT/'migrations').glob('[0-9]*.sql'))
    assert scripts[-1].name=='160_boundary_claim_serialization_v81.sql'
    native=(ROOT/'tests_v71'/'test_postgres_native.py').read_text()
    assert 'NATIVE_ACCEPTANCE_BLOCKED' in native
    assert 'test_v77_native_grid_reference' in native
