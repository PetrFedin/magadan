"""API, trust boundary and engineering sanity of synthetic modules V7.2."""
import copy
import math
import pytest
from sqlalchemy import text
from hydro_api.studies import compute_study, ForecastCase, PortfolioCase

F={
 'issued_at':'2026-10-01T09:00:00+03:00',
 'training':[{'observed_at':f'2026-09-{d:02d}T09:00:00+03:00',
              'available_at':f'2026-09-{d:02d}T10:00:00+03:00','flow_cms':float(90+d)} for d in (1,2,3,4)],
 'targets':[{'target_at':f'2026-10-{d:02d}T09:00:00+03:00',
             'truth_available_at':f'2026-10-{d:02d}T12:00:00+03:00',
             'actual_cms':float(100+d),'predicted_cms':float(101+d),
             'lower_cms':float(95+d),'upper_cms':float(105+d)} for d in (2,3,4)]}

def reservoir(name):
 return {'name':name,'initial_storage_m3':700000000,'min_storage_m3':600000000,
         'max_storage_m3':800000000,'local_inflow_cms':60,'turbine_release_cms':55,
         'spill_release_cms':5,'other_losses_cms':0,'min_total_release_cms':10,
         'head_m':100,'efficiency':0.9,'rated_capacity_mw':200}

CA={'period_hours':24,'upper':reservoir('upstream'), 'lower':reservoir('downstream'),
    'assumption':'instantaneous_upstream_release_no_travel_time'}
TU={'reference_load_mw':100,'comparable_band_percent':10,
 'baseline':[{'observed_at':f'2026-09-{i:02d}T10:00:00+03:00','load_mw':100,
              'vibration_mm_s':v} for i,v in enumerate([2.0,2.1,1.9,2.2,1.8,2.05],1)],
 'recent':[{'observed_at':f'2026-10-{i:02d}T10:00:00+03:00','load_mw':99,
            'vibration_mm_s':v} for i,v in enumerate([3.5,3.6,3.7],1)]}
GR={'reference_name':'Synthetic network, never Magadan field evidence',
    'source_voltage_kv_ll':20,'load_p_mw':5,'load_q_mvar':2,
    'line_r_ohm_per_phase':0.3,'line_x_ohm_per_phase':0.4,'period_hours':100}
HE={'mass_flow_kg_s':10,'supply_temp_c':90,'return_temp_c':60,'ambient_temp_c':-5,
    'cp_j_kg_k':4200,'length_m':1000,'overall_u_w_m_k':2}
PO={'discount_rate':'0.12','annual_budgets_rub':['40','10','10'],
    'projects':[{'project_id':'required','benefit_key':'safety','mandatory':True,
                  'costs_by_year_rub':['20','0','0'],'net_benefits_by_year_rub':['0','0']},
                {'project_id':'economical','benefit_key':'benefit-a',
                  'costs_by_year_rub':['20','0','0'],'net_benefits_by_year_rub':['30','30']},
                {'project_id':'oversized','benefit_key':'benefit-b',
                  'costs_by_year_rub':['30','0','0'],'net_benefits_by_year_rub':['60','60']} ]}
CASES={'hydroforecast':F,'cascade':CA,'turbine':TU,'gridloss':GR,'heatnet':HE,'hydrocapex':PO}

@pytest.mark.parametrize('module',list(CASES))
def test_six_modules_valid_standalone(module):
 x=compute_study(module,CASES[module])
 assert x['module']==module
 assert x['assurance']['industrial_decision_eligible'] is False
 assert x['result']

def test_hydroforecast_no_future_training_leak():
 bad=copy.deepcopy(F)
 bad['training'][0]['available_at']='2026-10-05T10:00:00+03:00'
 with pytest.raises(ValueError,match='FUTURE_INFORMATION_LEAKAGE'):
  compute_study('hydroforecast',bad)

def test_hydroforecast_rejects_naive_datetime():
 bad=copy.deepcopy(F);bad['issued_at']='2026-10-01T09:00:00'
 with pytest.raises(ValueError,match='Timezone-aware'):
  compute_study('hydroforecast',bad)

def test_hydroforecast_non_concealed_zero_denominator():
 bad=copy.deepcopy(F)
 for t in bad['targets']:
  t.update(actual_cms=0,predicted_cms=0,lower_cms=0,upper_cms=0)
 result=compute_study('hydroforecast',bad)['result']
 assert result['wape_percent'] is None
 assert result['mae_cms']==0

def test_cascade_mass_balances_and_infeasibility():
 r=compute_study('cascade',CA)['result']
 assert r['status']=='FEASIBLE_IN_SYNTHETIC_MODEL'
 assert math.isclose(r['upper']['final_storage_m3'],CA['upper']['initial_storage_m3'])
 assert r['lower']['final_storage_m3']>CA['lower']['initial_storage_m3']
 bad=copy.deepcopy(CA);bad['upper']['rated_capacity_mw']=0.01
 assert compute_study('cascade',bad)['result']['status']=='INFEASIBLE'

def test_turbine_not_a_failure_probability():
 r=compute_study('turbine',TU)['result']
 assert r['status']=='CHECK_SIGNAL' and r['failure_probability'] is None
 bad=copy.deepcopy(TU);bad['recent'][1]['load_mw']=200
 with pytest.raises(ValueError,match='INCOMPARABLE_OPERATING_LOAD'):
  compute_study('turbine',bad)

def test_heat_balance_units():
 r=compute_study('heatnet',HE)['result']
 assert r['delivered_heat_mw']==1.26
 assert r['estimated_pipe_loss_mw']==0.16
 assert r['estimated_upstream_supply_mw']==1.42

def test_portfolio_mandatory_budget_reconciliation():
 r=compute_study('hydrocapex',PO)['result']
 assert r['selected']==['economical','required']
 assert r['used_budget_by_year_rub'][0]=='40'
 x=copy.deepcopy(PO);x['annual_budgets_rub'][0]='10'
 assert compute_study('hydrocapex',x)['result']['status']=='NO_FEASIBLE_PORTFOLIO'

def test_portfolio_reject_duplicate_benefit_and_cycle():
 x=copy.deepcopy(PO);x['projects'][1]['benefit_key']='safety'
 with pytest.raises(ValueError,match='DUPLICATE_PROJECT_OR_BENEFIT_KEY'):
  compute_study('hydrocapex',x)
 x=copy.deepcopy(PO)
 x['projects'][0]['depends_on']=['economical'];x['projects'][1]['depends_on']=['required']
 with pytest.raises(ValueError,match='CYCLIC_DEPENDENCY'):
  compute_study('hydrocapex',x)

@pytest.mark.parametrize('module',list(CASES))
def test_http_creation_read_reproduce_by_authorized_actor(env,module):
 c,h=env['client'],env['h'];base='/v72/orgs/magadan-lab'
 actor='finance' if module=='hydrocapex' else 'lead'
 body={'asset_id':'feeder-a','module':module,'source_ref':'SYNTHETIC-HYDRO72',
       'scenario_group':'magadan-lab-case','case':CASES[module]}
 response=c.post(base+'/studies',json=body,headers=h(actor))
 assert response.status_code==201,response.text
 x=response.json();sid=x['id']
 assert x['status']=='SYNTHETIC_UNVERIFIED'
 assert x['allowed_as_industrial_decision_evidence'] is False
 assert c.get(base+'/studies/'+sid,headers=h('viewer')).status_code==200
 assert c.get('/v72/orgs/separate-org/studies/'+sid,headers=h('other')).status_code==404
 assert c.post(base+'/studies/'+sid+'/reproduce',headers=h('audit')).json()['reproduced'] is True
 assert c.post('/v7/orgs/magadan-lab/initiatives',headers=h('lead'),json={
  'asset_id':'feeder-a','run_id':sid,'title':'Unsafe study promotion to investment','effect_key':'test-no-promotion'}).status_code==404

def test_http_reject_real_data_claim_and_viewer_write(env):
 c,h=env['client'],env['h'];base='/v72/orgs/magadan-lab/studies'
 body={'asset_id':'feeder-a','module':'gridloss','source_ref':'REAL-MAGADAN-FEEDER',
       'scenario_group':'pilot-test','case':GR}
 assert c.post(base,json=body,headers=h('lead')).status_code==422
 body['source_ref']='SYNTHETIC-HYDRO72'
 assert c.post(base,json=body,headers=h('viewer')).status_code==403
 assert c.post(base,json=body,headers=h('other')).status_code==404

def test_http_comparison_marks_non_equivalent_scenarios(env):
 c,h=env['client'],env['h'];base='/v72/orgs/magadan-lab/studies'
 ids=[]
 for voltage in (20,21):
  data=copy.deepcopy(GR);data['source_voltage_kv_ll']=voltage
  x=c.post(base,json={'asset_id':'feeder-a','module':'gridloss',
          'source_ref':'SYNTHETIC-HYDRO72','scenario_group':'contrast','case':data},
          headers=h('lead'))
  assert x.status_code==201,x.text
  ids.append(x.json()['id'])
 r=c.post(base+'/compare-pair',json={'left_run_id':ids[0],'right_run_id':ids[1]},headers=h('lead'))
 assert r.status_code==200,r.text
 assert r.json()['comparability_status']=='UNVERIFIED_TAG_ONLY'
 assert r.json()['delta_right_minus_left'] is not None

def test_http_study_immutable_even_with_direct_update(env):
 c,h=env['client'],env['h'];base='/v72/orgs/magadan-lab/studies'
 x=c.post(base,json={'asset_id':'feeder-a','module':'heatnet','source_ref':'SYNTHETIC-HYDRO72',
      'scenario_group':'immutable','case':HE},headers=h('lead'))
 assert x.status_code==201
 with env['db']() as db:
  with pytest.raises(Exception,match='APPEND_ONLY'):
   db.execute(text('UPDATE study_runs SET source_ref=:ref WHERE id=:id'),
              {'ref':'SYNTHETIC-HACK','id':x.json()['id']});db.commit()
  db.rollback()
 assert c.post(base+'/'+x.json()['id']+'/reproduce',headers=h('audit')).status_code==200

def test_api_rejects_nonfinite_payload_as_422(env):
 c,h=env['client'],env['h'];from copy import deepcopy
 bad=deepcopy(GR);bad['load_p_mw']=float('nan')
 import json
 payload={'asset_id':'feeder-a','module':'gridloss','source_ref':'SYNTHETIC-HYDRO72',
     'scenario_group':'invalid-float','case':bad}
 r=c.post('/v72/orgs/magadan-lab/studies',headers={**h('lead'),'Content-Type':'application/json'},
          content=json.dumps(payload,allow_nan=True))
 assert r.status_code==422,r.text

def test_portfolio_magnitude_guard():
 bad=copy.deepcopy(PO);bad['annual_budgets_rub'][0]='1000000000000000000'
 with pytest.raises(ValueError,match='INVALID_OR_OUT_OF_RANGE_MONEY'):
  compute_study('hydrocapex',bad)

def test_module_schema_and_explicit_release_limits(env):
 c=env['client']
 meta=c.get('/v72/meta/modules').json()
 assert len(meta['modules'])==6
 assert meta['approval_pipeline_connected'] is False
 for name in CASES:
  resp=c.get(f'/v72/meta/modules/{name}/schema')
  assert resp.status_code==200
  assert resp.json()['request_scope']=='SYNTHETIC_LAB_ONLY'
  assert resp.json()['json_schema']['properties']
 assert c.get('/v72/meta/modules/unknown/schema').status_code==404
 readiness=c.get('/v71/meta/readiness').json()
 assert readiness['version']=='0.7.2'
 assert readiness['production_ready'] is False

def test_lab_rejects_non_lab_asset_even_if_member(env):
 from hydro_api.storage import Asset
 c,h=env['client'],env['h']
 with env['db']() as db:
  db.add(Asset(id='actual-like-asset',org_id='magadan-lab',name='Restricted asset',classification='REAL'))
  db.commit()
 r=c.post('/v72/orgs/magadan-lab/studies',headers=h('lead'),json={
  'asset_id':'actual-like-asset','module':'gridloss','source_ref':'SYNTHETIC-HYDRO72',
  'scenario_group':'classification-check','case':GR})
 assert r.status_code==409,r.text
 assert 'NON_SYNTHETIC_ASSET' in r.text
