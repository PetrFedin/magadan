"""Native PostgreSQL 17 acceptance for V8.1 trigger serialization.

NOT a SQLite substitute. Disabled unless a dedicated native configuration is
provided. These tests are necessary but not sufficient for production approval;
full concurrent benefit-source creation and independent DBA review remain gates.
"""
from __future__ import annotations
import os
from uuid import uuid4
import pytest

if not os.environ.get('HYDRO_NATIVE_CONFIG'):
    if os.environ.get('HYDRO_NATIVE_TESTS_REQUIRED') == '1':
        raise RuntimeError('NATIVE_ACCEPTANCE_BLOCKED: dedicated PostgreSQL 17 config missing')
    pytest.skip('NATIVE_POSTGRES17_UNAVAILABLE; SQL static tests are NOT native acceptance',
                allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests_v71.test_postgres_native import n, native  # noqa: F401: pytest fixture dependencies

pytestmark = pytest.mark.native_pg
LOCK_PREFIX='hk:v81:boundary-claim:org:'


def test_native_installed_version_and_exact_lock_contract(n):
    with n['admin'].connect() as db:
        assert int(db.scalar(text('SHOW server_version_num'))) >= 170000
        for name in ('freeze_boundary_after_claim_v8', 'guard_benefit_boundary_v8'):
            definition=db.scalar(text('''
              SELECT pg_get_functiondef(p.oid) FROM pg_proc p
              JOIN pg_namespace s ON s.oid=p.pronamespace
              WHERE s.nspname='hk_private' AND p.proname=:name'''),{'name':name})
            assert definition and "'hk:v81:boundary-claim:org:'" in definition
            assert "pg_advisory_xact_lock" in definition
            assert "V81_GRAPH_CLAIM_REQUIRES_READ_COMMITTED" in definition


def test_native_graph_write_locks_org_until_commit(n):
    bid='SYNTHETIC-V81-'+uuid4().hex[:12]
    org=n['org']
    sql='''INSERT INTO public.meter_boundaries_v8
     (org_id,id,quantity_class,source_ref,created_by)
     VALUES (:org,:id,'ELECTRIC_ENERGY',:source,:actor)'''
    params={'org':org,'id':bid,
            'source':'SYNTHETIC-V81-FIELD-NOT-ATTESTED-'+uuid4().hex[:8],
            'actor':n['ids']['engineer']}
    with n['admin'].begin() as holder:
        holder.execute(text(sql),params)
        with n['admin'].begin() as other:
            # Non-blocking attempt proves another session already holds the
            # same transaction lock a benefit reservation must obtain.
            acquired=other.scalar(text('SELECT pg_try_advisory_xact_lock('
                'pg_catalog.hashtextextended(:key,0))'),
                {'key':LOCK_PREFIX+org})
            assert acquired is False, 'Graph writer did not acquire the org lock'
            # A different tenant must not contend for the same scoped key.
            other_org=other.scalar(text('SELECT pg_try_advisory_xact_lock('
                'pg_catalog.hashtextextended(:key,0))'),
                {'key':LOCK_PREFIX+n['other']})
            assert other_org is True, 'Another org acquired an identical lock key'
    with n['admin'].begin() as after_commit:
        assert after_commit.scalar(text('SELECT pg_try_advisory_xact_lock('
             'pg_catalog.hashtextextended(:key,0))'),{'key':LOCK_PREFIX+org}) is True


def test_native_graph_authoring_rejects_repeatable_read(n):
    with pytest.raises(DBAPIError,match='V81_GRAPH_CLAIM_REQUIRES_READ_COMMITTED'):
        with n['admin'].begin() as db:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            db.execute(text('''INSERT INTO public.meter_boundaries_v8
               (org_id,id,quantity_class,source_ref,created_by)
               VALUES (:org,:id,'ELECTRIC_ENERGY',:source,:actor)'''),{
                'org':n['org'],'id':'SYNTHETIC-V81-'+uuid4().hex[:12],
                'source':'SYNTHETIC-V81-NO-FIELD-ATTESTATION-'+uuid4().hex[:8],
                'actor':n['ids']['engineer']})


def test_native_runtime_role_cannot_insert_graph(n):
    from tests_v71.test_postgres_native import bind
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as db:
            bind(db,n,'engineer')
            db.execute(text("""INSERT INTO public.meter_boundaries_v8
                  (org_id,id,quantity_class,source_ref,created_by)
                  VALUES (:org,:id,'ELECTRIC_ENERGY',:source,:actor)"""),{
                'org':n['org'],'id':'SYNTHETIC-V81-'+uuid4().hex[:12],
                'source':'SYNTHETIC-V81-NO-FIELD-ATTESTATION-'+uuid4().hex[:8],
                'actor':n['ids']['engineer']})
