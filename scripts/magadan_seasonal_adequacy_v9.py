#!/usr/bin/env python3
"""Сезонная адекватность изолированной системы Магаданской области (V9.6).

V9.5 оценивал систему при ПОЛНОЙ установленной мощности ГЭС круглый год
(1790 МВт) — система глубоко перерезервирована. V9.6 добавляет зимний
низководный сценарий: ГЭС ограничены гарантированной мощностью
(Колымская 224 МВт, Усть-Среднеканская 132 МВт — source_ref в
data/reference/kolyma_magadan_open_sources.json), то есть гидрочасть
системы 356 МВт вместо 1470 МВт, суммарно 676 МВт вместо 1790 МВт.

Оба сезона (annual_full_capacity / winter_guaranteed_capacity) считаются
на одной сетке: 2 пика (460, 574 МВт) × 3 FOR ТЭС (5,43 %; 10 %; 15 %)
× 3 разбиения ТЭС (1x320 / 2x160 / 4x80) = 36 сценариев. Нагрузка —
константа на пике (консервативная верхняя оценка LOLE/EENS).

Границы честности: дерейтинг ГЭС до гарантированной мощности —
планировочное приближение, не оперативная модель; энергетические
ограничения водохранилищ COPT не учитывает; натурной статистики отказов
нет => for_is_assumption=True => decision=HOLD во всех сценариях.

Выход: artifacts_v9/magadan_seasonal_adequacy_v9.json (+SHA-256 квитанции).

Запуск:
    PYTHONPATH=server python3 scripts/magadan_seasonal_adequacy_v9.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.seasonal_adequacy_v9 import (  # noqa: E402
    derate_group,
    evaluate_season,
)
from hydro_api.system_adequacy_v9 import (  # noqa: E402
    UnitGroupSpec,
    thermal_split_scenarios,
)

REF_DIR = ROOT / "data" / "reference"
SYS_REF = REF_DIR / "kolyma_magadan_open_sources.json"
FOR_REF = REF_DIR / "hydro_for_open_stats.json"
OUTPUT = ROOT / "artifacts_v9" / "magadan_seasonal_adequacy_v9.json"

THERMAL_FOR_GRID = (0.0543, 0.10, 0.15)
THERMAL_SPLITS = (1, 2, 4)


def main() -> int:
    for p in (SYS_REF, FOR_REF):
        if not p.is_file():
            print(f"FAIL: референс-файл не найден: {p}", file=sys.stderr)
            return 2
    sysref = json.loads(SYS_REF.read_text(encoding="utf-8"))
    forref = json.loads(FOR_REF.read_text(encoding="utf-8"))
    input_sha = {
        str(SYS_REF.relative_to(ROOT)): hashlib.sha256(SYS_REF.read_bytes()).hexdigest(),
        str(FOR_REF.relative_to(ROOT)): hashlib.sha256(FOR_REF.read_bytes()).hexdigest(),
    }

    kol = sysref["kolyma_hpp"]["parameters"]
    ust = sysref["ust_srednekan_hpp"]["parameters"]
    mps = sysref["magadan_power_system"]["parameters"]
    gads = next(e for e in forref["reference_stats"]
                if e["id"] == "gads-2008-2012-hydro")
    eford_hydro = gads["EFORd_pct"] / 100.0

    hydro_nominal = [
        UnitGroupSpec(
            name_prefix="KolymskayaHPP",
            n_units=kol["units_count"]["value"],
            unit_capacity_mw=kol["unit_capacity_mw"]["value"],
            eford_d=eford_hydro,
            source_ref=kol["units_count"]["source_ref"],
            eford_source_ref=gads["source_ref"]),
        UnitGroupSpec(
            name_prefix="UstSrednekanHPP",
            n_units=ust["units_count"]["value"],
            unit_capacity_mw=ust["unit_capacity_mw"]["value"],
            eford_d=eford_hydro,
            source_ref=ust["units_count"]["source_ref"],
            eford_source_ref=gads["source_ref"]),
    ]
    hydro_winter = [
        derate_group(hydro_nominal[0], kol["guaranteed_capacity_mw"]["value"]),
        derate_group(hydro_nominal[1], ust["guaranteed_capacity_mw"]["value"]),
    ]

    thermal_total = mps["installed_capacity_thermal_mw"]["value"]
    thermal_src = mps["installed_capacity_thermal_mw"]["source_ref"]
    peaks = [float(mps["max_load_2023_mw"]["value"]),
             float(max(mps["max_load_forecast_2025_2030_mw"]["value"]))]

    scenarios = []
    for season, hydro in (("annual_full_capacity", hydro_nominal),
                          ("winter_guaranteed_capacity", hydro_winter)):
        for peak in peaks:
            for for_d in THERMAL_FOR_GRID:
                splits = thermal_split_scenarios(
                    thermal_total, THERMAL_SPLITS, for_d,
                    thermal_src, "ASSUMPTION-GRID-NOT-DATA")
                for split_key, spec in splits.items():
                    name = f"{season}_peak{peak:g}MW_for{for_d * 100:g}pct_{split_key}"
                    scenarios.append(evaluate_season(
                        name, season, [*hydro, spec], peak).model_dump())

    winter = [s for s in scenarios if s["season"] == "winter_guaranteed_capacity"]
    annual = [s for s in scenarios if s["season"] == "annual_full_capacity"]
    report = {
        "n_scenarios": len(scenarios),
        "eford_hydro_class": eford_hydro,
        "peaks_mw": peaks,
        "thermal_for_grid": list(THERMAL_FOR_GRID),
        "thermal_splits": list(THERMAL_SPLITS),
        "hydro_installed_mw": sum(
            g.n_units * g.unit_capacity_mw for g in hydro_nominal),
        "hydro_guaranteed_mw": sum(
            g.n_units * g.unit_capacity_mw for g in hydro_winter),
        "load_model": "constant at peak (консервативная верхняя оценка LOLE/EENS)",
        "scenarios": scenarios,
        "season_summary": {
            "annual_full_capacity": {
                "worst_lole_hours_per_year": max(s["lole_hours_per_year"] for s in annual),
                "n_minus_1_insecure_count": sum(1 for s in annual if not s["n_minus_1_secure"]),
            },
            "winter_guaranteed_capacity": {
                "worst_lole_hours_per_year": max(s["lole_hours_per_year"] for s in winter),
                "n_minus_1_insecure_count": sum(1 for s in winter if not s["n_minus_1_secure"]),
                "n_minus_1_insecure_scenarios": [
                    s["scenario"] for s in winter if not s["n_minus_1_secure"]],
            },
        },
    }

    artifact = {
        "artifact": "MAGADAN-SEASONAL-ADEQUACY-V9-1",
        "model": ("COPT-свёртка adequacy_v9, два сезона: полная мощность ГЭС "
                  "vs зимняя гарантированная (дерейтинг агрегатов до 224+132 "
                  "МВт); EFORd-приор GADS hydro 5,43 %; ТЭС — сценарная сетка "
                  "(ASSUMPTION); нагрузка константа на пике"),
        "input_files": input_sha,
        "report": report,
        "note_ru": (
            "Сезонная граница вывода V9.5: годовая перерезервированность не "
            "переносится на зимнюю межень — при гарантированной мощности ГЭС "
            "запас системы 676 МВт, N-1 зависит от разбиения ТЭС. "
            "Планировочное приближение, НЕ оперативная модель (энергетические "
            "ограничения водохранилищ не учитываются). НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  scenarios={report['n_scenarios']}")
    for season, s in report["season_summary"].items():
        print(f"  {season}: worst LOLE={s['worst_lole_hours_per_year']:.4g} ч/год, "
              f"N-1 insecure={s['n_minus_1_insecure_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
