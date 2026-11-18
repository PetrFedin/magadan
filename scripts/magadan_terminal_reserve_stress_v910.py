"""V9.10: distinct synthetic load/initial-stock/thermal-outage stress matrix."""
from __future__ import annotations

import itertools
import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.winter_energy_balance_v9 import (
    WINTER_MONTHS, ReservoirSpec, monthly_inflow_quantiles,
)
from hydro_api.terminal_reserve_v910 import compare_reserve_and_incremental_load
from magadan_winter_energy_balance_v97 import (
    TSV, SYS_REF, CASCADE_REF, NATURAL_FROM, NATURAL_TO,
    QUANTILE_LEVELS, load_5858_series,
)

OUTPUT = ROOT / "artifacts_v9/magadan_terminal_reserve_stress_v910.json"
PRIOR_ARTIFACT = ROOT / "artifacts_v9/magadan_dispatch_policy_v99.json"
INPUTS = (
    TSV, SYS_REF, CASCADE_REF, PRIOR_ARTIFACT,
    ROOT / "server/hydro_api/winter_energy_balance_v9.py",
    ROOT / "server/hydro_api/terminal_reserve_v910.py",
    ROOT / "scripts/magadan_terminal_reserve_stress_v910.py",
)
INITIAL = (0.15, 0.30, 0.50)
FLOORS = (0.00, 0.10, 0.25)
THERMAL = (0.0, 160.0, 272.0, 320.0)
EXTRA = (0.0, 100.0, 250.0)
LOWFLOW_Q = (0.05, 0.50)
POLICIES = ("thermal_first", "hydro_first")
BASELINE_PEAK = 574.0
ETA = 0.90


def report() -> dict:
    for p in INPUTS:
        if not p.is_file():
            raise ValueError(f"V910_MISSING_SOURCE:{p}")
    baseline = json.loads(PRIOR_ARTIFACT.read_text(encoding="utf-8"))
    if baseline["comparison"]["scenario_count"] != 216:
        raise ValueError("V910_INCORRECT_HISTORICAL_V99_BASELINE")
    data_sha = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in INPUTS}
    refs = json.loads(SYS_REF.read_text(encoding="utf-8"))
    hydro = json.loads(CASCADE_REF.read_text(encoding="utf-8"))["cascade_hydrology"]
    def reservoir(key, name):
        x=refs[key]["parameters"]
        return ReservoirSpec(
            name_ru=name,
            usable_volume_km3=x["reservoir_useful_volume_km3"]["value"],
            head_m=x["design_head_m"]["value"],
            guaranteed_capacity_mw=x["guaranteed_capacity_mw"]["value"],
            source_ref=x["reservoir_useful_volume_km3"]["source_ref"],
        )
    upper = reservoir("kolyma_hpp", "Kolyma synthetic reference")
    lower = reservoir("ust_srednekan_hpp", "Ust-Srednekan synthetic reference")
    q = monthly_inflow_quantiles(load_5858_series(), months=WINTER_MONTHS,
          year_from=NATURAL_FROM, year_to=NATURAL_TO,
          quantile_levels=LOWFLOW_Q)
    rows = []
    reference = {}
    for initial, floor, thermal, extra, quantile, policy in itertools.product(
        INITIAL, FLOORS, THERMAL, EXTRA, LOWFLOW_Q, POLICIES
    ):
        if floor >= initial:
            continue
        case = (f"init{initial:g}_floor{floor:g}_thermal{thermal:g}_"
                f"extra{extra:g}_q{quantile:g}_{policy}")
        res = compare_reserve_and_incremental_load(
            case, kolyma=upper, ust_srednekan=lower,
            baseline_peak_load_mw=BASELINE_PEAK, extra_load_mw=extra,
            eta=ETA, thermal_available_mw=thermal,
            inflow_quantile=quantile,
            inflow_by_month_m3s={m: q[m][quantile] for m in WINTER_MONTHS},
            side_inflow_annual_km3=hydro["side_inflow_annual_volume_km3"]["value"],
            mean_annual_flow_m3s=hydro["mean_annual_flow_ust_srednekan_m3s"]["value"],
            initial_storage_fraction=initial,
            minimum_usable_storage_fraction=floor,
            dispatch_policy=policy,
            months=WINTER_MONTHS,
        )
        base, stressed, no_floor = (
            res["baseline_with_floor"],
            res["stress_with_floor"],
            res["stress_without_floor"],
        )
        rows.append({
            "case_id": case, "input_sha256": res["input_sha256"],
            "initial_fraction_assumption": initial,
            "minimum_stock_fraction_assumption": floor,
            "thermal_available_mw_assumption": thermal,
            "incremental_load_mw_assumption": extra,
            "historical_monthly_quantile_assumption": quantile,
            "dispatch_policy_assumption": policy,
            "baseline_total_unserved_gwh": base["total_deterministic_unserved_gwh"],
            "stress_total_unserved_gwh": stressed["total_deterministic_unserved_gwh"],
            "stress_no_floor_unserved_gwh": no_floor["total_deterministic_unserved_gwh"],
            "stress_minus_baseline_unserved_gwh": res[
                "delta_stress_minus_baseline_unserved_gwh"],
            "floor_minus_no_floor_unserved_gwh": res[
                "delta_floor_minus_no_floor_unserved_gwh"],
            "floor_minus_no_floor_terminal_stock_km3": res[
                "delta_terminal_absolute_water_floor_minus_no_floor_km3"],
            "stress_unserved_month_count": stressed["unserved_month_count"],
            "stress_terminal_total_stock_km3": round(
                stressed["upper_terminal_absolute_stock_km3"]
                + stressed["lower_terminal_absolute_stock_km3"], 9),
        })
        # Deeply inspectable reference trajectories: one baseline q05 low
        # reserve stress, one high initial inventory, and their policy pair.
        if (initial, floor, thermal, extra, quantile) in {
            (0.30, 0.25, 160.0, 250.0, 0.05),
            (0.50, 0.10, 272.0, 100.0, 0.50),
        }:
            reference[case] = res
    if len(rows) != 384 or len(reference) != 4:
        raise AssertionError("V910_MISSING_GRID_OR_REF_CASES")
    def anyshort(k):
        return sum(x[k] > 1e-9 for x in rows)
    worst = max(rows, key=lambda x: x["stress_total_unserved_gwh"])
    by_extra = {}
    for delta in EXTRA:
        group = [x for x in rows if x["incremental_load_mw_assumption"] == delta]
        by_extra[str(int(delta))] = {
            "count": len(group),
            "stress_deficit_cases": sum(x["stress_total_unserved_gwh"] > 1e-9 for x in group),
            "worst_stress_gwh": max(x["stress_total_unserved_gwh"] for x in group),
            "cases_with_positive_floor_delta": sum(
                x["floor_minus_no_floor_unserved_gwh"] > 1e-9 for x in group),
        }
    result = {
        "artifact": "MAGADAN-V910-ASSUMED-MINIMUM-USABLE-STOCK-STRESS-1",
        "study_not_approved_operating_rules": True,
        "grid_scenarios_are_not_probabilities": True,
        "operating_floor_enforced_each_month_not_terminal_only": True,
        "reservoir_floor_is_fraction_of_usable_volume_not_absolute_level": True,
        "natural_monthly_q_from_1933_1981_not_current_observed_hydrograph": True,
        "baseline_peak_load_mw_assumption": BASELINE_PEAK,
        "source_sha256": data_sha,
        "study_dimensions": {
            "initial_fraction_assumption": list(INITIAL),
            "minimum_fraction_assumption": list(FLOORS),
            "thermal_capacity_mw_assumption": list(THERMAL),
            "incremental_load_mw_assumption": list(EXTRA),
            "independent_monthly_quantile_assumption": list(LOWFLOW_Q),
            "dispatch_order_assumption": list(POLICIES),
        },
        "summary": {
            "scenario_count": len(rows),
            "baseline_deficit_cases": anyshort("baseline_total_unserved_gwh"),
            "stressed_deficit_cases": anyshort("stress_total_unserved_gwh"),
            "without_floor_deficit_cases": anyshort("stress_no_floor_unserved_gwh"),
            "positive_floor_deficit_delta_cases": anyshort(
                "floor_minus_no_floor_unserved_gwh"),
            "positive_additional_demand_deficit_delta_cases": anyshort(
                "stress_minus_baseline_unserved_gwh"),
            "max_stressed_unserved_gwh": worst["stress_total_unserved_gwh"],
            "worst_stress_case_id": worst["case_id"],
            "extra_load_groups": by_extra,
        },
        "rows": rows,
        "reference_trajectories": reference,
        "real_available_capacity_mw": None,
        "rights_cleared_actual_operator_data_used": False,
        "physical_water_rule_constraints_validated": False,
        "network_n_minus_one_verified": False,
        "probabilistic_lole_eens_computed": False,
        "production_ready": False,
        "investment_decision": "HOLD",
    }
    return result


def main() -> int:
    result = report()
    blob=json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False).encode()
    result["payload_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True,
                                 ensure_ascii=False), encoding="utf-8")
    print("V910_SCENARIOS=", result["summary"]["scenario_count"])
    print("V910_SUMMARY=", json.dumps(result["summary"], sort_keys=True))
    print("V910_PAYLOAD_SHA256=", result["payload_sha256"])
    print("V910_FILE_SHA256=", hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
