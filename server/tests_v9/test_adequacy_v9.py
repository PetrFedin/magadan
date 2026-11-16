"""Тесты генерационной адекватности (adequacy_v9)."""
import math

import pytest

from hydro_api.adequacy_v9 import (
    ENGINE_ID,
    GeneratingUnit,
    build_copt,
    evaluate_adequacy,
)


def unit(name, cap, for_, **kw):
    return GeneratingUnit(name=name, capacity_mw=cap, forced_outage_rate=for_, **kw)


class TestCopt:
    def test_single_unit_two_states(self):
        t = build_copt([unit("G1", 100.0, 0.05)])
        assert t == pytest.approx({100.0: 0.95, 0.0: 0.05})

    def test_two_units_convolution(self):
        t = build_copt([unit("G1", 50.0, 0.1), unit("G2", 50.0, 0.1)])
        assert t[100.0] == pytest.approx(0.81)
        assert t[50.0] == pytest.approx(0.18)
        assert t[0.0] == pytest.approx(0.01)

    def test_four_identical_units_match_binomial(self):
        # 4 агрегата по 25 МВт, FOR=0.2: P(k работают) = C(4,k) 0.8^k 0.2^(4-k)
        t = build_copt([unit(f"G{i}", 25.0, 0.2) for i in range(4)])
        for k in range(5):
            expected = math.comb(4, k) * 0.8 ** k * 0.2 ** (4 - k)
            assert t[25.0 * k] == pytest.approx(expected, abs=1e-12)

    def test_empty_units_rejected(self):
        with pytest.raises(ValueError, match="ADEQUACY_NO_UNITS"):
            build_copt([])

    def test_probabilities_sum_to_one(self):
        t = build_copt([unit("A", 30, 0.03), unit("B", 70, 0.07), unit("C", 120, 0.11)])
        assert sum(t.values()) == pytest.approx(1.0, abs=1e-12)


class TestEvaluate:
    def test_single_unit_constant_load(self):
        # 100 МВт, FOR=0.05, нагрузка 80 МВт 24 ч:
        # LOLE = 0.05*24 = 1.2 ч; EENS = 0.05*80*24 = 96 МВт·ч
        r = evaluate_adequacy([unit("G1", 100.0, 0.05)], [80.0] * 24)
        assert r.lole_hours == pytest.approx(1.2)
        assert r.eens_mwh == pytest.approx(96.0)
        assert r.loss_of_load_probability_peak == pytest.approx(0.05)

    def test_two_units_partial_deficit(self):
        # 2x50 МВт, FOR=0.1, нагрузка 60 МВт, 1 ч:
        # P(50)=0.18 -> дефицит 10; P(0)=0.01 -> дефицит 60
        # EENS = 0.18*10 + 0.01*60 = 2.4; LOLE = 0.19 ч
        r = evaluate_adequacy(
            [unit("G1", 50.0, 0.1), unit("G2", 50.0, 0.1)], [60.0])
        assert r.lole_hours == pytest.approx(0.19)
        assert r.eens_mwh == pytest.approx(2.4)

    def test_zero_load_zero_indices(self):
        r = evaluate_adequacy([unit("G1", 100.0, 0.5)], [0.0] * 10)
        assert r.lole_hours == 0.0
        assert r.eens_mwh == 0.0

    def test_time_varying_load(self):
        # 2 ч по 80 МВт + 2 ч по 40 МВт при 1 агрегате 100 МВт FOR=0.1
        # LOLE = 0.1*4 = 0.4; EENS = 0.1*(80*2 + 40*2) = 24
        r = evaluate_adequacy([unit("G1", 100.0, 0.1)], [80, 80, 40, 40])
        assert r.lole_hours == pytest.approx(0.4)
        assert r.eens_mwh == pytest.approx(24.0)

    def test_n_minus_1_secure(self):
        units = [unit(f"G{i}", 100.0, 0.02) for i in range(3)]
        r = evaluate_adequacy(units, [180.0])
        assert r.n_minus_1_secure is True
        assert r.n_minus_1_margin_mw == pytest.approx(20.0)

    def test_n_minus_1_insecure(self):
        units = [unit(f"G{i}", 100.0, 0.02) for i in range(3)]
        r = evaluate_adequacy(units, [250.0])
        assert r.n_minus_1_secure is False
        assert r.n_minus_1_margin_mw == pytest.approx(-50.0)

    def test_assumption_flag_gives_hold(self):
        r = evaluate_adequacy([unit("G1", 100.0, 0.05)], [50.0])
        assert r.decision == "HOLD"
        assert r.for_assumption is True
        assert r.production_ready is False
        assert r.engine == ENGINE_ID

    def test_measured_for_allows_review(self):
        r = evaluate_adequacy(
            [unit("G1", 100.0, 0.05, for_is_assumption=False)], [50.0])
        assert r.decision == "REVIEW"

    def test_magadan_scale_smoke(self):
        # Якорь энергосистемы: ГЭС 1470 + ТЭС 320, пик 460 МВт (СО ЕЭС)
        units = ([unit(f"H{i}", 180.0, 0.02) for i in range(5)]
                 + [unit(f"U{i}", 142.5, 0.02) for i in range(4)]
                 + [unit(f"T{i}", 80.0, 0.05) for i in range(4)])
        r = evaluate_adequacy(units, [460.0] * 8760)
        assert r.installed_capacity_mw == pytest.approx(1790.0)
        assert r.n_minus_1_secure is True
        assert r.lole_hours >= 0.0


class TestValidation:
    def test_for_one_rejected(self):
        with pytest.raises(ValueError):
            unit("G1", 100.0, 1.0)

    def test_negative_capacity_rejected(self):
        with pytest.raises(ValueError):
            unit("G1", -10.0, 0.05)

    def test_negative_load_rejected(self):
        with pytest.raises(ValueError, match="ADEQUACY_NEGATIVE_LOAD"):
            evaluate_adequacy([unit("G1", 100.0, 0.05)], [-1.0])

    def test_empty_load_rejected(self):
        with pytest.raises(ValueError, match="ADEQUACY_NO_LOAD"):
            evaluate_adequacy([unit("G1", 100.0, 0.05)], [])

    def test_zero_step_rejected(self):
        with pytest.raises(ValueError, match="ADEQUACY_STEP_HOURS"):
            evaluate_adequacy([unit("G1", 100.0, 0.05)], [50.0], step_hours=0.0)

    def test_extra_field_rejected(self):
        with pytest.raises(ValueError):
            GeneratingUnit(name="G1", capacity_mw=100.0,
                           forced_outage_rate=0.05, bogus=1)

    def test_nan_for_rejected(self):
        with pytest.raises(ValueError):
            unit("G1", 100.0, math.nan)
