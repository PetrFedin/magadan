"""V9.9: deterministic priority comparisons, never recommended operating regimes."""
from __future__ import annotations

import math
import pytest

from hydro_api.winter_energy_balance_v9 import (
    DEFICIT_EPS_GWH, WINTER_MONTHS, ReservoirSpec, simulate_winter_balance,
)
from hydro_api.dispatch_policy_v99 import compare_hydrothermal_policies

UPPER = ReservoirSpec(
    name_ru="SYNTHETIC-KOL", usable_volume_km3=7.24,
    head_m=108.0, guaranteed_capacity_mw=224.0,
    source_ref="SYNTHETIC-V99-ONLY",
)
LOWER = ReservoirSpec(
    name_ru="SYNTHETIC-UST", usable_volume_km3=2.57,
    head_m=58.4, guaranteed_capacity_mw=132.0,
    source_ref="SYNTHETIC-V99-ONLY",
)


def kwargs(**changes):
    values = dict(
        kolyma=UPPER, ust_srednekan=LOWER,
        peak_load_mw=460.0, eta=0.90,
        thermal_available_mw=320.0, inflow_quantile=0.5,
        inflow_by_month_m3s={m: 70.4 for m in WINTER_MONTHS},
        side_inflow_annual_km3=4.5, mean_annual_flow_m3s=739.0,
        initial_storage_fraction=1.0, months=(11,),
    )
    values.update(changes)
    return values


def simulate(policy="thermal_first", **changes):
    return simulate_winter_balance(
        "V99-TEST", **kwargs(**changes), dispatch_policy=policy
    )


def pair(**changes):
    return compare_hydrothermal_policies("V99-TEST", **kwargs(**changes))


def assert_balanced(result):
    assert abs(result.cascade_mass_residual_km3) < 1e-9
    assert not result.production_ready
    assert result.deficit_total_gwh >= 0
    for row in result.months:
        assert abs(row.cascade_mass_residual_km3) < 1e-9
        assert row.load_energy_gwh == pytest.approx(
            row.hydro_energy_gwh + row.thermal_energy_gwh
            + row.deficit_gwh, abs=1e-8
        )
        assert row.thermal_energy_gwh <= row.load_energy_gwh + 1e-9
        assert row.hydro_energy_gwh <= row.load_energy_gwh + 1e-9
        assert row.kolyma_spill_km3 >= 0
        assert row.ust_spill_km3 >= 0
        assert 0 <= row.kolyma_storage_end_km3 <= UPPER.usable_volume_km3 + 1e-9
        assert 0 <= row.ust_storage_end_km3 <= LOWER.usable_volume_km3 + 1e-9


def test_default_preserves_exact_v98_thermal_first_receipt():
    baseline = simulate_winter_balance("V99-TEST", **kwargs())
    explicit = simulate()
    assert baseline.model_dump() == explicit.model_dump()


def test_hydro_first_uses_both_capacity_limits_before_thermal():
    first = simulate("hydro_first").months[0]
    assert first.hydro_energy_gwh == pytest.approx(356 * 720 / 1000)
    assert first.thermal_energy_gwh == pytest.approx(104 * 720 / 1000)
    assert first.deficit_gwh < DEFICIT_EPS_GWH


def test_thermal_first_retains_existing_140_mw_hydro():
    first = simulate().months[0]
    assert first.hydro_energy_gwh == pytest.approx(140 * 720 / 1000)
    assert first.thermal_energy_gwh == pytest.approx(320 * 720 / 1000)


def test_dispatched_total_is_same_load_but_mix_differs():
    a = simulate()
    b = simulate("hydro_first")
    assert_balanced(a)
    assert_balanced(b)
    assert a.load_total_gwh == pytest.approx(b.load_total_gwh)
    assert b.hydro_total_gwh > a.hydro_total_gwh
    assert a.thermal_total_gwh > b.thermal_total_gwh


def test_hydro_first_uses_thermal_after_hydro_when_not_enough_water():
    b = simulate("hydro_first", initial_storage_fraction=0.01,
                 inflow_by_month_m3s={11: 0.0},
                 peak_load_mw=574.0, thermal_available_mw=320.0)
    assert_balanced(b)
    assert b.thermal_total_gwh > 0
    assert b.hydro_total_gwh > 0
    assert b.deficit_total_gwh > 0


def test_no_thermal_means_policies_converge():
    a = simulate(thermal_available_mw=0.0)
    b = simulate("hydro_first", thermal_available_mw=0.0)
    assert a.model_dump() == b.model_dump()


def test_full_thermal_covers_demand_only_for_thermal_first():
    a = simulate(thermal_available_mw=800.0)
    b = simulate("hydro_first", thermal_available_mw=800.0)
    assert a.hydro_total_gwh == 0
    assert a.thermal_total_gwh == pytest.approx(a.load_total_gwh)
    assert b.hydro_total_gwh > 0
    assert b.thermal_total_gwh < a.thermal_total_gwh
    assert_balanced(b)


@pytest.mark.parametrize("invalid", ["", "HYDRO_FIRST", "dispatch_all", None, False])
def test_rejects_unknown_dispatch_policies(invalid):
    with pytest.raises(ArithmeticError, match="WEB_UNKNOWN_DISPATCH_POLICY"):
        simulate(invalid)


def test_pair_has_same_input_hash_on_repeat():
    a = pair()
    b = pair()
    assert a == b
    assert len(a["input_sha256"]) == 64


def test_pair_hash_changes_when_inputs_change():
    a = pair()
    b = pair(initial_storage_fraction=0.75)
    assert a["input_sha256"] != b["input_sha256"]


def test_pair_reports_signed_mix_change_and_no_probabilities():
    out = pair()
    delta = out["hydro_minus_thermal"]
    assert delta["hydro_generation_gwh"] > 0
    assert delta["thermal_generation_gwh"] < 0
    assert delta["deterministic_unserved_gwh"] == 0
    assert out["probabilistic_lole_eens_computed"] is False
    assert out["grid_n_minus_one_verified"] is False
    assert out["physical_hydro_rules_validated"] is False
    assert out["real_available_capacity_mw"] is None
    assert out["investment_decision"] == "HOLD"
    assert out["production_ready"] is False


def test_pair_enforces_same_monthly_demand_and_input_flow():
    out = pair()
    a = out["policies"]["thermal_first"]
    b = out["policies"]["hydro_first"]
    assert a["load_total_gwh"] == b["load_total_gwh"]
    assert len(a["monthly"]) == len(b["monthly"]) == 1
    assert a["max_abs_mass_residual_km3"] < 1e-9
    assert b["max_abs_mass_residual_km3"] < 1e-9


@pytest.mark.parametrize("fraction", [0.1, 0.5, 1.0])
def test_full_winter_both_policies_conserve_mass(fraction):
    settings = dict(
        months=WINTER_MONTHS, initial_storage_fraction=fraction,
        peak_load_mw=574.0, thermal_available_mw=272.0,
        inflow_by_month_m3s={11: 70.4, 12: 32.2, 1: 15, 2: 8.72, 3: 5.93, 4: 5.25},
    )
    assert_balanced(simulate(**settings))
    assert_balanced(simulate("hydro_first", **settings))


@pytest.mark.parametrize("eta", [0.85, 0.9, 0.95])
def test_both_policies_work_at_synthetic_eta_levels(eta):
    a = simulate(eta=eta)
    b = simulate("hydro_first", eta=eta)
    assert_balanced(a)
    assert_balanced(b)


def test_pair_rejects_empty_horizon():
    with pytest.raises(ValueError, match="V99_EMPTY_OR_REPEATED_MONTHS"):
        pair(months=())


def test_pair_rejects_duplicate_month():
    with pytest.raises(ValueError, match="V99_EMPTY_OR_REPEATED_MONTHS"):
        pair(months=(11, 11))


def test_pair_rejects_nonwinter_month():
    with pytest.raises(ValueError, match="V99_OUTSIDE_WINTER_MONTHS"):
        pair(months=(7,))


def test_pair_rejects_nonfinite_input():
    with pytest.raises((ArithmeticError, ValueError)):
        pair(peak_load_mw=float("nan"))


def test_spill_is_not_counted_as_electricity():
    a = simulate(thermal_available_mw=460.0,
                 inflow_by_month_m3s={11: 200.0})
    b = simulate("hydro_first", thermal_available_mw=460.0,
                 inflow_by_month_m3s={11: 200.0})
    assert a.hydro_total_gwh == 0.0
    assert a.months[0].ust_spill_km3 > 0
    assert b.hydro_total_gwh > 0
    assert_balanced(a)
    assert_balanced(b)


def test_infinite_hydro_source_value_rejected():
    with pytest.raises((ArithmeticError, ValueError)):
        pair(inflow_by_month_m3s={11: float("inf")})


def test_no_real_data_attestation_from_comparison():
    out = pair(months=(11, 12), inflow_by_month_m3s={11: 10, 12: 20})
    assert out["real_operator_telemetry_used"] is False
    assert out["policy_comparison_not_a_dispatch_optimization"] is True
    assert out["same_assumed_input_series"] is True
