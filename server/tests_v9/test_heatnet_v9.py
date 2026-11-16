"""Тесты гидравлики и теплопотерь теплосети (heatnet_v9)."""
import math

import pytest

from hydro_api.heatnet_v9 import (
    ENGINE_ID,
    PipeSegment,
    _water_viscosity_default,
    evaluate_pipe,
    friction_factor_haaland,
    friction_factor_swamee_jain,
)


def seg(**kw) -> PipeSegment:
    base = dict(
        length_m=1000.0,
        inner_diameter_m=0.3,
        insulation_outer_diameter_m=0.5,
        insulation_conductivity_w_mk=0.04,
        mass_flow_kg_s=50.0,
        supply_temp_c=95.0,
        ground_temp_c=-5.0,
    )
    base.update(kw)
    return PipeSegment(**base)


class TestThermal:
    def test_outlet_matches_closed_form(self):
        s = seg()
        r = evaluate_pipe(s)
        r_prime = math.log(0.5 / 0.3) / (2 * math.pi * 0.04)
        decay = 50.0 * 4190.0 * r_prime
        expected = -5.0 + 100.0 * math.exp(-1000.0 / decay)
        assert r.outlet_temp_c == pytest.approx(expected, abs=1e-12)

    def test_energy_conservation(self):
        s = seg()
        r = evaluate_pipe(s)
        assert r.heat_loss_w == pytest.approx(
            50.0 * 4190.0 * (95.0 - r.outlet_temp_c), rel=1e-12)

    def test_longer_pipe_more_loss(self):
        r1 = evaluate_pipe(seg(length_m=500.0))
        r2 = evaluate_pipe(seg(length_m=2000.0))
        assert r2.heat_loss_w > r1.heat_loss_w
        assert r2.outlet_temp_c < r1.outlet_temp_c

    def test_better_insulation_less_loss(self):
        r_thin = evaluate_pipe(seg(insulation_conductivity_w_mk=0.08))
        r_thick = evaluate_pipe(seg(insulation_conductivity_w_mk=0.02))
        assert r_thick.heat_loss_w < r_thin.heat_loss_w

    def test_loss_per_metre_plausible_magadan_winter(self):
        # DN300, 2 км, подача 95°C, грунт -5°C: погонные потери порядка
        # десятков Вт/м, отпуск выше температуры грунта.
        r = evaluate_pipe(seg(length_m=2000.0))
        assert 10.0 < r.heat_loss_w_per_m < 500.0
        assert r.outlet_temp_c > -5.0
        assert r.outlet_temp_c < 95.0


class TestHydraulics:
    def test_laminar_friction_64_over_re(self):
        # малый расход => ламинарный режим
        s = seg(mass_flow_kg_s=0.05, supply_temp_c=20.0)
        r = evaluate_pipe(s)
        assert r.flow_regime == "laminar"
        assert r.friction_factor == pytest.approx(64.0 / r.reynolds, rel=1e-12)

    def test_turbulent_regime_flag(self):
        r = evaluate_pipe(seg())
        assert r.flow_regime == "turbulent"
        assert r.reynolds > 4000.0

    def test_swamee_jain_vs_haaland_close(self):
        # независимые явные аппроксимации должны согласоваться в процентах
        for re in (1e4, 1e5, 1e6, 1e7):
            for rel_rough in (1e-5, 1e-4, 1e-3):
                f_sj = friction_factor_swamee_jain(re, rel_rough)
                f_h = friction_factor_haaland(re, rel_rough)
                assert abs(f_sj - f_h) / f_sj < 0.03

    def test_pressure_drop_positive_and_scales_with_length(self):
        r1 = evaluate_pipe(seg(length_m=1000.0))
        r2 = evaluate_pipe(seg(length_m=2000.0))
        assert r1.pressure_drop_pa > 0
        assert r2.pressure_drop_pa == pytest.approx(2 * r1.pressure_drop_pa, rel=1e-9)
        assert r1.head_drop_m == pytest.approx(
            r1.pressure_drop_pa / (1000.0 * 9.80665), rel=1e-12)

    def test_viscosity_table_anchor_points(self):
        assert _water_viscosity_default(20.0) == pytest.approx(1.00e-6)
        assert _water_viscosity_default(100.0) == pytest.approx(0.29e-6)
        # монотонное убывание с температурой
        nus = [_water_viscosity_default(t) for t in range(0, 101, 10)]
        assert all(a > b for a, b in zip(nus[:-1], nus[1:]))


class TestCulture:
    def test_hold_when_uncalibrated(self):
        r = evaluate_pipe(seg())
        assert r.decision == "HOLD"
        assert r.production_ready is False
        assert r.engine == ENGINE_ID
        assert len(r.model_limitations) >= 2

    def test_calibrated_flag(self):
        r = evaluate_pipe(seg(calibrated=True))
        assert r.decision == "CALIBRATED-REVIEW"
        assert r.production_ready is False


class TestValidation:
    def test_insulation_smaller_than_pipe_rejected(self):
        with pytest.raises(ValueError, match="HEATNET_INSULATION_DIAMETER"):
            seg(insulation_outer_diameter_m=0.2)

    def test_zero_conductivity_rejected(self):
        with pytest.raises(ValueError):
            seg(insulation_conductivity_w_mk=0.0)

    def test_zero_flow_rejected(self):
        with pytest.raises(ValueError):
            seg(mass_flow_kg_s=0.0)

    def test_zero_length_rejected(self):
        with pytest.raises(ValueError):
            seg(length_m=0.0)

    def test_extra_field_rejected(self):
        with pytest.raises(ValueError):
            PipeSegment(
                length_m=100.0, inner_diameter_m=0.3,
                insulation_outer_diameter_m=0.5,
                insulation_conductivity_w_mk=0.04,
                mass_flow_kg_s=10.0, supply_temp_c=90.0,
                ground_temp_c=0.0, bogus=1)

    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            seg(length_m=math.nan)
