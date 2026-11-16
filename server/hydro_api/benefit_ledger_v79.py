"""V7.9 cross-module benefit ownership: synthetic estimates, never actual savings.

Reservation is keyed by an authoritative asset boundary, benefit family and
inclusive reporting years. Overlaps are rejected at the DB boundary.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import Field, model_validator
from .radial_grid import Strict

BenefitFamily = Literal[
    'ELECTRIC_ENERGY_COST', 'HEAT_ENERGY_COST', 'MAINTENANCE_COST',
    'GENERATION_VALUE', 'CAPEX_COST', 'DECISION_PROCESS', 'RELIABILITY_RISK'
]
SourceKind = Literal['GRID_ANNUAL_V78', 'ASSURANCE_V76', 'MAINTENANCE_HANDOFF_V75', 'PROGRAMME_V74']


class ReserveBenefitV79(Strict):
    asset_id: str = Field(min_length=1, max_length=120)
    family: BenefitFamily
    start_year: int = Field(ge=2026, le=2050)
    end_year: int = Field(ge=2026, le=2050)
    source_kind: SourceKind
    source_id: str = Field(min_length=1, max_length=120)
    measurement_plan_ref: str = Field(min_length=20, max_length=160,
                                      pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    measurement_boundary_description: str = Field(min_length=40, max_length=1200)
    comparison_normalization: str = Field(min_length=60, max_length=1200)

    @model_validator(mode='after')
    def period(self):
        if self.end_year < self.start_year:
            raise ValueError('BENEFIT_PERIOD_REVERSED')
        if self.end_year - self.start_year > 20:
            raise ValueError('BENEFIT_HORIZON_TOO_LONG')
        return self


def base_value_from_v78(report: dict, start_year: int, end_year: int) -> str | None:
    """Gross hypothetical avoided-cost values, not NPV nor realized savings.

    An unrepresented year or missing explicit cashflow forbids any total.
    """
    if report.get('industrial_approval_eligible') is not False:
        raise ValueError('NON_LAB_RESULT_NOT_ADMISSIBLE')
    try:
        rows = report['scenario_results']['base']['yearly_cashflows']
        by_year = {r['year']: r for r in rows}
        years = set(range(start_year, end_year + 1))
        if not years.issubset(by_year):
            return None
        values = [Decimal(by_year[y]['gross_rub']) for y in sorted(years)]
        if not all(x.is_finite() for x in values):
            return None
        return str(sum(values, Decimal('0')).quantize(Decimal('0.01')))
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return None


def claimed_overlap(left: dict, right: dict) -> bool:
    """Python policy oracle for SQL tests; not used instead of a DB constraint."""
    return (left['org_id'] == right['org_id'] and left['asset_id'] == right['asset_id']
            and left['family'] == right['family']
            and left['start_year'] <= right['end_year']
            and right['start_year'] <= left['end_year'])


def readiness_statement() -> dict:
    return {
        'release': '7.9-LAB', 'production_ready': False,
        'claim_semantics': 'LAB_RESERVATION_NEVER_REALIZED_SAVINGS',
        'field_savings_recognised': False, 'industrial_approval_eligible': False,
        'sqlite_overlap_trigger': 'TESTABLE_IN_LAB',
        'postgres_native_exclusion_constraint': 'NOT_ACCEPTED',
        'legacy_dossiers_auto_registered': False,
        'external_m_and_v_acceptance': False,
        'magadan_real_data': False,
    }
