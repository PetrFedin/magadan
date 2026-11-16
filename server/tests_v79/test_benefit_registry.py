"""V7.9: actual laboratory storage and HTTP tests. No PostgreSQL acceptance claim."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import pytest
from sqlalchemy import text
from hydro_api.storage import ResearchHandoff, BenefitReservationV79
from hydro_api.main import sha
from hydro_api.benefit_ledger_v79 import claimed_overlap, base_value_from_v78
from tests_v78.test_grid_dcf_http import create_programme, body
from tests_v73.test_radial_and_finance import pair

URL='/v79/orgs/magadan-lab/benefit-reservations'


def payload(source_id, kind='GRID_ANNUAL_V78', family='ELECTRIC_ENERGY_COST',
            start=2030, end=2031, asset='feeder-a'):
    return {'asset_id':asset,'family':family,'start_year':start,'end_year':end,
        'source_kind':kind,'source_id':source_id,
        'measurement_plan_ref':'SYNTHETIC-MAGADAN-MV-PLAN-2026-V1',
        'measurement_boundary_description':
            'Synthetic electrical feeder asset boundary, no field readings or permits.',
        'comparison_normalization':
            'Baseline and alternative must use identical loads, topology, conditions and metering boundary; no field baseline.'}


def annual_source(env):
    ids=pair(env);pid=create_programme(env,ids)
    r=env['client'].post('/v78/orgs/magadan-lab/grid-annual-dossiers',
                          headers=env['h']('finance'),json=body(pid,ids))
    assert r.status_code==201,r.text
    return r.json()['id']


def handoff_source(env, ident='one'):
    from tests_v75.test_handoff_api import register,maintenance_payload
    ids=register(env,('turbine',))
    data=maintenance_payload(ids)
    data['maintenance_bridge']['planning_reference']='SYNTHETIC-MAGADAN-REPAIR-'+ident+'-V79'
    out=env['client'].post('/v75/orgs/magadan-lab/handoffs',
        headers=env['h']('lead'),json=data)
    assert out.status_code==201,out.text
    return out.json()['id']


def test_source_derived_lab_value_and_roles(env):
    source=annual_source(env);c=env['client'];h=env['h'];claim=payload(source)
    assert c.post(URL,headers=h('lead'),json=claim).status_code==403
    assert c.post(URL,headers=h('viewer'),json=claim).status_code==403
    created=c.post(URL,headers=h('finance'),json=claim)
    assert created.status_code==201,created.text
    item=created.json()
    assert item['actual_savings_confirmed'] is False
    assert item['industrial_approval_eligible'] is False
    assert item['lab_estimated_gross_rub'] is not None
    assert item['source_integrity_checked'] is True
    saved=c.get(URL+'/'+item['id'],headers=h('audit'))
    assert saved.status_code==200,saved.text
    assert c.post(URL+'/'+item['id']+'/reproduce',headers=h('finance')).status_code==403
    assert c.post(URL+'/'+item['id']+'/reproduce',headers=h('audit')).json()['reproduced'] is True
    assert c.get('/v79/orgs/separate-org/benefit-reservations/'+item['id'],headers=h('otheraudit')).status_code==404
    assert c.post('/v79/orgs/separate-org/benefit-reservations',headers=h('otheraudit'),json=claim).status_code==403
    assert c.post(URL,headers=h('finance'),json=claim).status_code==409


def test_different_source_same_boundary_and_family_rejected(env):
    a=handoff_source(env,'one');b=handoff_source(env,'two')
    c,h=env['client'],env['h']
    one=payload(a,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST',start=2030,end=2035)
    two=payload(b,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST',start=2035,end=2040)
    assert c.post(URL,headers=h('finance'),json=one).status_code==201
    r=c.post(URL,headers=h('finance'),json=two)
    assert r.status_code==409,r.text
    assert 'DUPLICATE_OR_OVERLAPPING' in r.text
    # Non-overlapping intervals can be treated as separate observations.
    two['start_year']=2036
    assert c.post(URL,headers=h('finance'),json=two).status_code==201


def test_cross_family_source_reuse_rejected(env):
    source=handoff_source(env,'one');c,h=env['client'],env['h']
    item=payload(source,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST')
    assert c.post(URL,headers=h('finance'),json=item).status_code==201
    forged=deepcopy(item);forged['family']='CAPEX_COST'
    assert c.post(URL,headers=h('finance'),json=forged).status_code==409
    assert len(c.get(URL,headers=h('viewer')).json()['reservations'])==1


def test_tampered_evidence_denies_read_even_after_sqlite_trigger_removed(env):
    source=handoff_source(env,'one');c,h=env['client'],env['h']
    r=c.post(URL,headers=h('finance'),json=payload(source,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST'))
    assert r.status_code==201
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_benefit_reservations_v79_update'))
        db.execute(text('UPDATE benefit_reservations_v79 SET source_sha256=:p WHERE id=:i'),
                   {'p':'0'*64,'i':r.json()['id']})
        db.commit()
    result=c.get(URL+'/'+r.json()['id'],headers=h('audit'))
    assert result.status_code==409
    assert 'INTEGRITY' in result.text


def test_append_only_and_identity_binding(env):
    source=handoff_source(env,'one');c,h=env['client'],env['h']
    r=c.post(URL,headers=h('finance'),json=payload(source,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST'))
    assert r.status_code==201
    with env['db']() as db:
        with pytest.raises(Exception):
            db.execute(text('DELETE FROM benefit_reservations_v79 WHERE id=:i'),{'i':r.json()['id']});db.commit()
        db.rollback()
    bad=payload(source,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST',asset='feeder-b')
    assert c.post(URL,headers=h('finance'),json=bad).status_code==404


def test_concurrent_overlap_is_blocked_by_database(env):
    first=handoff_source(env,'one');second=handoff_source(env,'two')
    c,h=env['client'],env['h']
    reqs=[payload(first,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST'),
          payload(second,kind='MAINTENANCE_HANDOFF_V75',family='MAINTENANCE_COST')]
    def create(q):
        return c.post(URL,headers=h('finance'),json=q).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(create,reqs))
    assert sorted(replies)==[201,409],replies
    with env['db']() as db:
        assert db.query(BenefitReservationV79).count()==1


def test_invalid_period_and_source_rejected(env):
    c,h=env['client'],env['h']
    missing=payload('MISSING')
    assert c.post(URL,headers=h('finance'),json=missing).status_code==404
    missing['start_year']=2040;missing['end_year']=2039
    assert c.post(URL,headers=h('finance'),json=missing).status_code==422
    missing=payload('MISSING');missing['source_kind']='FAKE_APPROVAL'
    assert c.post(URL,headers=h('finance'),json=missing).status_code==422


def test_policy_oracle():
    x={'org_id':'a','asset_id':'one','family':'HEAT_ENERGY_COST','start_year':2030,'end_year':2035}
    y={**x,'start_year':2035,'end_year':2040}
    assert claimed_overlap(x,y)
    assert not claimed_overlap(x,{**y,'start_year':2036})
    assert not claimed_overlap(x,{**y,'org_id':'b'})
    assert not claimed_overlap(x,{**y,'family':'MAINTENANCE_COST'})


def test_base_value_not_manufactured_for_missing_year():
    fake={'industrial_approval_eligible':False,'scenario_results':{'base':{'yearly_cashflows':[
        {'year':2030,'gross_rub':'100.00'}]}}}
    assert base_value_from_v78(fake,2030,2030)=='100.00'
    assert base_value_from_v78(fake,2030,2031) is None
    with pytest.raises(ValueError,match='NON_LAB_RESULT'):
        base_value_from_v78({**fake,'industrial_approval_eligible':True},2030,2030)


def test_sql_contract_v79():
    root=Path(__file__).resolve().parents[1]
    migration=(root/'migrations'/'130_benefit_ledger_v79.sql').read_text()
    for token in ('EXCLUDE USING gist','int4range','btree_gist','FORCE ROW LEVEL SECURITY',
                  'ENABLE ROW LEVEL SECURITY','hk_security.allowed','hk_private.reject_mutation',
                  'hk_private.audit_business_change','source_sha256','ASSURANCE_V76',
                  'MAINTENANCE_HANDOFF_V75'):
        assert token in migration
    assert 'DROP TABLE' not in migration


def test_v79_native_acceptance_suite_contains_actual_sql_negative_tests():
    native=(Path(__file__).resolve().parents[1]/'tests_v71'/'test_postgres_native.py').read_text()
    assert 'test_v79_native_new_table_default_deny_and_runtime_non_owner' in native
    assert 'test_v79_native_concurrent_overlap_and_replay' in native
    assert 'NATIVE_ACCEPTANCE_BLOCKED' in native
