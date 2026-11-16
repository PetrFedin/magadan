"""Тесты модуля вынужденных простоев FOR/EFOR/EFORd (V9.4).

Опорные примеры — опубликованные расчёты:
  * FOR: FOH=200, SH=6000 => 3,23% (компиляция Generation Consulting
    Services по IEEE 762);
  * EFOR-вариант: FOH=48, EFDH=20 (дерейтинг 200 ч x 50/500 МВт), SH=6000
    => (48+20)/(48+6000) = 1,1243% (отраслевой разбор правил GADS, 2026 DRI);
  * класс GADS 2008-2012 hydro: FOR 5,79%, EFOR 5,99%, EFORd 5,43%
    (data/reference/hydro_for_open_stats.json).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hydro_api.forced_outage_v9 import (
    UnitOutageHours,
    binomial_station_availability,
    efor,
    eford,
    expected_forced_energy_loss_mwh,
    f_factor_full,
    for_rate,
    pool_class_average,
    two_state_capacity,
    unit_report,
)

REF_JSON = Path(__file__).resolve().parents[2] / "data" / "reference" / "hydro_for_open_stats.json"


class TestRates:
    def test_for_published_example(self):
        h = UnitOutageHours(foh=200.0, sh=6000.0, rsh=0.0, efdh=0.0)
        assert for_rate(h) * 100 == pytest.approx(3.23, abs=0.01)

    def test_for_with_sync_and_pumping(self):
        h = UnitOutageHours(foh=100.0, sh=5000.0, rsh=0.0, efdh=0.0, sync_hours=200.0, pumping_hours=100.0)
        assert for_rate(h) == pytest.approx(100.0 / 5400.0)

    def test_efor_published_example(self):
        h = UnitOutageHours(foh=48.0, sh=6000.0, rsh=0.0, efdh=20.0)
        assert efor(h) * 100 == pytest.approx(1.12, abs=0.01)

    def test_zero_denominator_fails(self):
        h = UnitOutageHours(foh=0.0, sh=0.0, rsh=0.0, efdh=0.0)
        with pytest.raises(ArithmeticError, match="FOR_ZERO_DENOMINATOR"):
            for_rate(h)


class TestEFORd:
    def test_f_factor_formula(self):
        # r=10, D=100, T=50: f = (0.1+0.02)/(0.1+0.02+0.01) = 0.9231
        h = UnitOutageHours(foh=20.0, sh=2000.0, rsh=1000.0, efdh=0.0,
                            n_forced_outages=2, n_actual_starts=20, n_attempted_starts=20)
        assert f_factor_full(h) == pytest.approx((0.1 + 0.02) / (0.13), rel=1e-12)

    def test_eford_with_factors(self):
        h = UnitOutageHours(foh=48.0, sh=6000.0, rsh=0.0, efdh=20.0)
        val = eford(h, 0.9, 0.8)
        assert val == pytest.approx((0.9 * 48 + 0.8 * 20) / (6000 + 0.9 * 48), rel=1e-12)

    def test_eford_factor_range_guard(self):
        h = UnitOutageHours(foh=10.0, sh=1000.0, rsh=0.0, efdh=0.0)
        with pytest.raises(ArithmeticError, match="EFORD_FACTOR_RANGE"):
            eford(h, 1.5, 0.5)

    def test_f_factor_counts_guard(self):
        h = UnitOutageHours(foh=10.0, sh=1000.0, rsh=0.0, efdh=0.0, n_forced_outages=0)
        with pytest.raises(ArithmeticError, match="F_FACTOR_COUNTS"):
            f_factor_full(h)


class TestPooling:
    def test_pjm_immature_unit_shrinkage(self):
        # n=0 -> класс; n=5 -> история; n=2.5 -> середина
        assert pool_class_average(0.10, 0, 0.0543) == pytest.approx(0.0543)
        assert pool_class_average(0.10, 5, 0.0543) == pytest.approx(0.10)
        assert pool_class_average(0.10, 2.5, 0.0543) == pytest.approx((0.10 + 0.0543) / 2)
        assert pool_class_average(0.10, 100, 0.0543) == pytest.approx(0.10)  # cap на зрелости

    def test_pool_guards(self):
        with pytest.raises(ArithmeticError, match="POOL_RATE_RANGE"):
            pool_class_average(1.5, 3, 0.05)
        with pytest.raises(ArithmeticError, match="POOL_YEARS_NEGATIVE"):
            pool_class_average(0.05, -1, 0.05)


class TestTwoStateAndBinomial:
    def test_two_state_pjm(self):
        mu, var = two_state_capacity(0.0543, 300.0)  # EFORd класса GADS hydro, агрегат 300 МВт
        assert mu == pytest.approx(0.9457 * 300.0)
        assert var == pytest.approx(0.9457 * 0.0543 * 300.0 ** 2)

    def test_binomial_ru_practice(self):
        # 4 агрегата, p=0,999 (норматив ВГЭК): P(все 4) = 0,999^4
        p_all = binomial_station_availability(4, 0.999, 4)
        assert p_all == pytest.approx(0.999 ** 4, rel=1e-9)
        # P(>=3 из 4) = 4*0,999^3*0,001 + 0,999^4
        p3 = binomial_station_availability(4, 0.999, 3)
        assert p3 == pytest.approx(4 * 0.999 ** 3 * 0.001 + 0.999 ** 4, rel=1e-9)
        # края: p=1 -> 1; p=0 -> 0
        assert binomial_station_availability(3, 1.0, 3) == 1.0
        assert binomial_station_availability(3, 0.0, 1) == 0.0

    def test_binomial_guards(self):
        with pytest.raises(ArithmeticError, match="BINOMIAL_CONFIG"):
            binomial_station_availability(3, 0.99, 0)
        with pytest.raises(ArithmeticError, match="BINOMIAL_P_RANGE"):
            binomial_station_availability(3, 1.01, 1)

    def test_expected_energy_loss(self):
        # 300 МВт x 5226,12 ч (SH класса GADS hydro) x EFORd 5,43%
        eens = expected_forced_energy_loss_mwh(0.0543, 300.0, 5226.12)
        assert eens == pytest.approx(0.0543 * 300.0 * 5226.12)


class TestUnitReportAndReference:
    def test_unit_report_consistency(self):
        h = UnitOutageHours(foh=48.0, sh=6000.0, rsh=1200.0, efdh=20.0,
                            n_forced_outages=3, n_actual_starts=24, n_attempted_starts=30)
        rep = unit_report(h, class_average_eford=0.0543, n_full_years=1.0)
        assert rep.for_rate <= rep.efor
        assert rep.production_ready is False
        assert 0.0 <= rep.eford_pooled <= 1.0
        # 1 год истории: pooled ближе к классу, чем к собственной оценке
        assert abs(rep.eford_pooled - 0.0543) < abs(rep.eford_pooled - rep.eford)

    def test_reference_json_integrity(self):
        data = json.loads(REF_JSON.read_text(encoding="utf-8"))
        assert data["data_class"] == "OPEN-PUBLISHED-REFERENCE"
        for entry in data["reference_stats"]:
            assert entry["source_ref"], entry["id"]
        gads = next(e for e in data["reference_stats"] if e["id"] == "gads-2008-2012-hydro")
        assert 0.1 <= gads["FOR_pct"] <= 10.0      # разумные границы класса
        assert gads["EFOR_pct"] >= gads["FOR_pct"]  # дерейтинги только добавляют
        # перекрёстная согласованность: EFORd <= EFOR (спрос-взвешивание не увеличивает)
        assert gads["EFORd_pct"] <= gads["EFOR_pct"]
