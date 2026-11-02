"""V8.3 strictly synthetic, one-day forecast -> two-reservoir physical screen.

Explicit mass conservation includes the water already *in transit*. Releases
are externally specified synthetic values, never optimized operating advice.
A V8.2 single target-day forecast is NOT an independent multi-day trajectory.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil, fsum, isclose
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .forecast_v82 import DailyForecastResearchV82, StrictForecast, evaluate_daily_forecast

SECONDS_PER_DAY = 86_400.0
HOURS_PER_DAY = 24.0
GRAVITY_M_S2 = 9.80665
ENGINE_TAG = 'v83.2-one-day-cascade-exact-piecewise-head-and-instantaneous-cap-v3'


class StrictV83(StrictForecast):
    @field_validator('*', mode='before')
    @classmethod
    def reject_bool_numerics(cls, value):
        if type(value) is bool:
            raise ValueError('BOOLEAN_NOT_ALLOWED_IN_HYDROLOGIC_ENGINEERING_INPUT')
        return value


class VolumeElevationPoint(StrictV83):
    volume_m3: float = Field(ge=0, le=1e13)
    upstream_elevation_m: float = Field(ge=-1000, le=7000)


class TailwaterPoint(StrictV83):
    discharge_cms: float = Field(ge=0, le=1e5)
    elevation_m: float = Field(ge=-1000, le=7000)


class EfficiencyPoint(StrictV83):
    turbine_flow_fraction: float = Field(ge=0, le=1)
    efficiency: float = Field(ge=0, le=1)


class ReservoirV83(StrictV83):
    asset_id: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=100)
    source_ref: str = Field(min_length=20, max_length=120, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    start_volume_m3: float = Field(ge=0, le=1e13)
    min_volume_m3: float = Field(ge=0, le=1e13)
    max_volume_m3: float = Field(gt=0, le=1e13)
    storage_curve: list[VolumeElevationPoint] = Field(min_length=2, max_length=40)
    tailwater_curve: list[TailwaterPoint] = Field(min_length=2, max_length=40)
    efficiency_curve: list[EfficiencyPoint] = Field(min_length=2, max_length=40)
    turbine_capacity_cms: float = Field(gt=0, le=1e5)
    turbine_release_cms: float = Field(ge=0, le=1e5)
    spill_release_cms: float = Field(ge=0, le=1e5)
    other_losses_cms: float = Field(ge=0, le=1e5)
    minimum_release_cms: float = Field(ge=0, le=1e5)
    previous_release_cms: float = Field(ge=0, le=1e5)
    max_daily_ramp_cms: float = Field(ge=0, le=1e5)
    hydraulic_head_loss_m: float = Field(ge=0, le=500)
    rated_capacity_mw: float = Field(gt=0, le=1e5)

    @model_validator(mode='after')
    def validate_curves_and_start(self):
        if not self.min_volume_m3 < self.max_volume_m3:
            raise ValueError('RESERVOIR_VOLUME_LIMITS_INVALID')
        if not self.min_volume_m3 <= self.start_volume_m3 <= self.max_volume_m3:
            raise ValueError('RESERVOIR_START_OUTSIDE_LIMITS')
        x = [v.volume_m3 for v in self.storage_curve]
        y = [v.upstream_elevation_m for v in self.storage_curve]
        if any(b <= a for a,b in zip(x,x[1:])) or any(b <= a for a,b in zip(y,y[1:])):
            raise ValueError('NONMONOTONE_STORAGE_ELEVATION_CURVE')
        if x[0] > self.min_volume_m3 or x[-1] < self.max_volume_m3:
            raise ValueError('RESERVOIR_LIMITS_OUTSIDE_SURVEYED_CURVE')
        q = [v.discharge_cms for v in self.tailwater_curve]
        stage = [v.elevation_m for v in self.tailwater_curve]
        if any(b <= a for a,b in zip(q,q[1:])) or any(b < a for a,b in zip(stage,stage[1:])):
            raise ValueError('NONMONOTONE_TAILWATER_CURVE')
        f = [v.turbine_flow_fraction for v in self.efficiency_curve]
        eta = [v.efficiency for v in self.efficiency_curve]
        if f[0] != 0 or f[-1] != 1 or any(b <= a for a,b in zip(f,f[1:])):
            raise ValueError('EFFICIENCY_CURVE_MUST_COVER_ZERO_TO_ONE')
        if eta[0] != 0 or any(e <= 0 for e in eta[1:]):
            raise ValueError('EFFICIENCY_CURVE_MUST_HAVE_VALID_POSITIVE_OPERATION')
        return self


class UniformTravelLagV83(StrictV83):
    """Pure translation of *uniform daily mean* discharges, not flood routing.

    Historical releases are most recent first and source-attested only as
    SYNTHETIC. A three-day lag needs three prior daily releases.
    """
    delay_hours: float = Field(ge=0, le=72)
    previous_daily_releases_cms: list[float] = Field(default_factory=list, max_length=3)
    source_ref: str = Field(min_length=20, max_length=120, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('previous_daily_releases_cms')
    @classmethod
    def valid_previous_flows(cls, xs):
        if any(type(v) is bool or v < 0 or v > 1e5 for v in xs):
            raise ValueError('INVALID_HISTORICAL_RELEASE')
        return xs

    @model_validator(mode='after')
    def required_daily_history(self):
        if len(self.previous_daily_releases_cms) != ceil(self.delay_hours / 24):
            raise ValueError('TRAVEL_LAG_HISTORY_LENGTH_INCONSISTENT')
        return self


class CoupledCascadeV83(StrictV83):
    scope: Literal['SYNTHETIC_CASCADE_RESEARCH_ONLY'] = 'SYNTHETIC_CASCADE_RESEARCH_ONLY'
    forecast: DailyForecastResearchV82
    daily_observation_semantics: Literal['UTC_DAILY_MEAN_PERIOD_END_AT_OBSERVED_AT']
    target_start_state_and_prior_release_basis: Literal['SYNTHETIC_CONDITIONAL_FUTURE_ASSUMPTIONS_NOT_KNOWN_AT_FORECAST_ISSUE']
    initial_storage_state_ref: str = Field(min_length=20, max_length=120, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    upper: ReservoirV83
    lower: ReservoirV83
    route: UniformTravelLagV83
    hydrological_mapping_ref: str = Field(min_length=20, max_length=120, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    lower_local_inflow_cms: float = Field(ge=0, le=1e5)
    lower_local_inflow_ref: str = Field(min_length=20, max_length=120, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    upper_other_local_inflow_cms: float = Field(default=0, ge=0, le=1e5)
    water_density_kg_m3: float = Field(default=1000, ge=900, le=1100)

    @model_validator(mode='after')
    def consistent_one_day_and_assets(self):
        if self.forecast.horizon_days != 2:
            raise ValueError('EXACTLY_TWO_DAY_END_TIMESTAMP_FOR_NEXT_FULL_TARGET_DAY_REQUIRED')
        if self.forecast.asset_id != self.upper.asset_id:
            raise ValueError('FORECAST_MEASUREMENT_BOUNDARY_MUST_MATCH_UPSTREAM_ASSET')
        if self.lower.asset_id == self.upper.asset_id:
            raise ValueError('TWO_DISTINCT_SYNTHETIC_ASSETS_REQUIRED')
        history = self.route.previous_daily_releases_cms
        if history and not isclose(history[0], self.upper.previous_release_cms, rel_tol=0, abs_tol=1e-9):
            raise ValueError('PREVIOUS_UPSTREAM_RELEASE_CONFLICTS_WITH_ROUTE_HISTORY')
        return self


def linear_interpolate(x: float, xs: list[float], ys: list[float]) -> float:
    if x < xs[0] or x > xs[-1]:
        raise ValueError('EXTRAPOLATION_FORBIDDEN')
    for i in range(1,len(xs)):
        if x <= xs[i]:
            return ys[i-1] + (ys[i] - ys[i-1]) * (x - xs[i-1]) / (xs[i] - xs[i-1])
    return ys[-1]


def route_uniform_day(current_cms:float, settings:UniformTravelLagV83)->dict:
    lag=settings.delay_hours/HOURS_PER_DAY
    series=[current_cms]+settings.previous_daily_releases_cms
    def length_of_overlap(a,b,c,d):
        return max(0.0,min(b,d)-max(a,c))
    weights=[length_of_overlap(lag-j, 1+lag-j, 0,1) for j in range(len(series))]
    arrived=fsum(q*w for q,w in zip(series,weights))
    # At midnight, all releases during the preceding lag interval are still
    # in transit. Before midnight release -j occupies [-j, 1-j] days.
    opening=SECONDS_PER_DAY*fsum(q*length_of_overlap(-j,1-j,-lag,0)
                                       for j,q in enumerate(series) if j>0)
    received=arrived*SECONDS_PER_DAY
    sent=current_cms*SECONDS_PER_DAY
    closing=opening+sent-received
    if min(opening,closing) < -1e-6 or abs(fsum(weights)-1)>1e-9:
        raise ValueError('NONCONSERVATIVE_LAG_KERNEL')
    return {'delay_hours':settings.delay_hours,
            'arrival_mean_flow_cms':arrived,
            'daily_input_m3':sent,'daily_arrival_m3':received,
            'opening_in_transit_m3':opening,
            'closing_in_transit_m3':max(0.0,closing),
            'coefficient_weights_current_then_history':[round(x,12) for x in weights],
            'mass_residual_m3':round(closing-(opening+sent-received),7),
            'hydraulic_attenuation_modelled':False}



def exact_mean_piecewise_linear(x0:float,x1:float,xs:list[float],ys:list[float])->float:
    """Exact time average for x(t) linear and y(x) piecewise linear.

    This integrates against the storage *volume coordinate*. The physical
    assumption is a constant net volume rate throughout the target day.
    It is NOT a transient solver for intraday varying head or dispatch.
    """
    if x0==x1:
        return linear_interpolate(x0,xs,ys)
    lo,hi=sorted((x0,x1))
    if lo < xs[0] or hi > xs[-1]:
        raise ValueError('EXTRAPOLATION_FORBIDDEN')
    knots=[lo]+[x for x in xs[1:-1] if lo<x<hi]+[hi]
    integrals=[]
    for a,b in zip(knots,knots[1:]):
        fa=linear_interpolate(a,xs,ys)
        fb=linear_interpolate(b,xs,ys)
        integrals.append((b-a)*(fa+fb)/2)
    return fsum(integrals)/(hi-lo)


def reservoir_step(res:ReservoirV83,inflow_cms:float,rho:float)->dict:
    """Synthetic constant-flow daily screen with exact piecewise head integral.

    Rate/volume constraints apply to a 24h constant-flow trajectory. The
    instantaneous electrical peak is separately checked at BOTH endpoints,
    preventing a midpoint-only false approval. Real intraday transients and
    power controls are NOT simulated.
    """
    outflow=res.turbine_release_cms+res.spill_release_cms
    final=res.start_volume_m3+(inflow_cms-outflow-res.other_losses_cms)*SECONDS_PER_DAY
    violations=[]
    if final < res.min_volume_m3-1e-6 or final > res.max_volume_m3+1e-6:
        violations.append('FINAL_STORAGE_OUTSIDE_ALLOWED_LIMITS')
    if res.turbine_release_cms > res.turbine_capacity_cms+1e-9:
        violations.append('TURBINE_DISCHARGE_CAPACITY_EXCEEDED')
    if outflow < res.minimum_release_cms-1e-9:
        violations.append('MINIMUM_RELEASE_NOT_MET')
    if abs(outflow-res.previous_release_cms)>res.max_daily_ramp_cms+1e-9:
        violations.append('RELEASE_RAMP_LIMIT_EXCEEDED')
    mean_head=None;head_start=None;head_end=None
    max_instantaneous_power=None
    power=None;energy=None;efficiency=None
    try:
        volumes=[p.volume_m3 for p in res.storage_curve]
        elevations=[p.upstream_elevation_m for p in res.storage_curve]
        start_elevation=linear_interpolate(res.start_volume_m3,volumes,elevations)
        end_elevation=linear_interpolate(final,volumes,elevations)
        average_elevation=exact_mean_piecewise_linear(
            res.start_volume_m3,final,volumes,elevations)
        tail=linear_interpolate(outflow,
                   [p.discharge_cms for p in res.tailwater_curve],
                   [p.elevation_m for p in res.tailwater_curve])
        head_start=start_elevation-tail-res.hydraulic_head_loss_m
        head_end=end_elevation-tail-res.hydraulic_head_loss_m
        mean_head=average_elevation-tail-res.hydraulic_head_loss_m
        if res.turbine_release_cms>0 and min(head_start,head_end)<=0:
            violations.append('NONPOSITIVE_NET_HEAD')
        fraction=res.turbine_release_cms/res.turbine_capacity_cms
        if fraction>1:
            raise ValueError('TURBINE_DISCHARGE_CURVE_DOMAIN_EXCEEDED')
        efficiency=linear_interpolate(fraction,
                   [p.turbine_flow_fraction for p in res.efficiency_curve],
                   [p.efficiency for p in res.efficiency_curve])
        # Storage-elevation is strictly increasing and outflow constant.
        # Therefore the highest hourly-scale instantaneous head over this
        # simplified linear-storage path is at one of the two endpoints.
        max_instantaneous_power=(rho*GRAVITY_M_S2*res.turbine_release_cms*
                                 max(head_start,head_end)*efficiency/1e6)
        if max_instantaneous_power>res.rated_capacity_mw+1e-9:
            violations.append('ELECTRICAL_RATED_CAPACITY_EXCEEDED')
        if not violations:
            power=rho*GRAVITY_M_S2*res.turbine_release_cms*mean_head*efficiency/1e6
            energy=power*HOURS_PER_DAY
    except ValueError:
        violations.append('ENGINEERING_CURVE_EXTRAPOLATION_FORBIDDEN')
    if violations:
        # A violated constraint makes the daily energy UNKNOWN, not zero.
        power=None;energy=None
    return {
      'asset_id':res.asset_id,'start_storage_m3':res.start_volume_m3,
      'end_storage_m3':final,'delta_storage_m3':final-res.start_volume_m3,
      'local_plus_routed_inflow_cms':inflow_cms,'turbine_release_cms':res.turbine_release_cms,
      'spill_release_cms':res.spill_release_cms,'other_losses_cms':res.other_losses_cms,
      'net_head_m':None if mean_head is None else round(mean_head,8),
      'head_at_start_m':head_start,'head_at_end_m':head_end,
      'max_instantaneous_theoretical_power_mw':max_instantaneous_power,
      'energy_integration_method':'EXACT_PIECEWISE_LINEAR_STAGE_AT_CONSTANT_NET_DAILY_FLOW',
      'interpolated_efficiency':efficiency,
      'power_mw':power,'energy_mwh':energy,
      'conservation_residual_m3':round(final-res.start_volume_m3-(inflow_cms-outflow-res.other_losses_cms)*SECONDS_PER_DAY,5),
      'violations':sorted(set(violations)),'status':'PHYSICAL_SCREEN_FAILED' if violations else 'LAB_FEASIBLE_ONLY'}


def evaluate_coupled_cascade_v83(case:CoupledCascadeV83)->dict:
    forecast=evaluate_daily_forecast(case.forecast)
    target=datetime.fromisoformat(forecast['forecast']['target_at'])
    issued=datetime.fromisoformat(forecast['issued_at'])
    if target.tzinfo is None or target.astimezone(timezone.utc).hour!=0:
        raise ValueError('TARGET_DAY_MUST_END_AT_UTC_MIDNIGHT')
    # Existing V8.2 timestamps are the END of the averaging day. The last
    # observed mean ending D is available at D+06. Issued at D+10, a forecast
    # for the day [D+1,D+2) must have target_at D+2, so h=2 is required.
    day_start=target-timedelta(days=1)
    if issued>=day_start:
        raise ValueError('ISSUE_MUST_PRECEDE_FULL_TARGET_DAY_START')
    f=forecast['forecast']
    upstream_q=case.upper.turbine_release_cms+case.upper.spill_release_cms
    routed=route_uniform_day(upstream_q,case.route)
    scenarios=[]
    for scenario,key in [('dry','lower_cms'),('central','point_cms'),('wet','upper_cms')]:
        q=f[key]
        upper=reservoir_step(case.upper,q+case.upper_other_local_inflow_cms,case.water_density_kg_m3)
        lower=reservoir_step(case.lower,case.lower_local_inflow_cms+routed['arrival_mean_flow_cms'],case.water_density_kg_m3)
        delta=fsum([upper['delta_storage_m3'],lower['delta_storage_m3'],
                    routed['closing_in_transit_m3']-routed['opening_in_transit_m3']])
        boundary_flux=fsum([q,case.upper_other_local_inflow_cms,case.lower_local_inflow_cms,
                            -case.upper.other_losses_cms,-case.lower.other_losses_cms,
                            -case.lower.turbine_release_cms,-case.lower.spill_release_cms])*SECONDS_PER_DAY
        residual=delta-boundary_flux
        violations=[f'upper:{v}' for v in upper['violations']]+[f'lower:{v}' for v in lower['violations']]
        if abs(residual)>max(1e-4,abs(boundary_flux)*1e-10):
            violations.append('GLOBAL_VOLUME_CONSERVATION_FAILED')
        feasible=not violations
        energy=fsum([upper['energy_mwh'],lower['energy_mwh']]) if feasible else None
        scenarios.append({'name':scenario,'upper_forecast_inflow_cms':q,
           'upstream_local_inflow_cms':case.upper_other_local_inflow_cms,
           'lower_local_inflow_cms':case.lower_local_inflow_cms,
           'upper':upper,'lower':lower,'transit':routed,
           'global_mass_balance_residual_m3':round(residual,5),
           'total_energy_mwh':energy,'feasible_under_synthetic_constraints':feasible,
           'violations':violations})
    energies=[s['total_energy_mwh'] for s in scenarios]
    any_failure=any(not s['feasible_under_synthetic_constraints'] for s in scenarios)
    critical=['EMPIRICAL_HOLDOUT_UNDERCOVERAGE','NO_GAIN_OVER_PERSISTENCE_ON_INDEPENDENT_HOLDOUT',
              'HIGH_FLOW_EXTREMES_NOT_SUFFICIENTLY_SAMPLED']
    risk=[v for v in critical if v in forecast['risk_flags']]
    return {
      'scope':'SYNTHETIC_ONE_DAY_CASCADE_FORECAST_SCREEN_NOT_OPERATIONAL',
      'engine':ENGINE_TAG,'target_day_start_utc':day_start.isoformat(),
      'target_day_end_utc':target.isoformat(),
      'forecast_issued_at':issued.isoformat(),
      'forecast_actual_lead_to_target_day_start_hours':(day_start-issued).total_seconds()/3600,
      'forecast_actual_lead_to_target_day_end_hours':(target-issued).total_seconds()/3600,
      'observation_timestamp_semantics':case.daily_observation_semantics,
      'target_start_state_and_prior_release_basis':case.target_start_state_and_prior_release_basis,
      'forecast_selected_model':forecast['selected_model'],
      'hydrology_report':{'horizon_days':forecast['horizon_days'],
                          'nominal_interval_fraction':forecast['calibration']['nominal_band_fraction'],
                          'holdout_empirical_coverage_fraction':forecast['holdout']['interval_empirical_coverage_fraction'],
                          'holdout_mae_cms':forecast['holdout']['mae_cms'],
                          'risk_flags':forecast['risk_flags'],
                          'interval_is_probabilistic_scenario_weight':False},
      'scenario_order':'dry_central_wet_not_probability_quantiles',
      'scenarios':scenarios,
      'feasible_all_three_synthetic_scenarios':not any_failure,
      'scenario_energy_span_mwh':None if any(x is None for x in energies) else max(energies)-min(energies),
      'calibration_and_stationarity_risk_flags':risk,
      'conditional_future_assumptions_flag':'TARGET_START_STORAGE_AND_PREVIOUS_DAY_RELEASES_ARE_SCENARIO_INPUTS_NOT_MEASURED_AT_ISSUE',
      'qualification':'SYNTHETIC_CONSTRAINT_FAILURE' if any_failure else (
         'SYNTHETIC_STATISTICS_UNCERTAIN' if risk else 'SYNTHETIC_PHYSICAL_SCREEN_ONLY'),
      'limitations':[
          'V8.2 supplies ONLY ONE TARGET DAY; timestamp is END of preceding 24h averaging period',
          'The synthetic starting storage represents target-day opening, not the as_of forecast instant',
          'Prior-day full release and target-day opening storage include FUTURE portions after the D10 issuance and are CONDITIONAL assumptions, not causal observations',
          'Dry/central/wet interval endpoints are NOT assigned scenario probabilities',
          'Upper and lower releases are fixed synthetic test inputs, never dispatch optimisation',
          'Pure travel-time shift assumes uniform daily flow; no attenuation, Saint-Venant hydraulics or backwater',
          'Daily energy uses exact piecewise-linear head integration under constant releases; instantaneous peaking is checked at daily endpoints but unmodelled subdaily transients remain out of scope',
          'Piecewise-linear storage/forebay, tailwater and efficiency curves are synthetic and not site-attested',
          'Hydraulic loss held constant; temperature, evaporation and river exchange not measured',
          'No hydropower benefit is derived from the scenario energy span; not NPV, tariffs, tax or project ROI'],
      'data_source_attested':False,'actual_magadan_hydro_curve_used':False,
      'external_engineer_verified':False,'probabilistic_generation_forecast_validated':False,
      'recommended_dispatch_cms':None,'monetary_benefit_rub':None,
      'eligible_for_financial_ledger':False,'production_ready':False,
    }
