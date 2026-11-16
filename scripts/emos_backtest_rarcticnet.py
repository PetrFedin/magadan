#!/usr/bin/env python3
"""EMOS-постобработка и повторный бэктест на реальном ряде R-ArcticNET (створ 5858).

Продолжение V9.2: бэктест показал хороший точечный скилл климатологии
(+0,437 против persistence), но узкие интервалы (покрытие 80% = 0,614).
Здесь климатологический ансамбль калибруется EMOS (log-NGR, CRPS-оптимально,
модуль emos_v9) строго по прошлым данным в двух постановках цели
(objective="log" и objective="original_scale") и верифицируется на одном
наборе случаев — сравнение честное, выводы по обеим фиксируются, включая
отрицательные.

Причинность (двойная):
  * предиктивный ансамбль для (Y, m) — климатология 20 лет < Y;
  * EMOS для (Y, m) обучается на парах (y, m) с y ∈ [Y-20, Y-1];
    ансамбль пары y — климатология 20 лет < y (до Y-40 вглубь).
Поэтому оценочный период EMOS — 1973..2000 (первые 20 лет ряда уходят на
обучение калибровки). Сравнение «сырая климатология vs EMOS» выполняется
на ОДНОМ наборе случаев 1973–2000 (не с цифрами V9.2 за 1953–2000).

Несходимость хотя бы одной подгонки — отказ всего прогона (fail-closed,
ArithmeticError из emos_v9 не перехватывается).

Запуск:
    PYTHONPATH=server python3 scripts/emos_backtest_rarcticnet.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.backtest_v9 import climatology_ensemble  # noqa: E402
from hydro_api.crps_decomposition_v9 import decompose_crps  # noqa: E402
from hydro_api.emos_v9 import emos_predictive_quantiles, fit_emos_log  # noqa: E402
from hydro_api.probabilistic_verification_v9 import (  # noqa: E402
    interval_coverage,
    mean_crps,
    pit_value,
    rank_histogram,
)

STATION_POINT_ID = "5858"
STATION_NAME = "Kolyma at Ust'-Srednekan (R-ArcticNET 5858, Roshydromet code 1010)"
WINDOW = 20          # климатологическое окно
TRAIN_YEARS = 20     # обучающее окно EMOS
MIN_HISTORY = 20
ENSEMBLE_M = 20      # размер предиктивного ансамбля (квантили)

INPUT = ROOT / "data" / "r-arcticnet" / "kolyma_ust_srednekan_5858_monthly_m3s.tsv"
OUTPUT = ROOT / "artifacts_v9" / "rarcticnet_emos_backtest_v9.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def read_series():
    series = {}
    with INPUT.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["PointID"] != STATION_POINT_ID:
                continue
            year = int(row["Year"])
            for i, m in enumerate(MONTHS, start=1):
                v = row[m].strip()
                if v:  # пропуски не интерполируются
                    series[(year, i)] = float(v)
    if not series:
        raise ArithmeticError("RARCTICNET_EMPTY_SERIES")
    return series


def main() -> int:
    if not INPUT.is_file():
        print(f"FAIL: входной файл не найден: {INPUT}", file=sys.stderr)
        return 2
    input_sha = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    series = read_series()
    years = sorted({y for y, _ in series})
    y0 = years[0] + WINDOW + TRAIN_YEARS  # 1973
    y1 = years[-1]                        # 2000 (неполные месяцы отсутствуют в series)

    cases = []  # (year, month, obs, raw_ens, emos_log, emos_orig, persistence)
    n_fits = 0
    for Y in range(y0, y1 + 1):
        for m in range(1, 13):
            if (Y, m) not in series or (Y - 1, m) not in series:
                continue
            train_ens, train_obs = [], []
            for y in range(Y - TRAIN_YEARS, Y):
                if (y, m) not in series:
                    continue
                train_ens.append(climatology_ensemble(
                    series, y, m, MIN_HISTORY, WINDOW))
                train_obs.append(series[(y, m)])
            if len(train_obs) < 10:
                continue
            fit_log = fit_emos_log(train_ens, train_obs, min_pairs=10,
                                   objective="log")
            fit_orig = fit_emos_log(train_ens, train_obs, min_pairs=10,
                                    objective="original_scale")
            n_fits += 2
            raw_ens = climatology_ensemble(series, Y, m, MIN_HISTORY, WINDOW)
            cases.append((Y, m, series[(Y, m)], raw_ens,
                          emos_predictive_quantiles(fit_log, raw_ens, m=ENSEMBLE_M),
                          emos_predictive_quantiles(fit_orig, raw_ens, m=ENSEMBLE_M),
                          series[(Y - 1, m)]))
    if not cases:
        raise ArithmeticError("EMOS_BACKTEST_NO_CASES")

    obs = [c[2] for c in cases]
    raw = [c[3] for c in cases]
    emos_log = [c[4] for c in cases]
    emos_orig = [c[5] for c in cases]
    pers = [[c[6]] for c in cases]

    def block(ens):
        return {
            "crps": mean_crps(ens, obs),
            "coverage_80": interval_coverage(ens, obs, alpha=0.2)["empirical_coverage"],
            "coverage_95": interval_coverage(ens, obs, alpha=0.05)["empirical_coverage"],
            "pit_mean": sum(pit_value(e, o) for e, o in zip(ens, obs)) / len(cases),
        }

    dec = decompose_crps(emos_orig, obs)
    report = {
        "period": [cases[0][0], cases[-1][0]],
        "n_cases": len(cases),
        "n_emos_fits": n_fits,
        "ensemble_size": ENSEMBLE_M,
        "nominal_coverage": {"80": 0.8, "95": 0.95},
        "raw_climatology": block(raw),
        "emos_log": block(emos_log),
        "emos_original_scale": block(emos_orig),
        "persistence_crps": mean_crps(pers, obs),
        "rank_histogram_emos_original_scale": list(rank_histogram(emos_orig, obs)),
        "decomposition_emos_original_scale": {
            k: getattr(dec, k) for k in ("reliability", "resolution", "uncertainty")
        },
    }
    for variant in ("raw_climatology", "emos_log", "emos_original_scale"):
        report[variant]["crps_skill_vs_persistence"] = (
            1.0 - report[variant]["crps"] / report["persistence_crps"])
    report["emos_original_scale"]["crps_skill_vs_raw"] = (
        1.0 - report["emos_original_scale"]["crps"] / report["raw_climatology"]["crps"])
    report["emos_log"]["crps_skill_vs_raw"] = (
        1.0 - report["emos_log"]["crps"] / report["raw_climatology"]["crps"])

    artifact = {
        "artifact": "RARCTICNET-EMOS-BACKTEST-V9-1",
        "model": "climatology (rolling 20y) + EMOS log-NGR, две постановки цели (log / original_scale), строго причинно",
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": input_sha,
        "station": STATION_NAME,
        "report": report,
        "note_ru": (
            "EMOS-постобработка базовой климатологии на реальном ряде R-ArcticNET v4.0. "
            "Калибровка строго по прошлым 20 годам, оценка 1973-2000. "
            "НЕ production-допуск: постобработка не добавляет физики притока."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  cases={report['n_cases']} ({report['period'][0]}-{report['period'][1]}), fits={n_fits}")
    for v in ("raw_climatology", "emos_log", "emos_original_scale"):
        b = report[v]
        print(f"  {v:22s} CRPS={b['crps']:7.1f} (skill vs pers {b['crps_skill_vs_persistence']:+.3f}) "
              f"cov80={b['coverage_80']:.3f} cov95={b['coverage_95']:.3f} PIT={b['pit_mean']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
