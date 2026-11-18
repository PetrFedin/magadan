#!/usr/bin/env python3
"""216 paired synthetic priority comparisons; no hydraulic or N-1 authority."""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.dispatch_policy_v99 import compare_hydrothermal_policies  # noqa: E402
from hydro_api.winter_energy_balance_v9 import (  # noqa: E402
    ReservoirSpec, WINTER_MONTHS, monthly_inflow_quantiles,
)
from magadan_winter_energy_balance_v97 import (  # noqa: E402
    CASCADE_REF, NATURAL_FROM, NATURAL_TO, QUANTILE_LEVELS,
    STATION, SYS_REF, TSV, load_5858_series,
)

V98_ARTIFACT = ROOT / "artifacts_v9/magadan_winter_energy_balance_v97.json"
OUTPUT = ROOT / "artifacts_v9/magadan_dispatch_policy_v99.json"
INPUT_FILES = (
    TSV,
    SYS_REF,
    CASCADE_REF,
    V98_ARTIFACT,
    ROOT / "server/hydro_api/winter_energy_balance_v9.py",
    ROOT / "server/hydro_api/dispatch_policy_v99.py",
)


def report() -> dict:
    for p in INPUT_FILES:
        if not p.is_file():
            raise ValueError("V99_SOURCE_FILE_MISSING:" + str(p))
    source_hash = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in INPUT_FILES
    }
    sysref = json.loads(SYS_REF.read_text(encoding="utf-8"))
    casref = json.loads(CASCADE_REF.read_text(encoding="utf-8"))
    old = json.loads(V98_ARTIFACT.read_text(encoding="utf-8"))
    if old["report"]["n_scenarios"] != 216:
        raise ValueError("V99_BASELINE_WRONG_SCENARIO_COUNT")
    baselines = {s["s"]: s for s in old["report"]["scenarios"]}
    kol_params = sysref["kolyma_hpp"]["parameters"]
    ust_params = sysref["ust_srednekan_hpp"]["parameters"]
    grid = casref["scenario_grids_assumption_not_data"]
    hydro = casref["cascade_hydrology"]
    mps = sysref["magadan_power_system"]["parameters"]

    def spec(name, data):
        return ReservoirSpec(
            name_ru=name,
            usable_volume_km3=data["reservoir_useful_volume_km3"]["value"],
            head_m=data["design_head_m"]["value"],
            guaranteed_capacity_mw=data["guaranteed_capacity_mw"]["value"],
            source_ref=data["reservoir_useful_volume_km3"]["source_ref"],
        )

    kolyma = spec("Колымская ГЭС", kol_params)
    ust = spec("Усть-Среднеканская ГЭС", ust_params)
    series = load_5858_series()
    qvalues = monthly_inflow_quantiles(
        series, months=WINTER_MONTHS,
        year_from=NATURAL_FROM, year_to=NATURAL_TO,
        quantile_levels=QUANTILE_LEVELS,
    )
    peaks = [
        float(mps["max_load_2023_mw"]["value"]),
        float(max(mps["max_load_forecast_2025_2030_mw"]["value"])),
    ]
    eta_grid = grid["eta_grid"]["value"]
    th_grid = grid["thermal_availability_grid"]["value"]
    storage_grid = grid["initial_storage_fraction_grid"]["value"]
    thermal_capacity = mps["installed_capacity_thermal_mw"]["value"]
    side = hydro["side_inflow_annual_volume_km3"]["value"]
    mean = hydro["mean_annual_flow_ust_srednekan_m3s"]["value"]

    rows = []
    references = {}
    labels = {
        (460.0, 0.90, 0.9457, 0.50, 1.0): "nominal_2023",
        (574.0, 0.90, 0.9457, 0.50, 1.0): "nominal_2030",
        (574.0, 0.85, 0.85, 0.05, 0.5): "binding_low_storage_2030",
    }
    for peak, eta, factor, quantile, initial in itertools.product(
        peaks, eta_grid, th_grid, QUANTILE_LEVELS, storage_grid
    ):
        name = (f"peak{peak:g}MW_eta{eta:g}_th{factor:g}_"
                f"q{int(quantile*100)}_s{int(initial*100)}")
        paired = compare_hydrothermal_policies(
            name,
            kolyma=kolyma, ust_srednekan=ust,
            peak_load_mw=peak, eta=eta,
            thermal_available_mw=thermal_capacity * factor,
            inflow_quantile=quantile,
            inflow_by_month_m3s={m: qvalues[m][quantile] for m in WINTER_MONTHS},
            side_inflow_annual_km3=side,
            mean_annual_flow_m3s=mean,
            initial_storage_fraction=initial,
            months=WINTER_MONTHS,
        )
        t = paired["policies"]["thermal_first"]
        h = paired["policies"]["hydro_first"]
        legacy = baselines.get(name)
        if legacy is None:
            raise ValueError("V99_MISSING_BASELINE_CASE")
        # V9.8 baseline artifact stores four decimal places; this check
        # detects ANY unacknowledged change in the original thermal-first path.
        for key, expected in (
            ("deterministic_unserved_total_gwh", legacy["d"]),
            ("hydro_total_gwh", legacy["h"]),
            ("upper_storage_min_km3", legacy["k"]),
            ("lower_storage_min_km3", legacy["u"]),
        ):
            if abs(t[key] - expected) > 0.000051:
                raise ValueError("V99_BASELINE_DIVERGENCE:" + name + ":" + key)
        if (t["deterministic_unserved_total_gwh"] < 1e-9) != legacy["f"]:
            raise ValueError("V99_BASELINE_FEASIBILITY_DIVERGENCE")
        summary = {
            "case_id": name,
            "load_mw_assumption": peak,
            "eta_assumption": eta,
            "thermal_availability_assumption": factor,
            "lowflow_quantile_assumption": quantile,
            "initial_storage_fraction_assumption": initial,
            "source_input_sha256": paired["input_sha256"],
            "thermal_first": {
                "unserved_gwh": t["deterministic_unserved_total_gwh"],
                "hydro_gwh": t["hydro_total_gwh"],
                "thermal_gwh": t["thermal_total_gwh"],
                "lower_spill_km3": t["lower_non_generating_spill_km3"],
                "upper_end_km3": t["upper_storage_end_km3"],
                "lower_end_km3": t["lower_storage_end_km3"],
            },
            "hydro_first": {
                "unserved_gwh": h["deterministic_unserved_total_gwh"],
                "hydro_gwh": h["hydro_total_gwh"],
                "thermal_gwh": h["thermal_total_gwh"],
                "lower_spill_km3": h["lower_non_generating_spill_km3"],
                "upper_end_km3": h["upper_storage_end_km3"],
                "lower_end_km3": h["lower_storage_end_km3"],
            },
            "hydro_minus_thermal": paired["hydro_minus_thermal"],
        }
        rows.append(summary)
        label = labels.get((peak, eta, factor, quantile, initial))
        if label:
            references[label] = paired

    if len(rows) != 216 or len(references) != 3:
        raise ValueError("V99_INCOMPLETE_SCENARIO_GRID")
    def results(policy):
        deficits = [x[policy]["unserved_gwh"] for x in rows]
        return {
            "count_deterministic_no_deficit": sum(x < 1e-9 for x in deficits),
            "max_deterministic_unserved_gwh": max(deficits),
            "total_grid_unserved_gwh_not_expected_value": round(sum(deficits), 9),
            "count_nonzero_deficit": sum(x >= 1e-9 for x in deficits),
            "max_lower_spill_km3": max(x[policy]["lower_spill_km3"] for x in rows),
        }
    delta = [r["hydro_minus_thermal"] for r in rows]
    comparison = {
        "scenario_count": len(rows),
        "different_energy_deficit_cases": sum(
            abs(x["deterministic_unserved_gwh"]) > 1e-8 for x in delta
        ),
        "hydro_first_higher_deficit_count": sum(
            x["deterministic_unserved_gwh"] > 1e-8 for x in delta
        ),
        "hydro_first_lower_deficit_count": sum(
            x["deterministic_unserved_gwh"] < -1e-8 for x in delta
        ),
        "different_spill_cases": sum(abs(x["lower_spill_km3"]) > 1e-8 for x in delta),
        "max_abs_unserved_delta_gwh": max(abs(x["deterministic_unserved_gwh"]) for x in delta),
        "max_abs_lower_spill_delta_km3": max(abs(x["lower_spill_km3"]) for x in delta),
        "max_abs_terminal_storage_delta_km3": max(
            abs(x["terminal_total_water_km3"]) for x in delta
        ),
    }
    return {
        "artifact": "MAGADAN-V99-SYNTHETIC-POLICY-SENSITIVITY-1",
        "station": STATION,
        "historical_natural_period": [NATURAL_FROM, NATURAL_TO],
        "source_hashes": source_hash,
        "method": (
            "216 paired deterministic comparisons of thermal-first and "
            "hydro-first sequential heuristics under exactly identical "
            "hypothetical demands, reservoir parameters, natural-period "
            "R-ArcticNET monthly quantiles and uncalibrated thermal settings"
        ),
        "thermal_first": results("thermal_first"),
        "hydro_first": results("hydro_first"),
        "comparison": comparison,
        "references": references,
        "scenarios": rows,
        "synthetic_grid_frequencies_are_not_probabilities": True,
        "physical_water_rule_constraints_validated": False,
        "hourly_route_or_grid_n_minus_one_verified": False,
        "probabilistic_lole_eens_calculated": False,
        "real_available_capacity_mw": None,
        "investment_decision": "HOLD",
        "production_ready": False,
    }


def main() -> int:
    result = report()
    blob = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False).encode()
    result["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, sort_keys=True, indent=2,
                                ensure_ascii=False), encoding="utf-8")
    print("V99_CASES=", result["comparison"]["scenario_count"])
    print("V99_THERMAL_FIRST=", json.dumps(result["thermal_first"], sort_keys=True))
    print("V99_HYDRO_FIRST=", json.dumps(result["hydro_first"], sort_keys=True))
    print("V99_COMPARISON=", json.dumps(result["comparison"], sort_keys=True))
    print("V99_RECEIPT_SHA256=", result["artifact_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
