"""V8.1 SQL-candidate contract. STATIC ONLY, NOT native PG acceptance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / 'server' / 'migrations' / '160_boundary_claim_serialization_v81.sql'
SOURCE = ROOT / 'server' / 'migrations' / '150_boundary_graph_v8.sql'
KEY = "'hk:v81:boundary-claim:org:' || NEW.org_id"


def _block(name: str) -> str:
    sql = SQL.read_text(encoding='utf-8')
    found = re.search(r'CREATE OR REPLACE FUNCTION hk_private\.' + name +
                      r'\(\) RETURNS trigger\s+LANGUAGE plpgsql SECURITY DEFINER '
                      r'SET search_path=pg_catalog AS \$\$(.*?)END \$\$;', sql, re.S)
    assert found, f'Missing updated trigger function: {name}'
    return found.group(1)


def test_all_graph_and_claim_writers_share_same_pg_transaction_lock():
    freeze = _block('freeze_boundary_after_claim_v8')
    guard = _block('guard_benefit_boundary_v8')
    for func in (freeze, guard):
        assert func.count(KEY) == 1
        assert 'pg_advisory_xact_lock' in func
        assert 'hashtextextended' in func
        assert func.index('pg_advisory_xact_lock') < func.index('SELECT ' if func is guard else 'IF EXISTS')
        assert "pg_catalog.current_setting('transaction_isolation') <> 'read committed'" in func
        assert "V81_GRAPH_CLAIM_REQUIRES_READ_COMMITTED" in func
        assert "ERRCODE='25000'" in func
    assert freeze.index(KEY) < freeze.index('benefit_reservations_v79')
    assert guard.index(KEY) < guard.index('g:= CASE')
    assert guard.index(KEY) < guard.index('boundary_assets_v8')


def test_historical_v8_migration_is_unchanged():
    src = SOURCE.read_bytes()
    manifest = json.loads((ROOT / 'MANIFEST_SHA256_V8.json').read_text())
    assert hashlib.sha256(src).hexdigest() == manifest['files']['server/migrations/150_boundary_graph_v8.sql']
    assert 'guard_benefit_boundary_v8' in src.decode()
    assert 'CREATE OR REPLACE FUNCTION' not in src.decode()


def test_migration_is_additive_and_role_permissions_do_not_expand():
    text = SQL.read_text(encoding='utf-8')
    assert text.count('CREATE OR REPLACE FUNCTION hk_private.') == 2
    assert text.count('ALTER FUNCTION hk_private.') == 2
    assert text.count('REVOKE ALL ON FUNCTION hk_private.') == 2
    for banned in ('DROP TABLE', 'ALTER TABLE', 'GRANT INSERT', 'GRANT UPDATE', 'GRANT DELETE',
                   'DISABLE ROW LEVEL SECURITY', 'BYPASSRLS', 'TRUNCATE'):
        # security notes may mention tokens, so test executable statements only
        commands=[line.strip().upper() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('--')]
        assert not any(line.startswith(banned) for line in commands), banned
    assert 'NOT industrial approval' in text


def test_migration_chain_and_bootstrap_run_every_file():
    paths = sorted((ROOT / 'server' / 'migrations').glob('[0-9]*.sql'))
    assert [p.name[:3] for p in paths] == [f'{n:03}' for n in [1,10,20,30,40,50,60,70,80,90,100,110,120,130,140,150,160]]
    assert paths[-1].name == '160_boundary_claim_serialization_v81.sql'
    bootstrap = (ROOT / 'scripts' / 'bootstrap_native.py').read_text()
    assert "sorted((root/'server'/'migrations').glob('*.sql'))" in bootstrap
    assert "if count:raise SystemExit('Refusing a non-empty database')" in bootstrap


def test_no_pg_native_pass_without_native_server():
    # An offline SQL string test must never masquerade as a live PostgreSQL pass.
    assert not (ROOT / 'artifacts_v81' / 'PG_NATIVE_ACCEPTED.json').exists()
