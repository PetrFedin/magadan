"""HTTP, tenant, source-identity, append-only and duplicate protection tests."""
from copy import deepcopy
from sqlalchemy import text
from tests_v73.test_radial_and_finance import pair
from tests_v78.test_grid_dcf_domain import dcf,wbs


def create_programme(env, ids):
    c,h=env['client'],env['h']
    body={
        'reference_code':'LAB-GRID-ONE-MEASURE-78',
        'title':'Synthetic feeder independent WBS',
        'purpose':'Synthetic isolated feeder comparison with a single exclusive construction WBS; not approved investment or corporate budget.',
        'study_ids':ids,'financial_dossier_ids':[],'links':[],'heat_screenings':[],
        'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY','capital':wbs()
    }
    response=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=body)
    assert response.status_code==201,response.text
    return response.json()['id']


def body(pid,ids):
    return {'programme_id':pid,'baseline_run_id':ids[0], 'proposed_run_id':ids[1],
            'parameters':dcf()}


def test_http_full_economic_chain_and_replay(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    api='/v78/orgs/magadan-lab/grid-annual-dossiers'
    assert c.post(api,json=body(pid,ids),headers=h('lead')).status_code==403
    assert c.post(api,json=body(pid,ids),headers=h('viewer')).status_code==403
    result=c.post(api,json=body(pid,ids),headers=h('finance'))
    assert result.status_code==201,result.text
    report=result.json()['report'];item_id=result.json()['id']
    assert report['wbs_total_capex_rub']=='2300000.00'
    assert report['partial_coverage_years']==[2030,2031]
    assert report['industrial_approval_eligible'] is False
    for role in ('lead','finance','audit','viewer'):
        x=c.get(api+'/'+item_id,headers=h(role))
        assert x.status_code==200,x.text
        assert x.json()['reproduced_from_sources'] is True
    assert c.post(api+'/'+item_id+'/reproduce',headers=h('finance')).status_code==403
    yes=c.post(api+'/'+item_id+'/reproduce',headers=h('audit'))
    assert yes.status_code==200,yes.text
    assert yes.json()['report_sha256']==result.json()['report_sha256']
    assert c.post(api,json=body(pid,ids),headers=h('finance')).status_code==409
    assert c.get(api,headers=h('audit')).status_code==200
    assert c.get('/v78/orgs/separate-org/grid-annual-dossiers/'+item_id,headers=h('otheraudit')).status_code==404
    assert c.get('/v78/orgs/separate-org/grid-annual-dossiers/'+item_id,headers=h('audit')).status_code==404
    assert c.post('/v78/orgs/separate-org/grid-annual-dossiers',headers=h('finance'),json=body(pid,ids)).status_code==404
    with env['db']() as db:
        # Append-only protection applies to SQLite as well as the prepared PG migration.
        import pytest
        with pytest.raises(Exception):
            db.execute(text('UPDATE grid_annual_dossiers_v78 SET benefit_key=:v WHERE id=:i'),{'v':'forged','i':item_id})
            db.commit()
        db.rollback()
        with pytest.raises(Exception):
            db.execute(text('DELETE FROM grid_annual_dossiers_v78 WHERE id=:i'),{'i':item_id})
            db.commit()
        db.rollback()


def test_http_guard_against_wbs_double_attribution(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    api='/v78/orgs/magadan-lab/grid-annual-dossiers'
    r=c.post(api,headers=h('finance'),json=body(pid,ids));assert r.status_code==201,r.text
    new=body(pid,ids);new['parameters']['benefit_key']='SYNTHETIC_V78_DIFFERENT_CODE'
    q=c.post(api,headers=h('finance'),json=new)
    assert q.status_code==409,q.text
    # Further false annual scenarios cannot be introduced under same project WBS.
    new=body(pid,list(reversed(ids)));new['parameters']['benefit_key']='SYNTHETIC_V78_ALTERNATE_DIRECTION'
    q=c.post(api,headers=h('finance'),json=new)
    assert q.status_code==409,q.text


def test_http_bad_physics_and_annual_horizon_rejected(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    url='/v78/orgs/magadan-lab/grid-annual-dossiers'
    inp=body(pid,ids);inp['parameters']['annual_assumptions'][0]['cycles']=61
    r=c.post(url,headers=h('finance'),json=inp)
    assert r.status_code==422 and 'YEARLY_WINDOW_HOURS_EXCEED_CALENDAR_YEAR' in r.text
    inp=body(pid,ids);inp['parameters']['annual_assumptions'][0]['avoided_supply_cost_rub_per_kwh']={'normal':'1'}
    r=c.post(url,headers=h('finance'),json=inp)
    assert r.status_code==422 and 'MISSING_OR_EXTRA_WINDOW_PRICE' in r.text


def test_http_programme_must_have_exclusive_capex_scope(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    body2=body(pid,list(reversed(ids)));body2['parameters']['benefit_key']='SYNTHETIC_REVERSED_CASE_V78'
    # Inverse engineering change is physically comparable, but WBS is still same exclusive scope.
    r=c.post('/v78/orgs/magadan-lab/grid-annual-dossiers',headers=h('finance'),json=body2)
    assert r.status_code==201,r.text
    # Third attempt on same WBS forbidden by the DB even with new benefit_key.
    x=body(pid,ids);x['parameters']['benefit_key']='UNIQUE_TEST_BENEFIT_NEW'
    y=c.post('/v78/orgs/magadan-lab/grid-annual-dossiers',headers=h('finance'),json=x)
    assert y.status_code==409,y.text


def test_http_preexisting_legacy_benefit_blocks_new_claim(env):
    c,h=env['client'],env['h'];ids=pair(env)
    from tests_v73.test_radial_and_finance import finance
    legacy=c.post('/v73/orgs/magadan-lab/economic-dossiers',headers=h('finance'),json={
        'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
        'benefit_key':'LEGACY_SYNTHETIC_BENEFIT_78','finance':finance()})
    assert legacy.status_code==201,legacy.text
    pid=create_programme(env,ids)
    inp=body(pid,ids);inp['parameters']['benefit_key']='SYNTHETIC_NEW_KEY_BUT_SAME_PAIR'
    result=c.post('/v78/orgs/magadan-lab/grid-annual-dossiers',headers=h('finance'),json=inp)
    assert result.status_code==409,result.text
    assert 'BENEFIT_ALREADY_USED' in result.text


def test_http_legacy_cannot_reclaim_existing_v78_effect(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    r=c.post('/v78/orgs/magadan-lab/grid-annual-dossiers',headers=h('finance'),json=body(pid,ids))
    assert r.status_code==201,r.text
    from tests_v73.test_radial_and_finance import finance
    legacy=c.post('/v73/orgs/magadan-lab/economic-dossiers',headers=h('finance'),json={
        'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
        'benefit_key':'A_LEGACY_DIFFERENT_EFFECT_KEY','finance':finance()})
    assert legacy.status_code==409,legacy.text
    assert 'BENEFIT_ALREADY_USED_IN_V78_GRID_DCF' in legacy.text


def test_http_detect_tampering_after_forced_administrator_trigger_disable(env):
    c,h=env['client'],env['h'];ids=pair(env);pid=create_programme(env,ids)
    r=c.post('/v78/orgs/magadan-lab/grid-annual-dossiers',headers=h('finance'),json=body(pid,ids))
    assert r.status_code==201,r.text
    item_id=r.json()['id']
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_grid_annual_dossiers_v78_update'))
        db.execute(text('UPDATE grid_annual_dossiers_v78 SET report=:bad WHERE id=:i'),
                   {'bad':'{"industrial_approval_eligible":true}', 'i':item_id})
        db.commit()
    response=c.get('/v78/orgs/magadan-lab/grid-annual-dossiers/'+item_id,headers=h('audit'))
    assert response.status_code==409,response.text
    assert 'INTEGRITY' in response.text
