"""V8.8 Magadan regional energy adequacy + conditional investment screen.

Every input is synthetic. Monthly regional aggregates cannot establish real
nodal transfer capability, N-1 reliability, plant dispatch, hydraulic
constraints or an investable project. This function NEVER books a benefit.
"""
from __future__ import annotations

import calendar
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ENGINE_TAG = "V88-SYNTHETIC-MONTHLY-ADEQUACY-AND-CONDITIONAL-NPV"
SCENARIO_CODES = ("NORMAL", "LOW_WATER", "NETWORK_CONTINGENCY")
SECTORS = ("industrial_processing", "data_processing", "mining", "municipal", "other")
MONEY_CENTS = Decimal("0.01")


class SafeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class CandidateProject(SafeInput):
    @field_validator("rated_mw", "utilization_fraction", "capex_rub",
                     "annual_fixed_opex_rub", "gross_value_rub_per_mwh",
                     "electricity_cost_rub_per_mwh", mode="before")
    @classmethod
    def reject_boolean_inputs(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value

    project_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]+$")
    title: str = Field(min_length=4, max_length=180)
    sector: Literal[
        "industrial_processing", "data_processing", "mining", "municipal", "other"
    ]
    rated_mw: float = Field(gt=0, le=2000)
    utilization_fraction: float = Field(ge=0, le=1)
    capex_rub: Decimal = Field(ge=0, le=100_000_000_000_000, allow_inf_nan=False)
    annual_fixed_opex_rub: Decimal = Field(ge=0, le=100_000_000_000_000, allow_inf_nan=False)
    gross_value_rub_per_mwh: Decimal = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    electricity_cost_rub_per_mwh: Decimal = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)


class MonthlyAdequacyInput(SafeInput):
    @field_validator("month", "hydro_deliverable_energy_mwh",
                     "thermal_deliverable_energy_mwh", "existing_demand_energy_mwh",
                     "existing_coincident_peak_mw", "firm_generation_peak_mw",
                     "regional_network_deliverable_peak_mw", "firm_operating_reserve_mw",
                     mode="before")
    @classmethod
    def reject_boolean_monthly_inputs(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value

    month: int = Field(ge=1, le=12)
    hydro_deliverable_energy_mwh: float = Field(ge=0, le=10_000_000)
    thermal_deliverable_energy_mwh: float = Field(ge=0, le=10_000_000)
    existing_demand_energy_mwh: float = Field(ge=0, le=10_000_000)
    existing_coincident_peak_mw: float = Field(ge=0, le=20_000)
    firm_generation_peak_mw: float = Field(ge=0, le=20_000)
    regional_network_deliverable_peak_mw: float = Field(ge=0, le=20_000)
    firm_operating_reserve_mw: float = Field(ge=0, le=10_000)


class HydrologyAndNetworkScenario(SafeInput):
    code: Literal["NORMAL", "LOW_WATER", "NETWORK_CONTINGENCY"]
    source_ref: str = Field(min_length=12, max_length=130, pattern=r"^SYNTHETIC-[A-Za-z0-9_.-]+$")
    months: list[MonthlyAdequacyInput] = Field(min_length=12, max_length=12)


class RegionalEnergyDecisionV88(SafeInput):
    @field_validator("year", "discount_rate_fraction", "investment_horizon_years",
                     mode="before")
    @classmethod
    def reject_boolean_global_inputs(cls, value):
        if isinstance(value, bool):
            raise ValueError("BOOLEAN_NOT_A_QUANTITY")
        return value

    year: int = Field(ge=2020, le=2100)
    source_ref: str = Field(min_length=12, max_length=130, pattern=r"^SYNTHETIC-[A-Za-z0-9_.-]+$")
    original_data_origin: Literal["SYNTHETIC_ONLY"]
    real_source_attested: Literal[False]
    corporate_financial_approval: Literal[False]
    independent_engineering_approval: Literal[False]
    discount_rate_fraction: Decimal = Field(ge=0, le=Decimal("0.60"), allow_inf_nan=False)
    investment_horizon_years: int = Field(ge=1, le=30)
    projects: list[CandidateProject] = Field(min_length=1, max_length=12)
    scenarios: list[HydrologyAndNetworkScenario] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_calendar_and_contract(self):
        if len({p.project_id for p in self.projects}) != len(self.projects):
            raise ValueError("DUPLICATE_PROJECT_ID")
        if {s.code for s in self.scenarios} != set(SCENARIO_CODES):
            raise ValueError("THREE_DISTINCT_REQUIRED_SCENARIOS")
        for scenario in self.scenarios:
            if sorted(month.month for month in scenario.months) != list(range(1, 13)):
                raise ValueError("SCENARIO_REQUIRES_ALL_12_DISTINCT_MONTHS")
            for month in scenario.months:
                hours = calendar.monthrange(self.year, month.month)[1] * 24
                if month.existing_demand_energy_mwh > month.existing_coincident_peak_mw * hours + 1e-6:
                    raise ValueError("EXISTING_ENERGY_EXCEEDS_PEAK_TIMES_HOURS")
                if (month.hydro_deliverable_energy_mwh + month.thermal_deliverable_energy_mwh
                        > month.firm_generation_peak_mw * hours + 1e-6):
                    raise ValueError("GENERATION_ENERGY_EXCEEDS_FIRM_POWER_TIMES_HOURS")
        baseline = next(item for item in self.scenarios if item.code == "NORMAL")
        by_code = {item.code: {month.month: month for month in item.months}
                   for item in self.scenarios}
        for month in baseline.months:
            if (by_code["LOW_WATER"][month.month].hydro_deliverable_energy_mwh
                    > month.hydro_deliverable_energy_mwh + 1e-6):
                raise ValueError("LOW_WATER_HYDRO_CANNOT_EXCEED_NORMAL")
            if (by_code["NETWORK_CONTINGENCY"][month.month].regional_network_deliverable_peak_mw
                    > month.regional_network_deliverable_peak_mw + 1e-6):
                raise ValueError("CONTINGENCY_NETWORK_LIMIT_CANNOT_EXCEED_NORMAL")
        return self


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_CENTS, rounding=ROUND_HALF_UP), "f")


def evaluate_regional_energy_v88(inp: RegionalEnergyDecisionV88) -> dict:
    """Deterministic balance without priority dispatch or financial recognition."""
    monthly_demand = {
        month: sum(
            candidate.rated_mw * candidate.utilization_fraction
            * (calendar.monthrange(inp.year, month)[1] * 24)
            for candidate in inp.projects
        )
        for month in range(1, 13)
    }
    candidate_peak_mw = sum(item.rated_mw for item in inp.projects)
    scenario_reports = []
    for code in SCENARIO_CODES:
        scenario = next(item for item in inp.scenarios if item.code == code)
        monthly = []
        annual_hydro = annual_thermal = annual_base = annual_request = 0.0
        annual_baseline_deficit = annual_incremental_deficit = annual_combined_deficit = 0.0
        greatest_peak_deficit_mw = 0.0
        for month in sorted(scenario.months, key=lambda item: item.month):
            hours = calendar.monthrange(inp.year, month.month)[1] * 24
            hydro, thermal = month.hydro_deliverable_energy_mwh, month.thermal_deliverable_energy_mwh
            supply = hydro + thermal
            base = month.existing_demand_energy_mwh
            additional = monthly_demand[month.month]
            baseline_shortfall = max(0.0, base - supply)
            total_shortfall = max(0.0, base + additional - supply)
            incremental_shortfall = max(0.0, total_shortfall - baseline_shortfall)
            peak_deliverable = max(
                0.0,
                min(month.firm_generation_peak_mw, month.regional_network_deliverable_peak_mw)
                - month.firm_operating_reserve_mw,
            )
            base_peak_deficit = max(0.0, month.existing_coincident_peak_mw - peak_deliverable)
            peak_deficit = max(0.0, month.existing_coincident_peak_mw + candidate_peak_mw - peak_deliverable)
            violations = []
            if baseline_shortfall > 1e-6:
                violations.append("EXISTING_ENERGY_UNSERVED_IN_SYNTHETIC_MODEL")
            if base_peak_deficit > 1e-6:
                violations.append("EXISTING_PEAK_UNSERVED_IN_SYNTHETIC_MODEL")
            if incremental_shortfall > 1e-6:
                violations.append("NEW_LOAD_ENERGY_DEFICIT_IN_SYNTHETIC_MODEL")
            if peak_deficit > 1e-6:
                violations.append("COINCIDENT_PEAK_OR_NETWORK_LIMIT_EXCEEDED")
            if month.firm_operating_reserve_mw > min(
                month.firm_generation_peak_mw, month.regional_network_deliverable_peak_mw
            ):
                violations.append("FIRM_RESERVE_EXCEEDS_TRANSFER_OR_GENERATION")
            monthly.append({
                "month": month.month,
                "hours": hours,
                "hydro_mwh": round(hydro, 4),
                "thermal_mwh": round(thermal, 4),
                "existing_demand_mwh": round(base, 4),
                "new_load_requested_mwh": round(additional, 4),
                "baseline_energy_shortfall_mwh": round(baseline_shortfall, 4),
                "incremental_energy_shortfall_mwh": round(incremental_shortfall, 4),
                "total_energy_shortfall_mwh": round(total_shortfall, 4),
                "firm_peak_after_reserve_mw": round(peak_deliverable, 4),
                "existing_peak_mw": round(month.existing_coincident_peak_mw, 4),
                "new_load_conservative_peak_mw": round(candidate_peak_mw, 4),
                "combined_peak_shortfall_mw": round(peak_deficit, 4),
                "violations": violations,
                "passes_all_synthetic_adequacy_limits": not violations,
            })
            annual_hydro += hydro
            annual_thermal += thermal
            annual_base += base
            annual_request += additional
            annual_baseline_deficit += baseline_shortfall
            annual_incremental_deficit += incremental_shortfall
            annual_combined_deficit += total_shortfall
            greatest_peak_deficit_mw = max(greatest_peak_deficit_mw, peak_deficit)
        scenario_reports.append({
            "code": code,
            "source_ref": scenario.source_ref,
            "hydro_mwh": round(annual_hydro, 4),
            "thermal_mwh": round(annual_thermal, 4),
            "existing_demand_mwh": round(annual_base, 4),
            "new_load_requested_mwh": round(annual_request, 4),
            "baseline_energy_shortfall_mwh": round(annual_baseline_deficit, 4),
            "incremental_energy_shortfall_mwh": round(annual_incremental_deficit, 4),
            "total_energy_shortfall_mwh": round(annual_combined_deficit, 4),
            "maximum_coincident_peak_shortfall_mw": round(greatest_peak_deficit_mw, 4),
            "all_months_feasible": all(m["passes_all_synthetic_adequacy_limits"] for m in monthly),
            "months": monthly,
        })
    project_economics = []
    pv_factor = sum(
        Decimal(1) / (Decimal(1) + inp.discount_rate_fraction) ** year
        for year in range(1, inp.investment_horizon_years + 1)
    )
    annual_hours = sum(calendar.monthrange(inp.year, month)[1] * 24 for month in range(1, 13))
    for candidate in inp.projects:
        annual_energy = candidate.rated_mw * candidate.utilization_fraction * annual_hours
        # Converting rounded MWh into Decimal ensures stable financial serialization.
        annual_energy_dec = Decimal(str(round(annual_energy, 4)))
        margin = candidate.gross_value_rub_per_mwh - candidate.electricity_cost_rub_per_mwh
        annual_net_cashflow = annual_energy_dec * margin - candidate.annual_fixed_opex_rub
        conditional_npv = -candidate.capex_rub + annual_net_cashflow * pv_factor
        project_economics.append({
            "project_id": candidate.project_id,
            "sector": candidate.sector,
            "rated_mw": candidate.rated_mw,
            "utilization_fraction": candidate.utilization_fraction,
            "annual_requested_energy_mwh": round(annual_energy, 4),
            "annual_margin_before_fixed_opex_rub": _money(annual_energy_dec * margin),
            "annual_fixed_opex_rub": _money(candidate.annual_fixed_opex_rub),
            "annual_net_cashflow_if_fully_supplied_rub": _money(annual_net_cashflow),
            "conditional_npv_if_fully_supplied_rub": _money(conditional_npv),
            "real_revenue_or_costs_verified": False,
            "eligible_for_investment_approval": False,
        })
    all_feasible = all(s["all_months_feasible"] for s in scenario_reports)
    return {
        "engine": ENGINE_TAG,
        "assessment_year": inp.year,
        "annual_hours": annual_hours,
        "source_ref": inp.source_ref,
        "portfolio_count": len(inp.projects),
        "portfolio_conservative_coincident_peak_mw": round(candidate_peak_mw, 4),
        "annual_requested_new_energy_mwh": round(sum(monthly_demand.values()), 4),
        "synthetic_all_scenarios_adequate": all_feasible,
        "modelled_operational_adequacy": "PASS_SYNTHETIC_ASSUMPTIONS_ONLY" if all_feasible else "DEFICIT_OR_RELIABILITY_LIMIT",
        "investment_decision": "HOLD",
        "production_dispatch_eligible": False,
        "financial_ledger_eligible": False,
        "real_input_source_verified": False,
        "external_hydraulic_and_grid_verification": False,
        "limitations": [
            "MONTHLY_AGGREGATION_CANNOT_PROVE_HOURLY_OR_NODAL_DELIVERABILITY",
            "CONSERVATIVE_FULL_NAMEPLATE_COINCIDENT_PEAK_ASSUMED_FOR_ALL_NEW_LOADS",
            "NO_NETWORK_TOPOLOGY_OR_N_MINUS_ONE_EMERGENCY_CONSTRAINTS",
            "NO_HYDROLOGY_RIGHTS_RULES_OR_RESERVOIR_MASS_BALANCE_IN_THIS_MODULE",
            "NO_TARIFF_TAX_FX_WORKING_CAPITAL_OR_FINANCING_VALIDATION",
            "FIXED_YEAR_DISCOUNTED_CASHFLOWS_ARE_ILLUSTRATIVE_NOT_A_BUSINESS_PLAN",
            "NO_ACTUAL_MAGADAN_FACILITY_OR_CARRIER_DATA_USED",
        ],
        "scenarios": scenario_reports,
        "conditional_project_economics": project_economics,
    }
