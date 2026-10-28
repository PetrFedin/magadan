"""Physics and finance checks for a deliberately synthetic Magadan-style study."""
import json
from pathlib import Path
from decimal import Decimal
import pytest
from pydantic import ValidationError
from hydro_api.studies import ForecastCase,CascadeCase
from hydro_api.assurance_v76 import RoutingSpecification,route_single_step,routed_ensemble,AnnualValueModel,discounted_value_model
from hydro_api.programme_v74 import CapitalScreen

S=json.loads((Path(__file__).parents[1]/'ui'/'samples_v72.json').read_text())

def route():
    return RoutingSpecification(time_constant_hours=12,initial_routed_outflow_cms=30,mapping_ref='SYNTHETIC-UNVALIDATED-WATERSHED-V76')

def budget():
    return CapitalScreen.model_validate({
       'title':'Synthetic Magadan grid construction screening','currency':'RUB','tax_basis':'EXCL_VAT_SYNTHETIC',
       'annual_caps_rub':{'2027':'500000','2028':'2000000','2029':'800000'},
       'contingency_percent':'0',
       'lines':[{'code':'survey','title':'Synthetic terrain survey','category':'survey','year':2027,'quantity':'1','unit':'package',
                 'unit_price_rub':'500000','price_source_ref':'SYNTHETIC-SURVEY-V76'},
                {'code':'power','title':'Synthetic apparatus delivery','category':'equipment','year':2028,'quantity':'1','unit':'package',
                 'unit_price_rub':'1800000','price_source_ref':'SYNTHETIC-EQUIPMENT-V76','predecessors':['survey']},
                {'code':'test','title':'Synthetic commissioning tests','category':'commissioning','year':2029,'quantity':'1','unit':'package',
                 'unit_price_rub':'750000','price_source_ref':'SYNTHETIC-COMMISSIONING-V76','predecessors':['power']}]
    })

def value():
    return AnnualValueModel.model_validate({
     'benefit_key':'V76_SYNTHETIC_ENERGY_SAVINGS','source_assumption_ref':'SYNTHETIC-VALUE-NOT-VERIFIED-V76',
     'discounted_from_year':2027,'discount_rate':'0.12','benefit_scenarios':{'low':'0.5','base':'1','high':'1.5'},
     'annual_gross_value_rub':{'2028':'200000','2029':'350000','2030':'500000','2031':'500000'},
     'annual_incremental_opex_rub':{'2028':'20000','2029':'30000','2030':'30000','2031':'30000'},
     'rationale':'Synthetic annual avoided losses only for software verification; not a claim of actual saving.'})

def test_routing_mass_conservation_and_physical_bounds():
    for incoming in (0.,5.,40.,200.):
        for prev in (0.,10.,90.):
            d=route_single_step(incoming,prev,3600,8*3600)
            assert abs(d['water_balance_residual_m3'])<1e-6
            assert min(prev,incoming)-1e-8<=d['mean_arrival_cms']<=max(prev,incoming)+1e-8
            assert min(prev,incoming)-1e-8<=d['end_arrival_cms']<=max(prev,incoming)+1e-8


def test_routed_ensemble_is_uncalibrated_and_does_not_optimise_production():
    result=routed_ensemble(ForecastCase.model_validate(S['hydroforecast']),CascadeCase.model_validate(S['cascade']),route())
    assert list(result['scenarios'])==['lower','point','upper']
    assert result['industrial_approval_eligible'] is False
    assert result['scenario_envelope_kind']=='UNCALIBRATED_INTERVAL_NOT_PROBABILITIES'
    assert all(len(v['rows'])==3 for v in result['scenarios'].values())
    assert all(abs(row['routing']['water_balance_residual_m3'])<1e-6 for c in result['scenarios'].values() for row in c['rows'])
    assert len({result['scenarios'][s]['total_energy_mwh'] for s in result['scenarios']})==1  # fixed release is NOT a dispatch optimisation
    assert result['scenarios']['lower']['end_upper_storage_m3']<result['scenarios']['point']['end_upper_storage_m3']<result['scenarios']['upper']['end_upper_storage_m3']


def test_bad_routing_rejected_without_implicit_defaults():
    with pytest.raises(ValidationError):RoutingSpecification(time_constant_hours=True,initial_routed_outflow_cms=0,mapping_ref='SYNTHETIC-VALID-REFERENCE-000')
    with pytest.raises(ValueError,match='INVALID_ROUTING_BOUNDARY'):route_single_step(2,-1,3600,3600)
    with pytest.raises(ValueError,match='ROUTING_STEP_BUDGET_EXCEEDED'):
        routed_ensemble(ForecastCase.model_validate(S['hydroforecast']),CascadeCase.model_validate(S['cascade']),route().model_copy(update={'max_time_steps':2}))


def test_financial_wbs_only_one_capex_source_and_no_grant_income():
    output=discounted_value_model(value(),budget())
    assert output['industrial_approval_eligible'] is False
    assert output['capital_screen']['total_synthetic_cost_rub']=='3050000.00'
    assert output['year_by_year']['base'][0]['wbs_capex_rub']=='500000.00'
    assert output['year_by_year']['base'][1]['wbs_capex_rub']=='1800000.00'
    assert Decimal(output['scenario_results']['low']['npv_rub'])<Decimal(output['scenario_results']['base']['npv_rub'])<Decimal(output['scenario_results']['high']['npv_rub'])
    assert Decimal(output['scenario_results']['base']['npv_rub'])<0


def test_finance_blocks_bad_annual_assumptions_and_budget_breaches():
    f=value().model_dump(mode='json')
    f['annual_incremental_opex_rub'].pop('2030')
    with pytest.raises(ValidationError):AnnualValueModel.model_validate(f)
    f=value().model_dump(mode='json');f['benefit_scenarios']['low']='1.8'
    with pytest.raises(ValidationError):AnnualValueModel.model_validate(f)
    cap=budget().model_dump(mode='json');cap['annual_caps_rub']['2028']='1'
    result=discounted_value_model(value(),CapitalScreen.model_validate(cap))
    assert result['status']=='LAB_CONSTRUCTION_CAP_BREACH'


def test_expenses_in_zero_revenue_years_are_not_dropped():
    f=value().model_dump(mode='json')
    f['annual_gross_value_rub']['2029']='0'
    r=discounted_value_model(AnnualValueModel.model_validate(f),budget())
    row=next(x for x in r['year_by_year']['base'] if x['year']==2029)
    assert Decimal(row['net_cashflow_rub'])==Decimal('-780000.00')


def test_hydrological_actuals_cannot_leak_into_routing():
    baseline=S['hydroforecast']
    from copy import deepcopy
    altered=deepcopy(baseline)
    for row in altered['targets']:
        row['actual_cms']=min(100000, row['actual_cms']+500)
    template=CascadeCase.model_validate(S['cascade'])
    before=routed_ensemble(ForecastCase.model_validate(baseline),template,route())
    after=routed_ensemble(ForecastCase.model_validate(altered),template,route())
    assert before==after


def test_routing_forecast_requires_contiguous_timeline():
    from copy import deepcopy
    altered=deepcopy(S['hydroforecast'])
    altered['targets'][1]['target_at']='2026-10-05T09:00:00+03:00'
    altered['targets'][1]['truth_available_at']='2026-10-05T12:00:00+03:00'
    with pytest.raises(ValueError,match='ROUTING_REQUIRES_CONTIGUOUS_FORECAST'):
        routed_ensemble(ForecastCase.model_validate(altered),CascadeCase.model_validate(S['cascade']),route())
