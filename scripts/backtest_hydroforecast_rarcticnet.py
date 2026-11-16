#!/usr/bin/env python3
"""V9.2 — бэктест HydroForecast на реальном ряде R-ArcticNET v4.0.

Створ: 5858, р. Колыма — Усть-Среднекан (R-ArcticNET v4.0, PointID 5858,
код станции 1010; Lammers et al., 2001, JGR 106(D4)) — 67 полных лет
месячного стока, 1933–1999 (2000-й неполный, исключён из оценки).

Вход: data/r-arcticnet/kolyma_ust_srednekan_5858_monthly_m3s.tsv
(подмножество полного файла; полный файл получается scripts/fetch_open_hydro_data.py).
Выход: artifacts_v9/rarcticnet_backtest_v9.json с SHA-256 входа и артефакта.

Метод: rolling-origin, строго причинно. Окно климатологии 20 лет
(window_years == min_history == 20 — единый размер ансамбля m=20, иначе
ранговая верификация и декомпозиция CRPS недопустимы). Оценка 1953–2000:
годы с неполными данными пропускаются самим движком без интерполяции.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INPUT = REPO / "data" / "r-arcticnet" / "kolyma_ust_srednekan_5858_monthly_m3s.tsv"
OUTPUT = REPO / "artifacts_v9" / "rarcticnet_backtest_v9.json"

STATION = "Kolyma at Ust'-Srednekan (R-ArcticNET v4.0 PointID 5858, code 1010)"
POINT_ID = "5858"


def read_series(path: Path):
    series = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pid, year, month, q = line.split("\t")
            if pid != POINT_ID:
                continue
            q = float(q)
            if q < 0:  # пропуски в R-ArcticNET кодируются отрицательными
                continue
            series[(int(year), int(month))] = q
    if not series:
        raise ArithmeticError("RARCTICNET_EMPTY_SERIES: нет данных по створу " + POINT_ID)
    return series


def main() -> int:
    import sys
    sys.path.insert(0, str(REPO / "server"))
    from hydro_api.backtest_v9 import run_monthly_backtest

    raw = INPUT.read_bytes()
    input_sha = hashlib.sha256(raw).hexdigest()
    series = read_series(INPUT)

    years = sorted({y for y, _ in series})
    months_per_year = {}
    for (y, m) in series:
        months_per_year.setdefault(y, set()).add(m)
    full_years = [y for y in years if len(months_per_year[y]) == 12]

    report = run_monthly_backtest(
        series,
        station=STATION,
        year_start=1953,
        year_end=2000,
        min_history=20,
        window_years=20,
    )

    out = {
        "artifact": "V9.2 реальный бэктест HydroForecast — R-ArcticNET v4.0, створ 5858",
        "engine_id": report.engine_id,
        "input_file": str(INPUT.relative_to(REPO)),
        "input_sha256": input_sha,
        "series_span": {
            "first": min(series), "last": max(series),
            "full_years_count": len(full_years),
            "full_years_range": [min(full_years), max(full_years)],
        },
        "report": json.loads(report.model_dump_json()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    OUTPUT.write_text(payload + "\n", encoding="utf-8")

    artifact_sha = hashlib.sha256((payload + "\n").encode("utf-8")).hexdigest()
    # вшиваем хэш артефакта отдельной строкой-комментарием рядом (сам файл не меняем)
    print(json.dumps({
        "cases_evaluated": report.cases_evaluated,
        "crps_climatology": round(report.crps_climatology, 3),
        "crps_persistence": round(report.crps_persistence, 3),
        "crps_skill_vs_persistence": round(report.crps_skill_vs_persistence, 4),
        "coverage_80": round(report.coverage_80, 4),
        "coverage_95": round(report.coverage_95, 4),
        "input_sha256": input_sha,
        "artifact_sha256": artifact_sha,
        "output": str(OUTPUT.relative_to(REPO)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
