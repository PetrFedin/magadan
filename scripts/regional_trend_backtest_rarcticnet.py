#!/usr/bin/env python3
"""Региональный тренд-анализ и мультистанционный бэктест R-ArcticNET (V9.5).

Продолжение V9.4: тренд-адаптивная климатология проверена на ОДНОМ створе
(5858, Усть-Среднекан) — обобщать на бассейн было нельзя. V9.5 переносит
проверку на 11 створов бассейна Колымы (PointID < 6000, >= 35 полных лет)
из верифицированного файла R-ArcticNET v4.0 и разделяет две гипотезы
зимнего роста стока:

  H1 (климат): рост зимнего базового стока в криолитозоне виден и на
      НЕрегулируемых притоках;
  H2 (регулирование): створы 5858/5951 ниже Колымской ГЭС (регулирование
      с 1982 г., data/reference/kolyma_magadan_open_sources.json)
      получают зимние попуски — «тренд» может быть антропогенным.

Бэктест (строго причинный, как в V9.4): для каждого створа и каждого
случая (Y, m), Y >= first_year + 20, с наличием (Y, m) и (Y-1, m):
  raw   — сырая климатология, окно 20 лет;
  trend — тренд-адаптивный ансамбль (окно 20 лет, m=20).
Случаи, где ансамбль не строится (ArithmeticError/ValueError), пропускаются;
число отобранных створов жёстко контролируется (fail-closed).

Выход: artifacts_v9/rarcticnet_regional_trend_v9.json (+SHA-256 квитанции).

Запуск:
    PYTHONPATH=server python3 scripts/regional_trend_backtest_rarcticnet.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from hydro_api.backtest_v9 import climatology_ensemble  # noqa: E402
from hydro_api.probabilistic_verification_v9 import (  # noqa: E402
    interval_coverage,
    mean_crps,
)
from hydro_api.regional_trend_v9 import (  # noqa: E402
    KOLYMSKY_HPP_REGULATION_ONSET_YEAR,
    MIN_YEARS,
    WINTER_MONTHS,
    seasonal_annual_means,
    trend_stats,
)
from hydro_api.trend_adaptive_v9 import trend_adaptive_ensemble  # noqa: E402

WINDOW = 20
MIN_HISTORY = 20
ENSEMBLE_M = 20

# Створы ниже Колымской ГЭС (регулирование с 1982 г.): 5858 (Усть-Среднекан)
# и 5951 (устье Колымы); остальные 9 — нерегулируемые притоки.
REGULATED_BELOW_DAM = {"5858", "5951"}

INPUT = ROOT / "data" / "r-arcticnet" / "kolyma_basin_multistation_v4.tsv"
OUTPUT = ROOT / "artifacts_v9" / "rarcticnet_regional_trend_v9.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_multistation():
    """Читает мультистанционный TSV -> {PointID: {(year, month): м³/с}}."""
    series: dict[str, dict[tuple[int, int], float]] = {}
    with INPUT.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            pid = row["PointID"]
            year = int(row["Year"])
            for i, m in enumerate(MONTHS, start=1):
                v = (row[m] or "").strip()
                if v:  # пропуски не интерполируются
                    series.setdefault(pid, {})[(year, i)] = float(v)
    if not series:
        raise ArithmeticError("RARCTICNET_EMPTY_SERIES")
    return series


def station_trends(series):
    """Тренды створа: годовой и зимний (дек—мар), полный период и до 1982."""
    annual = seasonal_annual_means(series, tuple(range(1, 13)))
    winter = seasonal_annual_means(series, WINTER_MONTHS)
    out = {
        "annual": trend_stats(annual, target="annual"),
        "winter_dec_mar": trend_stats(winter, target="winter_dec_mar"),
    }
    try:
        out["winter_dec_mar_pre_regulation"] = trend_stats(
            winter, target="winter_dec_mar_pre_regulation",
            year_to=KOLYMSKY_HPP_REGULATION_ONSET_YEAR - 1)
    except ArithmeticError:
        out["winter_dec_mar_pre_regulation"] = None  # ряд короче MIN_YEARS
    return out


def backtest_cases(series):
    """Причинный бэктест raw/trend на всех доступных случаях створа."""
    years = sorted({y for y, _ in series})
    cases = []  # (Y, m, obs, raw, trend)
    for Y in range(years[0] + WINDOW, years[-1] + 1):
        for m in range(1, 13):
            if (Y, m) not in series or (Y - 1, m) not in series:
                continue
            try:
                raw = climatology_ensemble(series, Y, m, MIN_HISTORY, WINDOW)
                trend, _fit = trend_adaptive_ensemble(
                    series, Y, m, min_history=MIN_HISTORY,
                    window_years=WINDOW, m=ENSEMBLE_M)
            except (ArithmeticError, ValueError):
                continue  # недостаточно истории в окне — случай пропускается
            cases.append((Y, m, series[(Y, m)], raw, trend))
    return cases


def metrics(ens, obs):
    """Метрики качества ансамбля на наборе случаев."""
    return {
        "crps": mean_crps(ens, obs),
        "coverage_80": interval_coverage(ens, obs, alpha=0.2)["empirical_coverage"],
        "coverage_95": interval_coverage(ens, obs, alpha=0.05)["empirical_coverage"],
    }


def main() -> int:
    if not INPUT.is_file():
        print(f"FAIL: входной файл не найден: {INPUT}", file=sys.stderr)
        return 2
    input_sha = hashlib.sha256(INPUT.read_bytes()).hexdigest()
    data = load_multistation()
    selected = sorted(data.keys())
    if len(selected) != 11:
        raise ArithmeticError(
            f"REGIONAL_STATION_COUNT: выбрано {len(selected)} створов != 11")

    stations = {}
    all_cases = []
    for pid in selected:
        series = data[pid]
        trends = station_trends(series)
        cases = backtest_cases(series)
        obs = [c[2] for c in cases]
        raw = [c[3] for c in cases]
        trend = [c[4] for c in cases]
        stations[pid] = {
            "n_years_total": len({y for y, _ in series}),
            "trends": {
                k: (v.model_dump() if v is not None else None)
                for k, v in trends.items()
            },
            "backtest": {
                "n_cases": len(cases),
                "period": [cases[0][0], cases[-1][0]] if cases else None,
                "raw_climatology": metrics(raw, obs) if cases else None,
                "trend_adaptive": metrics(trend, obs) if cases else None,
            },
        }
        all_cases.extend((pid, c) for c in cases)
    if not all_cases:
        raise ArithmeticError("REGIONAL_BACKTEST_NO_CASES")

    obs = [c[2] for _, c in all_cases]
    pooled_raw = metrics([c[3] for _, c in all_cases], obs)
    pooled_trend = metrics([c[4] for _, c in all_cases], obs)
    pooled = {
        "n_cases": len(all_cases),
        "ensemble_size": ENSEMBLE_M,
        "window_years": WINDOW,
        "raw_climatology": pooled_raw,
        "trend_adaptive": pooled_trend,
    }

    groups = {}
    for name, members in (
            ("regulated_below_dam", [p for p in selected if p in REGULATED_BELOW_DAM]),
            ("not_below_dam", [p for p in selected if p not in REGULATED_BELOW_DAM])):
        w = [trends_w for p in members
             for trends_w in [stations[p]["trends"]["winter_dec_mar"]]]
        slopes = [t["slope_pct_per_year"] for t in w]
        groups[name] = {
            "stations": members,
            "n_stations": len(members),
            "n_winter_positive": sum(1 for s in slopes if s > 0),
            "n_winter_significant": sum(
                1 for t in w if t["mk_significant_5pct"]),
            "median_winter_slope_pct_per_year": statistics.median(slopes),
        }

    report = {
        "n_stations": len(selected),
        "stations": selected,
        "winter_months": list(WINTER_MONTHS),
        "min_years": MIN_YEARS,
        "regulation_onset_year": KOLYMSKY_HPP_REGULATION_ONSET_YEAR,
        "station_results": stations,
        "pooled_backtest": pooled,
        "regulation_group_summary": groups,
    }

    artifact = {
        "artifact": "RARCTICNET-REGIONAL-TREND-V9-1",
        "model": ("Mann-Kendall + Theil-Sen (log) по 11 створам Колымы; "
                  "причинный бэктест raw vs trend-adaptive (окно 20 лет, m=20)"),
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": input_sha,
        "report": report,
        "note_ru": (
            "Региональный перенос тренд-диагностики V9.4 на 11 створов бассейна "
            "Колымы (R-ArcticNET v4.0, >= 35 полных лет). Разделение гипотез: "
            "климат (H1) vs регулирование Колымской ГЭС с 1982 г. (H2). "
            "НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  stations={report['n_stations']}, pooled cases={pooled['n_cases']}")
    for v in ("raw_climatology", "trend_adaptive"):
        b = pooled[v]
        print(f"  pooled {v:16s} CRPS={b['crps']:7.1f} "
              f"cov80={b['coverage_80']:.3f} cov95={b['coverage_95']:.3f}")
    for g, s in groups.items():
        print(f"  {g:20s} n={s['n_stations']} winter+={s['n_winter_positive']} "
              f"signif={s['n_winter_significant']} "
              f"median={s['median_winter_slope_pct_per_year']:+.2f} %/год")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
