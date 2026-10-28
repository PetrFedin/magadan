"""NATIVE, not mocked, acceptance of V7.8 on a DEDICATED PostgreSQL 17 DB.

Normal pytest run explicitly skips this module. Required mode without a real
configuration exits nonzero with NATIVE_ACCEPTANCE_BLOCKED.
"""
from __future__ import annotations
import os, copy
import pytest

if not os.environ.get('HYDRO_NATIVE_CONFIG'):
    if os.environ.get('HYDRO_NATIVE_TESTS_REQUIRED')=='1':
        raise RuntimeError('NATIVE_ACCEPTANCE_BLOCKED: HYDRO_NATIVE_CONFIG missing')
    pytest.skip('Dedicated PostgreSQL config absent: no native V7.8 RLS PASS', allow_module_level=True)
try:
    import psycopg  # noqa: F401
except ImportError:
    if os.environ.get('HYDRO_NATIVE_TESTS_REQUIRED')=='1':
        raise RuntimeError('NATIVE_ACCEPTANCE_BLOCKED: psycopg driver absent')
    pytest.skip('psycopg missing: no native V7.8 RLS PASS', allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests_v71.test_postgres_native import native, n, bind
from tests_v73.test_radial_and_finance import feeder
from tests_v78.test_grid_dcf_domain import wbs, dcf
pytestmark=pytest.mark.native_pg


def test_v78_real_postgres_rls_owner_and_privileges(n):
    with n['admin'].connect() as connection:
        row=connection.execute(text('''
           SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname
             FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
            WHERE c.oid='public.grid_annual_dossiers_v78'::regclass
        ''')).one()
        assert tuple(row)==(True,True,'hk_owner')
        assert connection.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname='hk_app'")) is False
        assert connection.scalar(text("SELECT has_table_privilege('hk_app','public.grid_annual_dossiers_v78','UPDATE')")) is False
        assert connection.scalar(text("SELECT has_table_privilege('hk_app','public.grid_annual_dossiers_v78','DELETE')")) is False
        assert connection.scalar(text("SELECT has_table_privilege('hk_app','public.grid_annual_dossiers_v78','TRUNCATE')")) is False
        assert connection.scalar(text("SELECT COUNT(*) FROM pg_policies WHERE tablename='grid_annual_dossiers_v78'"))>=3


def test_v78_real_postgres_full_dossier_and_tenant_barrier(n):
    c=n['client']; h=n['h'];org=n['org']; asset=n['asset']
    case=feeder(); alt=copy.deepcopy(case);alt['nodes'][0]['r_ohm_per_phase']=0.13
    studies=[]
    for entry in (case,alt):
        r=c.post(f'/v73/orgs/{org}/radial-runs',headers=h('engineer'),json={
          'asset_id':asset,'scenario_group':'native_v78_identical_baseline',
          'source_ref':'SYNTHETIC-V78-NATIVE-ONLY','case':entry})
        assert r.status_code==201,r.text
        studies.append(r.json()['run_id'])
    p=c.post(f'/v74/orgs/{org}/programmes',headers=h('economist'),json={
        'reference_code':'LAB-V78-NATIVE-ONE-WBS','title':'Native security test for one synthetic feeder',
        'purpose':'A separate isolated PostgreSQL acceptance proof for one synthetic intervention only.',
        'study_ids':studies,'financial_dossier_ids':[],'links':[],'heat_screenings':[],
        'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY','capital':wbs()})
    assert p.status_code==201,p.text
    programme_id=p.json()['id']
    dossier_url=f'/v78/orgs/{org}/grid-annual-dossiers'
    payload={'programme_id':programme_id,'baseline_run_id':studies[0],
             'proposed_run_id':studies[1],'parameters':dcf()}
    assert c.post(dossier_url,headers=h('engineer'),json=payload).status_code==403
    actual=c.post(dossier_url,headers=h('economist'),json=payload)
    assert actual.status_code==201,actual.text
    row_id=actual.json()['id']
    assert actual.json()['report']['industrial_approval_eligible'] is False
    assert c.post(dossier_url,headers=h('economist'),json=payload).status_code==409
    replay=c.post(dossier_url+'/'+row_id+'/reproduce',headers=h('auditor'))
    assert replay.status_code==200,replay.text
    assert replay.json()['reproduced'] is True
    assert c.get(f'/v78/orgs/{n["other"]}/grid-annual-dossiers/{row_id}',
                 headers=h('other')).status_code==404

    with n['appengine'].connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.grid_annual_dossiers_v78'))==0
    with n['appengine'].begin() as conn:
        bind(conn,n,actor='auditor')
        assert conn.scalar(text('SELECT count(*) FROM public.grid_annual_dossiers_v78 WHERE id=:v'),{'v':row_id})==1
    with n['appengine'].begin() as conn:
        bind(conn,n,actor='other',org=n['other'])
        assert conn.scalar(text('SELECT count(*) FROM public.grid_annual_dossiers_v78 WHERE id=:v'),{'v':row_id})==0
    with pytest.raises(DBAPIError):
        with n['appengine'].begin() as conn:
            bind(conn,n,actor='auditor')
            conn.execute(text("UPDATE public.grid_annual_dossiers_v78 SET benefit_key='forged' WHERE id=:v"),{'v':row_id})
