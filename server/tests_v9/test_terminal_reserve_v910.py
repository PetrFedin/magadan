"""V9.10 independent synthetic minimum usable water and incremental demand QA."""
from __future__ import annotations

import math
from pathlib import Path
import pytest

from hydro_api.winter_energy_balance_v9 import (
    ReservoirSpec, WINTER_MONTHS, simulate_winter_balance
)
from hydro_api.terminal_reserve_v910 import (
    compare_reserve_and_incremental_load
)

K = ReservoirSpec(name_ru="SYNTH-KOL",usable_volume_km3=7.24,
                  head_m=108.0,guaranteed_capacity_mw=224,
                  source_ref="SYNTHETIC-TEST-V910")
U = ReservoirSpec(name_ru="SYNTH-UST",usable_volume_km3=2.57,
                  head_m=58.4,guaranteed_capacity_mw=132,
                  source_ref="SYNTHETIC-TEST-V910")
MONTHS={11:70.4,12:32.2,1:15,2:8.72,3:5.93,4:5.25}

def params(**override):
    d=dict(
        kolyma=K,ust_srednekan=U,baseline_peak_load_mw=574.0,
        extra_load_mw=100.0,eta=0.90,thermal_available_mw=160.0,
        inflow_quantile=0.05,inflow_by_month_m3s=MONTHS,
        side_inflow_annual_km3=4.5,mean_annual_flow_m3s=739.0,
        initial_storage_fraction=0.30,
        minimum_usable_storage_fraction=0.25,
        dispatch_policy="thermal_first",months=WINTER_MONTHS,
    )
    d.update(override)
    return d

def study(**override):
    return compare_reserve_and_incremental_load("V910-SYNTHETIC-CASE",**params(**override))

def assert_strictly_closed(run, floor, initial):
    assert abs(run["maximum_abs_water_residual_km3"]) <= 1e-9
    assert run["total_deterministic_unserved_gwh"] >= 0
    assert run["total_demand_gwh"] == pytest.approx(
        run["total_hydro_gwh"]+run["total_thermal_gwh"]
        +run["total_deterministic_unserved_gwh"],abs=1e-8)
    assert len(run["months"]) == 6
    assert run["minimum_usable_storage_fraction_assumption"] == pytest.approx(floor)
    assert run["initial_usable_storage_fraction_assumption"] == pytest.approx(initial)
    for m in run["months"]:
        assert m["upper_absolute_usable_stock_km3"] >= K.usable_volume_km3*floor-1e-9
        assert m["lower_absolute_usable_stock_km3"] >= U.usable_volume_km3*floor-1e-9
        assert m["upper_absolute_usable_stock_km3"] <= K.usable_volume_km3+1e-9
        assert m["lower_absolute_usable_stock_km3"] <= U.usable_volume_km3+1e-9
        assert m["demand_gwh"] == pytest.approx(m["hydro_gwh"]+m["thermal_gwh"]+m["unserved_gwh"],abs=1e-8)

@pytest.mark.parametrize("policy",["thermal_first","hydro_first"])
def test_no_floor_stress_reproduces_validated_v99_engine(policy):
    p=params(minimum_usable_storage_fraction=0.0,extra_load_mw=0.0,
             dispatch_policy=policy)
    actual=compare_reserve_and_incremental_load("V910-REPRO",**p)
    original=simulate_winter_balance(
        "V910-PARENT",kolyma=K,ust_srednekan=U,
        peak_load_mw=p["baseline_peak_load_mw"],
        eta=p["eta"],thermal_available_mw=p["thermal_available_mw"],
        inflow_quantile=p["inflow_quantile"],
        inflow_by_month_m3s=p["inflow_by_month_m3s"],
        side_inflow_annual_km3=p["side_inflow_annual_km3"],
        mean_annual_flow_m3s=p["mean_annual_flow_m3s"],
        initial_storage_fraction=p["initial_storage_fraction"],
        months=WINTER_MONTHS,dispatch_policy=policy)
    for run in ("baseline_with_floor","stress_with_floor","stress_without_floor"):
        case=actual[run]
        assert case["total_hydro_gwh"]==pytest.approx(original.hydro_total_gwh,abs=1e-8)
        assert case["total_thermal_gwh"]==pytest.approx(original.thermal_total_gwh,abs=1e-8)
        assert case["total_deterministic_unserved_gwh"]==pytest.approx(original.deficit_total_gwh,abs=1e-8)
        assert case["upper_terminal_absolute_stock_km3"]==pytest.approx(original.months[-1].kolyma_storage_end_km3,abs=1e-8)
        assert case["lower_terminal_absolute_stock_km3"]==pytest.approx(original.months[-1].ust_storage_end_km3,abs=1e-8)

@pytest.mark.parametrize("policy",["thermal_first","hydro_first"])
def test_positive_floor_never_uses_held_water_in_each_month(policy):
    out=study(dispatch_policy=policy)
    assert_strictly_closed(out["baseline_with_floor"],0.25,0.30)
    assert_strictly_closed(out["stress_with_floor"],0.25,0.30)
    assert_strictly_closed(out["stress_without_floor"],0.0,0.30)

def test_same_input_deterministic_hash_and_outputs():
    assert study()==study()
    assert len(study()["input_sha256"])==64

@pytest.mark.parametrize("key,value",[
    ("extra_load_mw",101.0),("initial_storage_fraction",0.50),
    ("minimum_usable_storage_fraction",0.10),
    ("thermal_available_mw",272.0),
    ("dispatch_policy","hydro_first")
])
def test_input_hash_changes_with_assumption(key,value):
    assert study()["input_sha256"]!=study(**{key:value})["input_sha256"]

@pytest.mark.parametrize("bad",[-1.0,float("nan"),float("inf"),True,"100"])
def test_invalid_extra_load_is_fail_closed(bad):
    with pytest.raises((ValueError,TypeError)):
        study(extra_load_mw=bad)

@pytest.mark.parametrize("bad",[-0.1,1.0,1.2,float("nan"),float("inf"),True,"0.25",0.30])
def test_invalid_hypothetical_floor_rejected(bad):
    with pytest.raises((ValueError,TypeError)):
        study(minimum_usable_storage_fraction=bad)

@pytest.mark.parametrize("bad",[(),(11,11),(12,11),(7,),(11,1,12)])
def test_invalid_winter_horizon_rejected(bad):
    with pytest.raises(ValueError,match="V910_INVALID_MONTH_SEQUENCE|V910_NONCHRONOLOGICAL_MONTH_ORDER"):
        study(months=bad)

def test_research_contract_has_no_operational_or_regulatory_claims():
    r=study()
    assert r["normative_reservoir_floors_verified"] is False
    assert r["real_travel_time_calibrated"] is False
    assert r["grid_n_minus_one_verified"] is False
    assert r["probabilistic_lole_or_eens_computed"] is False
    assert r["real_available_capacity_mw"] is None
    assert r["investment_decision"]=="HOLD"
    assert r["production_ready"] is False
    assert r["model_deltas_are_not_consumer_shortfall_allocation"] is True

@pytest.mark.parametrize("policy",["thermal_first","hydro_first"])
def test_zero_extra_load_does_not_change_stressed_vs_baseline(policy):
    r=study(extra_load_mw=0.0,dispatch_policy=policy)
    assert r["baseline_with_floor"]=={
        **r["stress_with_floor"],
        "case_id": r["baseline_with_floor"]["case_id"],
    }
    assert r["delta_stress_minus_baseline_unserved_gwh"]==0

def test_low_initial_water_zero_thermal_produces_nonzero_shortage():
    r=study(thermal_available_mw=0.0,extra_load_mw=250.0,
            initial_storage_fraction=0.15,
            minimum_usable_storage_fraction=0.10,
            inflow_by_month_m3s={m:0.0 for m in WINTER_MONTHS})
    assert r["stress_with_floor"]["total_deterministic_unserved_gwh"]>0
    assert r["stress_with_floor"]["unserved_month_count"]>0
    assert_strictly_closed(r["stress_with_floor"],0.10,0.15)

def test_floored_run_protects_more_terminal_water_than_unfloored_under_stress():
    r=study(thermal_available_mw=0.0,extra_load_mw=250.0,
            initial_storage_fraction=0.15,
            minimum_usable_storage_fraction=0.10,
            inflow_by_month_m3s={m:0.0 for m in WINTER_MONTHS})
    assert r["delta_terminal_absolute_water_floor_minus_no_floor_km3"]>0
    assert r["delta_floor_minus_no_floor_unserved_gwh"]>=-1e-8

@pytest.mark.parametrize("policy",["thermal_first","hydro_first"])
def test_increased_demand_has_correct_monthly_volume(policy):
    r=study(dispatch_policy=policy,extra_load_mw=250.0)
    b=r["baseline_with_floor"];s=r["stress_with_floor"]
    delta=sum(
        250*m["month"]*0+250*(720 if m["month"] in (11,4) else 744 if m["month"] in (12,1,3) else 672)/1000
        for m in s["months"])
    assert s["total_demand_gwh"]-b["total_demand_gwh"]==pytest.approx(delta,abs=1e-8)

def test_monthly_zero_capacity_plus_floor_is_not_confused_with_nan():
    r=study(thermal_available_mw=0.0, extra_load_mw=0.0,
            initial_storage_fraction=0.15,minimum_usable_storage_fraction=0.10,
            inflow_by_month_m3s={m:0.0 for m in WINTER_MONTHS})
    assert math.isfinite(r["stress_with_floor"]["total_deterministic_unserved_gwh"])
    assert r["stress_with_floor"]["total_deterministic_unserved_gwh"]>0

@pytest.mark.parametrize("bad",["",None,42,"x"*161])
def test_bad_case_id_rejected(bad):
    with pytest.raises(ValueError,match="V910_BAD_CASE_ID"):
        compare_reserve_and_incremental_load(bad,**params())

def test_floor_equal_initial_fails_without_epsilon_fake_state():
    with pytest.raises(ValueError,match="V910_INITIAL_AT_FLOOR_NOT_SUPPORTED"):
        study(initial_storage_fraction=0.25,minimum_usable_storage_fraction=0.25)

def test_initial_below_floor_fails_closed():
    with pytest.raises(ValueError,match="V910_RESERVE_ABOVE_INITIAL_OR_INVALID_CAPACITY"):
        study(initial_storage_fraction=0.10,minimum_usable_storage_fraction=0.25)

def test_demand_is_not_assigned_to_specific_incremental_consumer():
    x=study(extra_load_mw=250.0)
    assert "incremental_consumer_unserved_gwh" not in x
    assert x["model_deltas_are_not_consumer_shortfall_allocation"] is True


def test_v910_persisted_research_artifact_and_source_bytes():
    """Scientific receipt must match exact original model, scenario and data bytes."""
    import hashlib
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    path=root/"artifacts_v9/magadan_terminal_reserve_stress_v910.json"
    assert path.is_file(),"V910_RESEARCH_RECEIPT_MISSING"
    result=json.loads(path.read_text(encoding="utf-8"))
    payload={k:v for k,v in result.items() if k!="payload_sha256"}
    encoded=json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False).encode()
    assert hashlib.sha256(encoded).hexdigest()==result["payload_sha256"]
    for filename,expected in result["source_sha256"].items():
        source=root/filename
        assert source.is_file(),filename
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected,filename
    assert len(result["rows"])==result["summary"]["scenario_count"]==384
    assert len(result["reference_trajectories"])==4
    assert result["summary"]["stressed_deficit_cases"]==372
    assert result["summary"]["baseline_deficit_cases"]==360
    assert result["summary"]["positive_floor_deficit_delta_cases"]==240
    assert result["normative_reservoir_floors_verified"] is False
    assert result["grid_scenarios_are_not_probabilities"] is True
    assert result["real_available_capacity_mw"] is None
    assert result["production_ready"] is False


def test_v910_paired_policy_and_floor_boundary_counts():
    """Post-processing of saved evidence cannot mistake a grid for probability."""
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    data=json.loads(
        (root/"artifacts_v9/magadan_terminal_reserve_stress_v910.json").read_text(
            encoding="utf-8"
        )
    )
    rows=data["rows"]
    keys=("initial_fraction_assumption","minimum_stock_fraction_assumption",
          "thermal_available_mw_assumption","incremental_load_mw_assumption",
          "historical_monthly_quantile_assumption")
    pairs={}
    for row in rows:
        key=tuple(row[k] for k in keys)
        pair=pairs.setdefault(key,{})
        assert row["dispatch_policy_assumption"] not in pair
        pair[row["dispatch_policy_assumption"]]=row
    assert len(pairs)==192
    hydro_higher=hydro_lower=same=0
    for pair in pairs.values():
        assert set(pair)=={"thermal_first","hydro_first"}
        diff=(pair["hydro_first"]["stress_total_unserved_gwh"]
             -pair["thermal_first"]["stress_total_unserved_gwh"])
        hydro_higher+=diff>1e-8
        hydro_lower+=diff< -1e-8
        same+=abs(diff)<=1e-8
    assert (hydro_higher,hydro_lower,same)==(30,0,162)
    newly_deficit_due_to_floor=sum(
        r["stress_total_unserved_gwh"]>1e-9
        and r["stress_no_floor_unserved_gwh"]<=1e-9
        for r in rows
    )
    assert newly_deficit_due_to_floor==24
    assert sum(
        r["stress_total_unserved_gwh"]<=1e-9
        and r["stress_no_floor_unserved_gwh"]>1e-9
        for r in rows
    )==0
    assert data["grid_scenarios_are_not_probabilities"] is True
