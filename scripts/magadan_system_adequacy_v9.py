#!/usr/bin/env python3
"""Адекватность изолированной энергосистемы Магаданской области (V9.5).

Мост EFORd -> LOLE/EENS/N-1: классовый приор GADS hydro (EFORd 5,43 %,
data/reference/hydro_for_open_stats.json) применяется к агрегатам
Колымского каскада (5x180 + 4x142,5 МВт, по данным СО ЕЭС /
data/reference/kolyma_magadan_open_sources.json), ТЭС 320 МВт
сканируется по разбиениям (1x320 / 2x160 / 4x80) и сетке FOR
{5,43 %; 10 %; 15 %} — состав ТЭС в открытых источниках не опубликован,
поэтому вся ТЭС-часть — ASSUMPTION (не данные).

Нагрузка — КОНСТАНТНАЯ на уровне пика (хронологическая кривая не
опубликована): консервативная ВЕРХНЯЯ оценка LOLE/EENS.
Пики: 460 МВт (максимум 2023) и 574 МВт (верх прогноза 2025-2030).

Перекрёстная проверка с оценкой СО ЕЭС (+832,1 МВт избытка при останове
наибольшего генерирующего ОБЪЕКТА) фиксируется без усреднения: это иное
определение, чем N-1 по наибольшему АГРЕГАТУ в adequacy_v9.

Выход: artifacts_v9/magadan_system_adequacy_v9.json (+SHA-256 квитанции).

Запуск:
    PYTHONPATH=server python3 scripts/magadan_system_adequacy_v9.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.system_adequacy_v9 import (  # noqa: E402
    UnitGroupSpec,
    evaluate_system,
    thermal_split_scenarios,
)

REF_DIR = ROOT / "data" / "reference"
SYS_REF = REF_DIR / "kolyma_magadan_open_sources.json"
FOR_REF = REF_DIR / "hydro_for_open_stats.json"
OUTPUT = ROOT / "artifacts_v9" / "magadan_system_adequacy_v9.json"

# Сетка FOR для ТЭС: классовый приор GADS hydro + стресс-уровни (ASSUMPTION).
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

    hydro_groups = [
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

    thermal_total = mps["installed_capacity_thermal_mw"]["value"]
    thermal_src = mps["installed_capacity_thermal_mw"]["source_ref"]
    peak_2023 = mps["max_load_2023_mw"]["value"]
    forecast_vals = mps["max_load_forecast_2025_2030_mw"]["value"]
    if not forecast_vals:
        raise ArithmeticError("SYSADQ_NO_FORECAST_VALUES")
    peak_2030_hi = float(max(forecast_vals))
    peaks = [float(peak_2023), peak_2030_hi]

    scenarios = []
    for peak in peaks:
        for for_d in THERMAL_FOR_GRID:
            splits = thermal_split_scenarios(
                thermal_total, THERMAL_SPLITS, for_d,
                thermal_src, "ASSUMPTION-GRID-NOT-DATA")
            for split_key, spec in splits.items():
                name = f"peak{peak:g}MW_for{for_d * 100:g}pct_{split_key}"
                res = evaluate_system(name, [*hydro_groups, spec], peak)
                scenarios.append(res.model_dump())

    worst = max(s["lole_hours_per_year"] for s in scenarios)
    report = {
        "n_scenarios": len(scenarios),
        "eford_hydro_class": eford_hydro,
        "peaks_mw": peaks,
        "thermal_total_mw": thermal_total,
        "thermal_for_grid": list(THERMAL_FOR_GRID),
        "thermal_splits": list(THERMAL_SPLITS),
        "load_model": "constant at peak (консервативная верхняя оценка LOLE/EENS)",
        "scenarios": scenarios,
        "worst_case_lole_hours_per_year": worst,
        "worst_case_eens_mwh_per_year": max(
            s["eens_mwh_per_year"] for s in scenarios),
        "installed_capacity_check": {
            "model_total_mw": scenarios[0]["installed_capacity_mw"],
            "reference_total_mw": mps["installed_capacity_total_mw"]["value"],
        },
        "cross_check_so_ups": {
            "surplus_with_largest_unit_outage_2025_mw":
                mps["surplus_with_largest_unit_outage_2025_mw"]["value"],
            "source_ref": mps["surplus_with_largest_unit_outage_2025_mw"]["source_ref"],
            "note_ru": (
                "Оценка СО ЕЭС: останов наибольшего генерирующего ОБЪЕКТА; "
                "в этом репозитории N-1 определён по наибольшему АГРЕГАТУ. "
                "Определения различаются; значения зафиксированы, "
                "усреднение не выполнялось."),
        },
    }

    artifact = {
        "artifact": "MAGADAN-SYSTEM-ADEQUACY-EFORD-V9-1",
        "model": ("COPT-свёртка adequacy_v9, LOLE/EENS/N-1 при постоянной "
                  "нагрузке на пике; EFORd-приор GADS hydro 5,43 %; ТЭС — "
                  "сценарная сетка разбиений и FOR (ASSUMPTION)"),
        "input_files": input_sha,
        "report": report,
        "note_ru": (
            "Оценка адекватности изолированной системы Магаданской области на "
            "открытых опорных данных (СО ЕЭС СиПР-2024). Натурной статистики "
            "отказов нет => for_is_assumption=True => decision=HOLD. "
            "НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  scenarios={report['n_scenarios']}, "
          f"worst LOLE={worst:.3e} ч/год, "
          f"EENS max={report['worst_case_eens_mwh_per_year']:.3f} МВт·ч/год")
    lole23 = [s["lole_hours_per_year"] for s in scenarios
              if s["peak_load_mw"] == peaks[0]]
    print(f"  peak {peaks[0]:g} МВт: LOLE {min(lole23):.2e}..{max(lole23):.2e} ч/год")
    print(f"  N-1 (1x320, peak {peaks[0]:g}): margin "
          f"{[s['n_minus_1_margin_mw'] for s in scenarios if s['scenario'].endswith('thermal_1x320MW') and s['peak_load_mw'] == peaks[0]][0]:.0f} МВт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
