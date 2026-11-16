#!/usr/bin/env python3
"""Низководный анализ 11 створов Колымы: Q80/Q90/Q95 минимумов (V9.6).

Продолжение V9.5: региональный тренд-анализ показал, что зимний сток
зарегулированных створов (5858, 5951) после 1982 г. растёт в основном
из-за попусков Колымской ГЭС. V9.6 переводит это в абсолютную
гидрологическую метрику: обеспеченные расходы низководного периода
(годовой минимум месячного стока и минимум зимней межени дек—мар),
с 95% ДИ бутстрепа и логнормальной перекрёстной оценкой, плюс тренды
тих же рядов и разделение до/после 1982 г. для створов ниже плотины.

Выход: artifacts_v9/rarcticnet_lowflow_v9.json (+SHA-256 квитанции).

Запуск:
    PYTHONPATH=server python3 scripts/lowflow_analysis_rarcticnet.py
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

from hydro_api.lowflow_v9 import (  # noqa: E402
    annual_min_monthly,
    quantile_stats,
)
from hydro_api.regional_trend_v9 import (  # noqa: E402
    KOLYMSKY_HPP_REGULATION_ONSET_YEAR,
    WINTER_MONTHS,
    trend_stats,
)

INPUT = ROOT / "data" / "r-arcticnet" / "kolyma_basin_multistation_v4.tsv"
OUTPUT = ROOT / "artifacts_v9" / "rarcticnet_lowflow_v9.json"

REGULATED_BELOW_DAM = {"5858", "5951"}
EXCEEDANCES = (80.0, 90.0, 95.0)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_multistation():
    series = {}
    with INPUT.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            pid = row["PointID"]
            year = int(row["Year"])
            for i, m in enumerate(MONTHS, start=1):
                v = (row[m] or "").strip()
                if v:
                    series.setdefault(pid, {})[(year, i)] = float(v)
    if not series:
        raise ArithmeticError("RARCTICNET_EMPTY_SERIES")
    return series


def target_block(values_by_year, target):
    """Квантили Q80/Q90/Q95 + тренд (если ряд >= 20 лет) одного ряда."""
    quantiles = {}
    for P in EXCEEDANCES:
        r = quantile_stats(values_by_year, target=target, exceedance_pct=P)
        quantiles[f"q{P:g}"] = r.model_dump()
    try:
        trend = trend_stats(values_by_year, target=target).model_dump()
    except ArithmeticError:
        trend = None   # ряд короче 20 лет — тренд не оценивается (fail-closed)
    return {
        "n_years": len(values_by_year),
        "year_from": min(values_by_year) if values_by_year else None,
        "year_to": max(values_by_year) if values_by_year else None,
        "quantiles": quantiles,
        "trend": trend,
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
            f"LOWFLOW_STATION_COUNT: выбрано {len(selected)} створов != 11")

    stations = {}
    for pid in selected:
        series = data[pid]
        annual_min = annual_min_monthly(series)                      # полные годы
        winter_min = annual_min_monthly(series, WINTER_MONTHS)       # дек—мар
        entry = {
            "annual_min_monthly": target_block(annual_min, "annual_min_monthly"),
            "winter_min_dec_mar": target_block(winter_min, "winter_min_dec_mar"),
        }
        if pid in REGULATED_BELOW_DAM:
            onset = KOLYMSKY_HPP_REGULATION_ONSET_YEAR
            split = {}
            for label, vby in (("annual_min_monthly", annual_min),
                               ("winter_min_dec_mar", winter_min)):
                pre = {y: v for y, v in vby.items() if y < onset}
                post = {y: v for y, v in vby.items() if y >= onset}
                split[label] = {
                    "pre_regulation": {
                        f"q{P:g}": quantile_stats(
                            pre, target=label + "_pre", exceedance_pct=P
                        ).model_dump()
                        for P in EXCEEDANCES if len(pre) >= 10
                    },
                    "post_regulation": {
                        f"q{P:g}": quantile_stats(
                            post, target=label + "_post", exceedance_pct=P
                        ).model_dump()
                        for P in EXCEEDANCES if len(post) >= 10
                    },
                }
            entry["regulation_split"] = split
            entry["regulation_onset_year"] = onset
        stations[pid] = entry

    # Сводка по нерегулируемым створам: медианный Q90 зимней межени.
    q90_winter = [stations[p]["winter_min_dec_mar"]["quantiles"]["q90"]["q_empirical_m3s"]
                  for p in selected if p not in REGULATED_BELOW_DAM]
    summary = {
        "not_below_dam_median_winter_q90_m3s": statistics.median(q90_winter),
        "regulated_q90_winter_m3s": {
            p: stations[p]["winter_min_dec_mar"]["quantiles"]["q90"]["q_empirical_m3s"]
            for p in sorted(REGULATED_BELOW_DAM)
        },
    }

    report = {
        "n_stations": len(selected),
        "stations": selected,
        "winter_months": list(WINTER_MONTHS),
        "regulation_onset_year": KOLYMSKY_HPP_REGULATION_ONSET_YEAR,
        "exceedances_pct": list(EXCEEDANCES),
        "station_results": stations,
        "summary": summary,
    }

    artifact = {
        "artifact": "RARCTICNET-LOWFLOW-FREQUENCY-V9-1",
        "model": ("Обеспеченные расходы Q80/Q90/Q95 годового и зимнего "
                  "(дек—мар) минимума месячного стока: эмпирическая квантиль "
                  "+ 95% ДИ бутстрепа (B=2000, seed фиксирован) + логнормальная "
                  "MLE перекрёстная оценка; тренды Манн—Кендалл/Тейл—Сен; "
                  "разделение до/после 1982 г. для створов ниже Колымской ГЭС"),
        "input_file": str(INPUT.relative_to(ROOT)),
        "input_sha256": input_sha,
        "report": report,
        "note_ru": (
            "Низководная характеристика 11 створов Колымы (R-ArcticNET v4.0). "
            "Q(P%) = расход, превышаемый в P% лет. Эмпирическая и логнормальная "
            "оценки приводятся РАЗДЕЛЬНО, без усреднения. Малые выборки помечены "
            "small_sample. НЕ production-допуск."
        ),
    }
    blob = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True).encode()
    artifact["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"OK: {OUTPUT}")
    print(f"  stations={report['n_stations']}")
    print(f"  not_below_dam median winter Q90 = "
          f"{summary['not_below_dam_median_winter_q90_m3s']:.2f} м³/с")
    for p in sorted(REGULATED_BELOW_DAM):
        sp = stations[p]["regulation_split"]["winter_min_dec_mar"]
        pre = sp["pre_regulation"].get("q90", {})
        post = sp["post_regulation"].get("q90", {})
        print(f"  {p} winter Q90: pre={pre.get('q_empirical_m3s')} "
              f"post={post.get('q_empirical_m3s')} м³/с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
