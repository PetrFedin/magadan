"""Тесты system_adequacy_v9 (V9.5): мост EFORd -> LOLE/EENS/N-1."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydro_api import system_adequacy_v9 as sa

REF_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"


def _group(name="G", n=2, cap=100.0, eford=0.1):
    return sa.UnitGroupSpec(
        name_prefix=name, n_units=n, unit_capacity_mw=cap, eford_d=eford,
        source_ref="TEST-SRC", eford_source_ref="TEST-EFORD")


class TestBuildUnits:
    def test_group_expansion(self):
        units = sa.build_units(_group(n=3, cap=50.0, eford=0.05))
        assert len(units) == 3
        assert all(u.capacity_mw == 50.0 for u in units)
        assert all(u.forced_outage_rate == 0.05 for u in units)
        assert all(u.for_is_assumption is True for u in units)
        assert [u.name for u in units] == ["G-1", "G-2", "G-3"]

    def test_total_capacity_preserved(self):
        units = sa.build_units(_group(n=5, cap=180.0))
        assert sum(u.capacity_mw for u in units) == pytest.approx(900.0)


class TestEvaluateSystem:
    def test_hand_computed_two_unit(self):
        # 2 агрегата по 100 МВт, FOR=0,1; пик 150 МВт; шаг 1 ч.
        # COPT: P(200)=0,81; P(100)=0,18; P(0)=0,01.
        # LOLP(150) = 0,19; EENS = (150-100)*0,18 + 150*0,01 = 10,5 МВт·ч.
        res = sa.evaluate_system("t", [_group()], 150.0, hours_per_year=1.0)
        assert res.lolp_at_peak == pytest.approx(0.19)
        assert res.lole_hours_per_year == pytest.approx(0.19)
        assert res.eens_mwh_per_year == pytest.approx(10.5)
        assert res.n_minus_1_secure is False
        assert res.n_minus_1_margin_mw == pytest.approx(200.0 - 100.0 - 150.0)
        assert res.decision == "HOLD"  # for_is_assumption=True
        assert res.production_ready is False

    def test_secure_system(self):
        res = sa.evaluate_system("big", [_group(n=9, cap=200.0, eford=0.05)],
                                 460.0)
        assert res.n_minus_1_secure is True
        assert res.n_minus_1_margin_mw == pytest.approx(1800.0 - 200.0 - 460.0)
        assert res.lolp_at_peak < 1e-6

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="SYSADQ_NO_SCENARIO_NAME"):
            sa.evaluate_system("", [_group()], 100.0)
        with pytest.raises(ArithmeticError, match="SYSADQ_PEAK_RANGE"):
            sa.evaluate_system("t", [_group()], 0.0)
        with pytest.raises(ArithmeticError, match="SYSADQ_HOURS_RANGE"):
            sa.evaluate_system("t", [_group()], 100.0, hours_per_year=0.0)
        with pytest.raises(ArithmeticError, match="SYSADQ_NO_GROUPS"):
            sa.evaluate_system("t", [], 100.0)


class TestThermalSplits:
    def test_splits(self):
        out = sa.thermal_split_scenarios(320.0, (1, 2, 4), 0.10,
                                         "SRC-TES", "ASSUMPTION-GRID-NOT-DATA")
        assert set(out) == {"thermal_1x320MW", "thermal_2x160MW", "thermal_4x80MW"}
        for k, spec in zip((1, 2, 4), out.values()):
            assert spec.n_units * spec.unit_capacity_mw == pytest.approx(320.0)
            assert spec.for_is_assumption is True

    def test_guards(self):
        with pytest.raises(ArithmeticError, match="SYSADQ_THERMAL_RANGE"):
            sa.thermal_split_scenarios(0.0, (1,), 0.1, "A", "B")
        with pytest.raises(ArithmeticError, match="SYSADQ_SPLIT_RANGE"):
            sa.thermal_split_scenarios(320.0, (0,), 0.1, "A", "B")


class TestReferenceIntegration:
    def test_open_reference_values_drive_model(self):
        sysref = json.loads((REF_DIR / "kolyma_magadan_open_sources.json")
                            .read_text(encoding="utf-8"))
        forref = json.loads((REF_DIR / "hydro_for_open_stats.json")
                            .read_text(encoding="utf-8"))
        kol = sysref["kolyma_hpp"]["parameters"]
        assert kol["units_count"]["value"] == 5
        assert kol["unit_capacity_mw"]["value"] == 180
        gads = next(e for e in forref["reference_stats"]
                    if e["id"] == "gads-2008-2012-hydro")
        assert gads["EFORd_pct"] == pytest.approx(5.43)
        spec = sa.UnitGroupSpec(
            name_prefix="KolymskayaHPP", n_units=kol["units_count"]["value"],
            unit_capacity_mw=kol["unit_capacity_mw"]["value"],
            eford_d=gads["EFORd_pct"] / 100.0,
            source_ref=kol["units_count"]["source_ref"],
            eford_source_ref=gads["source_ref"])
        units = sa.build_units(spec)
        assert len(units) == 5
        assert sum(u.capacity_mw for u in units) == pytest.approx(900.0)

    def test_adequacy_artifact_receipt(self):
        import hashlib
        art_path = (Path(__file__).resolve().parents[2]
                    / "artifacts_v9" / "magadan_system_adequacy_v9.json")
        assert art_path.exists()
        art = json.loads(art_path.read_text(encoding="utf-8"))
        receipt = art.pop("artifact_sha256")
        blob = json.dumps(art, ensure_ascii=False, indent=2, sort_keys=True).encode()
        assert hashlib.sha256(blob).hexdigest() == receipt
        rep = art["report"]
        assert rep["n_scenarios"] == 18
        assert rep["eford_hydro_class"] == pytest.approx(0.0543)
        # система глубоко резервирована: худший LOLE сильно ниже
        # отраслевого ориентира 2,4 ч/год (0,1 сут/год)
        assert rep["worst_case_lole_hours_per_year"] < 2.4
        # все сценарии — с for_is_assumption=True => decision=HOLD
        assert all(s["decision"] == "HOLD" for s in rep["scenarios"])
        assert all(s["n_minus_1_secure"] for s in rep["scenarios"])
