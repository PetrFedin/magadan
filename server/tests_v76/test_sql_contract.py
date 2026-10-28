"""Static contract only. NOT PostgreSQL native acceptance."""
from pathlib import Path
from hydro_api.storage import Base

ROOT=Path(__file__).parents[1]

def test_sql_tenant_rls_schema_and_research_only_gates():
    source=(ROOT/'migrations'/'100_assurance_pack_v76.sql').read_text()
    for token in (
        'CREATE TABLE public.assurance_packs_v76',
        'FOREIGN KEY (org_id,programme_id)',
        'UNIQUE (org_id,benefit_key)',
        'UNIQUE (org_id,programme_id,source_bundle_sha256)',
        'ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY',
        "hk_security.allowed(org_id,ARRAY['economist']",
        'created_by=hk_security.actor()',
        'RESEARCH_REVIEW_ONLY_NOT_AN_APPROVED_INVESTMENT',
        'industrial_approval_eligible',
        'ASSURANCE_UNVERIFIED_HANDOFF_SOURCE',
        'hk_private.reject_mutation()',
        'hk_private.audit_business_change()',
    ):
        assert token in source, token
    assert 'assurance_packs_v76' in Base.metadata.tables
    assert 'GRANT UPDATE' not in source and 'GRANT DELETE' not in source
    assert 'REFERENCES public.initiatives' not in source
    assert 'INSERT INTO public.initiatives' not in source


def test_migration_order_and_native_acceptance_blocked_by_default():
    paths=sorted((ROOT/'migrations').glob('[0-9]*.sql'))
    assert paths[-1].name=='150_boundary_graph_v8.sql'
    assert [p.name.split('_')[0] for p in paths]==['001','010','020','030','040','050','060','070','080','090','100','110','120','130','140','150']
    native=(ROOT/'tests_v71'/'test_postgres_native.py').read_text()
    assert 'NATIVE_ACCEPTANCE_BLOCKED' in native
    assert 'test_v76_native_assurance' in native
