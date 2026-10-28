"""V7.4: synthetic-only programme assurance, construction screening and module linkage.

All outputs are RESEARCH ONLY: no regulatory proof, signed engineering report,
field input, approved investment budget, or access to real Magadan infrastructure.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .studies import Strict,HeatCase
from .heat_economics_v74 import HeatMoney,compare_heat

Money = Decimal
CAT = ('survey','design','equipment','civil_works','logistics','commissioning','contingency','other')
LINK_TYPES = {
    'forecast_context_for_cascade': ('hydroforecast','cascade'),
    'cascade_context_for_capex': ('cascade','hydrocapex'),
    'diagnostics_context_for_capex': ('turbine','hydrocapex'),
    'grid_context_for_capex': ('gridloss','hydrocapex'),
    'heat_context_for_capex': ('heatnet','hydrocapex'),
}


def money(v:Decimal)->str:
    return str(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

class WBSLine(Strict):
    code: str = Field(min_length=2,max_length=48,pattern=r'^[A-Za-z0-9_.-]+$')
    title: str = Field(min_length=6,max_length=180)
    category: Literal['survey','design','equipment','civil_works','logistics','commissioning','contingency','other']
    year: int = Field(ge=2026,le=2045)
    quantity: Money = Field(gt=0,le=Decimal('1e12'))
    unit: str = Field(min_length=1,max_length=20)
    unit_price_rub: Money = Field(ge=0,le=Decimal('1e14'))
    price_source_ref: str = Field(min_length=18,max_length=150,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    predecessors: list[str] = Field(default_factory=list,max_length=20)

    @field_validator('quantity','unit_price_rub','year',mode='before')
    @classmethod
    def reject_bool(cls,v):
        if isinstance(v,bool): raise ValueError('BOOLEAN_NOT_A_BUDGET_QUANTITY')
        return v

class CapitalScreen(Strict):
    currency: Literal['RUB']='RUB'
    tax_basis: Literal['EXCL_VAT_SYNTHETIC']='EXCL_VAT_SYNTHETIC'
    title: str = Field(min_length=8,max_length=160)
    annual_caps_rub: dict[int,Money] = Field(min_length=1,max_length=20)
    lines: list[WBSLine] = Field(min_length=1,max_length=80)
    contingency_percent: Money = Field(ge=0,le=Decimal('25'))

    @field_validator('contingency_percent',mode='before')
    @classmethod
    def reject_bool_pct(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_NOT_A_PERCENTAGE')
        return v

    @field_validator('annual_caps_rub',mode='before')
    @classmethod
    def check_budget_cap_values(cls,v):
        if not isinstance(v,dict):return v
        if any(isinstance(z,bool) for z in v.values()):raise ValueError('BOOLEAN_NOT_A_BUDGET_CAP')
        return v

    @model_validator(mode='after')
    def validate_wbs(self):
        if any(y<2026 or y>2045 for y in self.annual_caps_rub):raise ValueError('INVALID_BUDGET_YEAR')
        if any(not m.is_finite() or m<0 or m>Decimal('1e15') for m in self.annual_caps_rub.values()):
            raise ValueError('INVALID_BUDGET_CAP')
        if self.contingency_percent>0 and any(line.category=='contingency' for line in self.lines):
            raise ValueError('DOUBLE_BOOKED_CONTINGENCY')
        ids={x.code:x for x in self.lines}
        if len(ids)!=len(self.lines):raise ValueError('DUPLICATE_WBS_CODE')
        if any(x.year not in self.annual_caps_rub for x in self.lines):raise ValueError('MISSING_YEAR_BUDGET_CAP')
        for x in self.lines:
            if not (x.quantity.is_finite() and x.unit_price_rub.is_finite()):raise ValueError('NON_FINITE_WBS_VALUE')
            for p in x.predecessors:
                if p not in ids:raise ValueError('UNKNOWN_WBS_PREDECESSOR')
                if p==x.code:raise ValueError('WBS_SELF_DEPENDENCY')
                if ids[p].year>x.year:raise ValueError('PREDECESSOR_SCHEDULED_AFTER_SUCCESSOR')
        color={}
        def dfs(x):
            if color.get(x)==1:raise ValueError('CYCLIC_WBS_DEPENDENCY')
            if color.get(x)==2:return
            color[x]=1
            for p in ids[x].predecessors:dfs(p)
            color[x]=2
        for x in ids:dfs(x)
        return self


def screen_capital(plan:CapitalScreen)->dict:
    raw=defaultdict(lambda:Decimal('0'))
    category=defaultdict(lambda:Decimal('0'))
    for line in plan.lines:
        value=line.quantity*line.unit_price_rub
        raw[line.year]+=value
        category[line.category]+=value
    factor=Decimal('1')+plan.contingency_percent/Decimal('100')
    annual={}
    all_ok=True
    for year,cap in sorted(plan.annual_caps_rub.items()):
        scheduled=raw[year]*factor
        diff=scheduled-cap
        annual[str(year)]={'raw_rub':money(raw[year]),'with_contingency_rub':money(scheduled),
                           'cap_rub':money(cap),'over_cap_rub':money(max(Decimal('0'),diff)),
                           'within_cap':diff<=0}
        all_ok=all_ok and diff<=0
    missing=[c for c in ('survey','design','commissioning') if c not in category]
    return {'status':'SYNTHETIC_WBS_WITHIN_ASSUMED_CAPS' if all_ok else 'ASSUMED_BUDGET_CAP_BREACHED',
            'cash_schedule':annual,'total_synthetic_cost_rub':money(sum(raw.values())*factor),
            'contingency_percent':str(plan.contingency_percent),
            'categories_rub':{c:money(category.get(c,Decimal('0'))) for c in CAT},
            'missing_project_stages':missing,
            'scope':'SYNTHETIC_NON_AUTHORITATIVE_NO_CONSTRUCTION_ESTIMATE',
            'limitations':['Prices not confirmed by suppliers or estimate norms',
                           'No permitting, geocryology, geotechnical surveys, VAT, escalation, contracts, commissioning or cost assurance',
                           'A compliant WBS is not permission to construct']}

class ProgrammeLink(Strict):
    from_study_id:str=Field(min_length=1,max_length=100)
    to_study_id:str=Field(min_length=1,max_length=100)
    relationship:Literal['forecast_context_for_cascade','cascade_context_for_capex',
      'diagnostics_context_for_capex','grid_context_for_capex','heat_context_for_capex']

class HeatScenarioScreen(Strict):
    baseline_study_id: str = Field(min_length=1,max_length=100)
    proposed_study_id: str = Field(min_length=1,max_length=100)
    benefit_key: str = Field(min_length=5,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    finance: HeatMoney

class ProgrammeNew(Strict):
    reference_code:str=Field(min_length=6,max_length=80,pattern=r'^LAB-[A-Za-z0-9_-]+$')
    title:str=Field(min_length=12,max_length=180)
    purpose:str=Field(min_length=30,max_length=1800)
    study_ids:list[str]=Field(min_length=1,max_length=24)
    financial_dossier_ids:list[str]=Field(default_factory=list,max_length=12)
    links:list[ProgrammeLink]=Field(default_factory=list,max_length=48)
    heat_screenings:list[HeatScenarioScreen]=Field(default_factory=list,max_length=8)
    capital:CapitalScreen|None=None
    scope:Literal['SYNTHETIC_MAGADAN_RESEARCH_ONLY']='SYNTHETIC_MAGADAN_RESEARCH_ONLY'

    @model_validator(mode='after')
    def no_repeats(self):
        if len(set(self.study_ids))!=len(self.study_ids):raise ValueError('DUPLICATE_STUDY_ID')
        if len(set(self.financial_dossier_ids))!=len(self.financial_dossier_ids):raise ValueError('DUPLICATE_FINANCIAL_DOSSIER_ID')
        edges=[(e.from_study_id,e.to_study_id,e.relationship) for e in self.links]
        if len(edges)!=len(set(edges)):raise ValueError('DUPLICATE_SEMANTIC_LINK')
        if any(e.from_study_id==e.to_study_id for e in self.links):raise ValueError('SELF_REFERENTIAL_SEMANTIC_LINK')
        if len({h.benefit_key for h in self.heat_screenings})!=len(self.heat_screenings):raise ValueError('DUPLICATE_HEAT_BENEFIT_KEY')
        return self

REQUIREMENTS = {
 'hydroforecast':['real_hydrometeorological_data_licensed','historical_leakage_free_backtest','independent_hydrology_validation'],
 'cascade':['water_use_rules_in_force','reservoir_characteristics_verified','independent_cascade_model_validation'],
 'turbine':['diagnostic_event_labels_verified','maintenance_history_authenticated','competent_technical_signoff'],
 'gridloss':['actual_as_built_topology_accepted','measurement_boundaries_validated','external_powerflow_reference'],
 'heatnet':['pipeline_as_built_and_instruments_verified','hydraulic_calibration','independent_thermohydraulic_reference'],
 'hydrocapex':['source_of_funds_verified','owner_approved_baseline','independent_cost_estimate'],
}


def evaluate_programme(studies:list[dict],dossiers:list[dict],links:list[ProgrammeLink],capital:CapitalScreen|None,heat_screenings:list[HeatScenarioScreen]|None=None)->dict:
    """Pure deterministic screening from *already verified* tenant-scoped DB records.

    Studies: {id,module,asset_id,scenario_group,result,result_sha256,input_sha256,engine_sha256}
    Dossiers: {id,asset_id,baseline_run_id,proposed_run_id,benefit_key,result,result_sha256}
    """
    study_by_id={s['id']:s for s in studies}
    if len(study_by_id)!=len(studies):raise ValueError('DUPLICATED_SOURCE_STUDY')
    units=[];blockers=[]
    for s in studies:
        module=s['module'];payload=s['result']['result']
        reasons=[]
        if module=='hydroforecast' and payload.get('evaluation_kind')!='HINDCAST_ONLY':
            reasons.append('UNEXPECTED_FORECAST_EVALUATION')
        if module=='cascade' and payload.get('violations'):
            reasons.append('CASCADE_SYNTHETIC_CONSTRAINT_BREACH')
        if module=='turbine' and payload.get('failure_probability') is not None:
            reasons.append('UNSUPPORTED_FAILURE_PROBABILITY')
        if module=='gridloss' and payload.get('constraint_violations'):
            reasons.append('GRID_SYNTHETIC_CONSTRAINT_BREACH')
        if module=='hydrocapex' and payload.get('status')=='NO_FEASIBLE_PORTFOLIO':
            reasons.append('CAPEX_SYNTHETIC_PORTFOLIO_INFEASIBLE')
        if module=='heatnet' and payload.get('delivered_heat_mw') is None:
            reasons.append('HEAT_CALCULATION_INCOMPLETE')
        units.append({'study_id':s['id'],'module':module,'asset_id':s['asset_id'],
                      'model_status':'LAB_CONSTRAINT_ALERT' if reasons else 'LAB_CALCULATED_NOT_FIELD_VALIDATED',
                      'warnings':reasons,'field_approval_eligible':False,
                      'required_field_evidence':REQUIREMENTS.get(module,[])})
        blockers.extend(f"{s['id']}:{reason}" for reason in reasons)
    typed=[]
    for link in links:
        left=study_by_id.get(link.from_study_id);right=study_by_id.get(link.to_study_id)
        if not left or not right:raise ValueError('LINK_SOURCE_NOT_INCLUDED')
        if (left['module'],right['module'])!=LINK_TYPES[link.relationship]:
            raise ValueError('INCORRECT_DOMAIN_LINK_DIRECTION')
        if left['scenario_group']!=right['scenario_group']:
            raise ValueError('SEMANTIC_LINK_SCENARIO_GROUP_MISMATCH')
        typed.append({'from':left['id'],'to':right['id'],'relationship':link.relationship,
                      'meaning':'SEMANTIC_LINK_NO_VERIFIED_NUMERIC_TRANSFER',
                      'cross_asset':left['asset_id']!=right['asset_id']})
    by_dossier=[]
    for d in dossiers:
        if d['baseline_run_id'] not in study_by_id or d['proposed_run_id'] not in study_by_id:
            raise ValueError('FINANCIAL_DOSSIER_MISSING_PINNED_STUDY')
        base=study_by_id[d['baseline_run_id']];alt=study_by_id[d['proposed_run_id']]
        if base['asset_id']!=d['asset_id'] or alt['asset_id']!=d['asset_id']:
            raise ValueError('FINANCIAL_ASSET_SCOPE_MISMATCH')
        if base['module']!='gridloss' or alt['module']!='gridloss':
            raise ValueError('UNSUPPORTED_FINANCIAL_EVIDENCE_CLASS')
        if d['result'].get('status')!='SYNTHETIC_RESEARCH_ONLY_NO_APPROVAL':
            raise ValueError('INDUSTRIAL_DOSSIER_CANNOT_ENTER_LAB')
        by_dossier.append({'id':d['id'],'benefit_key':d['benefit_key'],
                           'scenario_pair':[base['id'],alt['id']],
                           'npv_by_price_scenario_rub':{k:v['npv_rub'] for k,v in
                             d['result']['economic_result']['price_scenarios'].items()},
                           'monetary_effect_approved':False})
    if len(set(d['benefit_key'] for d in dossiers))!=len(dossiers):
        raise ValueError('DUPLICATE_BENEFIT_CLAIM')
    heat_results=[]
    heat_claims=heat_screenings or []
    if set(h.benefit_key for h in heat_claims)&set(d['benefit_key'] for d in dossiers):
        raise ValueError('DUPLICATE_CROSS_DOMAIN_BENEFIT_KEY')
    used_pairs=set()
    for h in heat_claims:
        if h.baseline_study_id==h.proposed_study_id:
            raise ValueError('HEAT_IDENTICAL_BASELINE_AND_PROPOSAL')
        pair=(h.baseline_study_id,h.proposed_study_id)
        if pair in used_pairs:raise ValueError('HEAT_PAIR_REUSED_WITH_ANOTHER_CLAIM')
        used_pairs.add(pair)
        left=study_by_id.get(h.baseline_study_id);right=study_by_id.get(h.proposed_study_id)
        if not left or not right:raise ValueError('HEAT_SOURCE_NOT_INCLUDED_IN_PROGRAMME')
        if left['module']!='heatnet' or right['module']!='heatnet':
            raise ValueError('HEAT_SOURCE_MUST_BE_HEATNET')
        if (left['asset_id'],left['scenario_group'])!=(right['asset_id'],right['scenario_group']):
            raise ValueError('HEAT_DIFFERENT_ASSET_OR_BASELINE_GROUP')
        lab=compare_heat(HeatCase.model_validate(left['case_payload']),
              HeatCase.model_validate(right['case_payload']),left['result']['result'],right['result']['result'],h.finance)
        heat_results.append({'benefit_key':h.benefit_key,'scenario_pair':list(pair),
                             'research_result':lab,'monetary_effect_approved':False})
    budget=screen_capital(capital) if capital is not None else None
    if budget and budget['status']=='ASSUMED_BUDGET_CAP_BREACHED':
        blockers.append('CAPITAL_ASSUMED_BUDGET_CAP_BREACHED')
    if budget and (by_dossier or heat_results):
        base_cost=sum(Decimal(d['result']['economic_result']['construction_cost_rub']) for d in dossiers)+sum(Decimal(h.finance.capital_cost_rub) for h in heat_claims)
        plan_cost=Decimal(budget['total_synthetic_cost_rub'])
        if abs(base_cost-plan_cost)>Decimal('0.01'):
            blockers.append('CAPEX_ASSUMPTION_CONFLICT_BETWEEN_WBS_AND_FINANCIAL_DOSSIERS')
    return {
      'programme_status':'LAB_SCREENING_HAS_GAPS' if blockers else 'LAB_SCREENING_WITHOUT_COMPUTATIONAL_BLOCKERS',
      'scope':'SYNTHETIC_MAGADAN_RESEARCH_ONLY',
      'field_ready':False,'eligible_for_industrial_approval':False,
      'calculation_count':len(studies),'represented_modules':sorted({s['module'] for s in studies}),
      'study_quality':units,'semantic_links':typed,'financial_dossiers':by_dossier,'heat_economic_screenings':heat_results,
      'capital_budget_screen':budget,'computational_blockers':blockers,
      'external_mandatory_gates':[
          'ASSET_OWNER_DATA_PERMISSION','NATIVE_POSTGRESQL_RLS_ACCEPTANCE',
          'CORPORATE_IDP_AND_MFA','INDEPENDENT_ENGINEERING_REFERENCE',
          'CONTRACTUAL_FINANCIAL_BASELINE','REGULATORY_AND_CONSTRUCTION_PERMITS_IF_APPLICABLE',
          'EXTERNAL_IMMUTABLE_AUDIT_ACCEPTANCE','DOCUMENTED_ENGINEERING_SIGNOFF',
          'MEASUREMENT_AND_VERIFICATION_PLAN'],
      'economic_consolidation_status':'NO_CROSS_EFFECT_NPV_SUMMATION_OR_CAUSAL_ATTRIBUTION',
      'reason':'No field rights, industrial model validation, signed technical acceptance, or approved tariffs/costs'
    }
