#!/usr/bin/env python3
"""V9.12 exact-SHA reproducible causal two-reservoir laboratory, no real MW."""
from __future__ import annotations
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from hydro_api.causal_cascade_v912 import Step, synthetic_demo  # noqa: E402

OUTPUT = ROOT / "artifacts_v9/magadan_causal_cascade_v912.json"
SOURCE = (
    ROOT / "server/hydro_api/causal_cascade_v912.py",
    ROOT / "scripts/magadan_causal_cascade_v912.py",
    ROOT / "data/reference/kolyma_cascade_rules_2025_v911.json",
    ROOT / "artifacts_v9/magadan_normative_screen_v911.json",
)
START = datetime.fromisoformat("2026-11-01T00:00:00+03:00")


def periods(**changed):
    default = {
        "duration_hours": 24.0, "upstream_inflow_m3_s": 100.0,
        "lateral_inflow_m3_s": 30.0, "upper_turbine_m3_s": 80.0,
        "upper_bypass_m3_s": 0.0, "lower_turbine_m3_s": 75.0,
        "lower_bypass_m3_s": 0.0, "demand_mw": 120.0,
        "thermal_available_mw": 100.0, "stable_negative_temperatures": True,
    }
    default.update(changed)
    return tuple(Step(
        start=(START + timedelta(days=i)).isoformat(), **default
    ) for i in range(8))


def report():
    for p in SOURCE:
        if not p.exists():
            raise ValueError("V912_MISSING_SOURCE:" + str(p))
    cases = {
        "coherent_no_shortfall": synthetic_demo(),
        "thermal_outage_shortfall": synthetic_demo(
            steps=periods(demand_mw=400, thermal_available_mw=0)),
        "zero_shortfall_cannot_approve_cold_bypass": synthetic_demo(
            steps=periods(upper_bypass_m3_s=20, thermal_available_mw=1000)),
        "unknown_temperature_is_insufficient": synthetic_demo(
            steps=periods(lower_bypass_m3_s=2,
                          stable_negative_temperatures=None)),
        "unaccounted_overflow_is_infeasible": synthetic_demo(
            steps=periods(upstream_inflow_m3_s=20000)),
        "unserved_export_sink_is_infeasible": synthetic_demo(
            steps=periods(demand_mw=1, thermal_available_mw=0)),
        "no_stable_cold_not_a_legal_approval": synthetic_demo(
            steps=periods(lower_bypass_m3_s=1,
                          stable_negative_temperatures=False)),
        "real_world_sources_missing": synthetic_demo(mode="field"),
    }
    expected = {
        "coherent_no_shortfall": ("SYNTHETIC_CONSISTENT", "NO_CALCULATED_SHORTFALL"),
        "thermal_outage_shortfall": ("SYNTHETIC_CONSISTENT", "DETERMINISTIC_SHORTFALL"),
        "zero_shortfall_cannot_approve_cold_bypass": ("INFEASIBLE_DISPATCH", "NOT_EVALUATED"),
        "unknown_temperature_is_insufficient": ("DATA_INSUFFICIENT", "NOT_EVALUATED"),
        "unaccounted_overflow_is_infeasible": ("INFEASIBLE_DISPATCH", "NOT_EVALUATED"),
        "unserved_export_sink_is_infeasible": ("INFEASIBLE_DISPATCH", "NOT_EVALUATED"),
        "no_stable_cold_not_a_legal_approval": ("SYNTHETIC_CONSISTENT", "NO_CALCULATED_SHORTFALL"),
        "real_world_sources_missing": ("DATA_INSUFFICIENT", "NOT_EVALUATED"),
    }
    for case, result in cases.items():
        if (result["status"], result["energy_status"]) != expected[case]:
            raise AssertionError("V912_UNEXPECTED_MODEL_OUTCOME:" + case + ":" + str(result["status"]))
        if (result["real_available_capacity_mw"] is not None or
                result["production_ready"] is not False or
                result["water_rule_certification"] is not False):
            raise AssertionError("V912_UNSUPPORTED_PRODUCTION_CLAIM")
        if result["status"] == "SYNTHETIC_CONSISTENT":
            if abs(result["season_mass_residual_km3"]) > 1e-9:
                raise ArithmeticError("V912_NONCONSERVATIVE_SYNTHETIC_MODEL")
    results = {
        "artifact": "MAGADAN-V912-CAUSAL-SYNTHETIC-LAB-1",
        "experiment_count": len(cases),
        "source_sha256": {
            str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
            for p in SOURCE
        },
        "method": "Two-reservoir multi-period synthetic mass and energy conservation with explicit water-in-flight. No source-verified hydraulic or dispatch calibration.",
        "discrete_lag_steps_assumed_not_calibrated": 2,
        "stationary_synthetic_curves_are_not_official_order_174_curves": True,
        "published_statutory_anchor_checks_reused_from_v911_but_not_operational_certification": True,
        "results": cases,
        "summary": {
            "synthetic_consistent_cases": sum(
                v["status"] == "SYNTHETIC_CONSISTENT" for v in cases.values()),
            "infeasible_cases": sum(
                v["status"] == "INFEASIBLE_DISPATCH" for v in cases.values()),
            "insufficient_evidence_cases": sum(
                v["status"] == "DATA_INSUFFICIENT" for v in cases.values()),
            "calculated_shortfall_cases": sum(
                v["energy_status"] == "DETERMINISTIC_SHORTFALL" for v in cases.values()),
            "zero_shortfall_overrides_a_hard_rule": False,
        },
        "real_operator_curves_used": False,
        "real_operating_regime_approved": False,
        "firm_capacity_mw": None,
        "network_n_minus_one_verified": False,
        "probabilistic_lole_eens_computed": False,
        "production_ready": False,
        "investment_decision": "HOLD",
    }
    body = json.dumps(results, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    results["payload_sha256"] = sha256(body).hexdigest()
    return results


def main():
    value = report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(value, sort_keys=True, indent=2,
                                 ensure_ascii=False), encoding="utf-8")
    print("V912_RESULTS=" + json.dumps(value["summary"], sort_keys=True))
    print("V912_PAYLOAD_SHA256=" + value["payload_sha256"])
    print("V912_FILE_SHA256=" + sha256(OUTPUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
