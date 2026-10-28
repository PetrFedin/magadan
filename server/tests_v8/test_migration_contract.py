from pathlib import Path

def test_v8_candidate_sql_has_separate_db_guard_and_no_writes_for_app():
    root=Path(__file__).resolve().parents[1]
    sql=(root/'migrations'/'150_boundary_graph_v8.sql').read_text()
    for token in ('FORCE ROW LEVEL SECURITY','guard_benefit_boundary_v8',
                  'pg_advisory_xact_lock','hashtextextended','hk_security.allowed',
                  'BENEFIT_BOUNDARY_PERIOD_OVERLAP','boundary_conflicts_v8',
                  'NO INSERT/UPDATE/DELETE grants','APPEND_ONLY_BOUNDARY_GRAPH_V8'):
        assert token in sql
    assert 'GRANT INSERT' not in sql
    assert 'DROP TABLE' not in sql


def test_native_postgres_is_not_mislabeled_accepted():
    assert not (Path(__file__).resolve().parents[2]/'artifacts_v8'/'PG_NATIVE_PASS.json').exists()
