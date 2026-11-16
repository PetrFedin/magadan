"""Explicit synthetic storage/elevation/efficiency assumptions for V8.3 tests."""
from tests_v82.fixture import daily_flow_fixture


def cascade_case_v83(delay_hours=12):
    upper={
       'asset_id':'feeder-a','name':'SYNTHETIC-UPPER-STATION',
       'source_ref':'SYNTHETIC-CASCADE-UPSTREAM-CURVE-2026',
       'start_volume_m3':1_000_000_000,'min_volume_m3':900_000_000,
       'max_volume_m3':1_100_000_000,
       'storage_curve':[{'volume_m3':900_000_000,'upstream_elevation_m':380},
                        {'volume_m3':1_000_000_000,'upstream_elevation_m':395},
                        {'volume_m3':1_100_000_000,'upstream_elevation_m':410}],
       'tailwater_curve':[{'discharge_cms':0,'elevation_m':300},
                          {'discharge_cms':250,'elevation_m':305},
                          {'discharge_cms':500,'elevation_m':310}],
       'efficiency_curve':[{'turbine_flow_fraction':0,'efficiency':0},
                           {'turbine_flow_fraction':0.5,'efficiency':0.90},
                           {'turbine_flow_fraction':1,'efficiency':0.93}],
       'turbine_capacity_cms':250,'turbine_release_cms':125,
       'spill_release_cms':25,'other_losses_cms':0,
       'minimum_release_cms':20,'previous_release_cms':150,
       'max_daily_ramp_cms':70,'hydraulic_head_loss_m':1,
       'rated_capacity_mw':120,
    }
    lower={
       'asset_id':'v83-lower','name':'SYNTHETIC-LOWER-STATION',
       'source_ref':'SYNTHETIC-CASCADE-DOWNSTREAM-CURVE-2026',
       'start_volume_m3':500_000_000,'min_volume_m3':400_000_000,
       'max_volume_m3':600_000_000,
       'storage_curve':[{'volume_m3':400_000_000,'upstream_elevation_m':300},
                        {'volume_m3':500_000_000,'upstream_elevation_m':315},
                        {'volume_m3':600_000_000,'upstream_elevation_m':330}],
       'tailwater_curve':[{'discharge_cms':0,'elevation_m':220},
                          {'discharge_cms':250,'elevation_m':226},
                          {'discharge_cms':500,'elevation_m':232}],
       'efficiency_curve':[{'turbine_flow_fraction':0,'efficiency':0},
                           {'turbine_flow_fraction':0.5,'efficiency':0.89},
                           {'turbine_flow_fraction':1,'efficiency':0.91}],
       'turbine_capacity_cms':200,'turbine_release_cms':145,
       'spill_release_cms':30,'other_losses_cms':0,
       'minimum_release_cms':25,'previous_release_cms':175,
       'max_daily_ramp_cms':80,'hydraulic_head_loss_m':1.5,
       'rated_capacity_mw':150,
    }
    from math import ceil
    history=[150.0]*ceil(delay_hours/24)
    return {
      'forecast':daily_flow_fixture(horizon=2),
      'daily_observation_semantics':'UTC_DAILY_MEAN_PERIOD_END_AT_OBSERVED_AT',
      'target_start_state_and_prior_release_basis':'SYNTHETIC_CONDITIONAL_FUTURE_ASSUMPTIONS_NOT_KNOWN_AT_FORECAST_ISSUE',
      'initial_storage_state_ref':'SYNTHETIC-CASCADE-TARGET-DAY-START-STORAGE-2026',
      'upper':upper,'lower':lower,
      'route':{'delay_hours':delay_hours,'previous_daily_releases_cms':history,
               'source_ref':'SYNTHETIC-UPSTREAM-DAILY-RELEASE-2026'},
      'hydrological_mapping_ref':'SYNTHETIC-FLOW-TO-UPSTREAM-RESERVOIR-2026',
      'lower_local_inflow_cms':45,'lower_local_inflow_ref':'SYNTHETIC-LOWER-LOCAL-FLOW-2026',
      'water_density_kg_m3':1000,
    }
