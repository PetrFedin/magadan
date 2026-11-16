"""Only invented V8.8 data. Never derived from Kolymenergo dispatch or actual grid."""
from copy import deepcopy


def synthetic_region_v88(mw=50, utilization=0.85, year=2031):
    def monthly(code):
        rows = []
        for month in range(1, 13):
            hydro = 285_000.0 if code != "LOW_WATER" else 215_000.0
            network = 840.0 if code != "NETWORK_CONTINGENCY" else 560.0
            rows.append({
                "month": month,
                "hydro_deliverable_energy_mwh": hydro,
                "thermal_deliverable_energy_mwh": 35_000.0,
                "existing_demand_energy_mwh": 200_000.0,
                "existing_coincident_peak_mw": 470.0,
                "firm_generation_peak_mw": 1000.0,
                "regional_network_deliverable_peak_mw": network,
                "firm_operating_reserve_mw": 90.0,
            })
        return {
            "code": code,
            "source_ref": "SYNTHETIC-V88-" + code,
            "months": rows,
        }
    return {
        "year": year,
        "source_ref": "SYNTHETIC-REGIONAL-RESEARCH-NOT-GRID-DATA",
        "original_data_origin": "SYNTHETIC_ONLY",
        "real_source_attested": False,
        "corporate_financial_approval": False,
        "independent_engineering_approval": False,
        "discount_rate_fraction": "0.10",
        "investment_horizon_years": 12,
        "projects": [{
            "project_id": "synthetic-data-workload",
            "title": "Synthetic compute consumer - NOT an actual connected facility",
            "sector": "data_processing",
            "rated_mw": mw,
            "utilization_fraction": utilization,
            "capex_rub": "1500000000",
            "annual_fixed_opex_rub": "40000000",
            "gross_value_rub_per_mwh": "12000",
            "electricity_cost_rub_per_mwh": "5500",
        }],
        "scenarios": [monthly(code) for code in (
            "NORMAL", "LOW_WATER", "NETWORK_CONTINGENCY"
        )],
    }
