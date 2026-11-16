"""V7.3 contract and independent arithmetic, synthetic-only HTTP flows."""
import copy
from decimal import Decimal
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from hydro_api.radial_grid import RadialCase,solve_radial,physical_comparability
from hydro_api.engineering import GridCase,balanced_two_bus
from hydro_api.finance_evidence import LabFinance,evaluate_feeder_alternative
from hydro_api.main import sha


def feeder():
 return {'model_kind':'radial_ac_v73','reference_name':'SYNTHETIC_MAGADAN_REFERENCE_ONLY',
  'source_voltage_kv_ll':20,'min_voltage_pu':0.90,
  'nodes':[
    {'node_id':'n1','parent_id':'SOURCE','r_ohm_per_phase':0.25,'x_ohm_per_phase':0.30,
     'load_p_mw':2,'load_q_mvar':0.6,'ampacity_a':1000},
    {'node_id':'n2','parent_id':'n1','r_ohm_per_phase':0.17,'x_ohm_per_phase':0.22,
     'load_p_mw':1.5,'load_q_mvar':0.55,'ampacity_a':1000},
    {'node_id':'n3','parent_id':'n1','r_ohm_per_phase':0.12,'x_ohm_per_phase':0.15,
     'load_p_mw':1,'load_q_mvar':0.3,'ampacity_a':1000}],
  'windows':[{'name':'normal','scale':1,'hours':120},{'name':'winter_peak','scale':1.2,'hours':24}]}


def finance():
 return {'scope':'SYNTHETIC_NOT_A_TARIFF','capital_cost_rub':'1800000',
  'annual_opex_delta_rub':'150000','value_per_kwh_rub':{'low':'2','base':'3','high':'5'},
  'discount_rate':'0.12','years':8,'annual_repeat_count':'50',
  'notes':'Synthetic price not a real tariff or economic expectation.'}


def pair(env,variant=None):
 c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab/radial-runs'
 base=feeder(); alt=copy.deepcopy(base)
 alt['nodes'][0]['r_ohm_per_phase']=0.13
 if variant:variant(alt)
 ids=[]
 for data in (base,alt):
  r=c.post(url,headers=h('lead'),json={'asset_id':'feeder-a','scenario_group':'lab_risk_case',
       'source_ref':'SYNTHETIC-V73-MAGADAN','case':data})
  assert r.status_code==201,r.text
  ids.append(r.json()['run_id'])
 return ids


def test_physical_two_bus_matches_legacy():
 x=feeder();x['nodes']=x['nodes'][:1];x['nodes'][0].update(load_p_mw=5,load_q_mvar=2,r_ohm_per_phase=.3,x_ohm_per_phase=.4)
 x['windows']=[{'name':'one','scale':1,'hours':100}]
 rad=solve_radial(RadialCase.model_validate(x))
 old=balanced_two_bus(GridCase(source_voltage_kv_ll=20,load_p_mw=5,load_q_mvar=2,
       line_r_ohm_per_phase=.3,line_x_ohm_per_phase=.4,period_hours=100,reference_name='synthetic test'))
 assert rad['total_line_energy_loss_mwh']==pytest.approx(old['line_energy_loss_mwh'],rel=1e-8,abs=1e-8)
 assert rad['status']=='LAB_ENGINEERING_LIMITS_MET'
 assert rad['windows'][0]['max_kcl_discrepancy_v']<1e-4


def test_branch_balances_topology_and_hour_weighting():
 x=feeder();x['nodes']=list(reversed(x['nodes']))
 r=solve_radial(RadialCase.model_validate(x))
 assert r['status']=='LAB_ENGINEERING_LIMITS_MET'
 assert len(r['windows'][0]['nodes'])==3
 assert r['windows'][0]['power_balance_residual_mw']<1e-7
 assert r['windows'][0]['power_balance_residual_mvar']<1e-7
 assert r['total_line_energy_loss_mwh']==pytest.approx(
  r['windows'][0]['line_loss_p_mw']*120+r['windows'][1]['line_loss_p_mw']*24, abs=2e-7)
 assert min(x['node_id'] for x in x['nodes'])=='n1'


@pytest.mark.parametrize('mutator,match',[
 (lambda x:x['nodes'][1].update(node_id='n1'),'DUPLICATE'),
 (lambda x:x['nodes'][1].update(parent_id='bogus'),'UNKNOWN_PARENT'),
 (lambda x:x['nodes'][0].update(parent_id='n2'),'CYCLIC'),
 (lambda x:x['nodes'][0].update(parent_id='n1'),'SELF_LOOP'),
 (lambda x:x['windows'].append({'name':'normal','scale':1,'hours':5}),'DUPLICATE_WINDOW'),
 (lambda x:x['windows'][0].update(hours=8784),'TIME_WINDOW'),
 (lambda x:x['nodes'][0].update(load_p_mw=float('nan')),'finite'),
])
def test_graph_data_rejected(mutator,match):
 x=feeder();mutator(x)
 with pytest.raises((ValueError,ValidationError),match=match):RadialCase.model_validate(x)


def test_thermal_violations_are_retained_as_violations():
 x=feeder();x['nodes'][1]['ampacity_a']=1
 result=solve_radial(RadialCase.model_validate(x))
 assert result['status']=='LAB_CONSTRAINT_BREACH'
 assert 'thermal:n2' in result['constraint_violations']


def test_comparison_forbids_load_and_time_mismatches():
 b=RadialCase.model_validate(feeder());x=feeder();x['nodes'][0]['r_ohm_per_phase']=0.13
 assert physical_comparability(b,RadialCase.model_validate(x))[0] is True
 x['nodes'][0]['load_p_mw']=2.1
 good,reasons=physical_comparability(b,RadialCase.model_validate(x))
 assert not good and 'n1.load_p_mw' in reasons
 x=feeder();x['nodes'][0]['r_ohm_per_phase']=0.13;x['windows'][0]['scale']=1.1
 assert 'load_windows' in physical_comparability(b,RadialCase.model_validate(x))[1]
 assert 'NO_ENGINEERING_ALTERNATIVE_CHANGED' in physical_comparability(b,b)[1]


def test_financial_valuation_derived_from_physical_loss_units():
 b=RadialCase.model_validate(feeder());v=feeder();v['nodes'][0]['r_ohm_per_phase']=0.13
 alt=RadialCase.model_validate(v)
 r=evaluate_feeder_alternative(b,alt,solve_radial(b),solve_radial(alt),LabFinance.model_validate(finance()))
 assert r['industrial_investment_eligible'] is False
 expected=Decimal(r['window_savings_mwh'])*1000*50
 assert abs(Decimal(r['annual_energy_savings_kwh'])-expected)<Decimal('0.0001')
 low=Decimal(r['price_scenarios']['low']['npv_rub']); high=Decimal(r['price_scenarios']['high']['npv_rub'])
 assert low<high
 assert r['modelled_window_hours']=='144.0'


def test_financial_refuses_assumed_annual_hours_overflow():
 b=RadialCase.model_validate(feeder());v=feeder();v['nodes'][0]['r_ohm_per_phase']=0.13
 f=finance();f['annual_repeat_count']='65'
 with pytest.raises(ValueError,match='ASSUMED_YEAR_EXCEEDS'):
  evaluate_feeder_alternative(b,RadialCase.model_validate(v),solve_radial(b),solve_radial(RadialCase.model_validate(v)),LabFinance.model_validate(f))


def test_financial_rejects_unpermitted_engineering_alt_and_ordering():
 b=RadialCase.model_validate(feeder());v=feeder();v['nodes'][1]['ampacity_a']=1;v['nodes'][0]['r_ohm_per_phase']=0.13
 with pytest.raises(ValueError,match='PROPOSED_SCENARIO_HAS_ENGINEERING_LIMIT_BREACH'):
  evaluate_feeder_alternative(b,RadialCase.model_validate(v),solve_radial(b),solve_radial(RadialCase.model_validate(v)),LabFinance.model_validate(finance()))
 f=finance();f['value_per_kwh_rub']['low']='8'
 with pytest.raises((ValueError,ValidationError),match='UNORDERED_PRICE_SCENARIOS'):
  LabFinance.model_validate(f)


def test_end_to_end_http_dossier_reproduction_and_roles(env):
 ids=pair(env);c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab'
 cmp=c.post(url+'/radial-runs/compare',headers=h('audit'),json={'baseline_run_id':ids[0],'proposed_run_id':ids[1]})
 assert cmp.status_code==200 and cmp.json()['comparability']=='MATCHED_SYNTHETIC_INVARIANTS'
 body={'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
       'benefit_key':'caseA-synthetic-2026','finance':finance()}
 assert c.post(url+'/economic-dossiers',headers=h('lead'),json=body).status_code==403
 assert c.post(url+'/economic-dossiers',headers=h('viewer'),json=body).status_code==403
 res=c.post(url+'/economic-dossiers',headers=h('finance'),json=body)
 assert res.status_code==201,res.text
 item=res.json();assert item['can_be_submitted_to_investment_approval'] is False
 dossier_id=item['dossier_id']
 assert c.get(url+'/economic-dossiers/'+dossier_id,headers=h('viewer')).status_code==200
 repro=c.post(url+'/economic-dossiers/'+dossier_id+'/reproduce',headers=h('audit'))
 assert repro.status_code==200,repro.text
 assert repro.json()['reproduced'] is True and not repro.json()['industrial_approval_eligible']
 assert c.get('/v73/orgs/separate-org/economic-dossiers/'+dossier_id,headers=h('other')).status_code==404
 assert c.post('/v7/orgs/magadan-lab/initiatives',headers=h('lead'),json={
   'asset_id':'feeder-a','run_id':ids[0], 'title':'Forbidden leap into industrial investment',
   'effect_key':'caseA-synthetic-2026'}).status_code==404
 assert c.get('/v7/orgs/magadan-lab/audit/verify',headers=h('audit')).json()['valid'] is True
 assert len(c.get(url+'/economic-dossiers',headers=h('viewer')).json())==1
 assert c.get('/v73/meta/readiness').json()['production_ready'] is False


def test_same_physical_pair_and_effect_cannot_be_double_counted(env):
 ids=pair(env);c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab/economic-dossiers'
 body={'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
       'benefit_key':'unique-effect-for-org','finance':finance()}
 assert c.post(url,headers=h('finance'),json=body).status_code==201
 assert c.post(url,headers=h('finance'),json=body).status_code==409
 body['benefit_key']='different-name-same-pair'
 assert c.post(url,headers=h('finance'),json=body).status_code==409


def test_incorrect_baseline_is_not_economically_valued(env):
 ids=pair(env,lambda v: v['nodes'][0].update(load_p_mw=2.75))
 c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab'
 comp=c.post(url+'/radial-runs/compare',headers=h('lead'),json={'baseline_run_id':ids[0],'proposed_run_id':ids[1]})
 assert comp.status_code==200 and comp.json()['comparability']=='NOT_COMPARABLE'
 assert 'n1.load_p_mw' in comp.json()['mismatch_reasons']
 body={'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
       'benefit_key':'unapproved-assumptions','finance':finance()}
 assert c.post(url+'/economic-dossiers',headers=h('finance'),json=body).status_code==409


def test_cross_tenant_scope_and_synthetic_gate(env):
 c,h=env['client'],env['h']
 payload={'asset_id':'feeder-a','scenario_group':'region_laboratory','source_ref':'SYNTHETIC-V73-VALID-CASE',
          'case':feeder()}
 assert c.post('/v73/orgs/magadan-lab/radial-runs',headers=h('viewer'),json=payload).status_code==403
 assert c.post('/v73/orgs/separate-org/radial-runs',headers=h('other'),json=payload).status_code==404
 payload['source_ref']='REAL-SUBSTATION-SECRET'
 assert c.post('/v73/orgs/magadan-lab/radial-runs',headers=h('lead'),json=payload).status_code==422


def test_dossier_row_immutable_in_sqlite_lab(env):
 ids=pair(env);c,h=env['client'],env['h'];url='/v73/orgs/magadan-lab'
 body={'asset_id':'feeder-a','baseline_run_id':ids[0],'proposed_run_id':ids[1],
       'benefit_key':'immutable-financial-dossier','finance':finance()}
 r=c.post(url+'/economic-dossiers',headers=h('finance'),json=body);assert r.status_code==201,r.text
 with env['db']() as db:
  with pytest.raises(Exception,match='APPEND_ONLY'):
   db.execute(text("UPDATE grid_economic_dossiers SET benefit_key='forged' WHERE id=:id"),{'id':r.json()['dossier_id']});db.commit()
  db.rollback()
 assert c.post(url+'/economic-dossiers/'+r.json()['dossier_id']+'/reproduce',headers=h('audit')).status_code==200


def test_openapi_v73_has_no_industrial_commands(env):
 routes=env['client'].get('/openapi.json').json()['paths']
 assert '/v73/orgs/{org_id}/radial-runs' in routes
 assert '/v73/orgs/{org_id}/economic-dossiers' in routes
 assert all('scada' not in x.lower() and 'breaker' not in x.lower() for x in routes)


def test_tiny_impedance_and_boolean_measurement_rejected():
 x=feeder();x['nodes'][0]['r_ohm_per_phase']=1e-320
 with pytest.raises((ValueError,ValidationError)):
  RadialCase.model_validate(x)
 x=feeder();x['nodes'][0]['load_p_mw']=True
 with pytest.raises((ValueError,ValidationError),match='BOOLEAN_IS_NOT_A_MEASUREMENT'):
  RadialCase.model_validate(x)
 x=feeder();x['windows'][0]['scale']=True
 with pytest.raises((ValueError,ValidationError),match='BOOLEAN_IS_NOT_A_MEASUREMENT'):
  RadialCase.model_validate(x)
 f=finance();f['value_per_kwh_rub']['base']=True
 with pytest.raises((ValueError,ValidationError),match='BOOLEAN_IS_NOT_A_PRICE'):
  LabFinance.model_validate(f)


def test_bounded_complexity_is_enforced():
 x=feeder();x['nodes']=[{'node_id':f'n{i}','parent_id':'SOURCE','r_ohm_per_phase':.1,
   'x_ohm_per_phase':.1,'load_p_mw':1,'load_q_mvar':.2,'ampacity_a':1000} for i in range(16)]
 x['windows']=[{'name':f'w{i}','scale':1,'hours':1} for i in range(13)]
 with pytest.raises((ValueError,ValidationError),match='LAB_COMPLEXITY_BUDGET_EXCEEDED'):
  RadialCase.model_validate(x)


def test_v73_synthetic_npv_is_negative_in_all_three_price_scenarios():
    """Regression guard: a physical improvement must not be advertised as profitable."""
    b=RadialCase.model_validate(feeder())
    raw=feeder();raw['nodes'][0]['r_ohm_per_phase']=.13
    p=RadialCase.model_validate(raw)
    result=evaluate_feeder_alternative(b,p,solve_radial(b),solve_radial(p),LabFinance.model_validate(finance()))
    npvs={k:Decimal(v['npv_rub']) for k,v in result['price_scenarios'].items()}
    assert npvs['low']<npvs['base']<npvs['high']<0
    assert abs(npvs['base']-Decimal('-1762946.67'))<Decimal('0.01')
    assert Decimal(result['break_even_unit_value_rub_per_kwh'])>Decimal('9')


def test_v73_negative_physical_savings_do_not_become_positive_financial_value():
    """If proposed grid loses more power, gross values must become negative."""
    b=RadialCase.model_validate(feeder())
    raw=feeder();raw['nodes'][0]['r_ohm_per_phase']=.35
    p=RadialCase.model_validate(raw)
    result=evaluate_feeder_alternative(b,p,solve_radial(b),solve_radial(p),LabFinance.model_validate(finance()))
    assert Decimal(result['annual_energy_savings_kwh'])<0
    assert result['break_even_unit_value_rub_per_kwh'] is None
    assert all(Decimal(v['gross_annual_value_rub'])<0 for v in result['price_scenarios'].values())
