"""Тесты regional_trend_v9 (V9.5): Манн—Кендалл, сезонные агрегаты, тренды."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hydro_api import regional_trend_v9 as rt
from hydro_api import trend_adaptive_v9 as ta

REPO_TSV = (Path(__file__).resolve().parents[2]
            / "data" / "r-arcticnet" / "kolyma_basin_multistation_v4.tsv")


class TestMannKendall:
    def test_monotone_increasing_significant(self):
        res = rt.mann_kendall([float(i) for i in range(1, 26)])
        assert res.s == 25 * 24 // 2
        assert res.z > 0
        assert res.p_two_sided < 0.001
        assert res.significant_5pct is True

    def test_alternating_not_significant(self):
        vals = [1.0 if i % 2 == 0 else 0.0 for i in range(24)]
        res = rt.mann_kendall(vals)
        assert abs(res.z) < 1.0
        assert res.significant_5pct is False
        assert res.tie_groups == 2  # две группы связок (нули и единицы)

    def test_tie_correction_reduces_variance(self):
        no_ties = [float(i) + (0.5 if i % 3 else 0.0) for i in range(20)]
        with_ties = [float(i // 2) for i in range(20)]
        res_nt = rt.mann_kendall(no_ties)
        res_wt = rt.mann_kendall(with_ties)
        n = 20
        plain = n * (n - 1) * (2 * n + 5) / 18.0
        assert res_nt.var_s == pytest.approx(plain)
        assert res_wt.var_s < plain

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="MK_INSUFFICIENT_YEARS"):
            rt.mann_kendall([1.0] * 19)
        with pytest.raises(ArithmeticError, match="MK_ZERO_VARIANCE"):
            rt.mann_kendall([7.0] * 25)
        with pytest.raises(ArithmeticError, match="MK_NONFINITE_VALUE"):
            rt.mann_kendall([1.0] * 24 + [float("nan")])


class TestSeasonalMeans:
    def _series(self):
        # год 2000: все 12 месяцев = 10; год 2001: май (не зимний) пропущен
        s = {(2000, m): 10.0 for m in range(1, 13)}
        s.update({(2001, m): 20.0 for m in range(1, 13) if m != 5})
        return s

    def test_complete_years_only(self):
        s = self._series()
        annual = rt.seasonal_annual_means(s, tuple(range(1, 13)))
        assert annual == {2000: 10.0}
        winter = rt.seasonal_annual_means(s, rt.WINTER_MONTHS)
        assert winter == {2000: 10.0, 2001: 20.0}  # май не в зимнем наборе

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="SEASON_EMPTY_MONTHS"):
            rt.seasonal_annual_means(self._series(), ())
        with pytest.raises(ArithmeticError, match="SEASON_MONTH_RANGE"):
            rt.seasonal_annual_means(self._series(), (13,))


class TestTrendStats:
    def test_recovers_log_trend(self):
        # Q(y) = 100 * exp(0.02 * (y - 1960)) — точный тренд 2 %/год
        vals = {y: 100.0 * math.exp(0.02 * (y - 1960)) for y in range(1960, 1990)}
        res = rt.trend_stats(vals, target="annual")
        assert res.slope_log_per_year == pytest.approx(0.02, abs=1e-9)
        assert res.slope_pct_per_year == pytest.approx(
            100 * (math.exp(0.02) - 1), rel=1e-9)
        assert res.mk_significant_5pct is True
        assert res.year_from == 1960 and res.year_to == 1989
        assert res.n_years == 30
        assert res.production_ready is False

    def test_flat_series_zero_trend(self):
        vals = {y: 50.0 + (y % 2) * 1e-6 for y in range(1950, 1980)}
        res = rt.trend_stats(vals, target="winter_dec_mar")
        assert abs(res.slope_pct_per_year) < 0.01

    def test_period_filter(self):
        vals = {y: 10.0 * (1.01 ** (y - 1930)) for y in range(1930, 2000)}
        res = rt.trend_stats(vals, target="annual_pre1982", year_to=1981)
        assert res.year_to == 1981
        assert res.slope_log_per_year == pytest.approx(math.log(1.01), abs=1e-9)

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="TREND_STATS_INSUFFICIENT"):
            rt.trend_stats({y: 10.0 for y in range(1990, 2005)}, target="annual")
        with pytest.raises(ArithmeticError, match="TREND_STATS_MIN_YEARS"):
            rt.trend_stats({y: 10.0 for y in range(1960, 1990)},
                           target="annual", min_years=5)

    def test_theil_sen_public_wrapper(self):
        x = [float(i) for i in range(10)]
        y = [2.0 * i + 5.0 for i in range(10)]
        assert ta.theil_sen_ci(x, y) == ta._theil_sen_ci(x, y)


class TestRepoMultistationTSV:
    def test_parses_and_covers_kolyma_stations(self):
        assert REPO_TSV.exists(), "подмножество R-ArcticNET должно быть в репо"
        import csv
        with REPO_TSV.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        stations = {r["PointID"] for r in rows}
        assert len(stations) == 11
        assert "5858" in stations and "5951" in stations
        # у каждого створа >= 35 полных лет (критерий отбора)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        complete = {}
        for r in rows:
            ok = all((r[m] or "").strip() and float(r[m]) > 0 for m in months)
            complete[r["PointID"]] = complete.get(r["PointID"], 0) + (1 if ok else 0)
        assert all(c >= 35 for c in complete.values())

    def test_deterministic_engine_id(self):
        a = rt.mann_kendall([float((i * 7) % 13) + i for i in range(30)])
        b = rt.mann_kendall([float((i * 7) % 13) + i for i in range(30)])
        assert a.model_dump_json() == b.model_dump_json()
        assert a.engine == "V9-REGIONAL-TREND-ANALYSIS-1"


class TestRegionalArtifactIntegrity:
    def test_artifact_schema_and_receipt(self):
        art_path = (Path(__file__).resolve().parents[2]
                    / "artifacts_v9" / "rarcticnet_regional_trend_v9.json")
        assert art_path.exists()
        art = json.loads(art_path.read_text(encoding="utf-8"))
        import hashlib
        receipt = art.pop("artifact_sha256")
        blob = json.dumps(art, ensure_ascii=False, indent=2, sort_keys=True).encode()
        assert hashlib.sha256(blob).hexdigest() == receipt
        rep = art["report"]
        assert rep["n_stations"] == 11
        assert rep["regulation_onset_year"] == 1982
        groups = rep["regulation_group_summary"]
        assert groups["regulated_below_dam"]["n_stations"] == 2
        assert groups["not_below_dam"]["n_stations"] == 9
        # климатический сигнал: большинство нерегулируемых створов с
        # положительным зимним трендом (зафиксированный результат прогона)
        assert groups["not_below_dam"]["n_winter_positive"] >= 6
