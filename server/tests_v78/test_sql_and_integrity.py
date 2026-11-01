"""Static SQL contract: this does NOT count as actual PostgreSQL RLS acceptance."""
from pathlib import Path
from hydro_api.storage import Base

ROOT=Path(__file__).parents[1]

def test_v78_rls_and_immutable_table_contract():
    sql=(ROOT/'migrations'/'120_grid_annual_dcf_v78.sql').read_text()
    for text in [
        'CREATE TABLE public.grid_annual_dossiers_v78',
        'ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY',
        "ARRAY['economist']::text[]",'created_by=hk_security.actor()',
        'grid_dcf_v78_unique_wbs_single_measure','grid_dcf_v78_unique_pair',
        'FOREIGN KEY(org_id,asset_id)',
        'FOREIGN KEY(org_id,programme_id)',
        'hk_private.validate_grid_dcf_v78()',
        'hk_private.reject_mutation()',
        'hk_private.audit_business_change()',
        "industrial_approval_eligible' IS NOT DISTINCT FROM 'false'",
        "source_is_not_third_party_attested' IS NOT DISTINCT FROM 'true'",
        'RESEARCH_ONLY_SINGLE_MEASURE_WBS_MISSING',
    ]:
        assert text in sql,text
    assert 'GRANT UPDATE' not in sql
    assert 'GRANT DELETE' not in sql
    assert 'grid_annual_dossiers_v78' in Base.metadata.tables


def test_v78_migration_sequence_and_native_gate_remains_open():
    files=sorted((ROOT/'migrations').glob('[0-9]*.sql'))
    assert [x.name.split('_')[0] for x in files]==['001','010','020','030','040','050','060','070','080','090','100','110','120','130','140','150','160']
    assert 'NATIVE_ACCEPTANCE_BLOCKED' in (ROOT/'tests_v71'/'test_postgres_native.py').read_text()
