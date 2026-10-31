#!/usr/bin/env python3
"""V8.1 Kolyma legal-hydrology reference and research-only scenario screens.

No hydrological model is fitted here. Source annual runoff is a *statistical*
regulatory climatology, not new data or a forecast of the next water year.
No operational dispatch, economic savings or investment is approved.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path

SITES = ('KOLYMA_UPSTREAM', 'UST_SREDNEKAN_DOWNSTREAM')
EXCEEDANCE = ('1', '5', '10', '25', '50', '75', '90', '95', '97', '99')
EXPECTED_DOC = 'ROSVODRESURSY_ORDER_174_2025'
SECONDS_MEAN_YEAR = Decimal('365.2425') * Decimal('86400')
FLOWS = {'KOLYMA_UPSTREAM': Decimal('100'),
         'UST_SREDNEKAN_DOWNSTREAM': Decimal('70')}


class InvalidReference(ValueError):
    pass


def decimal_value(value, label):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int)):
        raise InvalidReference(f'{label}: numeric input must be exact decimal text or integer')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidReference(f'{label}: invalid decimal') from exc
    if not result.is_finite() or result <= 0:
        raise InvalidReference(f'{label}: positive finite value required')
    return result


def validate(raw):
    if not isinstance(raw, dict) or raw.get('schema_version') != 'HYDRO_V81':
        raise InvalidReference('Unsupported reference schema')
    if raw.get('document_id') != EXPECTED_DOC or raw.get('document_date') != '2025-07-07':
        raise InvalidReference('Document identification mismatch')
    if raw.get('observation_window') != '1934-2021' or raw.get('observation_years') != 88:
        raise InvalidReference('88-year observation window mismatch')
    if raw.get('volume_unit') != 'km3_per_water_year':
        raise InvalidReference('Runoff is an annual water volume (not a rate)')
    if raw.get('source_type') != 'PUBLISHED_REGULATORY_TABLE':
        raise InvalidReference('Reference must be explicitly a regulatory table')
    if raw.get('scope') != 'KOLYMA_CASCADE_PUBLIC_HYDROLOGY':
        raise InvalidReference('Not the permitted source scope')
    stations = raw.get('stations')
    if not isinstance(stations, dict) or set(stations) != set(SITES):
        raise InvalidReference('Exactly two known regulatory gauging sections required')
    for key in SITES:
        row = stations[key]
        if not isinstance(row, dict) or row.get('unit') != 'km3_per_water_year':
            raise InvalidReference(key + ': wrong volume unit')
        minimum = decimal_value(row.get('observed_min_km3'), key + ':min')
        maximum = decimal_value(row.get('observed_max_km3'), key + ':max')
        average = decimal_value(row.get('mean_annual_km3'), key + ':mean')
        if not minimum < average < maximum:
            raise InvalidReference(key + ': historical mean/extrema inconsistent')
        quantiles = row.get('exceedance_km3')
        if not isinstance(quantiles, dict) or set(quantiles) != set(EXCEEDANCE):
            raise InvalidReference(key + ': exceedance probabilities missing/duplicated')
        q = [decimal_value(quantiles[p], key + ':p' + p) for p in EXCEEDANCE]
        if not all(a >= b for a, b in zip(q, q[1:])):
            raise InvalidReference(key + ': annual exceedance curve must be nonincreasing')
        # Fitted low-probability exceedance estimates may extend beyond observed extrema.
        # Official downstream P01 39.8 km3 exceeds observed historic max 39.3 km3.
        if not minimum <= q[4] <= maximum:
            raise InvalidReference(key + ': central estimate beyond historical range')
        required = decimal_value(row.get('nominal_sanitary_release_cms'), key + ':sanitary')
        if required != FLOWS[key]:
            raise InvalidReference(key + ': sanitary release no longer matches pinned source')
    if raw.get('stations_are_independent') is not False:
        raise InvalidReference('Nested upstream/downstream basins must not be added')
    if raw.get('raw_88_year_daily_dataset_available') is not False:
        raise InvalidReference('Source has no authorized 88-year raw daily time series')
    return stations


def public_reference_report(raw):
    """Source-typed scenarios, NOT a future-specific forecast."""
    stations = validate(raw)
    summary = {}
    for key in SITES:
        row = stations[key]
        mean = decimal_value(row['mean_annual_km3'], 'mean')
        q = row['exceedance_km3']
        summary[key] = {
            'observed_min_km3': str(decimal_value(row['observed_min_km3'], 'min')),
            'mean_annual_km3': str(mean),
            'observed_max_km3': str(decimal_value(row['observed_max_km3'], 'max')),
            'p95_low_runoff_km3': str(decimal_value(q['95'], 'p95')),
            'p50_median_exceedance_km3': str(decimal_value(q['50'], 'p50')),
            'p05_high_runoff_km3': str(decimal_value(q['5'], 'p05')),
            'mean_annualized_flow_equivalent_cms': str(
                (mean * Decimal('1000000000') / SECONDS_MEAN_YEAR).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
            'regulatory_sanitary_release_cms': str(FLOWS[key]),
            'source_scope': 'regulatory_annual_natural_runoff_at_specific_gauging_section',
        }
    return {
        'status': 'PUBLIC_REFERENCE_ONLY', 'schema_version': 'HYDRO_V81',
        'document_id': EXPECTED_DOC,
        'period': '1934-2021', 'observed_years': 88,
        'stations': summary, 'cascade_summed_runoff_km3': None,
        'forecast_next_water_year_km3': None,
        'scenario_probabilities_are_next_year_predictions': False,
        'hydropower_mwh_forecast': None, 'financial_savings_rub': None,
        'approved_for_dispatch': False, 'approved_for_investment': False,
        'operational_status': 'HOLD_NO_APPROVED_DAILY_INFLOW_DATA',
        'limitations': (
            'Official 2025 order summary of 1934-2021 natural annual runoff. '
            'P05/P50/P95 are regulatory exceedance scenarios, not specific-year predictions. '
            'The downstream river section includes upstream water. '
            'Annual-equivalent flow is dimensional illustration, not an operating flow. '
            'No daily source observations, reservoir-level curves, owner permission, '
            'independent hydrologist validation or safe dispatch authorization.'
        ),
    }


def sanitary_release_screen(raw, proposals):
    """Non-operational red-flag screen, never a full dispatch rule."""
    validate(raw)
    if not isinstance(proposals, dict) or set(proposals) != set(SITES):
        raise InvalidReference('Both hydro site proposals are required')
    screening = {}
    for site in SITES:
        if isinstance(proposals[site], str) and proposals[site] == '0':
            proposed = Decimal('0')
        elif isinstance(proposals[site], int) and not isinstance(proposals[site], bool) and proposals[site] == 0:
            proposed = Decimal('0')
        else:
            proposed = decimal_value(proposals[site], site + ':proposed_release')
        minimum = FLOWS[site]
        screening[site] = {
            'proposed_release_cms': str(proposed),
            'reference_sanitary_release_cms': str(minimum),
            'screen': 'BELOW_NOMINAL_SANITARY_FLOW' if proposed < minimum
                      else 'NOT_BELOW_NOMINAL_SANITARY_FLOW',
        }
    return {
        'screening': screening, 'status': 'RESEARCH_SCREEN_ONLY',
        'approved_for_dispatch': False, 'water_balance_approved': False,
        'limitations': 'A pass against nominal flow is NOT compliance with full 2025 water use rules, seasonal levels, fishery/navigation, or legal dispatch rights.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = public_reference_report(json.loads(args.reference.read_text(encoding='utf-8')))
        code = 0
    except (InvalidReference, OSError, json.JSONDecodeError) as exc:
        result = {'status': 'INVALID', 'error': str(exc),
                  'approved_for_dispatch': False, 'approved_for_investment': False}
        code = 2
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content, encoding='utf-8')
    print(content)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
