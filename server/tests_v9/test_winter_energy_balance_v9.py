"""Тесты зимнего энергетического баланса каскада (V9.7).

Покрытие: физика E=rho*g*H*V*eta и обратные преобразования; fail-closed;
помесячные квантили притока; консервация запаса в балансе; ограничение
выработки при пустом водохранилище; согласованность с опорными данными
и с артефактом V9.6 (связи внутри линии V9); детерминизм; квитанция
артефакта.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hydro_api.winter_energy_balance_v9 import (
    DEFICIT_EPS_GWH,
    ENGINE_ID,
    MONTH_HOURS,
    WINTER_MONTHS,
    ReservoirSpec,
    flow_to_power_mw,
    monthly_inflow_quantiles,
    power_to_release_km3,
    simulate_winter_balance,
    storage_energy_gwh,
)

ROOT = Path(__file__).resolve().parents[2]
SYS_REF = ROOT / "data" / "reference" / "kolyma_magadan_open_sources.json"
CASCADE_REF = ROOT / "data" / "reference" / "kolyma_cascade_energy_v97.json"
ARTIFACT = ROOT / "artifacts_v9" / "magadan_winter_energy_balance_v97.json"
V96_ARTIFACT = ROOT / "artifacts_v9" / "magadan_seasonal_adequacy_v9.json"

ETA = 0.90
KOL = ReservoirSpec(name_ru="Колымская ГЭС", usable_volume_km3=7.24,
                    head_m=108.0, guaranteed_capacity_mw=224.0,
                    source_ref="SRC-WIKIPEDIA-KOLYMA-HPP")
UST = ReservoirSpec(name_ru="Усть-Среднеканская ГЭС", usable_volume_km3=2.57,
                    head_m=58.4, guaranteed_capacity_mw=132.0,
                    source_ref="SRC-WIKIPEDIA-UST-SREDNEKAN-HPP")
MEDIAN_INFLOW = {11: 70.4, 12: 32.2, 1: 15.0, 2: 8.72, 3: 5.93, 4: 5.25}


def run_balance(**kw):
    args = dict(
        kolyma=KOL, ust_srednekan=UST, peak_load_mw=460.0, eta=ETA,
        thermal_available_mw=320.0, inflow_quantile=0.5,
        inflow_by_month_m3s=dict(MEDIAN_INFLOW),
        side_inflow_annual_km3=4.5, mean_annual_flow_m3s=739.0,
        initial_storage_fraction=1.0)
    args.update(kw)
    return simulate_winter_balance("t", **args)


# --- физика ---------------------------------------------------------------

def test_storage_energy_known_value():
    # 1 км³ при напоре 108 м и eta=1: rho*g*H*V/3.6e12 = 294,2 ГВт·ч
    expected = 1000.0 * 9.80665 * 108.0 * 1e9 / 3.6e12
    assert storage_energy_gwh(1.0, 108.0, 1.0) == pytest.approx(expected)
    assert storage_energy_gwh(1.0, 108.0, 0.9) == pytest.approx(expected * 0.9)


def test_flow_power_inverse_roundtrip():
    # расход -> мощность -> объём -> энергия возвращает исходную энергию
    hours = 744
    p = flow_to_power_mw(146.85, 108.0, ETA)
    vol = power_to_release_km3(p, hours, 108.0, ETA)
    e_back = storage_energy_gwh(vol, 108.0, ETA)
    assert e_back == pytest.approx(p * hours / 1000.0, rel=1e-12)


def test_zero_power_zero_release():
    assert power_to_release_km3(0.0, 744, 108.0, ETA) == 0.0


# --- fail-closed ----------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(volume_km3=-1.0),
    dict(volume_km3=float("nan")),
    dict(head_m=-5.0),
    dict(eta=0.0),
    dict(eta=1.01),
    dict(eta=float("inf")),
])
def test_fail_closed_storage(kwargs):
    base = dict(volume_km3=1.0, head_m=100.0, eta=0.9)
    base.update(kwargs)
    with pytest.raises(ArithmeticError):
        storage_energy_gwh(**base)


def test_fail_closed_balance():
    with pytest.raises(ArithmeticError):
        run_balance(peak_load_mw=0.0)
    with pytest.raises(ArithmeticError):
        run_balance(initial_storage_fraction=0.0)
    with pytest.raises(ArithmeticError):
        run_balance(inflow_quantile=1.0)
    with pytest.raises(ArithmeticError):
        run_balance(inflow_by_month_m3s={11: 70.4})  # нет остальных месяцев


def test_monthly_quantiles_fail_closed():
    with pytest.raises(ArithmeticError):
        monthly_inflow_quantiles({}, year_from=1933, year_to=1981)
    with pytest.raises(ArithmeticError):
        monthly_inflow_quantiles({(1950, 11): 5.0}, months=(13,),
                                 year_from=1933, year_to=1981)
    with pytest.raises(ArithmeticError):
        monthly_inflow_quantiles({(1950, 11): 5.0},
                                 year_from=1981, year_to=1933)


def test_monthly_quantiles_known_values():
    series = {}
    for i, y in enumerate(range(1933, 1982)):  # 49 лет
        series[(y, 11)] = float(i + 1)  # 1..49
        series[(y, 5)] = 999.0          # посторонний месяц не участвует
    out = monthly_inflow_quantiles(series, months=(11,),
                                   year_from=1933, year_to=1981,
                                   quantile_levels=(0.05, 0.5))
    # линейная квантиль: q*(n-1) -> 0.05*48=2.4 -> 3+0.4=3.4; медиана=25
    assert out[11][0.5] == pytest.approx(25.0)
    assert out[11][0.05] == pytest.approx(3.4)


# --- баланс ---------------------------------------------------------------

def test_nominal_balance_feasible_and_covering():
    r = run_balance()
    assert r.feasible_no_deficit
    assert r.deficit_total_gwh < DEFICIT_EPS_GWH
    for step in r.months:
        assert step.hydro_energy_gwh + step.thermal_energy_gwh \
            == pytest.approx(step.load_energy_gwh, rel=1e-9)


def test_storage_conservation_no_clamp():
    r = run_balance()
    kol_prev = KOL.usable_volume_km3
    ust_prev = UST.usable_volume_km3
    for step in r.months:
        assert step.kolyma_storage_end_km3 == pytest.approx(
            min(KOL.usable_volume_km3,
                kol_prev + step.kolyma_inflow_km3 - step.kolyma_release_km3),
            rel=1e-12)
        assert step.ust_storage_end_km3 == pytest.approx(
            min(UST.usable_volume_km3,
                ust_prev + step.ust_inflow_km3 - step.ust_release_km3),
            rel=1e-12)
        # каскадная связь: приток нижней ступени >= сброса верхней
        assert step.ust_inflow_km3 >= step.kolyma_release_km3
        kol_prev = step.kolyma_storage_end_km3
        ust_prev = step.ust_storage_end_km3


def test_empty_storage_curtails_hydro():
    # почти пустые водохранилища + высокий пик: выработка ограничена водой
    r = run_balance(peak_load_mw=574.0, thermal_available_mw=0.0,
                    initial_storage_fraction=0.05,
                    inflow_by_month_m3s={m: 0.0 for m in WINTER_MONTHS})
    assert not r.feasible_no_deficit
    assert r.deficit_total_gwh > 0.0
    assert r.kolyma_storage_min_km3 >= 0.0
    for step in r.months:
        assert step.kolyma_storage_end_km3 >= 0.0
        assert step.ust_storage_end_km3 >= 0.0


def test_determinism():
    assert run_balance().model_dump() == run_balance().model_dump()


# --- связи с опорными данными и линией V9 ---------------------------------

def test_reference_consistency():
    sysref = json.loads(SYS_REF.read_text(encoding="utf-8"))
    cas = json.loads(CASCADE_REF.read_text(encoding="utf-8"))
    kol_g = sysref["kolyma_hpp"]["parameters"]["guaranteed_capacity_mw"]["value"]
    ust_g = sysref["ust_srednekan_hpp"]["parameters"]["guaranteed_capacity_mw"]["value"]
    assert kol_g == 224 and ust_g == 132
    hydro = cas["cascade_hydrology"]
    assert hydro["mean_annual_flow_ust_srednekan_m3s"]["value"] == 739
    assert hydro["side_inflow_annual_volume_km3"]["value"] == 4.5
    # сценарные сетки обязаны быть помечены как ASSUMPTION
    for g in cas["scenario_grids_assumption_not_data"].values():
        assert "ASSUMPTION" in g["source_ref"]


def test_v96_artifact_link():
    v96 = json.loads(V96_ARTIFACT.read_text(encoding="utf-8"))
    assert v96["report"]["hydro_guaranteed_mw"] == pytest.approx(356.0)


def test_artifact_receipt_and_key_findings():
    assert ARTIFACT.is_file()
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert art["artifact"] == "MAGADAN-WINTER-ENERGY-BALANCE-V97-1"
    assert len(art["artifact_sha256"]) == 64
    rep = art["report"]
    assert rep["winter_hours_total"] == sum(
        MONTH_HOURS[m] for m in WINTER_MONTHS) == 4344
    assert rep["n_scenarios"] == len(rep["scenarios"]) == 216
    # сетка хранится компактной сводкой; engine/production_ready —
    # на полных эталонных сценариях
    refs = rep["reference_scenarios"]
    assert all(s["engine"] == ENGINE_ID for s in refs.values())
assert all(s["production_ready"] is False for s in refs.values())
    assert all(set(s) == {"s", "d", "k", "u", "h", "f"}
               for s in rep["scenarios"])
    cc = rep["cross_checks"]
    # зимний приток сам по себе даёт менее 5% гарантированной мощности
    assert cc["inflow_only_share_of_guaranteed_pct"] < 5.0
    # средний сток R-ArcticNET согласуется с опубликованным (допуск 5%)
    assert cc["mean_flow_discrepancy_pct"] < 5.0
    assert cc["v96_hydro_guaranteed_matches"] is True
    # каскадный эффект: напор 108+58,4 м
    assert cc["cascade_head_m"] == pytest.approx(166.4)
    # входы артефакта зафиксированы криптографически
    for path, sha in art["input_files"].items():
        assert (ROOT / path).is_file(), path
        assert len(sha) == 64
    # эталонные сценарии несут полные помесячные траектории
    assert set(refs) == {
        "nominal_2023", "nominal_2030", "binding_low_storage_2030"}
    for ref in refs.values():
        assert len(ref["months"]) == len(WINTER_MONTHS)


def test_artifact_sha256_is_canonical_payload_receipt():
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    payload = {k: v for k, v in art.items() if k != "artifact_sha256"}
    blob = json.dumps(payload, ensure_ascii=False, indent=2,
                      sort_keys=True).encode()
    assert hashlib.sha256(blob).hexdigest() == art["artifact_sha256"]
