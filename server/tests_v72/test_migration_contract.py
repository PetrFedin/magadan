"""SQL structure checks are not proof of actual Postgres enforcement."""
from pathlib import Path
from hydro_api.storage import Base
ROOT=Path(__file__).resolve().parents[1]/'migrations'

def test_studies_table_protected_by_native_policy_and_immutable_trigger():
    sql=(ROOT/'060_studies_v72.sql').read_text()
    for fragment in ['CREATE TABLE public.study_runs',
        'FORCE ROW LEVEL SECURITY','hk_security.allowed(org_id',
        'FOREIGN KEY (org_id,asset_id)','study_runs_immutable',
        "source_ref LIKE 'SYNTHETIC-%'",'hk_private.audit_business_change()']:
        assert fragment in sql
    assert 'study_runs' in Base.metadata.tables

def test_migrations_are_monotonically_ordered_and_no_drop_statements():
    paths=sorted(ROOT.glob('[0-9]*.sql'))
    assert paths[-1].name=='150_boundary_graph_v8.sql'
    for p in paths:
        assert 'DROP TABLE' not in p.read_text().upper()
