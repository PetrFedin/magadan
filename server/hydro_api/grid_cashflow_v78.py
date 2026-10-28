"""V7.8: physically linked, annual window-level DCF for SYNTHETIC radial networks.

Only laboratory research. Prices are hypothetical avoided-cost assumptions, never a tariff.
All capital comes from a version-pinned single-intervention WBS, and benefits begin
strictly after its commissioning year. No safety, corporate or field sign-off.
"""
from __future__ import annotations
from calendar import isleap
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .radial_grid import Strict, RadialCase, physical_comparability
from .programme_v74 import CapitalScreen, screen_capital

D = Decimal
MONEY = D('0.01')


def decimal_string(n:Decimal, digits='0.01')->str:
    return str(n.quantize(D(digits), rounding=ROUND_HALF_UP))


class ValueFactors(Strict):
    low: Decimal = Field(ge=D('0'), le=D('3'))
    base: Decimal = Field(ge=D('0'), le=D('3'))
    high: Decimal = Field(ge=D('0'), le=D('3'))

    @field_validator('low','base','high',mode='before')
    @classmethod
    def no_bools(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_NUMERIC_SCENARIO_FACTOR')
        return v

    @model_validator(mode='after')
    def ordered(self):
        if not self.low<=self.base<=self.high:raise ValueError('VALUE_FACTORS_NOT_ORDERED')
        return self


class AnnualWindowAssumptions(Strict):
    year: int = Field(ge=2026, le=2045)
    cycles: int = Field(ge=0, le=8784)
    avoided_supply_cost_rub_per_kwh: dict[str,Decimal] = Field(min_length=1,max_length=48)
    retained_physical_savings_fraction: Decimal = Field(ge=D('0'), le=D('1'))
    additional_opex_rub: Decimal = Field(ge=-D('1000000000000000'),le=D('1000000000000000'))
    cost_assumption_ref: str = Field(min_length=20,max_length=150,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('year','cycles','retained_physical_savings_fraction','additional_opex_rub',mode='before')
    @classmethod
    def no_bool(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_FINANCIAL_VALUE')
        return v

    @field_validator('avoided_supply_cost_rub_per_kwh',mode='before')
    @classmethod
    def no_bool_map(cls,v):
        if isinstance(v,dict) and any(isinstance(x,bool) for x in v.values()):
            raise ValueError('BOOLEAN_IS_NOT_ENERGY_PRICE')
        return v

    @model_validator(mode='after')
    def bounded_prices(self):
        if any(not p.is_finite() or p<0 or p>D('100000') for p in self.avoided_supply_cost_rub_per_kwh.values()):
            raise ValueError('INVALID_COST_PER_KWH')
        return self


class GridDCFInputV78(Strict):
    scope: Literal['SYNTHETIC_SINGLE_INTERVENTION_NO_TARIFF']='SYNTHETIC_SINGLE_INTERVENTION_NO_TARIFF'
    benefit_key: str=Field(min_length=5,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    discount_anchor_year:int=Field(ge=2025,le=2044)
    nominal_discount_rate:Decimal=Field(ge=D('0'),le=D('0.6'))
    discount_source_ref:str=Field(min_length=20,max_length=150,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    first_full_service_year:int=Field(ge=2026,le=2045)
    price_scenario_factors:ValueFactors
    annual_assumptions:list[AnnualWindowAssumptions]=Field(min_length=1,max_length=20)
    economic_rationale:str=Field(min_length=70,max_length=3000)
    basis:Literal['NOMINAL_RUB_WITH_NOMINAL_DISCOUNT_NO_VAT_OR_TAX']='NOMINAL_RUB_WITH_NOMINAL_DISCOUNT_NO_VAT_OR_TAX'

    @field_validator('discount_anchor_year','nominal_discount_rate','first_full_service_year',mode='before')
    @classmethod
    def no_bool(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_FINANCIAL_VALUE')
        return v

    @model_validator(mode='after')
    def validate_timeline(self):
        years=[x.year for x in self.annual_assumptions]
        if len(set(years))!=len(years):raise ValueError('DUPLICATED_FINANCIAL_YEAR')
        if min(years)!=self.first_full_service_year:raise ValueError('FIRST_SERVICE_YEAR_MISSING')
        if sorted(years)!=list(range(min(years),max(years)+1)):
            raise ValueError('NONCONTIGUOUS_FINANCIAL_YEARS')
        if self.discount_anchor_year>=self.first_full_service_year:
            raise ValueError('DISCOUNT_ANCHOR_NOT_BEFORE_SERVICE')
        return self


def evaluate_grid_dcf_v78(baseline_case:RadialCase,alternative_case:RadialCase,
                          baseline_result:dict,alternative_result:dict,
                          capital:CapitalScreen,params:GridDCFInputV78)->dict:
    """Deterministic, transparent laboratory DCF. Expects already pinned source runs.

    Independent DB hash verification and authorization happen in the API boundary.
    No monetary attribution from the synthetic solver to a real grid is implied.
    """
    matched,reasons=physical_comparability(baseline_case,alternative_case)
    if not matched:raise ValueError('ENGINEERING_INVARIANT_MISMATCH:'+','.join(reasons))
    if alternative_result.get('status')!='LAB_ENGINEERING_LIMITS_MET' or alternative_result.get('constraint_violations'):
        raise ValueError('ALTERNATIVE_ENGINEERING_LIMITS_NOT_MET')
    if baseline_result.get('industrial_decision_eligible') is not False or alternative_result.get('industrial_decision_eligible') is not False:
        raise ValueError('UNAUTHORIZED_ENGINEERING_SCOPE')
    b_rows={row['window']:row for row in baseline_result['windows']}
    a_rows={row['window']:row for row in alternative_result['windows']}
    windows={w.name:w for w in baseline_case.windows}
    if not b_rows or set(b_rows)!=set(windows) or set(a_rows)!=set(windows):
        raise ValueError('ENGINEERING_RESULT_WINDOW_SET_MISMATCH')
    for name,w in windows.items():
        if abs(float(b_rows[name]['hours'])-w.hours)>1e-8 or abs(float(a_rows[name]['hours'])-w.hours)>1e-8:
            raise ValueError('ENGINEERING_RESULT_WINDOW_HOURS_MISMATCH')
    if capital.currency!='RUB' or capital.tax_basis!='EXCL_VAT_SYNTHETIC':
        raise ValueError('INCOMPATIBLE_WBS_CURRENCY_OR_TAX_BASIS')
    commissioned=[x.year for x in capital.lines if x.category=='commissioning']
    if not commissioned:raise ValueError('COMMISSIONING_WBS_REQUIRED')
    last_commissioning=max(commissioned)
    if params.first_full_service_year<=last_commissioning:
        raise ValueError('BENEFIT_BEFORE_FULL_SERVICE_YEAR')
    if max(x.year for x in capital.lines)>=params.first_full_service_year:
        raise ValueError('SINGLE_MEASURE_CONSTRUCTION_OVERLAPS_FULL_SERVICE')
    if params.discount_anchor_year>=min(x.year for x in capital.lines):
        raise ValueError('DISCOUNT_ANCHOR_NOT_BEFORE_FIRST_CAPEX')
    if any(set(row.avoided_supply_cost_rub_per_kwh)!=set(windows) for row in params.annual_assumptions):
        raise ValueError('MISSING_OR_EXTRA_WINDOW_PRICE')

    wbs=screen_capital(capital)
    capex_by_year={int(y):D(x['with_contingency_rub']) for y,x in wbs['cash_schedule'].items()}
    by_year={r.year:r for r in params.annual_assumptions}
    last_year=max(max(capex_by_year),max(by_year))
    financial_years=list(range(min(capex_by_year),last_year+1))
    with localcontext() as ctx:
        ctx.prec=42
        annual_rows={}
        for year in financial_years:
            annual=by_year.get(year)
            per_window=[]
            gross=D('0');total_savings_kwh=D('0');total_hours=D('0')
            if annual:
                for name,w in windows.items():
                    consumed_hours=D(str(w.hours))*D(annual.cycles)
                    baseline_loss_mwh=D(str(b_rows[name]['line_loss_p_mw']))*D(str(w.hours))
                    alt_loss_mwh=D(str(a_rows[name]['line_loss_p_mw']))*D(str(w.hours))
                    signed_saved_kwh=(baseline_loss_mwh-alt_loss_mwh)*D('1000')*D(annual.cycles)
                    physically_realized=signed_saved_kwh*annual.retained_physical_savings_fraction
                    price=annual.avoided_supply_cost_rub_per_kwh[name]
                    estimated_value=physically_realized*price
                    total_hours+=consumed_hours
                    total_savings_kwh+=physically_realized
                    gross+=estimated_value
                    # Technical loss ratio is a SYNTHETIC ratio of this modeled feeder,
                    # not the audited or regulated network loss percentage.
                    delivered_mw=D(str(sum(node.load_p_mw for node in baseline_case.nodes)))*D(str(w.scale))
                    base_loss_power=D(str(b_rows[name]['line_loss_p_mw']))
                    alt_loss_power=D(str(a_rows[name]['line_loss_p_mw']))
                    base_loss_ratio=(base_loss_power/(delivered_mw+base_loss_power)*D('100')) if (delivered_mw+base_loss_power)>0 else None
                    alt_loss_ratio=(alt_loss_power/(delivered_mw+alt_loss_power)*D('100')) if (delivered_mw+alt_loss_power)>0 else None
                    per_window.append({'name':name,'hours_in_cycle':str(w.hours),
                        'assumed_cycles':annual.cycles,'modelled_hours':str(consumed_hours),
                        'base_loss_mwh_per_cycle':decimal_string(baseline_loss_mwh,'0.000000001'),
                        'alternative_loss_mwh_per_cycle':decimal_string(alt_loss_mwh,'0.000000001'),
                        'avoided_kwh_after_retention':decimal_string(physically_realized,'0.000001'),
                        'price_rub_per_kwh':str(price),
                        'gross_value_rub':decimal_string(estimated_value),
                        'modeled_delivered_active_power_mw':decimal_string(delivered_mw,'0.000001'),
                        'base_technical_loss_pct_of_input':(decimal_string(base_loss_ratio,'0.000001') if base_loss_ratio is not None else None),
                        'alternative_technical_loss_pct_of_input':(decimal_string(alt_loss_ratio,'0.000001') if alt_loss_ratio is not None else None),
                        'base_min_voltage_pu':str(b_rows[name]['min_voltage_pu']),
                        'alternative_min_voltage_pu':str(a_rows[name]['min_voltage_pu']),
                        'alternative_thermal_violations':a_rows[name]['thermal_violations'],
                        'alternative_voltage_violations':a_rows[name]['voltage_violations']})
                calendar_hours=D('8784') if isleap(year) else D('8760')
                if total_hours>calendar_hours:
                    raise ValueError('YEARLY_WINDOW_HOURS_EXCEED_CALENDAR_YEAR:'+str(year))
                coverage='FULL_SYNTHETIC_YEAR' if total_hours==calendar_hours else 'PARTIAL_YEAR_NO_EXTRAPOLATION'
            else:
                coverage='NO_BENEFITS_DURING_CONSTRUCTION'
            annual_rows[year]={'year':year,'modeled_hours':str(total_hours),
                'calendar_hours':(8784 if isleap(year) else 8760),'coverage_status':coverage,
                'signed_saved_energy_kwh':decimal_string(total_savings_kwh,'0.000001'),
                'gross_avoided_cost_rub':decimal_string(gross),
                'opex_delta_rub':decimal_string(annual.additional_opex_rub if annual else D('0')),
                'wbs_capex_rub':decimal_string(capex_by_year.get(year,D('0'))),
                'window_calculations':per_window}
        scenarios={}
        for scenario in ('low','base','high'):
            factor=getattr(params.price_scenario_factors,scenario)
            npv=D('0');gross_pv=D('0');opex_pv=D('0');capital_pv=D('0')
            years=[];cumulative=D('0');payback=None
            for year in financial_years:
                data=annual_rows[year]
                gross=D(data['gross_avoided_cost_rub'])*factor
                opex=D(data['opex_delta_rub']);cap=D(data['wbs_capex_rub'])
                net=gross-opex-cap
                t=year-params.discount_anchor_year
                df=(D('1')+params.nominal_discount_rate)**t
                pv=net/df
                gross_pv+=gross/df;opex_pv+=opex/df;capital_pv+=cap/df
                npv+=pv;cumulative+=pv
                if payback is None and year>=params.first_full_service_year and cumulative>=0:
                    payback=year  # first year-end with nonnegative discounted cumulative flow
                years.append({'year':year,'t_year_end':t,
                    'gross_rub':decimal_string(gross),'opex_delta_rub':decimal_string(opex),
                    'capex_from_wbs_rub':decimal_string(cap),'net_rub':decimal_string(net),
                    'pv_rub':decimal_string(pv),'cumulative_pv_rub':decimal_string(cumulative)})
            break_even=None
            if gross_pv>0:
                break_even=max(D('0'),(opex_pv+capital_pv)/gross_pv)
            scenarios[scenario]={'scenario_factor':str(factor),
                'npv_rub':decimal_string(npv),'pv_gross_rub':decimal_string(gross_pv),
                'pv_opex_rub':decimal_string(opex_pv),'pv_capex_rub':decimal_string(capital_pv),
                'discounted_payback_year':payback,
                'break_even_extra_gross_multiplier':(decimal_string(break_even,'0.000001') if break_even is not None else None),
                'yearly_cashflows':years,'positive_npv':npv>0}
    source_breach=bool(baseline_result.get('constraint_violations'))
    partial_years=[year for year,data in annual_rows.items() if data['coverage_status']=='PARTIAL_YEAR_NO_EXTRAPOLATION']
    return {'status':'LAB_BUDGET_LIMIT_BREACHED' if wbs['status']=='ASSUMED_BUDGET_CAP_BREACHED' else 'LAB_NON_AUTHORITATIVE_RESEARCH',
            'scope':'SYNTHETIC_SINGLE_MEASURE_ONLY',
            'benefit_key':params.benefit_key,
            'financial_basis':params.basis,
            'discount_rate':str(params.nominal_discount_rate),
            'anchor_date':'31-DEC-'+str(params.discount_anchor_year),
            'year_end_convention':True,'first_full_service_year':params.first_full_service_year,
            'annual_physical_economics':[annual_rows[y] for y in financial_years],
            'scenario_results':scenarios,'wbs_total_capex_rub':wbs['total_synthetic_cost_rub'],
            'wbs_status':wbs['status'],'wbs_missing_stages':wbs['missing_project_stages'],
            'partial_coverage_years':partial_years,
            'baseline_constraints_breached':source_breach,
            'obligation_or_safety_must_be_separately_assessed':source_breach,
            'economic_gain_is_not_mandatory_project_priority':True,
            'irr_status':'NOT_REPORTED_MAY_HAVE_MULTIPLE_ROOTS',
            'tax_and_tariff_model':'EXCLUDED_NOT_VERIFIED',
            'source_is_not_third_party_attested':True,
            'independent_engineering_accepted':False,
            'industrial_approval_eligible':False,
            'limitations':[
                'Synthetic radial balanced PQ feeder with fixed topology and artificial loads only',
                'Only specified annual load windows are monetized; partial-year cases not extrapolated',
                'No actual tariff: window prices are synthetic avoided-cost assumptions',
                'Savings retention factors are assumptions, NOT probabilities or measured degradation',
                'No VAT, income tax, financing, depreciation, regulatory approval or field M&V',
                'WBS applies to exactly one measure; avoid double-counting programme-level CAPEX',
                'Year-end nominal cashflows discounted to 31 December of the discount anchor year',
                'Independent engineering and financial validation required before any decision',
            ]}
