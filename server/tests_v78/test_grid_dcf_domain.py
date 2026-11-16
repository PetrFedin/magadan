"""V7.8 reproducible physics -> time windows -> WBS -> nominal DCF tests."""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal as D
from calendar import isleap
import pytest
from pydantic import ValidationError
from hydro_api.radial_grid import RadialCase,solve_radial
from hydro_api.programme_v74 import CapitalScreen,screen_capital
from hydro_api.grid_cashflow_v78 import GridDCFInputV78,evaluate_grid_dcf_v78
from tests_v73.test_radial_and_finance import feeder


def wbs():
    return {
        'title':'Synthetic single feeder improvement','currency':'RUB',
        'tax_basis':'EXCL_VAT_SYNTHETIC',
        'annual_caps_rub':{'2027':'400000','2028':'1700000','2029':'600000'},
        'contingency_percent':'0',
        'lines':[
            {'code':'survey','title':'Synthetic field survey','category':'survey','year':2027,
             'quantity':'1','unit':'lot','unit_price_rub':'300000','price_source_ref':'SYNTHETIC-V78-SURVEY'},
            {'code':'equipment','title':'Synthetic apparatus','category':'equipment','year':2028,
             'quantity':'1','unit':'lot','unit_price_rub':'1500000','price_source_ref':'SYNTHETIC-V78-EQUIPMENT','predecessors':['survey']},
            {'code':'commission','title':'Synthetic commissioning','category':'commissioning','year':2029,
             'quantity':'1','unit':'lot','unit_price_rub':'500000','price_source_ref':'SYNTHETIC-V78-COMMISSION','predecessors':['equipment']},
        ]}


def dcf():
    return {'benefit_key':'SYNTHETIC_V78_MEASURE_01',
            'discount_anchor_year':2026,'nominal_discount_rate':'0.12',
            'discount_source_ref':'SYNTHETIC-NOMINAL-DISCOUNT-V78',
            'first_full_service_year':2030,
            'price_scenario_factors':{'low':'0.7','base':'1','high':'1.3'},
            'annual_assumptions':[
               {'year':2030,'cycles':50,'avoided_supply_cost_rub_per_kwh':{'normal':'3','winter_peak':'8'},
                'retained_physical_savings_fraction':'1','additional_opex_rub':'100000',
                'cost_assumption_ref':'SYNTHETIC-AVOIDED-COST-2030'},
               {'year':2031,'cycles':50,'avoided_supply_cost_rub_per_kwh':{'normal':'4','winter_peak':'9'},
                'retained_physical_savings_fraction':'0.95','additional_opex_rub':'120000',
                'cost_assumption_ref':'SYNTHETIC-AVOIDED-COST-2031'}],
            'economic_rationale':'The proposed synthetic feeder has altered resistance while loads remain identical. Benefits are priced independently by load window and year; no field verification exists.',
            'basis':'NOMINAL_RUB_WITH_NOMINAL_DISCOUNT_NO_VAT_OR_TAX'}


def inputs():
    case=feeder(); alternative=deepcopy(case)
    alternative['nodes'][0]['r_ohm_per_phase']=0.13
    bc,ac=RadialCase.model_validate(case),RadialCase.model_validate(alternative)
    return bc,ac,solve_radial(bc),solve_radial(ac),CapitalScreen.model_validate(wbs()),GridDCFInputV78.model_validate(dcf())


def test_complete_chain_does_not_extrapolate_7200_hours_to_full_year():
    result=evaluate_grid_dcf_v78(*inputs())
    assert result['industrial_approval_eligible'] is False
    assert result['wbs_total_capex_rub']=='2300000.00'
    assert result['partial_coverage_years']==[2030,2031]
    by_year={r['year']:r for r in result['annual_physical_economics']}
    assert by_year[2027]['coverage_status']=='NO_BENEFITS_DURING_CONSTRUCTION'
    assert by_year[2030]['modeled_hours']=='7200.0'
    assert by_year[2030]['calendar_hours']==8760
    assert by_year[2030]['coverage_status']=='PARTIAL_YEAR_NO_EXTRAPOLATION'
    normal=next(x for x in by_year[2030]['window_calculations'] if x['name']=='normal')
    winter=next(x for x in by_year[2030]['window_calculations'] if x['name']=='winter_peak')
    assert normal['price_rub_per_kwh']=='3'
    assert winter['price_rub_per_kwh']=='8'
    assert D(by_year[2031]['signed_saved_energy_kwh']) < D(by_year[2030]['signed_saved_energy_kwh'])
    assert result['baseline_constraints_breached'] is False
    assert result['irr_status'].startswith('NOT_REPORTED')


def test_cashflows_recompute_from_pinned_wbs_and_window_economics():
    r=evaluate_grid_dcf_v78(*inputs())
    total=D('0')
    rows=r['scenario_results']['base']['yearly_cashflows']
    assert [x['year'] for x in rows]==[2027,2028,2029,2030,2031]
    assert [D(x['capex_from_wbs_rub']) for x in rows[:3]]==[D('300000'),D('1500000'),D('500000')]
    assert all(D(x['gross_rub'])==0 for x in rows[:3])
    for item in rows:
        year=item['year'];net=D(item['net_rub']);t=year-2026
        total+=net/(D('1.12')**t)
    assert abs(total-D(r['scenario_results']['base']['npv_rub']))<D('0.05')
    assert D(r['scenario_results']['low']['npv_rub'])<D(r['scenario_results']['base']['npv_rub'])<D(r['scenario_results']['high']['npv_rub'])
    assert r['tax_and_tariff_model']=='EXCLUDED_NOT_VERIFIED'


def test_too_many_hours_and_leap_year_are_checked():
    bc,ac,br,ar,cap,params=inputs()
    broken=dcf();broken['annual_assumptions'][0]['cycles']=61
    with pytest.raises(ValueError,match='YEARLY_WINDOW_HOURS_EXCEED_CALENDAR_YEAR'):
        evaluate_grid_dcf_v78(bc,ac,br,ar,cap,GridDCFInputV78.model_validate(broken))
    broken=dcf();broken['annual_assumptions'][0]['year']=2032
    with pytest.raises((ValueError,ValidationError),match='FIRST_SERVICE_YEAR_MISSING|NONCONTIGUOUS'):
        GridDCFInputV78.model_validate(broken)
    assert isleap(2032) and not isleap(2031)


def test_engineering_invariants_and_alternative_limits():
    bc,ac,br,ar,cap,params=inputs()
    bad=ac.model_copy(deep=True);bad.nodes[1].load_p_mw+=0.5
    with pytest.raises(ValueError,match='ENGINEERING_INVARIANT_MISMATCH'):
        evaluate_grid_dcf_v78(bc,bad,br,ar,cap,params)
    bad=ac.model_copy(deep=True);bad.nodes[0].ampacity_a=1
    with pytest.raises(ValueError,match='ALTERNATIVE_ENGINEERING_LIMITS_NOT_MET'):
        evaluate_grid_dcf_v78(bc,bad,br,solve_radial(bad),cap,params)


def test_full_service_must_be_after_commissioning_and_capex():
    bc,ac,br,ar,cap,_=inputs()
    bad=dcf();bad['first_full_service_year']=2029
    bad['annual_assumptions'][0]['year']=2029;bad['annual_assumptions'][1]['year']=2030
    with pytest.raises(ValueError,match='BENEFIT_BEFORE_FULL_SERVICE_YEAR'):
        evaluate_grid_dcf_v78(bc,ac,br,ar,cap,GridDCFInputV78.model_validate(bad))
    cap2=cap.model_copy(deep=True);cap2.lines=[line for line in cap2.lines if line.category!='commissioning']
    with pytest.raises(ValueError,match='COMMISSIONING_WBS_REQUIRED'):
        evaluate_grid_dcf_v78(bc,ac,br,ar,cap2,GridDCFInputV78.model_validate(dcf()))


def test_window_prices_explicit_and_numeric_not_boolean():
    bc,ac,br,ar,cap,_=inputs()
    bad=dcf();bad['annual_assumptions'][0]['avoided_supply_cost_rub_per_kwh']={'normal':'3'}
    with pytest.raises(ValueError,match='MISSING_OR_EXTRA_WINDOW_PRICE'):
        evaluate_grid_dcf_v78(bc,ac,br,ar,cap,GridDCFInputV78.model_validate(bad))
    bad=dcf();bad['annual_assumptions'][0]['avoided_supply_cost_rub_per_kwh']['normal']=True
    with pytest.raises(ValidationError,match='BOOLEAN_IS_NOT_ENERGY_PRICE'):
        GridDCFInputV78.model_validate(bad)
    bad=dcf();bad['annual_assumptions'][0]['avoided_supply_cost_rub_per_kwh']['normal']='NaN'
    with pytest.raises(ValidationError):GridDCFInputV78.model_validate(bad)


def test_budget_breach_visible_but_no_automatic_financing_approval():
    bc,ac,br,ar,cap,params=inputs()
    cap.annual_caps_rub[2028]=D('500000')
    result=evaluate_grid_dcf_v78(bc,ac,br,ar,cap,params)
    assert result['status']=='LAB_BUDGET_LIMIT_BREACHED'
    assert not result['industrial_approval_eligible']


def test_worsened_physics_not_sold_as_avoided_cost():
    case=feeder(); alt=deepcopy(case);alt['nodes'][0]['r_ohm_per_phase']=0.40
    bc,ac=RadialCase.model_validate(case),RadialCase.model_validate(alt)
    r=evaluate_grid_dcf_v78(bc,ac,solve_radial(bc),solve_radial(ac),CapitalScreen.model_validate(wbs()),GridDCFInputV78.model_validate(dcf()))
    y=next(x for x in r['annual_physical_economics'] if x['year']==2030)
    assert D(y['signed_saved_energy_kwh'])<0
    assert D(y['gross_avoided_cost_rub'])<0
    assert D(r['scenario_results']['base']['npv_rub'])<D('-1000000')


def test_discount_anchor_and_wbs_versioned_money():
    bc,ac,br,ar,cap,params=inputs()
    bad=dcf();bad['discount_anchor_year']=2027
    with pytest.raises(ValueError,match='DISCOUNT_ANCHOR_NOT_BEFORE_FIRST_CAPEX'):
        evaluate_grid_dcf_v78(bc,ac,br,ar,cap,GridDCFInputV78.model_validate(bad))
    bad=dcf();bad['annual_assumptions'].append(deepcopy(bad['annual_assumptions'][1]))
    with pytest.raises(ValidationError,match='DUPLICATED_FINANCIAL_YEAR'):
        GridDCFInputV78.model_validate(bad)
