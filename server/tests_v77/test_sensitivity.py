from decimal import Decimal
from tests_v76.test_assurance_domain import budget,value
from tests_v76.test_assurance_api import sources,create_parent,handoffs,payload
from hydro_api.assurance_v76 import discounted_value_model
from hydro_api.sensitivity_v77 import evaluate_sensitivity


def test_baseline_and_break_even_and_stresses():
    r=evaluate_sensitivity(value(),budget())
    base=discounted_value_model(value(),budget())
    assert r['scenario_npvs_rub']['baseline']['base']==base['scenario_results']['base']['npv_rub']
    assert Decimal(r['scenario_npvs_rub']['capex_plus_20_percent']['base'])<Decimal(r['scenario_npvs_rub']['baseline']['base'])
    assert Decimal(r['scenario_npvs_rub']['benefit_plus_20_percent']['base'])>Decimal(r['scenario_npvs_rub']['baseline']['base'])
    assert Decimal(r['break_even_multiplier_of_base_gross_value'])>Decimal('2')
    assert not r['industrial_approval_eligible']
    assert r['probabilities_assigned'] is False


def test_http_assurance_sensitivity_and_tenant_permissions(env):
    c,h=env['client'],env['h'];ids=sources(env);pid=create_parent(env,ids);hs=handoffs(env,ids,pid)
    result=c.post('/v76/orgs/magadan-lab/assurance-packs',headers=h('finance'),json=payload(pid,hs))
    assert result.status_code==201,result.text
    aid=result.json()['id']
    url='/v77/orgs/magadan-lab/assurance-packs/'+aid+'/sensitivity'
    assert c.get(url,headers=h('viewer')).status_code==403
    assert c.get(url,headers=h('lead')).status_code==403
    r=c.get(url,headers=h('finance'))
    assert r.status_code==200,r.text
    assert r.json()['report']['scenario_npvs_rub']['baseline']['base']==result.json()['financial']['scenario_results']['base']['npv_rub']
    assert r.json()['industrial_approval_eligible'] is False
    assert c.get(url,headers=h('audit')).status_code==200
    assert c.get('/v77/orgs/separate-org/assurance-packs/'+aid+'/sensitivity',headers=h('other')).status_code==403
    assert c.get('/v77/orgs/separate-org/assurance-packs/'+aid+'/sensitivity',headers=h('otheraudit')).status_code==404


def test_sensitive_wbs_budget_breach_is_visible_not_approved():
    response=evaluate_sensitivity(value(),budget())
    assert response['scenario_budget_status']['baseline']=='LAB_ANNUAL_CASHFLOW_CALCULATED'
    assert response['scenario_budget_status']['capex_plus_20_percent']=='LAB_CONSTRUCTION_CAP_BREACH'
    assert response['industrial_approval_eligible'] is False


def test_zero_benefit_has_no_fabricated_break_even():
    f=value().model_copy(deep=True)
    f.annual_gross_value_rub={year:Decimal('0') for year in f.annual_gross_value_rub}
    response=evaluate_sensitivity(f,budget())
    assert response['break_even_multiplier_of_base_gross_value'] is None
    assert response['break_even_exists_under_model'] is False
    assert Decimal(response['scenario_npvs_rub']['baseline']['base'])<0


def test_negative_opex_is_not_transformed_into_extra_savings_under_adverse_stress():
    f=value().model_copy(deep=True)
    f.annual_incremental_opex_rub={y:Decimal('-10000') for y in f.annual_incremental_opex_rub}
    r=evaluate_sensitivity(f,budget())
    assert Decimal(r['scenario_npvs_rub']['opex_adverse_20_percent']['base'])<Decimal(r['scenario_npvs_rub']['baseline']['base'])
