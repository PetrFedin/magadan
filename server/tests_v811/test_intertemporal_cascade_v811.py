"""Reproducible synthetic two-reservoir water/energy timing experiments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hydro_api.intertemporal_cascade_v811 import (
    HourlyPlan, Reservoir, SyntheticCascade, compare_synthetic_travel_delays,
    simulate_synthetic_cascade,
)

D = Decimal
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_case(delay=0, horizon=3):
    assert horizon >= 3
    upstream = Reservoir(initial_1000m3="10", minimum_1000m3="0", maximum_1000m3="12",
                         max_turbine_1000m3_per_hour="6", max_total_release_1000m3_per_hour="8",
                         hypothetical_energy_mwh_per_1000m3="0.1")
    lower = Reservoir(initial_1000m3="0", minimum_1000m3="0", maximum_1000m3="12",
                      max_turbine_1000m3_per_hour="6", max_total_release_1000m3_per_hour="8",
                      hypothetical_energy_mwh_per_1000m3="0.1")
    hours = []
    for t in range(horizon):
        hours.append(HourlyPlan(
            hour_utc=T0 + timedelta(hours=t),
            upper_local_inflow_1000m3="0", lower_lateral_inflow_1000m3="0",
            upper_turbine_1000m3="6" if t == 0 else "0",
            upper_spill_1000m3="0",
            lower_turbine_1000m3="6" if t == delay else "0",
            lower_spill_1000m3="0",
            hydro_only_demand_mwh="1.2" if t == 0 else "0",
        ))
    return SyntheticCascade(
        mode="SYNTHETIC_RESEARCH_ONLY",
        source_ref="SYNTHETIC-FAKE-CASCADE-DATA",
        scenario_id=f"SYNTHETIC-CASCADE-delay-{delay}",
        actual_operational_data_accepted=False,
        real_source_rights_verified=False,
        independently_certified_n1=False,
        upper=upstream, lower=lower, routing_delay_hours=delay,
        historical_in_transit_1000m3=[D("0")] * delay, hours=hours,
    )


def update_plan(case, **changes):
    data = case.model_dump(mode="python")
    data.update(changes)
    return SyntheticCascade.model_validate(data)


def test_instant_and_delayed_same_total_energy_but_different_first_hour():
    result = compare_synthetic_travel_delays(make_case(0), make_case(1))
    assert result["same_horizon_total_generation_and_demand"] is True
    assert result["instant"]["hypothetical_generated_mwh"] == "1.2"
    assert result["delayed"]["hypothetical_generated_mwh"] == "1.2"
    assert result["instant"]["hypothetical_hydro_only_unserved_mwh"] == "0"
    assert result["delayed"]["hypothetical_hydro_only_unserved_mwh"] == "0.6"
    assert result["absolute_unserved_difference_mwh"] == "0.6"
    assert result["instant"]["mass_balance_residual_1000m3"] == "0"
    assert result["delayed"]["mass_balance_residual_1000m3"] == "0"
    assert result["instant"]["water_remaining_upper_1000m3"] == "4"
    assert result["instant"]["water_remaining_lower_1000m3"] == "0"
    assert result["delayed"]["water_remaining_in_pipeline_1000m3"] == "0"


def test_late_water_cannot_cover_early_demand():
    result = simulate_synthetic_cascade(make_case(1))
    assert [x["upstream_arrival_lower_1000m3"] for x in result["hours"]] == ["0", "6", "0"]
    assert [x["hydro_only_deterministic_shortfall_mwh"] for x in result["hours"]] == ["0.6", "0", "0"]
    assert result["hypothetical_hydro_only_shortfall_hours"] == 1


def test_impossible_early_release_of_future_upstream_water_is_rejected():
    case = make_case(1)
    case.hours[0].lower_turbine_1000m3 = D("6")
    case.hours[1].lower_turbine_1000m3 = D("0")
    with pytest.raises(ValueError, match="LOWER_STORAGE_BOUND_VIOLATED_OR_FUTURE_WATER_USED"):
        simulate_synthetic_cascade(case)


def test_lower_cascade_arrival_cannot_be_double_counted():
    case = make_case(0)
    case.hours[1].lower_turbine_1000m3 = D("6")
    with pytest.raises(ValueError, match="LOWER_STORAGE_BOUND_VIOLATED_OR_FUTURE_WATER_USED"):
        simulate_synthetic_cascade(case)


def test_pipeline_mass_remains_at_horizon_boundary():
    case = make_case(3, horizon=3)
    for row in case.hours:
        row.lower_turbine_1000m3 = D("0")
    result = simulate_synthetic_cascade(case)
    assert result["water_remaining_in_pipeline_1000m3"] == "6"
    assert result["water_remaining_upper_1000m3"] == "4"
    assert result["water_exiting_lower_1000m3"] == "0"
    assert result["mass_balance_residual_1000m3"] == "0"


def test_historical_in_transit_water_is_counted_as_initial_state():
    case = make_case(1)
    case.historical_in_transit_1000m3 = [D("2")]
    case.hours[0].lower_turbine_1000m3 = D("2")
    result = simulate_synthetic_cascade(case)
    assert result["water_initial_including_pipeline_1000m3"] == "12"
    assert result["water_exiting_lower_1000m3"] == "8"
    assert result["water_remaining_upper_1000m3"] == "4"
    assert result["mass_balance_residual_1000m3"] == "0"


def test_upstream_spill_does_not_create_upper_generation():
    case = make_case(1)
    case.hours[0].upper_turbine_1000m3 = D("0")
    case.hours[0].upper_spill_1000m3 = D("6")
    result = simulate_synthetic_cascade(case)
    assert result["hypothetical_generated_mwh"] == "0.6"
    assert result["hypothetical_hydro_only_unserved_mwh"] == "1.2"


def test_lower_spill_does_not_create_lower_generation():
    case = make_case(0)
    case.hours[0].lower_turbine_1000m3 = D("0")
    case.hours[0].lower_spill_1000m3 = D("6")
    result = simulate_synthetic_cascade(case)
    assert result["hypothetical_generated_mwh"] == "0.6"
    assert result["water_exiting_lower_1000m3"] == "6"


def test_exact_decimal_fractional_energy():
    case = make_case(0)
    case.hours[0].hydro_only_demand_mwh = D("1.2001")
    assert simulate_synthetic_cascade(case)["hypothetical_hydro_only_unserved_mwh"] == "0.0001"


def test_upper_release_limit_is_enforced():
    case = make_case(0)
    case.hours[0].upper_spill_1000m3 = D("3")
    with pytest.raises(ValueError, match="UPPER_RELEASE_CONSTRAINT_VIOLATED"):
        simulate_synthetic_cascade(case)


def test_lower_turbine_limit_is_enforced():
    case = make_case(0)
    case.hours[0].lower_turbine_1000m3 = D("7")
    with pytest.raises(ValueError, match="LOWER_RELEASE_CONSTRAINT_VIOLATED"):
        simulate_synthetic_cascade(case)


def test_upper_reservoir_minimum_is_enforced():
    case = make_case(0)
    case.upper.minimum_1000m3 = D("5")
    with pytest.raises(ValueError, match="UPPER_STORAGE_BOUND_VIOLATED"):
        simulate_synthetic_cascade(case)


def test_upper_reservoir_maximum_is_enforced():
    case = make_case(0)
    case.hours[1].upper_local_inflow_1000m3 = D("20")
    with pytest.raises(ValueError, match="UPPER_STORAGE_BOUND_VIOLATED"):
        simulate_synthetic_cascade(case)


def test_lower_reservoir_maximum_is_enforced():
    case = make_case(1)
    case.hours[0].lower_lateral_inflow_1000m3 = D("20")
    with pytest.raises(ValueError, match="LOWER_STORAGE_BOUND_VIOLATED"):
        simulate_synthetic_cascade(case)


def test_hourly_inflow_affects_water_mass_budget():
    case = make_case(0)
    case.hours[2].upper_local_inflow_1000m3 = D("1.25")
    case.hours[2].lower_lateral_inflow_1000m3 = D("0.75")
    result = simulate_synthetic_cascade(case)
    assert result["water_external_inflow_1000m3"] == "2.00"
    assert result["water_remaining_upper_1000m3"] == "5.25"
    assert result["water_remaining_lower_1000m3"] == "0.75"
    assert result["mass_balance_residual_1000m3"] == "0.00"


def test_reproducible_hash_and_different_delay_hash():
    a = simulate_synthetic_cascade(make_case(0))
    assert a == simulate_synthetic_cascade(make_case(0))
    assert a["input_sha256"] != simulate_synthetic_cascade(make_case(1))["input_sha256"]


def test_full_contract_never_approves_grid_or_hydraulic_calibration():
    result = compare_synthetic_travel_delays(make_case(0), make_case(1))
    for out in (result, result["instant"], result["delayed"]):
        assert out["real_available_capacity_mw"] is None
        assert out["investment_decision"] == "HOLD"
        assert out["production_ready"] is False
    assert result["delayed"]["real_travel_time_calibrated"] is False
    assert result["delayed"]["hydraulic_head_and_efficiency_validated"] is False
    assert result["delayed"]["probabilistic_lole_or_eens_calculated"] is False
    assert result["delayed"]["network_deliverability_verified"] is False


def test_boolean_time_delay_rejected():
    with pytest.raises(ValidationError, match="BOOLEAN_NOT_A_TRAVEL_TIME"):
        update_plan(make_case(0), routing_delay_hours=True)


def test_boolean_turbine_volume_rejected():
    row = make_case(0).hours[0].model_dump(mode="python")
    row["upper_turbine_1000m3"] = True
    with pytest.raises(ValidationError, match="BOOLEAN_NOT_A_WATER_OR_ENERGY_QUANTITY"):
        HourlyPlan.model_validate(row)


def test_negative_inflow_rejected():
    row = make_case(0).hours[0].model_dump(mode="python")
    row["upper_local_inflow_1000m3"] = D("-1")
    with pytest.raises(ValidationError):
        HourlyPlan.model_validate(row)


def test_nan_water_rejected():
    row = make_case(0).hours[0].model_dump(mode="python")
    row["upper_local_inflow_1000m3"] = D("NaN")
    with pytest.raises(ValidationError):
        HourlyPlan.model_validate(row)


def test_naive_time_rejected():
    row = make_case(0).hours[0].model_dump(mode="python")
    row["hour_utc"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="REQUIRE_EXACT_UTC_HOUR"):
        HourlyPlan.model_validate(row)


def test_local_timezone_rejected():
    row = make_case(0).hours[0].model_dump(mode="python")
    row["hour_utc"] = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3)))
    with pytest.raises(ValidationError, match="REQUIRE_EXACT_UTC_HOUR"):
        HourlyPlan.model_validate(row)


def test_duplicate_timestamp_rejected():
    case = make_case(0)
    case.hours[1].hour_utc = case.hours[0].hour_utc
    with pytest.raises(ValidationError, match="MISSING_DUPLICATE_OR_UNORDERED_UTC_HOUR"):
        simulate_synthetic_cascade(case)


def test_timestamp_gap_rejected():
    case = make_case(0)
    case.hours[2].hour_utc += timedelta(hours=1)
    with pytest.raises(ValidationError, match="MISSING_DUPLICATE_OR_UNORDERED_UTC_HOUR"):
        simulate_synthetic_cascade(case)


def test_historical_pipeline_shape_rejected():
    with pytest.raises(ValidationError, match="PRIOR_PIPELINE_STATE_LENGTH_MISMATCH"):
        update_plan(make_case(1), historical_in_transit_1000m3=[])


def test_negative_pipeline_rejected():
    with pytest.raises(ValidationError, match="INVALID_PRIOR_PIPELINE_STATE"):
        update_plan(make_case(1), historical_in_transit_1000m3=[D("-1")])


def test_real_data_mode_not_allowed():
    with pytest.raises(ValidationError):
        update_plan(make_case(0), mode="ACTUAL_ENERGY_DATA")
    with pytest.raises(ValidationError):
        update_plan(make_case(0), actual_operational_data_accepted=True)
    with pytest.raises(ValidationError):
        update_plan(make_case(0), real_source_rights_verified=True)
    with pytest.raises(ValidationError):
        update_plan(make_case(0), independently_certified_n1=True)


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        update_plan(make_case(0), firm_available_magadan_mw=900)


def test_post_validation_hack_cannot_bypass_real_rights():
    case = make_case(0)
    case.real_source_rights_verified = True
    with pytest.raises(ValidationError):
        simulate_synthetic_cascade(case)


def test_counterexample_demand_mismatch_rejected():
    b = make_case(1)
    b.hours[0].hydro_only_demand_mwh = D("1.3")
    with pytest.raises(ValueError, match="EXOGENOUS_SERIES_OR_UPSTREAM_PLAN_CHANGED"):
        compare_synthetic_travel_delays(make_case(0), b)


def test_counterexample_upstream_release_mismatch_rejected():
    b = make_case(1)
    b.hours[0].upper_turbine_1000m3 = D("5")
    with pytest.raises(ValueError, match="EXOGENOUS_SERIES_OR_UPSTREAM_PLAN_CHANGED"):
        compare_synthetic_travel_delays(make_case(0), b)


def test_counterexample_downstream_total_release_mismatch_rejected():
    b = make_case(1)
    b.hours[1].lower_turbine_1000m3 = D("5")
    with pytest.raises(ValueError, match="TOTAL_DOWNSTREAM_RELEASE_CHANGED"):
        compare_synthetic_travel_delays(make_case(0), b)


def test_counterexample_reservoir_contract_mismatch_rejected():
    b = make_case(1)
    b.upper.hypothetical_energy_mwh_per_1000m3 = D("0.2")
    with pytest.raises(ValueError, match="RESERVOIR_CONTRACTS_DIFFER"):
        compare_synthetic_travel_delays(make_case(0), b)


def test_counterexample_nonempty_historical_pipeline_rejected():
    b = make_case(1)
    b.historical_in_transit_1000m3 = [D("1")]
    with pytest.raises(ValueError, match="COUNTEREXAMPLE_REQUIRES_EMPTY_INITIAL_PIPELINE"):
        compare_synthetic_travel_delays(make_case(0), b)


def test_counterexample_delay_zero_and_positive_required():
    with pytest.raises(ValueError, match="ZERO_AND_POSITIVE_SYNTHETIC_DELAYS_REQUIRED"):
        compare_synthetic_travel_delays(make_case(1), make_case(1))


def test_initial_reservoir_bounds_rejected():
    x = make_case(0).upper.model_dump(mode="python")
    x["initial_1000m3"] = D("13")
    with pytest.raises(ValidationError, match="INVALID_INITIAL_RESERVOIR_BOUNDS"):
        Reservoir.model_validate(x)


def test_release_limit_consistency_rejected():
    x = make_case(0).upper.model_dump(mode="python")
    x["max_turbine_1000m3_per_hour"] = D("10")
    with pytest.raises(ValidationError, match="TURBINE_LIMIT_EXCEEDS_TOTAL_RELEASE_LIMIT"):
        Reservoir.model_validate(x)


def test_input_json_roundtrip_deterministic():
    case = make_case(1)
    restored = SyntheticCascade.model_validate_json(case.model_dump_json())
    assert simulate_synthetic_cascade(restored) == simulate_synthetic_cascade(case)
