"""Тесты seasonal_adequacy_v9 (V9.6): зимний дерейтинг ГЭС до гарантированной мощности."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hydro_api import seasonal_adequacy_v9 as se
from hydro_api.system_adequacy_v9 import UnitGroupSpec

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts_v9" / "magadan_seasonal_adequacy_v9.json"


def _group(name="KolymskayaHPP", n=5, cap=180.0, eford=0.0543):
    return UnitGroupSpec(
        name_prefix=name, n_units=n, unit_capacity_mw=cap, eford_d=eford,
        source_ref="TEST-SRC", eford_source_ref="TEST-EFORD")


class TestDerateGroup:
    def test_kolymskaya_hand_value(self):
        # 900 -> 224 МВт: агрегат 180 * 224/900 = 44,8 МВт.
        g = se.derate_group(_group(), 224.0)
        assert g.unit_capacity_mw == pytest.approx(44.8)
        assert g.n_units == 5
        assert g.name_prefix.endswith("-winter")
        assert g.n_units * g.unit_capacity_mw == pytest.approx(224.0)
        # EFORd и источники сохраняются.
        assert g.eford_d == pytest.approx(0.0543)
        assert g.source_ref == "TEST-SRC"

    def test_ust_srednekan_hand_value(self):
        # 570 -> 132 МВт: агрегат 142,5 * 132/570 = 33,0 МВт.
        g = se.derate_group(_group("UstSrednekanHPP", n=4, cap=142.5), 132.0)
        assert g.unit_capacity_mw == pytest.approx(33.0)

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="SEASONAL_DERATE_RANGE"):
            se.derate_group(_group(), 0.0)
        with pytest.raises(ArithmeticError, match="SEASONAL_DERATE_ABOVE_INSTALLED"):
            se.derate_group(_group(), 901.0)


class TestEvaluateSeason:
    def test_winter_worse_than_annual(self):
        hydro = [_group()]
        winter = [se.derate_group(hydro[0], 224.0)]
        peak = 460.0
        a = se.evaluate_season("a", "annual_full_capacity", hydro, peak)
        w = se.evaluate_season("w", "winter_guaranteed_capacity", winter, peak)
        assert w.hydro_available_mw == pytest.approx(224.0)
        assert w.lole_hours_per_year > a.lole_hours_per_year
        assert w.decision == "HOLD"
        assert w.production_ready is False

    def test_unknown_season(self):
        with pytest.raises(ArithmeticError, match="SEASONAL_UNKNOWN_SEASON"):
            se.evaluate_season("t", "summer", [_group()], 100.0)


class TestArtifact:
    def test_receipt_self_consistent(self):
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        receipt = art.pop("artifact_sha256")
        blob = json.dumps(art, ensure_ascii=False, indent=2, sort_keys=True).encode()
        assert hashlib.sha256(blob).hexdigest() == receipt

    def test_scenario_grid_and_n_minus_1(self):
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        rep = art["report"]
        assert rep["n_scenarios"] == 36
        assert rep["hydro_installed_mw"] == pytest.approx(1470.0)
        assert rep["hydro_guaranteed_mw"] == pytest.approx(356.0)
        winter = [s for s in rep["scenarios"]
                  if s["season"] == "winter_guaranteed_capacity"]
        assert len(winter) == 18
        # Ручной N-1: 676 - 320 - 460 = -104 МВт (1x320, пик 460) -> insecure;
        # 676 - 80 - 574 = +22 МВт (4x80, пик 574) -> secure.
        by_name = {s["scenario"]: s for s in winter}
        s1 = by_name["winter_guaranteed_capacity_peak460MW_for5.43pct_thermal_1x320MW"]
        assert s1["n_minus_1_secure"] is False
        assert s1["n_minus_1_margin_mw"] == pytest.approx(-104.0)
        s4 = by_name["winter_guaranteed_capacity_peak574MW_for5.43pct_thermal_4x80MW"]
        assert s4["n_minus_1_secure"] is True
        assert s4["n_minus_1_margin_mw"] == pytest.approx(22.0)
        # Годовой сезон: N-1 выполняется везде (как в V9.5).
        assert rep["season_summary"]["annual_full_capacity"]["n_minus_1_insecure_count"] == 0
        assert rep["season_summary"]["winter_guaranteed_capacity"]["n_minus_1_insecure_count"] == 9
        # Все сценарии остаются HOLD (натурной статистики отказов нет).
        assert all(s["decision"] == "HOLD" for s in rep["scenarios"])
        assert all(s["production_ready"] is False for s in rep["scenarios"])

    def test_winter_lole_exceeds_annual_everywhere(self):
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        rep = art["report"]
        by_season = {}
        for s in rep["scenarios"]:
            key = s["scenario"].split("_peak", 1)[1]
            by_season.setdefault(key, {})[s["season"]] = s
        for pair in by_season.values():
            assert (pair["winter_guaranteed_capacity"]["lole_hours_per_year"]
                    > pair["annual_full_capacity"]["lole_hours_per_year"])
