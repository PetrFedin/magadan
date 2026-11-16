"""V7.5: explicitly bounded synthetic domain couplings; NEVER operating instructions.

Hydrological input is a historical prediction from a HINDCAST test, not a
live forecast. Turbine anomaly scores are not calibrated failure risks.
"""
from __future__ import annotations
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .studies import Strict, ForecastCase, CascadeCase, ReservoirStep


class ForecastCascadeBridge(Strict):
    """Published contract for the *mapping*, not a generic semantics label."""
    kind: Literal['HISTORICAL_PREDICTION_TO_UPPER_LOCAL_INFLOW']='HISTORICAL_PREDICTION_TO_UPPER_LOCAL_INFLOW'
    scenario: Literal['point','lower','upper']='point'
    step_hours: int=Field(ge=1,le=168)
    travel_lag_steps: int=Field(ge=0,le=4)
    arrival_history_cms: list[float]=Field(default_factory=list,max_length=4)
    max_steps: int=Field(ge=3,le=72,default=72)
    hydrological_mapping_ref: str=Field(min_length=20,max_length=140,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('arrival_history_cms',mode='before')
    @classmethod
    def reject_boolean_arrival_history(cls,value):
        if isinstance(value,list) and any(isinstance(x,bool) for x in value):
            raise ValueError('BOOLEAN_NOT_A_FLOW_MEASUREMENT')
        return value

    @field_validator('step_hours','travel_lag_steps','max_steps',mode='before')
    @classmethod
    def forbid_bools(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_PERIOD')
        return v

    @model_validator(mode='after')
    def history(self):
        if len(self.arrival_history_cms)!=self.travel_lag_steps:
            raise ValueError('TRAVEL_LAG_REQUIRES_EXPLICIT_HISTORY')
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or x<0 or x>1e5 or x!=x for x in self.arrival_history_cms):
            raise ValueError('INVALID_ARRIVAL_HISTORY')
        return self


def advance(step:ReservoirStep, initial_storage:float, incoming_cms:float, hours:float)->dict:
    """Simplified constant-head, constant-release mass balance for a research timestep."""
    outgoing=step.turbine_release_cms+step.spill_release_cms
    result_volume=initial_storage+(incoming_cms-outgoing-step.other_losses_cms)*hours*3600.0
    power_mw=0.00981*step.turbine_release_cms*step.head_m*step.efficiency
    errors=[]
    if initial_storage<step.min_storage_m3-0.01 or initial_storage>step.max_storage_m3+0.01:
        errors.append('INITIAL_STORAGE_OUT_OF_BOUNDS')
    if result_volume<step.min_storage_m3-0.01 or result_volume>step.max_storage_m3+0.01:
        errors.append('FINAL_STORAGE_OUT_OF_BOUNDS')
    if outgoing<step.min_total_release_cms:
        errors.append('MIN_RELEASE_BREACH')
    if power_mw>step.rated_capacity_mw+1e-9:
        errors.append('NAMEPLATE_BREACH')
    return {'initial_storage_m3':round(initial_storage,3),'inflow_cms':round(incoming_cms,6),
            'outflow_cms':round(outgoing,6),'final_storage_m3':round(result_volume,3),
            'power_mw':round(power_mw,6),'energy_mwh':round(power_mw*hours,6),
            'constraints_breached':errors}


def couple_forecast_to_cascade(forecast:ForecastCase,template:CascadeCase,settings:ForecastCascadeBridge)->dict:
    """A time-indexed forecast→reservoir *research adapter*, not physical routing."""
    if template.period_hours!=settings.step_hours:
        raise ValueError('STEP_HOURS_MUST_MATCH_CASCADE_TEMPLATE')
    if len(forecast.targets)>settings.max_steps:
        raise ValueError('LAB_MAX_STEP_BUDGET_EXCEEDED')
    targets=sorted(forecast.targets,key=lambda x:x.target_at.astimezone(timezone.utc))
    seconds=settings.step_hours*3600.0
    for i,t in enumerate(targets):
        if i and abs((t.target_at-targets[i-1].target_at).total_seconds()-seconds)>0.001:
            raise ValueError('NON_CONTIGUOUS_FORECAST_TIMELINE')
        if t.target_at<=forecast.issued_at:
            raise ValueError('FORECAST_TARGET_BEFORE_ISSUE')
    if template.upper.name==template.lower.name:
        raise ValueError('CASCADE_RESERVOIR_NAMES_NOT_DISTINCT')
    up_store=template.upper.initial_storage_m3
    down_store=template.lower.initial_storage_m3
    release_history=list(settings.arrival_history_cms)
    rows=[];errors=[];sum_energy=0.0
    for ix,target in enumerate(targets):
        q={'point':target.predicted_cms,'lower':target.lower_cms,'upper':target.upper_cms}[settings.scenario]
        up=advance(template.upper,up_store,q,settings.step_hours)
        current_up_release=up['outflow_cms']
        if settings.travel_lag_steps:
            arriving=release_history.pop(0)
            release_history.append(current_up_release)
        else:
            arriving=current_up_release
        lower_q=template.lower.local_inflow_cms+arriving
        down=advance(template.lower,down_store,lower_q,settings.step_hours)
        for label,run in (('upper',up),('lower',down)):
            errors.extend(f"t{ix}:{label}:{e}" for e in run['constraints_breached'])
        up_store=up['final_storage_m3']
        down_store=down['final_storage_m3']
        sum_energy+=up['energy_mwh']+down['energy_mwh']
        rows.append({'target_at_utc':target.target_at.astimezone(timezone.utc).isoformat(),
                     'historical_forecast_cms':q,'lagged_arrival_cms':round(arriving,6),
                     'upper':up,'lower':down})
    return {'status':'LAB_CONSTRAINT_BREACH' if errors else 'LAB_MASS_BALANCE_OK',
            'issue_at_utc':forecast.issued_at.astimezone(timezone.utc).isoformat(),
            'scenario':settings.scenario,'mapping':settings.kind,'step_hours':settings.step_hours,
            'travel_lag_steps':settings.travel_lag_steps,'n_steps':len(rows),'rows':rows,
            'synthetic_total_energy_mwh':round(sum_energy,6),'constraint_violations':errors,
            'historic_actuals_used_for_hydraulic_input':False,
            'assumptions':['Forecast source is a historical hindcast, NOT an operational forecast',
                           'Fixed releases, head, efficiency and reservoir limits; no active dispatch',
                           'No hydrodynamic routing; fixed integer-step travel lag is illustrative',
                           'Hydrological mapping and reservoir parameters are synthetic, not Kolymaskaya/Ust-Srednekan physical parameters'],
            'industrial_approval_eligible':False}


class MaintenanceOption(Strict):
    option_id:str=Field(min_length=3,max_length=48,pattern=r'^[A-Za-z0-9_-]+$')
    action:Literal['inspection','repair','replacement','defer']
    materials_rub:Decimal=Field(ge=0,le=Decimal('1e13'))
    labor_rub:Decimal=Field(ge=0,le=Decimal('1e13'))
    north_logistics_rub:Decimal=Field(ge=0,le=Decimal('1e13'))
    outage_hours:Decimal=Field(ge=0,le=Decimal('1e5'))
    downtime_value_rub_per_hour:Decimal=Field(ge=0,le=Decimal('1e10'))
    lead_time_days:int=Field(ge=0,le=3650)
    basis_ref:str=Field(min_length=20,max_length=150,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('materials_rub','labor_rub','north_logistics_rub','outage_hours','downtime_value_rub_per_hour','lead_time_days',mode='before')
    @classmethod
    def avoid_bool(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_COST_OR_DURATION')
        return v

    @model_validator(mode='after')
    def defer_is_not_a_zero_risk_shortcut(self):
        if self.action=='defer' and (self.materials_rub+self.labor_rub+self.north_logistics_rub+self.outage_hours)>0:
            raise ValueError('DEFER_CANNOT_CLAIM_COMPLETED_WORK_OR_OUTAGE')
        return self

class MaintenanceBridge(Strict):
    planning_reference:str=Field(min_length=20,max_length=140,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    options:list[MaintenanceOption]=Field(min_length=2,max_length=8)
    @model_validator(mode='after')
    def unique(self):
        if len(set(v.option_id for v in self.options))!=len(self.options):
            raise ValueError('DUPLICATE_MAINTENANCE_OPTION')
        return self


def build_maintenance_decision(turbine_result:dict,settings:MaintenanceBridge)->dict:
    if turbine_result.get('failure_probability') is not None:
        raise ValueError('UNSUPPORTED_FAILURE_PROBABILITY_IN_SOURCE')
    if turbine_result.get('status') not in {'CHECK_SIGNAL','NO_LAB_THRESHOLD_BREACH','INSUFFICIENT_VARIABILITY_FOR_SCORE'}:
        raise ValueError('UNKNOWN_DIAGNOSTIC_RESULT')
    lines=[]
    for op in settings.options:
        direct=op.materials_rub+op.labor_rub+op.north_logistics_rub
        downtime=op.outage_hours*op.downtime_value_rub_per_hour
        total=direct+downtime
        if not total.is_finite():raise ValueError('NONFINITE_MAINTENANCE_COST')
        lines.append({'option_id':op.option_id,'action':op.action,'direct_expenditure_rub':str(direct.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                      'assumed_downtime_cost_rub':str(downtime.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                      'total_direct_plus_downtime_rub':str(total.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                      'lead_time_days':op.lead_time_days,'source_ref':op.basis_ref})
    return {'status':'LAB_MAINTENANCE_OPTIONS_UNRANKED',
            'diagnostic_state':turbine_result['status'],
            'diagnostic_robust_z':turbine_result.get('robust_z'),
            'calibrated_failure_probability':None,
            'expected_avoided_failure_cost_rub':None,
            'options':lines,
            'auto_recommended_option_id':None,
            'economic_comparison_completeness':'DIRECT_COSTS_ONLY_NOT_LIFECYCLE_RISK',
            'required_professional_evidence':['Confirmed condition assessment and actual failure history',
                                              'Approved repair methodology and maintenance window',
                                              'Manufacturer specifications and technical safety judgement',
                                              'Verified costs, supplier lead times and outage valuation'],
            'limitations':['Cannot prefer deferral as cheapest when failure consequences are unknown',
                           'Vibration anomaly does not prove fault or failure probability',
                           'All prices and delays are synthetic, including north logistics'],
            'industrial_approval_eligible':False}
