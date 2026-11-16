#!/usr/bin/env python3
"""Тренд-адаптивная климатология: бэктест на реальном ряде R-ArcticNET (створ 5858).

Продолжение V9.3: EMOS показал, что дефицит покрытия структурный —
скользящее окно отстаёт от уровня на нестационарном ряде. Здесь проверяется
ответ на уровне самого ансамбля: тренд-адаптивная климатология
(trend_adaptive_v9: наклон Тейла—Сена в лог-шкале, перенос уровня на целевой
год, инфляция дисперсии от ДИ Сена наклона) и её сочетание с EMOS
(original_scale) как финальным слоем — ровно та архитектура, которую
рекомендовал вывод V9.3.

Три варианта на ОДНОМ наборе случаев 1973–2000 (сравнение честное, в т.ч.
с цифрами V9.3):
  raw          — сырая климатология, скользящее окно 20 лет;
  trend        — тренд-адаптивный ансамбль (окно 20 лет, m=20);
  trend_emos   — тренд-адаптивный ансамбль + EMOS original_scale.

Причинность (тройная для trend_emos):
  * ансамбль для (Y, m) использует только годы [Y-20, Y-1];
  * EMOS для (Y, m) обучается на парах (y, m), y ∈ [Y-20, Y-1], где
    ансамбль пары y сам построен по годам [y-20, y-1] (до Y-40 вглубь).

Несходимость любой EMOS-подгонки — отказ всего прогона (fail-closed).

Запуск:
    PYTHONPATH=server python3 scripts/trend_adaptive_backtest_rarcticnet.py
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
from hydro_api.trend_adaptive_v9 import trend_adaptive_ensemble  # noqa: E402

STATION_POINT_ID = "5858"
STATION_NAME = "Kolyma at Ust'-Srednekan (R-ArcticNET 5858, Roshydromet code 1010)"
WINDOW = 20
TRAIN_YEARS = 20
MIN_HISTORY = 20
ENSEMBLE_M = 20

INPUT = ROOT / "data" / "r-arcticnet" / "kolyma_ust_srednekan_5858_monthly_m3s.tsv"
OUTPUT = ROOT / "artifacts_v9" / "rarcticnet_trend_backtest_v9.json"

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
    y0 = years[0] + WINDOW + TRAIN_YEARS  # 1973 — тот же период, что у V9.3
    y1 = years[-1]

    cases = []  # (Y, m, obs, raw, trend, trend_emos, persistence)
    n_fits = 0
    slope_log = []  # диагностика наклонов тренда
    pred_vars = []
    for Y in range(y0, y1 + 1):
        for m in range(1, 13):
            if (Y, m) not in series or (Y - 1, m) not in series:
                continue
            train_ens, train_obs = [], []
            for y in range(Y - TRAIN_YEARS, Y):
                if (y, m) not in series:
                    continue
                e_y, _ = trend_adaptive_ensemble(
                    series, y, m, min_history=MIN_HISTORY, window_years=WINDOW, m=ENSEMBLE_M)
                train_ens.append(e_y)
                train_obs.append(series[(y, m)])
            if len(train_obs) < 10:
                continue
            trend_ens, fit = trend_adaptive_ensemble(
                series, Y, m, min_history=MIN_HISTORY, window_years=WINDOW, m=ENSEMBLE_M)
            fit_emos = fit_emos_log(train_ens, train_obs, min_pairs=10,
                                    objective="original_scale")
            n_fits += 1
            slope_log.append(fit.slope_log_per_year)
            pred_vars.append(fit.pred_var_log)
            cases.append((Y, m, series[(Y, m)],
                          climatology_ensemble(series, Y, m, MIN_HISTORY, WINDOW),
                          trend_ens,
                          emos_predictive_quantiles(fit_emos, trend_ens, m=ENSEMBLE_M),
                          series[(Y - 1, m)]))
    if not cases:
        raise ArithmeticError("TREND_BACKTEST_NO_CASES")

    obs = [c[2] for c in cases]
    raw = [c[3] for c in cases]
    trend = [c[4] for c in cases]
    trend_emos = [c[5] for c in cases]
    pers = [[c[6]] for c in cases]

    def block(ens):
        return {
            "crps": mean_crps(ens, obs),
            "coverage_80": interval_coverage(ens, obs, alpha=0.2)["empirical_coverage"],
            "coverage_95": interval_coverage(ens, obs, alpha=0.05)["empirical_coverage"],
            "pit_mean": sum(pit_value(e, o) for e, o in zip(ens, obs)) / len(cases),
        }

    dec = decompose_crps(trend_emos, obs)
    report = {
        "period": [cases[0][0], cases[-1][0]],
        "n_cases": len(cases),
        "n_emos_fits": n_fits,
        "ensemble_size": ENSEMBLE_M,
        "nominal_coverage": {"80": 0.8, "95": 0.95},
        "raw_climatology": block(raw),
        "trend_adaptive": block(trend),
        "trend_emos_original_scale": block(trend_emos),
        "persistence_crps": mean_crps(pers, obs),
        "rank_histogram_trend_emos": list(rank_histogram(trend_emos, obs)),
        "decomposition_trend_emos": {
            k: getattr(dec, k) for k in ("reliability", "resolution", "uncertainty")
        },
        "trend_diagnostics": {
            "mean_slope_log_per_year": sum(slope_log) / len(slope_log),
            "min_slope_log_per_year": min(slope_log),
            "max_slope_log_per_year": max(slope_log),
            "mean_pred_var_log": sum(pred_vars) / len(pred_vars),
        },
    }
    for variant in ("raw_climatology", "trend_adaptive", "trend_emos_original_scale"):
        report[variant]["crps_skill_vs_persistence"] = (
            1.0 - report[variant]["crps"] / report["persistence_crps"])
        report[variant]["crps_skill_vs_raw"] = (
            1.0 - report[variant]["crps"] / report["raw_climatology"]["crps"])

    artifact = {
        "artifact": "RARCTICNET-TREND-ADAPTIVE-BACKTEST-V9-1",
        "model": "trend-adaptive climatology (Theil-Sen log-slope, Sen CI inflation, m=20) + EMOS original_scale, строго причинно",
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": input_sha,
        "station": STATION_NAME,
        "report": report,
        "note_ru": (
            "Тренд-адаптивная климатология на реальном ряде R-ArcticNET v4.0 — ответ "
            "на структурный дефицит покрытия V9.3. Оценка 1973-2000, тот же набор "
            "случаев, что у EMOS-бэктеста V9.3. НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  cases={report['n_cases']} ({report['period'][0]}-{report['period'][1]}), fits={n_fits}")
    for v in ("raw_climatology", "trend_adaptive", "trend_emos_original_scale"):
        b = report[v]
        print(f"  {v:26s} CRPS={b['crps']:7.1f} (skill vs pers {b['crps_skill_vs_persistence']:+.3f}, "
              f"vs raw {b['crps_skill_vs_raw']:+.3f}) cov80={b['coverage_80']:.3f} "
              f"cov95={b['coverage_95']:.3f} PIT={b['pit_mean']:.3f}")
    d = report["trend_diagnostics"]
    print(f"  trend slope log/yr: mean={d['mean_slope_log_per_year']:+.4f} "
          f"[{d['min_slope_log_per_year']:+.4f} .. {d['max_slope_log_per_year']:+.4f}], "
          f"mean pred_var_log={d['mean_pred_var_log']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
