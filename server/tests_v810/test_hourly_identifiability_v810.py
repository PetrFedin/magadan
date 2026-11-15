"""Full-calendar-month counterexamples from invented hourly inputs only."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hydro_api.hourly_identifiability_v810 import (
    HourlyState, SyntheticMonth, compare_permuted_synthetic_months,
    evaluate_synthetic_month,
)


def scenario(order='adequate', year=2026, month=1):
    total = calendar.monthrange(year, month)[1] * 24
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    good = [90, 90, 50, 50]
    bad = [50, 90, 90, 50]
    cap = good if order == 'adequate' else bad
    hours = []
    for index in range(total):
        baseline = [40, 30, 20, 0][index] if index < 4 else 40
        additional = [40, 30, 20, 20][index] if index < 4 else 0
        available = cap[index] if index < 4 else 50
        hours.append(HourlyState(
            hour_utc=first + timedelta(hours=index),
            existing_demand_mw=baseline,
            additional_demand_mw=additional,
            usable_generation_mw=available,
            network_envelope_mw=100,
            held_operating_reserve_mw=0,
        ))
    return SyntheticMonth(
        mode='SYNTHETIC_RESEARCH_ONLY',
        case_id='SYNTHETIC-CASE-' + order + '-' + str(year) + '-' + str(month),
        source_ref='SYNTHETIC-OFFLINE-RESEARCH-FAKE',
        real_source_rights_verified=False,
        real_operational_data_accepted=False,
        independent_n1_verified=False,
        hours=hours,
    )


def invalid(case, **changes):
    data = case.model_dump(mode='python')
    data.update(changes)
    return SyntheticMonth.model_validate(data)


def test_real_month_counterexample_same_aggregate_but_thirty_unserved_mwh():
    result = compare_permuted_synthetic_months(scenario(), scenario('stressed'))
    assert result['counterexample_proven_for_synthetic_inputs'] is True
    assert result['same_demand_and_resource_marginals'] is True
    assert result['same_optimistic_monthly_proxy_results'] is True
    good, bad = result['adequate_case'], result['stressed_case']
    assert good['complete_utc_hour_count'] == bad['complete_utc_hour_count'] == 744
    assert good['capacity_hour_envelope_mwh_not_actual_generation'] == '37280'
    assert good['combined_demand_mwh'] == '29800'
    assert good['capacity_hour_envelope_mwh_not_actual_generation'] == bad['capacity_hour_envelope_mwh_not_actual_generation']
    assert good['maximum_hourly_envelope_mw_not_firm'] == bad['maximum_hourly_envelope_mw_not_firm'] == '90'
    assert good['maximum_hourly_demand_mw'] == bad['maximum_hourly_demand_mw'] == '80'
    assert good['optimistic_aggregate_envelope_pass'] and bad['optimistic_aggregate_envelope_pass']
    assert good['optimistic_maximum_peak_pass'] and bad['optimistic_maximum_peak_pass']
    assert good['combined_deterministic_shortfall_mwh'] == '0'
    assert bad['combined_deterministic_shortfall_mwh'] == '30'
    assert bad['incremental_deterministic_shortfall_mwh'] == '30'
    assert bad['combined_shortfall_hours'] == 1
    assert bad['first_shortfall_hour_utc'] == '2026-01-01T00:00:00+00:00'


def test_full_month_leap_february_count():
    case = scenario(year=2028, month=2)
    assert evaluate_synthetic_month(case)['complete_utc_hour_count'] == 696
    assert compare_permuted_synthetic_months(case, scenario('stressed', 2028, 2))['counterexample_proven_for_synthetic_inputs']


def test_nonleap_february_count():
    assert evaluate_synthetic_month(scenario(year=2027, month=2))['complete_utc_hour_count'] == 672


def test_synthetic_input_hash_is_reproducible_and_sensitive_to_order():
    a = evaluate_synthetic_month(scenario())
    assert a == evaluate_synthetic_month(scenario())
    assert a['input_sha256'] != evaluate_synthetic_month(scenario('stressed'))['input_sha256']


def test_unchanged_supply_order_is_not_counterexample():
    a = scenario()
    b = scenario('stressed')
    for index in range(len(a.hours)):
        b.hours[index].usable_generation_mw = a.hours[index].usable_generation_mw
    out = compare_permuted_synthetic_months(a, b)
    assert out['counterexample_proven_for_synthetic_inputs'] is False
    assert out['status'] == 'NO_TARGETED_COUNTEREXAMPLE'


def test_no_lole_eens_or_actual_n1_is_claimed():
    output = compare_permuted_synthetic_months(scenario(), scenario('stressed'))
    assert output['probabilistic_lole_or_eens_calculated'] is False
    assert output['formal_n_minus_one_study_performed'] is False
    assert output['real_source_rights_verified'] is False
    assert output['real_available_capacity_mw'] is None
    assert output['investment_decision'] == 'HOLD'
    assert output['production_ready'] is False
    for item in (output['adequate_case'], output['stressed_case']):
        assert item['probabilistic_lole_or_eens_calculated'] is False
        assert item['formal_n_minus_one_study_performed'] is False
        assert item['water_balance_and_thermal_constraints_modelled'] is False
        assert item['real_available_capacity_mw'] is None


def test_existing_baseline_shortfall_not_misattributed_to_new_load():
    case = scenario('stressed')
    case.hours[0].existing_demand_mw = Decimal('70')
    case.hours[0].additional_demand_mw = Decimal('10')
    out = evaluate_synthetic_month(case)
    assert out['baseline_deterministic_shortfall_mwh'] == '20'
    assert out['combined_deterministic_shortfall_mwh'] == '30'
    assert out['incremental_deterministic_shortfall_mwh'] == '10'
    assert out['baseline_shortfall_hours'] == 1


def test_network_envelope_can_bind():
    case = scenario()
    case.hours[0].network_envelope_mw = Decimal('50')
    out = evaluate_synthetic_month(case)
    assert out['combined_deterministic_shortfall_mwh'] == '30'


def test_held_reserve_reduces_hourly_envelope():
    case = scenario()
    case.hours[0].held_operating_reserve_mw = Decimal('30')
    out = evaluate_synthetic_month(case)
    assert out['combined_deterministic_shortfall_mwh'] == '20'


def test_missing_hour_rejected():
    case = scenario()
    case.hours.pop(4)
    with pytest.raises(ValidationError, match='MISSING_OR_EXCESS_UTC_HOURLY_ROWS'):
        SyntheticMonth.model_validate(case.model_dump())


def test_duplicate_hour_rejected():
    case = scenario()
    case.hours[12].hour_utc = case.hours[11].hour_utc
    with pytest.raises(ValidationError, match='OUT_OF_ORDER_DUPLICATE_OR_MISSING_UTC_HOUR'):
        SyntheticMonth.model_validate(case.model_dump())


def test_hour_in_wrong_order_rejected():
    case = scenario()
    case.hours[3], case.hours[2] = case.hours[2], case.hours[3]
    with pytest.raises(ValidationError, match='OUT_OF_ORDER_DUPLICATE_OR_MISSING_UTC_HOUR'):
        SyntheticMonth.model_validate(case.model_dump())


def test_month_must_start_first_midnight_utc():
    case = scenario()
    for row in case.hours:
        row.hour_utc += timedelta(hours=1)
    with pytest.raises(ValidationError, match='UTC_MONTH_MUST_START_AT_FIRST_MIDNIGHT'):
        SyntheticMonth.model_validate(case.model_dump())


def test_non_utc_time_rejected():
    with pytest.raises(ValidationError, match='HOURLY_TIMESTAMP_MUST_BE_ON_UTC_HOUR'):
        HourlyState(hour_utc=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3))), existing_demand_mw=0,
                    additional_demand_mw=0, usable_generation_mw=10, network_envelope_mw=10,
                    held_operating_reserve_mw=0)


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError, match='HOURLY_TIMESTAMP_MUST_BE_ON_UTC_HOUR'):
        HourlyState(hour_utc=datetime(2026, 1, 1), existing_demand_mw=0,
                    additional_demand_mw=0, usable_generation_mw=10, network_envelope_mw=10,
                    held_operating_reserve_mw=0)


def test_fractional_hour_rejected():
    with pytest.raises(ValidationError, match='HOURLY_TIMESTAMP_MUST_BE_ON_UTC_HOUR'):
        HourlyState(hour_utc=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc), existing_demand_mw=0,
                    additional_demand_mw=0, usable_generation_mw=10, network_envelope_mw=10,
                    held_operating_reserve_mw=0)


def test_boolean_mw_rejected():
    with pytest.raises(ValidationError, match='BOOLEAN_CANNOT_REPRESENT_MW'):
        HourlyState(hour_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), existing_demand_mw=True,
                    additional_demand_mw=0, usable_generation_mw=10, network_envelope_mw=10,
                    held_operating_reserve_mw=0)


def test_negative_capacity_rejected():
    with pytest.raises(ValidationError):
        HourlyState(hour_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), existing_demand_mw=0,
                    additional_demand_mw=0, usable_generation_mw=-1, network_envelope_mw=10,
                    held_operating_reserve_mw=0)


def test_reserve_cannot_exceed_available():
    with pytest.raises(ValidationError, match='RESERVE_EXCEEDS_INSTANTANEOUS_ENVELOPE'):
        HourlyState(hour_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), existing_demand_mw=0,
                    additional_demand_mw=0, usable_generation_mw=5, network_envelope_mw=10,
                    held_operating_reserve_mw=6)


def test_real_sources_cannot_be_switched_on():
    case = scenario()
    with pytest.raises(ValidationError):
        invalid(case, real_operational_data_accepted=True)
    with pytest.raises(ValidationError):
        invalid(case, real_source_rights_verified=True)
    with pytest.raises(ValidationError):
        invalid(case, independent_n1_verified=True)


def test_unknown_data_is_not_accepted():
    case = scenario()
    with pytest.raises(ValidationError):
        invalid(case, injected_real_capacity_mw=999)


def test_different_hourly_demand_rejected_in_pair():
    bad = scenario('stressed')
    bad.hours[0].additional_demand_mw += Decimal('1')
    with pytest.raises(ValueError, match='DEMAND_OR_UTC_AXIS_NOT_IDENTICAL'):
        compare_permuted_synthetic_months(scenario(), bad)


def test_different_resource_multiset_rejected_in_pair():
    bad = scenario('stressed')
    bad.hours[4].usable_generation_mw += Decimal('1')
    with pytest.raises(ValueError, match='HOURLY_RESOURCE_MULTISETS_NOT_IDENTICAL'):
        compare_permuted_synthetic_months(scenario(), bad)


def test_different_month_pair_rejected():
    with pytest.raises(ValueError, match='DIFFERENT_UTC_CALENDAR_MONTH'):
        compare_permuted_synthetic_months(scenario(), scenario('stressed', 2028, 2))


def test_identical_case_ids_rejected():
    a, b = scenario(), scenario('stressed')
    b.case_id = a.case_id
    with pytest.raises(ValueError, match='DISTINCT_SYNTHETIC_CASE_IDS_REQUIRED'):
        compare_permuted_synthetic_months(a, b)


def test_roundtrip_from_json_contract():
    case = scenario()
    copy = SyntheticMonth.model_validate_json(case.model_dump_json())
    assert evaluate_synthetic_month(copy) == evaluate_synthetic_month(case)
