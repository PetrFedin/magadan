"""Тесты degree-day модели снеготаяния (snowmelt_v9)."""
import math

import pytest

from hydro_api.snowmelt_v9 import (
    ENGINE_ID,
    SnowmeltParams,
    run_snowmelt,
    snow_fraction,
)


def make_params(**kw) -> SnowmeltParams:
    kw.setdefault("ddf_mm_per_deg_day", 3.0)
    return SnowmeltParams(**kw)


class TestSnowFraction:
    def test_cold_all_snow(self):
        assert snow_fraction(-10.0, 0.0, 1.0) == 1.0

    def test_warm_all_rain(self):
        assert snow_fraction(10.0, 0.0, 1.0) == 0.0

    def test_band_center_half(self):
        assert snow_fraction(0.0, 0.0, 1.0) == pytest.approx(0.5)

    def test_band_edges(self):
        assert snow_fraction(-1.0, 0.0, 1.0) == pytest.approx(1.0)
        assert snow_fraction(1.0, 0.0, 1.0) == pytest.approx(0.0)


class TestRunSnowmelt:
    def test_permanent_frost_accumulates_everything(self):
        p = make_params()
        r = run_snowmelt([-15.0] * 30, [2.0] * 30, p)
        assert r.swe_mm[-1] == pytest.approx(60.0)
        assert r.total_release_mm == pytest.approx(0.0)
        assert r.melt_mm[-1] == 0.0

    def test_warm_no_pack_immediate_rain_release(self):
        p = make_params()
        r = run_snowmelt([10.0] * 10, [5.0] * 10, p)
        # без снежного покрова дождь проходит насквозь (hold = 0.1*SWE = 0)
        assert r.swe_mm[-1] == 0.0
        assert r.total_release_mm == pytest.approx(50.0)

    def test_melt_limited_by_swe(self):
        p = make_params()
        # 5 мм снега в покрове, жара 10°C => потенциал 30 мм, реально 5
        r = run_snowmelt([10.0], [0.0], p, initial_swe_mm=5.0)
        assert r.melt_mm[0] == pytest.approx(5.0)

    def test_hand_computed_three_days(self):
        # день1: T=-5, P=10 (всё в снег). день2: T=+4, P=0: таяние 12 мм,
        # покров SWE=10 => melt=10, liquid=10, hold=0 => release=10.
        # день3: T=-5, P=0: жидкости нет, ничего не происходит.
        p = make_params()
        r = run_snowmelt([-5.0, 4.0, -5.0], [10.0, 0.0, 0.0], p)
        assert r.swe_mm[0] == pytest.approx(10.0)
        assert r.swe_mm[1] == pytest.approx(0.0)
        assert r.release_mm[1] == pytest.approx(10.0)
        assert r.total_release_mm == pytest.approx(10.0)

    def test_water_balance_conserved(self):
        p = make_params()
        temps = [-20, -15, -5, 0, 2, 6, 9, 12, 8, 3, -2, -8]
        precs = [4, 3, 5, 6, 2, 0, 1, 0, 2, 5, 7, 6]
        r = run_snowmelt(temps, precs, p)
        assert abs(r.water_balance_residual_mm) < 1e-9
        assert r.total_release_mm + r.swe_mm[-1] + r.liquid_mm[-1] == pytest.approx(
            sum(precs))

    def test_refreeze_returns_liquid_to_pack(self):
        # liquid в покрове при остывании замерзает обратно.
        p2 = make_params(refreeze_coeff=1.0)
        r = run_snowmelt([2.0, -10.0], [0.0, 0.0], p2, initial_swe_mm=10.0)
        # день1: melt=min(6,10)=6; SWE=4; liquid=6; hold=0.4 => release=5.6; liquid=0.4
        # день2: T=-10: cold=1.0*3.0*10=30 => frozen=min(0.4,30)=0.4; SWE=4.4
        assert r.swe_mm[0] == pytest.approx(4.0)
        assert r.release_mm[0] == pytest.approx(5.6)
        assert r.swe_mm[1] == pytest.approx(4.4)

    def test_uncalibrated_params_give_hold(self):
        r = run_snowmelt([5.0], [1.0], make_params())
        assert r.decision == "HOLD"
        assert r.production_ready is False
        assert r.engine == ENGINE_ID

    def test_calibrated_flag_propagates(self):
        p = make_params(calibrated=True, params_source="OPEN-PUBLISHED-KOLYMA-MAGADAN-REFERENCE-1")
        r = run_snowmelt([5.0], [1.0], p)
        assert r.decision == "CALIBRATED-REVIEW"
        assert r.production_ready is False  # натурной верификации всё равно нет


class TestValidation:
    def test_negative_precip_rejected(self):
        with pytest.raises(ValueError, match="SNOWMELT_NEGATIVE_PRECIP"):
            run_snowmelt([0.0, 1.0], [1.0, -0.5], make_params())

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError, match="SNOWMELT_LENGTH_MISMATCH"):
            run_snowmelt([0.0], [1.0, 2.0], make_params())

    def test_empty_input_rejected(self):
        with pytest.raises(ValueError, match="SNOWMELT_EMPTY_INPUT"):
            run_snowmelt([], [], make_params())

    def test_zero_ddf_rejected(self):
        with pytest.raises(ValueError):
            make_params(ddf_mm_per_deg_day=0.0)

    def test_extra_field_rejected(self):
        with pytest.raises(ValueError):
            SnowmeltParams(ddf_mm_per_deg_day=3.0, bogus=1)

    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            make_params(ddf_mm_per_deg_day=math.nan)
