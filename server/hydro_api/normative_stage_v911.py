"""V9.11: independently source-linked necessary normative checks, NEVER dispatch approval.

Order 174 (2025) excerpts were manually transcribed from public copies. Their
official original SHA/engineering sign-off is NOT available. This module:
 * independently checks exact statutory stage/volume anchors and unit algebra;
 * refuses to invent intermediate V(z) or z_tail(Q) curves;
 * highlights winter non-turbine spill conflicts conditional on stable cold;
 * computes only an explicitly synthetic mechanical P=rho*g*Q*H*eta example.
NO network, certified reservoir operations, legal consent, or firm MW output.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

VERSION = "V911-STATUTORY-ANCHOR-NECESSARY-REVIEW-NO-APPROVAL-1"
RESEARCH_ONLY = True
REFERENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data/reference/kolyma_cascade_rules_2025_v911.json"
)
WINTER_MONTHS = frozenset((10, 11, 12, 1, 2, 3, 4))
SPILL_TOL_KM3 = Decimal("0.000000001")
RESERVOIRS = frozenset(("kolyma", "ust_srednekan"))

# Corroborated with public excerpts of Order 174, sections V and VI.
# They are *necessary anchors*, NOT sufficient operating instructions.
EXPECTED = {
    "kolyma": {
        "stage_m_bs": {"umo": "431.06", "npu": "450.56", "fpu": "456.66"},
        "total_volume_km3": {"umo": "7.838", "npu": "15.077", "fpu": "17.961"},
        "usable_volume_km3": "7.239",
        "forced_volume_km3": "2.884",
        "net_head_operating_interval_m": {"minimum": "90", "maximum": "119"},
        "zone_I_sanitary_release_m3s": "100",
        "maximum_daily_drawdown_m": "1.00",
        "maximum_daily_rise_m": None,
        "installed_capacity_mw": "900",
    },
    "ust_srednekan": {
        "stage_m_bs": {"umo": "278.00", "npu": "290.00", "fpu": "292.30"},
        "total_volume_km3": {"umo": "2.863", "npu": "5.436", "fpu": "6.085"},
        "usable_volume_km3": "2.573",
        "forced_volume_km3": "0.649",
        "net_head_operating_interval_m": {"minimum": "38", "maximum": "61"},
        "zone_I_sanitary_release_m3s": "70",
        "maximum_daily_drawdown_m": "1.00",
        "maximum_daily_rise_m": "1.00",
        "installed_capacity_mw": "570",
    },
}


def decimal_value(value: Any, name: str) -> Decimal:
    """Strict numerical parser; never turn bool, NaN or infinity into water."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("V911_INVALID_NUMERIC:" + name)
    try:
        out = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("V911_INVALID_NUMERIC:" + name) from exc
    if not out.is_finite():
        raise ValueError("V911_NONFINITE:" + name)
    return out


def catalog_bytes(path: Path = REFERENCE_PATH) -> bytes:
    return path.read_bytes()


def load_catalog(path: Path = REFERENCE_PATH) -> dict:
    value = json.loads(catalog_bytes(path).decode("utf-8"))
    validate_anchor_catalog(value)
    return value


def validate_anchor_catalog(ref: dict) -> dict:
    if not isinstance(ref, dict):
        raise ValueError("V911_CATALOG_NOT_OBJECT")
    doc = ref.get("source_document")
    if not isinstance(doc, dict) or (
        doc.get("order_number") != "174"
        or doc.get("order_date") != "2025-07-07"
        or doc.get("registration_number") != "83126"
        or doc.get("registration_date") != "2025-08-01"
    ):
        raise ValueError("V911_SOURCE_VERSION_NOT_CONFIRMED")
    if doc.get("original_document_independently_checked") is not False:
        raise ValueError("V911_UNSUPPORTED_PRIMARY_ORIGINAL_CLAIM")
    if doc.get("primary_official_document_sha256") is not None:
        raise ValueError("V911_UNSIGNED_ORIGINAL_BYTES_CLAIM")
    if ref.get("full_stage_volume_curves_ingested") is not False:
        raise ValueError("V911_UNVERIFIED_STAGE_VOLUME_CURVE")
    if ref.get("real_operator_data_present") is not False:
        raise ValueError("V911_UNVERIFIED_OPERATOR_DATA")
    if ref.get("production_ready") is not False:
        raise ValueError("V911_UNVERIFIED_PRODUCTION_STATUS")
    reservoirs = ref.get("reservoirs")
    if not isinstance(reservoirs, dict) or set(reservoirs) != RESERVOIRS:
        raise ValueError("V911_RESERVOIR_IDENTITIES")
    computed = {}
    for key, baseline in EXPECTED.items():
        value = reservoirs[key]
        if value.get("stage_datum") != "BS":
            raise ValueError("V911_DATUM_MISMATCH:" + key)
        for field, goal in baseline.items():
            actual = value.get(field)
            if isinstance(goal, dict):
                if not isinstance(actual, dict) or set(actual) != set(goal):
                    raise ValueError("V911_MISSING_ANCHOR:" + key + ":" + field)
                for subkey, numeric_goal in goal.items():
                    if decimal_value(actual[subkey], field) != Decimal(numeric_goal):
                        raise ValueError("V911_NORMATIVE_ANCHOR_DRIFT:" + key + ":" + field)
            elif goal is None:
                if actual is not None:
                    raise ValueError("V911_UNSUPPORTED_NORMATIVE_LIMIT:" + key + ":" + field)
            elif decimal_value(actual, field) != Decimal(goal):
                raise ValueError("V911_NORMATIVE_ANCHOR_DRIFT:" + key + ":" + field)
        stage = {k: decimal_value(v, k) for k, v in value["stage_m_bs"].items()}
        volume = {k: decimal_value(v, k) for k, v in value["total_volume_km3"].items()}
        if not stage["umo"] < stage["npu"] < stage["fpu"]:
            raise ValueError("V911_STAGE_NOT_STRICTLY_ORDERED")
        if not volume["umo"] < volume["npu"] < volume["fpu"]:
            raise ValueError("V911_VOLUME_NOT_STRICTLY_ORDERED")
        if volume["npu"] - volume["umo"] != decimal_value(
            value["usable_volume_km3"], "usable"
        ):
            raise ValueError("V911_USEFUL_WATER_IDENTITY_FAILED")
        if volume["fpu"] - volume["npu"] != decimal_value(
            value["forced_volume_km3"], "forced"
        ):
            raise ValueError("V911_FORCED_WATER_IDENTITY_FAILED")
        computed[key] = {
            "usable_km3": str(volume["npu"] - volume["umo"]),
            "forced_km3": str(volume["fpu"] - volume["npu"]),
            "stage_datum": "BS",
        }
    upper = reservoirs["kolyma"]
    if decimal_value(upper.get("os_above_bs_m"), "os_above_bs") != Decimal("0.94"):
        raise ValueError("V911_KOLYMA_VERTICAL_DATUM_OFFSET")
    if reservoirs["ust_srednekan"].get("os_above_bs_m") is not None:
        raise ValueError("V911_INVENTED_UST_OS_DATUM")
    flow = ref.get("historical_long_run_water_balance", {})
    up = decimal_value(flow.get("upper_outflow_to_lower_km3_per_year"), "upstream_flow")
    lateral = decimal_value(flow.get("lateral_lower_inflow_km3_per_year"), "lateral")
    lower = decimal_value(flow.get("lower_total_inflow_km3_per_year"), "lower_flow")
    if up + lateral != lower:
        raise ValueError("V911_ANNUAL_CASCADE_FLOW_IDENTITY")
    if (up, lateral, lower) != (
        Decimal("15.193"), Decimal("9.820"), Decimal("25.013")
    ):
        raise ValueError("V911_ANNUAL_NORMATIVE_FLOW_DRIFT")
    regime = ref.get("seasonal_regime_guardrails", {})
    if (regime.get("normative_section") != "VIII, paragraphs 44-52"
            or regime.get("in_stable_cold_season_discharge_via_hydropower_units_only") is not True
            or regime.get("winter_bypass_prohibition_conditional_on_stable_negative_temperatures") is not True):
        raise ValueError("V911_MISSING_CONDITIONAL_WINTER_DISCHARGE_RULE")
    if set(regime.get("winter_cold_period_months", [])) != WINTER_MONTHS:
        raise ValueError("V911_WINTER_MONTH_DEFINITION_MISMATCH")
    return {
        "anchor_consistency_checked": True,
        "modeled_volume_curves_calibrated": False,
        "official_source_bytes_independently_verified": False,
        "annual_upper_outflow_plus_lateral_equals_lower_km3": str(lower),
        "usable_identity_by_reservoir": computed,
        "published_long_run_lateral_km3_per_year": str(lateral),
        "legacy_lateral_km3_per_year": "4.5",
        "absolute_lateral_reference_difference_km3_per_year": str(lateral - Decimal("4.5")),
        "data_periods_and_observation_methods_comparable": False,
        "real_operator_approval": False,
    }


def only_published_stage_anchor(
    catalog: dict, reservoir: str, target_level_bs: Any
) -> dict:
    """Return only *exactly listed* stage/volume pairs, never interpolation."""
    validate_anchor_catalog(catalog)
    if reservoir not in RESERVOIRS:
        raise ValueError("V911_UNKNOWN_RESERVOIR")
    level = decimal_value(target_level_bs, "level_m_bs")
    obj = catalog["reservoirs"][reservoir]
    for name, point in obj["stage_m_bs"].items():
        if decimal_value(point, "stage") == level:
            return {
                "stage_m_bs": str(level),
                "total_volume_km3": str(decimal_value(obj["total_volume_km3"][name], "volume")),
                "is_exact_statutory_anchor": True,
                "interpolation_performed": False,
                "engineering_approval": False,
            }
    raise ValueError("V911_NON_ANCHOR_CURVE_NOT_DIGITIZED")


def seasonal_max_stage_bs(catalog: dict, reservoir: str, day: date) -> Decimal:
    validate_anchor_catalog(catalog)
    if not isinstance(day, date):
        raise ValueError("V911_DATE_REQUIRED")
    if reservoir not in RESERVOIRS:
        raise ValueError("V911_UNKNOWN_RESERVOIR")
    stage = catalog["reservoirs"][reservoir]["stage_m_bs"]
    # Section VI.26: Oct..May 20 NPU; May 21..Sep FPU.
    flood = (day.month == 5 and day.day >= 21) or 6 <= day.month <= 9
    return decimal_value(stage["fpu" if flood else "npu"], "seasonal_cap")


def review_necessary_stage_bounds(
    catalog: dict, reservoir: str, day: date, level_m_bs: Any
) -> dict:
    """One necessary stage check, never a certification of allowed operation."""
    cap = seasonal_max_stage_bs(catalog, reservoir, day)
    level = decimal_value(level_m_bs, "stage")
    bottom = decimal_value(catalog["reservoirs"][reservoir]["stage_m_bs"]["umo"], "umo")
    violation = []
    if level < bottom:
        violation.append("BELOW_STATUTORY_UMO")
    if level > cap:
        violation.append("ABOVE_SEASONAL_STATUTORY_CAP")
    return {
        "status": "OUTSIDE_PUBLISHED_BOUND" if violation else "NECESSARY_STAGE_BOUND_ONLY",
        "violations": violation,
        "upper_stage_cap_m_bs": str(cap),
        "statutory_umo_m_bs": str(bottom),
        "comprehensive_dispatch_compliance_established": False,
    }


def review_daily_level_slew(
    catalog: dict, reservoir: str, previous_stage_bs: Any,
    next_stage_bs: Any, elapsed_days: Any,
) -> dict:
    validate_anchor_catalog(catalog)
    if reservoir not in RESERVOIRS:
        raise ValueError("V911_UNKNOWN_RESERVOIR")
    days = decimal_value(elapsed_days, "elapsed_days")
    if days <= 0:
        raise ValueError("V911_INVALID_ELAPSED_DAYS")
    previous = decimal_value(previous_stage_bs, "previous")
    current = decimal_value(next_stage_bs, "current")
    rate = (current - previous) / days
    max_fall = decimal_value(
        catalog["reservoirs"][reservoir]["maximum_daily_drawdown_m"], "daily_drawdown"
    )
    rise = catalog["reservoirs"][reservoir]["maximum_daily_rise_m"]
    violated = rate < -max_fall or (
        rise is not None and rate > decimal_value(rise, "daily_rise")
    )
    return {
        "stage_rate_m_per_day": str(rate),
        "necessary_daily_level_rate_checked": True,
        "rate_bound_breached": bool(violated),
        "full_hydraulic_operating_constraints_verified": False,
    }


def hydraulic_power_synthetic_mw(
    catalog: dict, reservoir: str, q_m3_s: Any, net_head_m: Any,
    efficiency_fraction: Any, water_density_kg_m3: Any = "1000"
) -> Decimal:
    """P=rho*g*Q*H*eta, W -> MW; illustrative calculation ONLY.

    The real H(z,Q) and efficiency curves are unavailable. No value returned
    here represents commissioned firm power, a dispatch set-point or head
    calibration. Bounds check is necessary but not sufficient.
    """
    validate_anchor_catalog(catalog)
    if reservoir not in RESERVOIRS:
        raise ValueError("V911_UNKNOWN_RESERVOIR")
    q = decimal_value(q_m3_s, "q")
    head = decimal_value(net_head_m, "net_head")
    eta = decimal_value(efficiency_fraction, "eta")
    density = decimal_value(water_density_kg_m3, "rho")
    if q < 0 or not Decimal("0") < eta <= Decimal("1") or not (
        Decimal("900") <= density <= Decimal("1100")
    ):
        raise ValueError("V911_INVALID_SYNTHETIC_PHYSICS_INPUT")
    limits = catalog["reservoirs"][reservoir]["net_head_operating_interval_m"]
    if not (decimal_value(limits["minimum"], "minimum_head") <= head <=
            decimal_value(limits["maximum"], "maximum_head")):
        raise ValueError("V911_NET_HEAD_OUTSIDE_PUBLISHED_EQUIPMENT_RANGE")
    power = density * Decimal("9.80665") * q * head * eta / Decimal("1000000")
    rating = decimal_value(catalog["reservoirs"][reservoir]["installed_capacity_mw"], "rating")
    if power > rating:
        raise ValueError("V911_POWER_EXCEEDS_INSTALLED_RATING")
    return power


def review_winter_spill(
    month: int, upper_non_turbine_km3: Any, lower_non_turbine_km3: Any,
    stable_negative_temperatures_confirmed: bool | None = None,
) -> dict:
    """Fail-closed necessary gate: no returned status means 'compliant'.

    Stable negative temperatures are a *material condition* in section
    VIII.52. Unknown meteorology therefore yields CONDITIONAL, not a legal
    verdict. Non-generating release=0 still doesn't prove dispatcher-zone
    compliance or the ability to store excess water in winter.
    """
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("V911_INVALID_MONTH")
    if (stable_negative_temperatures_confirmed is not None
            and type(stable_negative_temperatures_confirmed) is not bool):
        raise ValueError("V911_INVALID_COLDNESS_EVIDENCE")
    upper = decimal_value(upper_non_turbine_km3, "upper_non_turbine")
    lower = decimal_value(lower_non_turbine_km3, "lower_non_turbine")
    if min(upper, lower) < 0:
        raise ValueError("V911_NEGATIVE_SPILL")
    exceed = upper > SPILL_TOL_KM3 or lower > SPILL_TOL_KM3
    if month not in WINTER_MONTHS:
        status = "NOT_REVIEWED_BY_WINTER_SECTION_VIII_52"
    elif not exceed:
        status = "NO_NON_TURBINE_SPILL_DETECTED_OTHER_RULES_UNVERIFIED"
    elif stable_negative_temperatures_confirmed is True:
        status = "CONFLICT_WITH_VIII_52_DURING_CONFIRMED_STABLE_COLD"
    elif stable_negative_temperatures_confirmed is None:
        status = "POTENTIAL_VIII_52_CONFLICT_PENDING_COLDNESS_EVIDENCE"
    else:
        status = "STABLE_NEGATIVE_TEMPERATURE_CONDITION_NOT_MET_OTHER_RULES_UNVERIFIED"
    return {
        "status": status,
        "positive_non_turbine_release": exceed,
        "paragraph": "VIII.52",
        "temperature_condition_verified": stable_negative_temperatures_confirmed,
        "legally_compliant": None,
        "model_physically_calibrated": False,
    }


def review_v99_winter_grid(catalog: dict, v99: dict) -> dict:
    validate_anchor_catalog(catalog)
    if v99.get("artifact") != "MAGADAN-V99-SYNTHETIC-POLICY-SENSITIVITY-1":
        raise ValueError("V911_V99_WRONG_ARTIFACT")
    rows = v99.get("scenarios")
    if not isinstance(rows, list) or len(rows) != 216:
        raise ValueError("V911_V99_INCOMPLETE")
    status = {}
    for policy in ("thermal_first", "hydro_first"):
        potential = 0
        no_lower_spill = 0
        for row in rows:
            record = row.get(policy, {})
            volume = decimal_value(record.get("lower_spill_km3"), "lower_spill")
            if volume < 0:
                raise ValueError("V911_NEGATIVE_AGGREGATE")
            # A strictly positive Oct-Apr TOTAL proves at least one winter
            # month has non-turbine release; it DOES NOT identify that hour.
            if volume > SPILL_TOL_KM3:
                potential += 1
            else:
                no_lower_spill += 1
        status[policy] = {
            "selected_cases_with_positive_lower_non_turbine_winter_release": potential,
            "selected_cases_without_reported_lower_non_turbine_release": no_lower_spill,
            "cases_certified_compliant": 0,
        }
    return {
        "v99_total_selected_scenarios": len(rows),
        "policy_winter_non_turbine_screening": status,
        "upper_spill_series_in_complete_v99_grid_available": False,
        "weather_condition_of_viii_52_documented_for_each_scenario": False,
        "observed_real_operating_regime_assessed": False,
        "regulatory_admission": "HOLD",
        "probabilistic_reliability_estimate": False,
    }


def review_v910_reference_trajectories(catalog: dict, v910: dict) -> dict:
    """Only four V9.10 references have complete monthly release trajectories."""
    validate_anchor_catalog(catalog)
    if v910.get("artifact") != "MAGADAN-V910-ASSUMED-MINIMUM-USABLE-STOCK-STRESS-1":
        raise ValueError("V911_V910_WRONG_ARTIFACT")
    rows = v910.get("rows")
    refs = v910.get("reference_trajectories")
    if not isinstance(rows, list) or len(rows) != 384 or not isinstance(refs, dict):
        raise ValueError("V911_V910_GRID_INCOMPLETE")
    scenarios = len(refs)
    reviews = 0
    potential = 0
    for key, obj in refs.items():
        if not isinstance(key, str):
            raise ValueError("V911_BAD_REFERENCE_KEY")
        for variant in ("baseline_with_floor", "stress_with_floor", "stress_without_floor"):
            trajectory = obj.get(variant, {})
            months = trajectory.get("months", [])
            if len(months) != 6:
                raise ValueError("V911_REFERENCE_NOT_SIX_MONTHS")
            for row in months:
                status = review_winter_spill(
                    row["month"], row["upper_spill_km3"], row["lower_spill_km3"]
                )
                reviews += 1
                potential += int(status["status"] ==
                    "POTENTIAL_VIII_52_CONFLICT_PENDING_COLDNESS_EVIDENCE")
    return {
        "v910_selected_scenario_rows": len(rows),
        "fully_detailed_reference_scenarios_only": scenarios,
        "reference_trajectory_variants_checked": scenarios * 3,
        "reference_months_checked": reviews,
        "reference_months_with_potential_conditional_viii_52_conflicts": potential,
        "remaining_undetailed_scenarios_not_certified": len(rows) - scenarios,
        "regulatory_admission": "HOLD",
    }


def build_v911_research_receipt(
    catalog: dict, v99: dict, v910: dict, source_hashes: dict[str, str]
) -> dict:
    if not source_hashes or not all(
        isinstance(k, str) and isinstance(v, str) and len(v) == 64
        for k, v in source_hashes.items()
    ):
        raise ValueError("V911_INVALID_SOURCE_HASH_LEDGER")
    output = {
        "research_engine": VERSION,
        "normative_anchors": validate_anchor_catalog(catalog),
        "v99_winter_screen": review_v99_winter_grid(catalog, v99),
        "v910_reference_screen": review_v910_reference_trajectories(catalog, v910),
        "source_sha256": source_hashes,
        "official_document_original_bytes_verified": False,
        "published_full_stage_volume_tailwater_curves_ingested": False,
        "necessary_screen_not_comprehensive_rule_compliance": True,
        "conditional_stable_cold_requirement_acknowledged": True,
        "full_dispacher_zone_graphs_and_operational_data_missing": True,
        "field_data_or_operator_approval": False,
        "firm_capacity_mw": None,
        "probabilistic_lole_eens_computed": False,
        "production_ready": False,
        "investment_decision": "HOLD",
    }
    canonical = json.dumps(output, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")
    output["payload_sha256"] = sha256(canonical).hexdigest()
    return output
