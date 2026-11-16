#!/usr/bin/env python3
"""Бэктест HydroForecast на реальном ряде R-ArcticNET (створ 5858, Колыма — Усть-Среднекан).

Читает зафиксированное в репозитории подмножество R-ArcticNET v4.0
`data/r-arcticnet/kolyma_ust_srednekan_5858_monthly_m3s.tsv`
(извлечено из полного файла `Anadyr_and_Kolyma_Data_m3_s.txt`, SHA-256
полного файла c2cad85039b3163fa59bea51ce2ca8ac026aa4ffaf62f1610a6a43f73a4ce4f0),
гоняет rolling-origin бэктест климатологического ансамбля (скользящее окно
20 лет, строго без будущего) и пишет квитанцию с SHA-256 в
`artifacts_v9/rarcticnet_backtest_v9.json`.

Запуск:
    PYTHONPATH=server python3 scripts/backtest_hydroforecast_rarcticnet.py

Fail-closed: файл должен существовать и содержать створ целиком; хэш входа
фиксируется в артефакте. Это верификация БАЗОВОЙ климатологической модели
на реальных данных, а не production-допуск.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.backtest_v9 import run_monthly_backtest  # noqa: E402

STATION_POINT_ID = "5858"
STATION_NAME = "Kolyma at Ust'-Srednekan (R-ArcticNET 5858, Roshydromet code 1010)"
WINDOW = 20
MIN_HISTORY = 20

INPUT = ROOT / "data" / "r-arcticnet" / "kolyma_ust_srednekan_5858_monthly_m3s.tsv"
OUTPUT = ROOT / "artifacts_v9" / "rarcticnet_backtest_v9.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def main() -> int:
    if not INPUT.is_file():
        print(f"FAIL: входной файл не найден: {INPUT}", file=sys.stderr)
        return 2
    raw = INPUT.read_bytes()
    input_sha = hashlib.sha256(raw).hexdigest()

    series = {}
    with INPUT.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["PointID"] != STATION_POINT_ID:
                continue
            year = int(row["Year"])
            for i, m in enumerate(MONTHS, start=1):
                v = row[m].strip()
                if v:  # пропуски не интерполируются (fail-closed)
                    series[(year, i)] = float(v)
    if not series:
        print(f"FAIL: створ {STATION_POINT_ID} не найден во входном файле", file=sys.stderr)
        return 3
    years = sorted({y for y, _ in series})
    print(f"Створ {STATION_POINT_ID}: {len(series)} месяцев, годы {years[0]}..{years[-1]}")

    report = run_monthly_backtest(
        series, STATION_NAME,
        year_start=years[0] + WINDOW, year_end=years[-1],
        min_history=MIN_HISTORY, window_years=WINDOW)

    artifact = {
        "artifact": "RARCTICNET-BACKTEST-V9-1",
        "benchmark_model": "climatology (rolling 20-year window, strictly causal)",
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": input_sha,
        "station": STATION_NAME,
        "report": json.loads(report.model_dump_json()),
        "note_ru": (
            "Верификация базовой климатологической модели HydroForecast на реальном "
            "измерительном ряде R-ArcticNET v4.0. НЕ production-допуск: прогнозная "
            "модель — климатология, а не гидрологическая модель притока."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  cases={report.n_cases}, CRPS_clim={report.crps_climatology:.1f} m3/s, "
          f"CRPS_pers={report.crps_persistence:.1f} m3/s, "
          f"skill={report.crps_skill_vs_persistence:+.3f}")
    print(f"  coverage80={report.coverage_80:.3f} (номинал 0.80), "
          f"coverage95={report.coverage_95:.3f} (номинал 0.95)")
    print(f"  REL={report.decomposition_reliability:.2f}, "
          f"RES={report.decomposition_resolution:.2f}, "
          f"UNC={report.decomposition_uncertainty:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
