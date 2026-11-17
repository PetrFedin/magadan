#!/usr/bin/env python3
"""Зимний энергетический баланс каскада Колымских ГЭС (V9.7).

Мост «низководный сток -> гарантированная энергия -> адекватность»:
замыкает цепочку V9.6 (Q80/Q90/Q95 межени, seasonal adequacy) на
энергетику водохранилищ. Зимний приток Колымы ничтожен (створ 5858,
естественный период 1933-1981: медианный расход февраля ~8,7 м³/с
при среднегодовом ~731 м³/с), поэтому зимняя выработка питается
запасом водохранилищ. Скрипт:

  1) считает помесячные квантили низкого стока (5/10/20/50 %) по
     R-ArcticNET 5858 за естественный период (n=49 на месяц);
  2) гоняет сетку детерминированных сценариев каскадного баланса
     ноя—апр: 2 пика нагрузки x 3 КПД x 3 доступности ТЭС x 4 квантили
     притока x 3 начальных заполнения = 216 сценариев;
  3) сводит итоги: доля сценариев без дефицита, минимальные запасы,
     энергетические эквиваленты полезных объёмов, каскадный эффект,
     перекрёстные проверки с опубликованными числами и с артефактом
     V9.6 (сезонная адекватность).

Все опорные числа — из data/reference/*.json с source_ref; КПД,
доступность ТЭС, начальное заполнение — ASSUMPTION-сетки, не данные.
production_ready=False всегда.

Запуск:
    PYTHONPATH=server python3 scripts/magadan_winter_energy_balance_v97.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.winter_energy_balance_v9 import (  # noqa: E402
    MONTH_HOURS,
    WINTER_MONTHS,
    flow_to_power_mw,
    monthly_inflow_quantiles,
    simulate_winter_balance,
    storage_energy_gwh,
    ReservoirSpec,
)

TSV = ROOT / "data" / "r-arcticnet" / "kolyma_basin_multistation_v4.tsv"
SYS_REF = ROOT / "data" / "reference" / "kolyma_magadan_open_sources.json"
CASCADE_REF = ROOT / "data" / "reference" / "kolyma_cascade_energy_v97.json"
V96_ARTIFACT = ROOT / "artifacts_v9" / "magadan_seasonal_adequacy_v9.json"
OUTPUT = ROOT / "artifacts_v9" / "magadan_winter_energy_balance_v97.json"

STATION = "5858"
NATURAL_FROM, NATURAL_TO = 1933, 1981
QUANTILE_LEVELS = (0.05, 0.10, 0.20, 0.50)


def load_5858_series():
    series = {}
    with TSV.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        if header[0] != "PointID":
            raise ArithmeticError("WEB_TSV_HEADER")
        for row in reader:
            if row[0] != STATION:
                continue
            year = int(row[2])
            for i, m in enumerate(range(1, 13)):
                v = row[3 + i].strip()
                if v in ("", "-999", "-999.0"):
                    continue
                series[(year, m)] = float(v)
    if not series:
        raise ArithmeticError("WEB_EMPTY_TSV")
    return series


def main() -> int:
    for p in (TSV, SYS_REF, CASCADE_REF):
        if not p.is_file():
            print(f"FAIL: вход не найден: {p}", file=sys.stderr)
            return 2
    input_sha = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (TSV, SYS_REF, CASCADE_REF)
    }

    sysref = json.loads(SYS_REF.read_text(encoding="utf-8"))
    casref = json.loads(CASCADE_REF.read_text(encoding="utf-8"))
    kol_p = sysref["kolyma_hpp"]["parameters"]
    ust_p = sysref["ust_srednekan_hpp"]["parameters"]
    mps = sysref["magadan_power_system"]["parameters"]
    hydro = casref["cascade_hydrology"]
    grids = casref["scenario_grids_assumption_not_data"]

    kolyma = ReservoirSpec(
        name_ru="Колымская ГЭС",
        usable_volume_km3=kol_p["reservoir_useful_volume_km3"]["value"],
        head_m=kol_p["design_head_m"]["value"],
        guaranteed_capacity_mw=kol_p["guaranteed_capacity_mw"]["value"],
        source_ref=kol_p["reservoir_useful_volume_km3"]["source_ref"])
    ust = ReservoirSpec(
        name_ru="Усть-Среднеканская ГЭС",
        usable_volume_km3=ust_p["reservoir_useful_volume_km3"]["value"],
        head_m=ust_p["design_head_m"]["value"],
        guaranteed_capacity_mw=ust_p["guaranteed_capacity_mw"]["value"],
        source_ref=ust_p["reservoir_useful_volume_km3"]["source_ref"])

    series = load_5858_series()
    inflow_q = monthly_inflow_quantiles(
        series, months=WINTER_MONTHS,
        year_from=NATURAL_FROM, year_to=NATURAL_TO,
        quantile_levels=QUANTILE_LEVELS)

    mean_flow_pub = hydro["mean_annual_flow_ust_srednekan_m3s"]["value"]
    mean_flow_tsv = sum(
        v for (y, _m), v in series.items()
        if NATURAL_FROM <= y <= NATURAL_TO) / (12 * (NATURAL_TO - NATURAL_FROM + 1))
    side_km3 = hydro["side_inflow_annual_volume_km3"]["value"]

    eta_grid = grids["eta_grid"]["value"]
    thermal_grid = grids["thermal_availability_grid"]["value"]
    storage_grid = grids["initial_storage_fraction_grid"]["value"]
    thermal_total = mps["installed_capacity_thermal_mw"]["value"]
    peaks = [float(mps["max_load_2023_mw"]["value"]),
             float(max(mps["max_load_forecast_2025_2030_mw"]["value"]))]

    # Эталонные сценарии с полной помесячной траекторией; остальные
    # сценарии сетки хранятся в сводном виде (воспроизводимы скриптом).
    REFERENCE_SCENARIOS = {
        ("nominal_2023", 460.0, 0.90, 0.9457, 0.50, 1.0),
        ("nominal_2030", 574.0, 0.90, 0.9457, 0.50, 1.0),
        ("binding_low_storage_2030", 574.0, 0.85, 0.85, 0.05, 0.5),
    }
    ref_by_key = {}
    scenarios = []
    worst_full = None  # полная точность, до округления сетки
    min_storage_full = None
    for peak in peaks:
        for eta in eta_grid:
            for avail in thermal_grid:
                for q in QUANTILE_LEVELS:
                    inflow = {m: inflow_q[m][q] for m in WINTER_MONTHS}
                    for s0 in storage_grid:
                        name = (f"peak{peak:g}MW_eta{eta:g}_th{avail:g}_"
                                f"q{int(q * 100)}_s{int(s0 * 100)}")
                        result = simulate_winter_balance(
                            name,
                            kolyma=kolyma, ust_srednekan=ust,
                            peak_load_mw=peak, eta=eta,
                            thermal_available_mw=thermal_total * avail,
                            inflow_quantile=q,
                            inflow_by_month_m3s=inflow,
                            side_inflow_annual_km3=side_km3,
                            mean_annual_flow_m3s=mean_flow_pub,
                            initial_storage_fraction=s0)
                        full = result.model_dump()
                        if (worst_full is None
                                or full["deficit_total_gwh"]
                                > worst_full["deficit_total_gwh"]):
                            worst_full = full
                        if (min_storage_full is None
                                or full["kolyma_storage_min_km3"]
                                < min_storage_full["kolyma_storage_min_km3"]):
                            min_storage_full = full
                        key = (peak, eta, avail, q, s0)
                        for label, *ref_key in REFERENCE_SCENARIOS:
                            if tuple(ref_key) == key:
                                ref_by_key[label] = full
                        # компактная сводка сетки (округление до 4 знаков;
                        # полная точность воспроизводится этим скриптом):
                        # s=scenario, d=deficit_gwh, k=kolyma_min_km3,
                        # u=ust_min_km3, h=hydro_total_gwh, f=feasible
                        scenarios.append({
                            "s": name,
                            "d": round(full["deficit_total_gwh"], 4),
                            "k": round(full["kolyma_storage_min_km3"], 4),
                            "u": round(full["ust_storage_min_km3"], 4),
                            "h": round(full["hydro_total_gwh"], 4),
                            "f": full["feasible_no_deficit"],
                        })

    n_ok = sum(1 for s in scenarios if s["f"])

    # --- Перекрёстные проверки (связи между данными линии V9) ---
eta_mid = 0.90
    q95_feb = inflow_q[2][0.05]  # самый низководный месяц, 5% квантиль
    kol_inflow_share = 1.0 - side_km3 / (mean_flow_pub * 31.536e6 / 1e9)
    inflow_only_power_mw = flow_to_power_mw(
        q95_feb * kol_inflow_share, kolyma.head_m, eta_mid)
    cascade_head = kolyma.head_m + ust.head_m
    storage_equiv = {
        "kolyma_single_head_gwh": {
            f"eta_{eta:g}": storage_energy_gwh(
                kolyma.usable_volume_km3, kolyma.head_m, eta)
            for eta in eta_grid},
        "kolyma_water_cascade_head_gwh": {
            f"eta_{eta:g}": storage_energy_gwh(
                kolyma.usable_volume_km3, cascade_head, eta)
            for eta in eta_grid},
        "ust_srednekan_single_gwh": {
            f"eta_{eta:g}": storage_energy_gwh(
                ust.usable_volume_km3, ust.head_m, eta)
            for eta in eta_grid},
    }
    winter_hours_total = sum(MONTH_HOURS[m] for m in WINTER_MONTHS)
    cross_checks = {
        "mean_flow_published_m3s": mean_flow_pub,
        "mean_flow_rarcticnet_5858_pre1982_m3s": mean_flow_tsv,
        "mean_flow_discrepancy_pct": abs(mean_flow_tsv - mean_flow_pub)
        / mean_flow_pub * 100.0,
        "feb_q05_inflow_only_power_mw_eta0.90": inflow_only_power_mw,
        "kolyma_guaranteed_capacity_mw": kolyma.guaranteed_capacity_mw,
        "inflow_only_share_of_guaranteed_pct": (
            inflow_only_power_mw / kolyma.guaranteed_capacity_mw * 100.0),
        "cascade_head_m": cascade_head,
        "cascade_vs_single_head_gain_pct": (
            ust.head_m / kolyma.head_m * 100.0),
        "v96_hydro_guaranteed_mw": None,
        "v96_hydro_guaranteed_matches": None,
    }
    if V96_ARTIFACT.is_file():
        v96 = json.loads(V96_ARTIFACT.read_text(encoding="utf-8"))
        v96_guaranteed = v96["report"]["hydro_guaranteed_mw"]
        cross_checks["v96_hydro_guaranteed_mw"] = v96_guaranteed
        cross_checks["v96_hydro_guaranteed_matches"] = (
            abs(v96_guaranteed - (kolyma.guaranteed_capacity_mw
                                  + ust.guaranteed_capacity_mw)) < 1e-9)
        input_sha[str(V96_ARTIFACT.relative_to(ROOT))] = hashlib.sha256(
            V96_ARTIFACT.read_bytes()).hexdigest()

    winter_hours_total = sum(MONTH_HOURS[m] for m in WINTER_MONTHS)
    report = {
        "station": STATION,
        "natural_period": [NATURAL_FROM, NATURAL_TO],
        "winter_months": list(WINTER_MONTHS),
        "winter_hours_total": winter_hours_total,
        "inflow_quantiles_m3s": {
            str(m): {f"q{int(q * 100)}": inflow_q[m][q] for q in QUANTILE_LEVELS}
            for m in WINTER_MONTHS},
        "n_scenarios": len(scenarios),
        "peaks_mw": peaks,
        "eta_grid_assumption": eta_grid,
        "thermal_availability_grid_assumption": thermal_grid,
        "initial_storage_fraction_grid_assumption": storage_grid,
        "thermal_installed_mw": thermal_total,
        "hydro_guaranteed_mw": (kolyma.guaranteed_capacity_mw
                                + ust.guaranteed_capacity_mw),
        "storage_energy_equivalents": storage_equiv,
        "cross_checks": cross_checks,
        "feasible_no_deficit_count": n_ok,
        "feasible_share_pct": n_ok / len(scenarios) * 100.0,
        "worst_scenario": {
            "scenario": worst_full["scenario"],
            "deficit_total_gwh": worst_full["deficit_total_gwh"],
            "kolyma_storage_min_km3": worst_full["kolyma_storage_min_km3"],
            "ust_storage_min_km3": worst_full["ust_storage_min_km3"],
        },
        "min_storage_scenario": {
            "scenario": min_storage_full["scenario"],
            "kolyma_storage_min_km3": min_storage_full["kolyma_storage_min_km3"],
            "ust_storage_min_km3": min_storage_full["ust_storage_min_km3"],
        },
        "reference_scenarios": ref_by_key,
        "scenarios": scenarios,
    }

    artifact = {
        "artifact": "MAGADAN-WINTER-ENERGY-BALANCE-V97-1",
        "model": ("Месячный каскадный энергобаланс ноя—апр: ГЭС несут "
                  "гарантированную мощность из запаса водохранилищ "
                  "(E=rho*g*H*V*eta), приток — помесячные квантили низкого "
                  "стока R-ArcticNET 5858 за естественный период 1933-1981, "
                  "боковая приточность выделена по опубликованному годовому "
                  "объёму; нагрузка константна на пике; ТЭС покрывает остаток "
                  "со сценарной доступностью"),
        "input_files": input_sha,
        "report": report,
        "note_ru": (
            "Зимняя выработка каскада Колымских ГЭС — функция ЗАПАСА "
            "водохранилищ, а не притока: приток февральской межени (5% "
            "квантиль) даёт менее 2% гарантированной мощности Колымской ГЭС. "
            "КПД/доступность ТЭС/начальное заполнение — ASSUMPTION-сетки. "
            "Планировочное приближение, НЕ оперативная модель, "
            "НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  scenarios={report['n_scenarios']}, без дефицита={n_ok} "
          f"({report['feasible_share_pct']:.1f}%)")
    print(f"  худший по дефициту: {worst_full['scenario']}, "
          f"дефицит={worst_full['deficit_total_gwh']:.2e} ГВт·ч")
    print(f"  минимум запаса: {min_storage_full['scenario']}, "
          f"Колымское min={min_storage_full['kolyma_storage_min_km3']:.3f} км³")
    print(f"  приток-only мощность (фев, q05, eta=0.90): {inflow_only_power_mw:.2f} МВт "
          f"= {cross_checks['inflow_only_share_of_guaranteed_pct']:.2f}% гарантированной")
    print(f"  средний сток: TSV {mean_flow_tsv:.1f} vs публ. {mean_flow_pub} м³/с "
          f"({cross_checks['mean_flow_discrepancy_pct']:.2f}%)")
    if cross_checks["v96_hydro_guaranteed_matches"] is not None:
        print(f"  связь с V9.6: hydro_guaranteed 356 МВт совпадает = "
              f"{cross_checks['v96_hydro_guaranteed_matches']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
