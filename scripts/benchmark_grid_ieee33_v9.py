#!/usr/bin/env python3
"""Бенчмарк многоузлового NR-солвера ГИДРОКОНТУР 360 против pandapower
на эталонной распределительной сети IEEE 33-bus (Baran & Wu, 1989).

Литературные значения (Baran & Wu, 1989, DOI 10.1109/61.19227):
    Vmin = 0.9131 pu (узел 18 в 1-индексации), P_loss = 202.67 кВт.

Скрипт:
  1. решает сеть нашим солвером (hydro_api.grid_powerflow_v9);
  2. если установлен pandapower — решает ту же сеть им и сравнивает;
  3. пишет машиночитаемую квитанцию в artifacts_v9/grid_ieee33_benchmark_v9.json.

Код выхода: 0 — бенчмарк пройден, 2 — расхождение выше допуска, 3 — pandapower
недоступен (внутренняя проверка на литературные значения всё равно выполняется).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from hydro_api.grid_powerflow_v9 import Branch, PQLoad, RadialNetwork, solve_power_flow

TOL_VOLTAGE_PU = 1e-6
TOL_LOSS_KW = 1e-3

# IEEE 33-bus, Baran & Wu (1989). Ветви: (от, к, R Ом, X Ом), 1-индексация.
BRANCHES_1IDX = [
    (1, 2, 0.0922, 0.0470), (2, 3, 0.4930, 0.2511), (3, 4, 0.3660, 0.1864),
    (4, 5, 0.3811, 0.1941), (5, 6, 0.8190, 0.7070), (6, 7, 0.1872, 0.6188),
    (7, 8, 0.7114, 0.2351), (8, 9, 1.0300, 0.7400), (9, 10, 1.0440, 0.7400),
    (10, 11, 0.1966, 0.0650), (11, 12, 0.3744, 0.1238), (12, 13, 1.4680, 1.1550),
    (13, 14, 0.5416, 0.7129), (14, 15, 0.5910, 0.5260), (15, 16, 0.7463, 0.5450),
    (16, 17, 1.2890, 1.7210), (17, 18, 0.7320, 0.5740), (2, 19, 0.1640, 0.1565),
    (19, 20, 1.5042, 1.3554), (20, 21, 0.4095, 0.4784), (21, 22, 0.7089, 0.9373),
    (3, 23, 0.4512, 0.3083), (23, 24, 0.8980, 0.7091), (24, 25, 0.8960, 0.7011),
    (6, 26, 0.2030, 0.1034), (26, 27, 0.2842, 0.1447), (27, 28, 1.0590, 0.9337),
    (28, 29, 0.8042, 0.7006), (29, 30, 0.5075, 0.2585), (30, 31, 0.9744, 0.9630),
    (31, 32, 0.3105, 0.3619), (32, 33, 0.3410, 0.5302),
]
# Нагрузки: (узел, P кВт, Q квар), 1-индексация.
LOADS_1IDX = [
    (2, 100, 60), (3, 90, 40), (4, 120, 80), (5, 60, 30), (6, 60, 20),
    (7, 200, 100), (8, 200, 100), (9, 60, 20), (10, 60, 20), (11, 45, 30),
    (12, 60, 35), (13, 60, 35), (14, 120, 80), (15, 60, 10), (16, 60, 20),
    (17, 60, 20), (18, 90, 40), (19, 90, 40), (20, 90, 40), (21, 90, 40),
    (22, 90, 40), (23, 90, 50), (24, 420, 200), (25, 420, 200), (26, 60, 25),
    (27, 60, 25), (28, 60, 20), (29, 120, 70), (30, 200, 600), (31, 150, 70),
    (32, 210, 100), (33, 60, 40),
]

LITERATURE = {"vmin_pu": 0.9131, "vmin_bus_1idx": 18, "loss_kw": 202.67}


def build_network() -> RadialNetwork:
    return RadialNetwork(
        base_kv=12.66,
        base_mva=10.0,
        branches=[Branch(from_bus=f - 1, to_bus=t - 1, r_ohm=r, x_ohm=x)
                  for f, t, r, x in BRANCHES_1IDX],
        loads=[PQLoad(bus=b - 1, p_mw=p / 1000.0, q_mvar=q / 1000.0)
               for b, p, q in LOADS_1IDX],
    )


def main() -> int:
    net = build_network()
    res = solve_power_flow(net)
    ours_vmin = res["min_voltage_pu"]
    ours_loss_kw = res["total_loss_mw"] * 1000.0

    receipt = {
        "artifact": "grid_ieee33_benchmark_v9",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "network": "IEEE 33-bus (Baran & Wu 1989), 12.66 kV, radial",
        "solver": {"engine": res["engine"], "iterations": res["iterations"],
                   "converged": res["converged"]},
        "ours": {"vmin_pu": ours_vmin, "vmin_bus_1idx": res["min_voltage_bus"] + 1,
                 "loss_kw": ours_loss_kw},
        "literature": LITERATURE,
        "literature_match": {
            "vmin_abs_err": abs(ours_vmin - LITERATURE["vmin_pu"]),
            "loss_abs_err_kw": abs(ours_loss_kw - LITERATURE["loss_kw"]),
        },
        "external_benchmark": None,
        "benchmarked_against_external_solver": False,
        "production_ready": False,
    }

    exit_code = 0
    try:
        import pandapower as pp  # noqa: PLC0415
    except ImportError:
        receipt["external_benchmark"] = {
            "status": "SKIPPED", "reason": "pandapower not installed"}
        exit_code = 3
    else:
        net_pp = pp.create_empty_network()
        buses = [pp.create_bus(net_pp, vn_kv=12.66) for _ in range(33)]
        pp.create_ext_grid(net_pp, bus=0, vm_pu=1.0)
        for f, t, r, x in BRANCHES_1IDX:
            pp.create_line_from_parameters(
                net_pp, from_bus=buses[f - 1], to_bus=buses[t - 1], length_km=1.0,
                r_ohm_per_km=r, x_ohm_per_km=x, c_nf_per_km=0.0, max_i_ka=10.0)
        for b, p, q in LOADS_1IDX:
            pp.create_load(net_pp, bus=buses[b - 1], p_mw=p / 1000.0,
                           q_mvar=q / 1000.0)
        pp.runpp(net_pp, max_iteration=100, tolerance_mva=1e-12)
        pp_v = net_pp.res_bus.vm_pu.values
        pp_loss_kw = float(net_pp.res_line.pl_mw.sum() * 1000.0)
        max_dv = float(max(abs(pp_v[i] - res["voltage_pu"][i]) for i in range(33)))
        dloss = abs(pp_loss_kw - ours_loss_kw)
        passed = max_dv < TOL_VOLTAGE_PU and dloss < TOL_LOSS_KW
        receipt["external_benchmark"] = {
            "status": "PASS" if passed else "FAIL",
            "reference_solver": f"pandapower {pp.__version__}",
            "pandapower": {"vmin_pu": float(pp_v.min()),
                           "vmin_bus_1idx": int(pp_v.argmin()) + 1,
                           "loss_kw": pp_loss_kw},
            "max_abs_voltage_diff_pu": max_dv,
            "abs_loss_diff_kw": dloss,
            "tolerances": {"voltage_pu": TOL_VOLTAGE_PU, "loss_kw": TOL_LOSS_KW},
        }
        receipt["benchmarked_against_external_solver"] = bool(passed)
        if not passed:
            exit_code = 2

    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
    receipt["sha256"] = hashlib.sha256(payload).hexdigest()

    out = Path(__file__).resolve().parent.parent / "artifacts_v9" / "grid_ieee33_benchmark_v9.json"
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
