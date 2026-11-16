"""Deterministic, assumption-labeled OAT sensitivity for synthetic WBS DCF.

No probability distributions, grant claims, corporate tariffs or actual Magadan cost inputs.
The only source of CAPEX is the linked WBS. Not a project appraisal.
"""
from __future__ import annotations
from decimal import Decimal
from .programme_v74 import CapitalScreen,screen_capital
from .assurance_v76 import AnnualValueModel,discounted_value_model

D=Decimal


def _modified(fin:AnnualValueModel,cap:CapitalScreen,*,gross=D('1'),opex=D('1'),capex=D('1'),discount=D('0')):
    if capex<0 or gross<0 or opex<0:raise ValueError('NEGATIVE_SENSITIVITY_FACTOR')
    if not D('0')<=fin.discount_rate+discount<=D('0.6'):
        raise ValueError('SENSITIVITY_DISCOUNT_OUT_OF_MODEL_BOUNDS')
    f=fin.model_copy(deep=True);c=cap.model_copy(deep=True)
    f.discount_rate+=discount
    f.annual_gross_value_rub={y:v*gross for y,v in f.annual_gross_value_rub.items()}
    f.annual_incremental_opex_rub={y:v*(opex if v>=0 else max(D('0'), D('2')-opex)) for y,v in f.annual_incremental_opex_rub.items()}
    for l in c.lines:l.unit_price_rub*=capex
    return discounted_value_model(f,c)


def evaluate_sensitivity(finance:AnnualValueModel,capital:CapitalScreen)->dict:
    baseline=_modified(finance,capital)
    changes=[('benefit_minus_20_percent',{'gross':D('0.8')}),
             ('benefit_plus_20_percent',{'gross':D('1.2')}),
             ('capex_plus_20_percent',{'capex':D('1.2')}),
             ('opex_adverse_20_percent',{'opex':D('1.2')})]
    if finance.discount_rate+D('0.03')<=D('0.6'):
        changes.append(('discount_plus_3_percentage_points',{'discount':D('0.03')}))
    results={'baseline':baseline['scenario_results']}
    budget_flags={'baseline':baseline['status']}
    for name,kw in changes:
        changed=_modified(finance,capital,**kw)
        results[name]=changed['scenario_results']
        budget_flags[name]=changed['status']
    cap_by_year={int(y):D(v['with_contingency_rub']) for y,v in screen_capital(capital)['cash_schedule'].items()}
    years=set(cap_by_year)|set(finance.annual_gross_value_rub)
    r=finance.discount_rate; y0=finance.discounted_from_year
    pv_gross=sum((finance.annual_gross_value_rub.get(y,D('0'))*finance.benefit_scenarios.base
                 /((D('1')+r)**(y-y0)) for y in years),D('0'))
    pv_cost=sum(((cap_by_year.get(y,D('0'))+finance.annual_incremental_opex_rub.get(y,D('0')))
                 /((D('1')+r)**(y-y0)) for y in years),D('0'))
    threshold=None if pv_gross==0 else max(D('0'),pv_cost/pv_gross)
    return {'scope':'SYNTHETIC_SENSITIVITY_WITHOUT_PROBABILITIES',
            'status':'LAB_ANALYTICAL_SCREEN_ONLY', 'benefit_key':finance.benefit_key,
            'source_assumption_ref':finance.source_assumption_ref,
            'baseline_discount_rate':str(finance.discount_rate),
            'scenario_npvs_rub':{label:{k:v['npv_rub'] for k,v in values.items()} for label,values in results.items()},
            'scenario_budget_status':budget_flags,
            'break_even_multiplier_of_base_gross_value':None if threshold is None else str(threshold.quantize(D('0.000001'))),
            'break_even_exists_under_model':threshold is not None,
            'capital_source':'WBS_ONLY','probabilities_assigned':False,
            'uncertainty_does_not_imply_risk_distribution':True,
            'industrial_approval_eligible':False,
            'limitations':['One-at-a-time scenarios only, not P10/P50/P90 or probabilistic risk',
               'No taxes, tariffs, escalation, contractual or site-specific cost validation',
               'Real-world engineering obligation can override financial NPV']}
