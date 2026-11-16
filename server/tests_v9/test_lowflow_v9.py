"""Тесты lowflow_v9 (V9.6): меженные минимумы, Q90/Q95, бутстреп-ДИ."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hydro_api import lowflow_v9 as lf

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts_v9" / "rarcticnet_lowflow_v9.json"


def _series(years, value_fn):
    return {(y, m): value_fn(y, m) for y in years for m in range(1, 13)}


class TestAnnualMinMonthly:
    def test_complete_years_only(self):
        # 2000: 12 месяцев; 2001: только 11 -> исключён.
        s = _series(range(2000, 2002), lambda y, m: float(m))
        del s[(2001, 12)]
        out = lf.annual_min_monthly(s)
        assert out == {2000: 1.0}

    def test_season_filter(self):
        s = _series(range(2000, 2001), lambda y, m: float(m))
        out = lf.annual_min_monthly(s, months=(12, 1, 2, 3))
        assert out == {2000: 1.0}
        # Неполный зимний сезон исключается.
        del s[(2000, 3)]
        assert lf.annual_min_monthly(s, months=(12, 1, 2, 3)) == {}

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="LOWFLOW_EMPTY_MONTHS"):
            lf.annual_min_monthly({}, months=())
        with pytest.raises(ArithmeticError, match="LOWFLOW_MONTH_RANGE"):
            lf.annual_min_monthly({}, months=(13,))
        with pytest.raises(ArithmeticError, match="LOWFLOW_BAD_VALUE"):
            lf.annual_min_monthly({(2000, 1): -1.0})


class TestQuantileStats:
    def test_hand_computed_empirical(self):
        # 10 лет, значения 1..10; Q90 обеспеченности => квантиль 0,10.
        # Линейная интерполяция: pos = 0,1*(10-1) = 0,9 -> 1*0,1 + 2*0,9 = 1,9.
        vals = {2000 + i: float(i + 1) for i in range(10)}
        res = lf.quantile_stats(vals, target="t", exceedance_pct=90.0)
        assert res.n_years == 10
        assert res.q_empirical_m3s == pytest.approx(1.9)
        assert res.small_sample is True
        assert res.lognormal_applicable is True
        assert res.q_empirical_ci95_lo_m3s <= res.q_empirical_m3s
        assert res.q_empirical_ci95_hi_m3s >= res.q_empirical_m3s
        assert res.production_ready is False

    def test_bootstrap_determinism(self):
        vals = {2000 + i: float(i + 1) for i in range(10)}
        a = lf.quantile_stats(vals, target="t", exceedance_pct=95.0)
        b = lf.quantile_stats(vals, target="t", exceedance_pct=95.0)
        assert a.q_empirical_ci95_lo_m3s == b.q_empirical_ci95_lo_m3s
        assert a.q_empirical_ci95_hi_m3s == b.q_empirical_ci95_hi_m3s

    def test_lognormal_inapplicable_with_zero(self):
        vals = {2000 + i: float(i) for i in range(10)}  # нулевой расход
        res = lf.quantile_stats(vals, target="t", exceedance_pct=90.0)
        assert res.lognormal_applicable is False
        assert res.q_lognormal_m3s is None

    def test_year_window(self):
        vals = {y: 1.0 + (y - 1950) for y in range(1950, 1990)}
        res = lf.quantile_stats(vals, target="t", exceedance_pct=90.0,
                                year_from=1970, year_to=1979)
        assert (res.year_from, res.year_to, res.n_years) == (1970, 1979, 10)

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="LOWFLOW_INSUFFICIENT_YEARS"):
            lf.quantile_stats({2000: 1.0}, target="t", exceedance_pct=90.0)
        vals = {2000 + i: float(i + 1) for i in range(10)}
        with pytest.raises(ArithmeticError, match="LOWFLOW_NO_TARGET"):
            lf.quantile_stats(vals, target="", exceedance_pct=90.0)
        with pytest.raises(ArithmeticError, match="LOWFLOW_EXCEEDANCE_RANGE"):
            lf.quantile_stats(vals, target="t", exceedance_pct=100.0)
        bad = dict(vals)
        bad[2000] = float("nan")
        with pytest.raises(ArithmeticError, match="LOWFLOW_BAD_VALUE"):
            lf.quantile_stats(bad, target="t", exceedance_pct=90.0)


class TestArtifact:
    def test_receipt_self_consistent(self):
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        receipt = art.pop("artifact_sha256")
        blob = json.dumps(art, ensure_ascii=False, indent=2, sort_keys=True).encode()
        assert hashlib.sha256(blob).hexdigest() == receipt

    def test_regulation_split_direction(self):
        # Зимняя Q90 ниже Колымской ГЭС растёт после 1982 г. (регулирование).
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        rep = art["report"]
        for st in ("5858", "5951"):
            split = rep["station_results"][st]["regulation_split"]["winter_min_dec_mar"]
            pre = split["pre_regulation"]["q90"]["q_empirical_m3s"]
            post = split["post_regulation"]["q90"]["q_empirical_m3s"]
            assert post > pre
        # Отрицательный тренд зимних минимумов на 5884 (согласовано с V9.5).
        tr = rep["station_results"]["5884"]["winter_min_dec_mar"]["trend"]
        assert tr["slope_pct_per_year"] < 0
        assert tr["mk_significant_5pct"] is True

    def test_production_flags(self):
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for st, d in art["report"]["station_results"].items():
            for target in ("annual_min_monthly", "winter_min_dec_mar"):
                for q in d[target]["quantiles"].values():
                    assert q["production_ready"] is False
