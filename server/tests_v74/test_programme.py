"""V7.4 tests for synthetic, multi-domain, tenant-isolated research dossiers."""
import copy
import json
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from hydro_api.programme_v74 import CapitalScreen, ProgrammeNew, ProgrammeLink, screen_capital, evaluate_programme
from hydro_api.main import sha

ROOT=Path(__file__).parents[1]
SAMPLES=json.loads((ROOT/'ui'/'samples_v72.json').read_text())


def plan(cap='2000000',contingency='0'):
    return {'title':'Synthetic WBS for Magadan region', 'currency':'RUB',
      'tax_basis':'EXCL_VAT_SYNTHETIC', 'annual_caps_rub':{'2027':cap},
      'contingency_percent':contingency,
      'lines':[{'code':'01.01','title':'Laboratory survey only','category':'survey',
        'year':2027,'quantity':'1','unit':'lot','unit_price_rub':'1800000',
        'price_source_ref':'SYNTHETIC-ESTIMATE-V74','predecessors':[]}]}


def create_studies(env,names=None):
    c,h=env['client'],env['h'];ids={}
    for name in (names or list(SAMPLES)):
        actor='finance' if name=='hydrocapex' else 'lead'
        r=c.post('/v72/orgs/magadan-lab/studies',headers=h(actor),json={
            'asset_id':'feeder-a','module':name,'source_ref':'SYNTHETIC-V74-MAGADAN-RESEARCH',
            'scenario_group':'single_synthetic_2027','case':SAMPLES[name]})
        assert r.status_code==201,(name,r.text)
        ids[name]=r.json()['id']
    return ids


def bundle_body(ids,*,capital=None,financial=None):
    links=[]
    for left,right,relation in [
      ('hydroforecast','cascade','forecast_context_for_cascade'),
      ('cascade','hydrocapex','cascade_context_for_capex'),
      ('turbine','hydrocapex','diagnostics_context_for_capex'),
      ('gridloss','hydrocapex','grid_context_for_capex'),
      ('heatnet','hydrocapex','heat_context_for_capex'),
    ]:
        if left in ids and right in ids:
            links.append({'from_study_id':ids[left],'to_study_id':ids[right],'relationship':relation})
    return {'reference_code':'LAB-MAGADAN-V74-A','title':'Synthetic regional energy programme',
      'purpose':'Demonstrate six domains and prevent unverified field claims for Magadan research.',
      'study_ids':list(ids.values()),'links':links,'financial_dossier_ids':financial or [],
      'capital':capital,'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY'}


def test_wbs_exact_decimal_aggregation_and_stages():
    x=CapitalScreen.model_validate(plan(cap='2000000',contingency='10'))
    result=screen_capital(x)
    assert result['total_synthetic_cost_rub']=='1980000.00'
    assert result['cash_schedule']['2027']['within_cap'] is True
    assert 'design' in result['missing_project_stages']
    x=CapitalScreen.model_validate(plan(cap='1900000',contingency='10'))
    assert screen_capital(x)['status']=='ASSUMED_BUDGET_CAP_BREACHED'

@pytest.mark.parametrize('mutation,match',[
    (lambda d:d['lines'].append(copy.deepcopy(d['lines'][0])),'DUPLICATE_WBS_CODE'),
    (lambda d:d['lines'][0].update(quantity=True),'BOOLEAN'),
    (lambda d:d['lines'][0].update(unit_price_rub='NaN'),'finite|NON_FINITE'),
    (lambda d:d['lines'][0].update(predecessors=['not-present']),'UNKNOWN_WBS_PREDECESSOR'),
    (lambda d:d['lines'][0].update(predecessors=['01.01']),'WBS_SELF_DEPENDENCY'),
    (lambda d:d['lines'][0].update(category='contingency') or d.update(contingency_percent='2'),'DOUBLE_BOOKED_CONTINGENCY'),
])
def test_wbs_rejects_bad_inputs(mutation,match):
    p=plan();mutation(p)
    with pytest.raises((ValueError,ValidationError),match=match):CapitalScreen.model_validate(p)


def test_wbs_cycle_and_dependency_date_validation():
    p=plan(); second=copy.deepcopy(p['lines'][0]);second.update(code='02',title='Synthetic design mock',category='design',
           year=2028,predecessors=['01.01'])
    p['annual_caps_rub']['2028']='3000000';p['lines'].append(second)
    assert screen_capital(CapitalScreen.model_validate(p))['cash_schedule']['2028']['within_cap'] is True
    p['lines'][0]['predecessors']=['02']
    with pytest.raises(ValueError,match='PREDECESSOR_SCHEDULED_AFTER_SUCCESSOR'):
        CapitalScreen.model_validate(p)
    p['lines'][0]['year']=2028
    with pytest.raises(ValueError,match='CYCLIC_WBS_DEPENDENCY'):
        CapitalScreen.model_validate(p)


def test_all_six_studies_one_programme_and_reproduction(env):
    ids=create_studies(env)
    c,h=env['client'],env['h'];body=bundle_body(ids,capital=plan())
    root='/v74/orgs/magadan-lab/programmes'
    assert c.post(root,headers=h('viewer'),json=body).status_code==403
    assert c.post(root,headers=h('lead'),json=body).status_code==403
    res=c.post(root,headers=h('finance'),json=body)
    assert res.status_code==201,res.text
    v=res.json();assert v['industrial_approval_eligible'] is False
    assert len(v['summary']['study_quality'])==6
    assert len(v['summary']['semantic_links'])==5
    assert v['summary']['field_ready'] is False
    assert v['summary']['capital_budget_screen']['total_synthetic_cost_rub']=='1800000.00'
    ident=v['id']
    duplicate=c.post(root,headers=h('finance'),json=body)
    assert duplicate.status_code==409,duplicate.text
    assert c.get(root+'/'+ident,headers=h('viewer')).status_code==200
    assert c.get('/v74/orgs/separate-org/programmes/'+ident,headers=h('other')).status_code==404
    assert c.post(root+'/'+ident+'/reproduce',headers=h('viewer')).status_code==403
    reproduced=c.post(root+'/'+ident+'/reproduce',headers=h('audit'))
    assert reproduced.status_code==200,reproduced.text
    assert reproduced.json()['reproduced'] is True
    assert reproduced.json()['source_count']==6
    assert c.get('/v74/meta/readiness').json()['production_ready'] is False
    with env['db']() as db:
        assert db.scalar(text('SELECT count(*) FROM research_programme_studies'))==6
        assert db.scalar(text('SELECT count(*) FROM research_programme_links'))==5
        assert db.scalar(text('SELECT count(*) FROM research_programmes'))==1
        assert db.scalar(text('SELECT count(*) FROM audit_events WHERE event_type=:event'),
            {'event':'research.programme.synthetic.created'})==1
        with pytest.raises(Exception,match='APPEND_ONLY'):
            db.execute(text('UPDATE research_programmes SET title=:t WHERE id=:id'),
                   {'t':'Hacked','id':ident});db.commit()
        db.rollback()


def test_bad_domain_link_rejected_without_db_rows(env):
    ids=create_studies(env,['hydroforecast','cascade'])
    body=bundle_body(ids)
    body['links'][0]['relationship']='grid_context_for_capex'
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=body)
    assert r.status_code==422,r.text
    with env['db']() as db:assert db.scalar(text('SELECT count(*) FROM research_programmes'))==0


def test_unrelated_scenario_group_cannot_be_linked(env):
    ids=create_studies(env,['hydroforecast','cascade'])
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_study_runs_update'))
        db.execute(text('UPDATE study_runs SET scenario_group=:group WHERE id=:id'),
                  {'group':'different','id':ids['cascade']})
        db.commit()
    body=bundle_body(ids)
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=body)
    assert r.status_code==409, r.text  # SHA tampering is caught before semantic comparison


def test_no_cross_org_or_unauthorized_real_asset(env):
    ids=create_studies(env,['hydroforecast'])
    body=bundle_body(ids)
    r=env['client'].post('/v74/orgs/separate-org/programmes',headers=env['h']('other'),json=body)
    assert r.status_code in (403,404)
    from hydro_api.storage import Asset
    with env['db']() as db:
        db.add(Asset(id='non-lab-hydrokontur',org_id='magadan-lab',name='Non lab asset',classification='REAL'))
        db.commit()
    r=env['client'].post('/v74/orgs/magadan-lab/capital-screen',headers=env['h']('viewer'),json=plan())
    assert r.status_code==403


def test_wbs_linked_finance_mismatch_is_visible(env):
    from tests_v73.test_radial_and_finance import feeder,finance
    c,h=env['client'],env['h']
    base=feeder();alt=copy.deepcopy(base)
    alt['nodes'][0]['r_ohm_per_phase']=.13
    ids=[]
    for inputs in (base,alt):
        res=c.post('/v73/orgs/magadan-lab/radial-runs',headers=h('lead'),json={
            'asset_id':'feeder-a','scenario_group':'compare-v74','source_ref':'SYNTHETIC-V74-MAGADAN',
            'case':inputs})
        assert res.status_code==201,res.text
        ids.append(res.json()['run_id'])
    econ=c.post('/v73/orgs/magadan-lab/economic-dossiers',headers=h('finance'),json={
        'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
        'benefit_key':'synthetic-v74-grid-savings','finance':finance()})
    assert econ.status_code==201,econ.text
    body={'reference_code':'LAB-MAGADAN-GRID-74','title':'Synthetic grid WBS and economic dossier',
        'purpose':'Shows engineering to finance provenance and independent budget screen, not a real investment.',
        'study_ids':ids,'financial_dossier_ids':[econ.json()['dossier_id']],
        'links':[],'capital':plan(cap='1900000',contingency='0')}
    res=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=body)
    assert res.status_code==201,res.text
    summary=res.json()['summary']
    assert len(summary['financial_dossiers'])==1
    assert summary['financial_dossiers'][0]['monetary_effect_approved'] is False
    assert 'CAPEX_ASSUMPTION_CONFLICT_BETWEEN_WBS_AND_FINANCIAL_DOSSIERS' not in summary['computational_blockers']
    # Changing cost to 1.9m creates a visible mismatch with finance 1.8m, not a fictitious approval.
    body['reference_code']='LAB-MAGADAN-GRID-75'
    body['capital']['lines'][0]['unit_price_rub']='1900000'
    res=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=body)
    assert res.status_code==201,res.text
    assert 'CAPEX_ASSUMPTION_CONFLICT_BETWEEN_WBS_AND_FINANCIAL_DOSSIERS' in res.json()['summary']['computational_blockers']
    # Removing one of the pinned source runs cannot sneak an ungrounded finance memo into the programme.
    body['reference_code']='LAB-MAGADAN-GRID-76'
    body['study_ids']=ids[:1]
    invalid=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=body)
    assert invalid.status_code==422,invalid.text


def test_tenant_composite_foreign_keys_in_sqlite(env):
    from hydro_api.storage import ResearchProgrammeStudy
    ids=create_studies(env,['heatnet'])
    body=bundle_body(ids)
    c,h=env['client'],env['h']
    r=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=body)
    assert r.status_code==201,r.text
    with env['db']() as db:
        db.add(ResearchProgrammeStudy(org_id='separate-org',programme_id=r.json()['id'],study_id=ids['heatnet']))
        with pytest.raises(Exception,match='FOREIGN KEY'):
            db.commit()
        db.rollback()


def test_replay_detects_missing_source_link(env):
    ids=create_studies(env,['heatnet'])
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=bundle_body(ids))
    assert r.status_code==201,r.text
    with env['db']() as db:
        db.execute(text('DROP TRIGGER lock_research_programme_studies_delete'))
        db.execute(text('DELETE FROM research_programme_studies WHERE programme_id=:id'),{'id':r.json()['id']})
        db.commit()
    res=env['client'].post(f"/v74/orgs/magadan-lab/programmes/{r.json()['id']}/reproduce",headers=env['h']('audit'))
    assert res.status_code==409 and 'RELATIONAL_LINK_DRIFT' in res.text


def heat_finance():
    return {'scope':'SYNTHETIC_HEAT_NOT_TARIFF','hours_per_year':'5000',
            'value_rub_per_kwh':{'low':'2','base':'3','high':'5'},
            'capital_cost_rub':'1000000','annual_opex_delta_rub':'100000',
            'discount_rate':'0.12','years':8,
            'notes':'The heat price and project cost are synthetic placeholders only.'}


def heat_pair(env,mutator=None):
    c,h=env['client'],env['h'];base=copy.deepcopy(SAMPLES['heatnet']);alt=copy.deepcopy(base)
    alt['overall_u_w_m_k']=1
    if mutator:mutator(alt)
    ids=[]
    for case in (base,alt):
        r=c.post('/v72/orgs/magadan-lab/studies',headers=h('lead'),json={
            'asset_id':'feeder-a','module':'heatnet','source_ref':'SYNTHETIC-V74-HEAT-NET',
            'scenario_group':'same_heat_baseline','case':case})
        assert r.status_code==201,r.text
        ids.append(r.json()['id'])
    return ids


def test_synthetic_heat_screening_from_two_pinned_studies(env):
    ids=heat_pair(env);c,h=env['client'],env['h']
    body=bundle_body({'heatnet':ids[0]},capital=None)
    body['study_ids']=ids
    body['heat_screenings']=[{'baseline_study_id':ids[0],'proposed_study_id':ids[1],
        'benefit_key':'synthetic_heat_efficiency','finance':heat_finance()}]
    r=c.post('/v74/orgs/magadan-lab/programmes',json=body,headers=h('finance'))
    assert r.status_code==201,r.text
    e=r.json()['summary']['heat_economic_screenings'][0]['research_result']
    assert Decimal(e['annual_synthetic_savings_kwh'])==Decimal('400000')
    assert Decimal(e['prices']['low']['npv_rub'])<Decimal(e['prices']['high']['npv_rub'])
    assert e['industrial_finance_eligible'] is False
    pid=r.json()['id']
    assert c.post('/v74/orgs/magadan-lab/programmes/'+pid+'/reproduce',
        headers=h('audit')).json()['reproduced'] is True


def test_heat_screen_rejects_incomparable_physical_scenarios(env):
    ids=heat_pair(env,lambda alt:alt.update(mass_flow_kg_s=11))
    body=bundle_body({'heatnet':ids[0]})
    body['study_ids']=ids
    body['heat_screenings']=[{'baseline_study_id':ids[0],'proposed_study_id':ids[1],
        'benefit_key':'wrong_heat_comparison','finance':heat_finance()}]
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=body)
    assert r.status_code==422 and 'UNMATCHED_HEAT_ENGINEERING_BASELINE' in r.text


def test_heat_financial_screening_does_not_make_worsening_an_improvement(env):
    from hydro_api.heat_economics_v74 import HeatMoney,compare_heat
    from hydro_api.studies import HeatCase,heat_balance
    base=HeatCase.model_validate(SAMPLES['heatnet'])
    alt=HeatCase.model_validate({**SAMPLES['heatnet'],'overall_u_w_m_k':3})
    outcome=compare_heat(base,alt,heat_balance(base),heat_balance(alt),HeatMoney.model_validate(heat_finance()))
    assert Decimal(outcome['annual_synthetic_savings_kwh'])<0
    assert Decimal(outcome['prices']['base']['npv_rub'])<0
    assert outcome['industrial_finance_eligible'] is False


def test_heat_claims_not_double_counted_in_cross_module_registry(env):
    ids=heat_pair(env)
    body=bundle_body({'heatnet':ids[0]})
    body['study_ids']=ids
    h={'baseline_study_id':ids[0],'proposed_study_id':ids[1],
        'benefit_key':'repeat-heat','finance':heat_finance()}
    body['heat_screenings']=[h,copy.deepcopy(h)]
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=body)
    assert r.status_code==422 and 'DUPLICATE_HEAT_BENEFIT_KEY' in r.text


def test_heat_explicitly_requires_pinned_source_runs(env):
    ids=heat_pair(env)
    body=bundle_body({'heatnet':ids[0]})
    body['heat_screenings']=[{'baseline_study_id':ids[0],'proposed_study_id':ids[1],
        'benefit_key':'missing-source','finance':heat_finance()}]
    r=env['client'].post('/v74/orgs/magadan-lab/programmes',headers=env['h']('finance'),json=body)
    assert r.status_code==422 and 'HEAT_SOURCE_NOT_INCLUDED_IN_PROGRAMME' in r.text


def test_deep_reproduction_executes_actual_engine_not_only_hashes(env,monkeypatch):
    ids=create_studies(env,['heatnet'])
    c,h=env['client'],env['h']
    res=c.post('/v74/orgs/magadan-lab/programmes',headers=h('finance'),json=bundle_body(ids))
    assert res.status_code==201,res.text
    uri=f"/v74/orgs/magadan-lab/programmes/{res.json()['id']}"
    assert c.get(uri,headers=h('audit')).status_code==200
    import hydro_api.programme_api_v74 as package
    # Simulate altered implementation without modifying stored hashes.
    monkeypatch.setattr(package,'compute_study',lambda *_args,**_kw:{'new_incorrect_result':'not pinned'})
    invalid=c.post(uri+'/reproduce',headers=h('audit'))
    assert invalid.status_code==409,invalid.text
    assert 'UNDERLYING_STUDY_REPLAY_DIVERGED' in invalid.text
