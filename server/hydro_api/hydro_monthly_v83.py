#!/usr/bin/env python3
"""Official hydrological characteristic-water-year profiles, NOT weather forecast.

Only reports verbatim historical monthly runoff in two nested gauge sections.
The three characteristic years are SELECTED EXAMPLES, NOT random samples or
three forecast quantiles. This module cannot emit a dispatch or power result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path

MONTHS = ('05', '06', '07', '08', '09', '10', '11', '12', '01', '02', '03', '04')
SITES = ('KOLYMA_UPSTREAM', 'UST_SREDNEKAN_DOWNSTREAM')
CASES = {'wet':'2004/05', 'average':'2002/03', 'dry':'1952/53'}
DOC = 'ROSVODRESURSY_ORDER_174_2025'
# Research-controlled transcription integrity, not government cryptographic signature.
PINNED_CASES_SHA256 = '2c58b3c4234a061db6e6bc198d6fd5c516e33663b4d58abaab0edceba16c79c5'


class InvalidReference(ValueError):
    pass


def _amount(raw):
    if not isinstance(raw, str):
        raise InvalidReference('Monthly/annual volumes require exact decimal strings')
    try:
        value = Decimal(raw)
    except InvalidOperation as err:
        raise InvalidReference('Non-numeric runoff volume') from err
    if not value.is_finite() or value < 0 or value > 100 or value.as_tuple().exponent < -2:
        raise InvalidReference('Out-of-range or overly precise monthly volume')
    return value


def validate(raw):
    if not isinstance(raw,dict) or raw.get('schema_version')!='HYDRO_V83_PUBLIC_MONTHLY':
        raise InvalidReference('Unsupported source schema')
    if raw.get('document_id')!=DOC or raw.get('source_date')!='2025-07-07':
        raise InvalidReference('Document identity mismatch')
    if raw.get('source_url')!='https://www.consultant.ru/document/cons_doc_LAW_511518/080fd801a8ed3e26f5c81964b6d1f06a42753b04/':
        raise InvalidReference('Published source URL changed')
    if raw.get('volume_unit')!='km3_per_water_year_month' or tuple(raw.get('water_year_months',()))!=MONTHS:
        raise InvalidReference('Month order and units must match water year May-April')
    if raw.get('data_kind')!='PUBLISHED_SELECTED_HISTORICAL_YEARS_NOT_CURRENT_MONITORING':
        raise InvalidReference('Do not recast selected characteristic years as telemetry')
    if raw.get('raw_daily_archives_available') is not False or raw.get('operational_dispatch_authorization') is not False:
        raise InvalidReference('Raw daily data/operational authority cannot be fabricated')
    if raw.get('estimate_for_2027') is not None:
        raise InvalidReference('No 2027 estimate may be attached to this reference')
    cases=raw.get('cases')
    if not isinstance(cases,dict) or set(cases)!=set(SITES):
        raise InvalidReference('Exactly two source gauge sections required')
    for site in SITES:
        row=cases[site]
        if not isinstance(row,dict) or set(row)!=set(CASES):
            raise InvalidReference(f'{site}: missing characteristic water year')
        for case,year in CASES.items():
            obs=row[case]
            if not isinstance(obs,dict) or obs.get('water_year')!=year:
                raise InvalidReference(f'{site}/{case}: water year mismatch')
            vs=obs.get('monthly_km3')
            if not isinstance(vs,list) or len(vs)!=12:
                raise InvalidReference(f'{site}/{case}: must have exactly 12 months')
            vals=[_amount(x) for x in vs]
            annual=_amount(obs.get('reported_annual_km3'))
            if annual<=0 or abs(sum(vals)-annual)>Decimal('0.02'):
                raise InvalidReference(f'{site}/{case}: monthly total does not reconcile with source annual')
    # Detect *plausible* edited numbers that still reconcile in total.
    canonical=json.dumps(cases,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    if hashlib.sha256(canonical).hexdigest()!=PINNED_CASES_SHA256:
        raise InvalidReference('Published characteristic-year table changed from pinned source transcription')
    return cases


def profile(raw):
    cases=validate(raw)
    result={'status':'PUBLIC_CHARACTERISTIC_YEARS_ONLY','source':DOC,
            'observations':{},'forecast_for_2027':None,'forecast_distribution':None,
            'approved_for_hydroforecast':False,'approved_for_cascade':False,
            'approved_for_dispatch':False,'approved_for_investment':False,
            'monthly_cases_are_statistically_representative_sample':False,
            'nested_gauge_total_km3':None,
            'source_url':raw['source_url'],
            'limitations':[
                'Selected three real water years, not 88-year monthly sample or probabilistic quantiles',
                'Total downstream river runoff includes upstream water; never add site totals',
                '2027 weather, daily inflow, storage, releases, MWh and revenue not predicted',
                'Printed monthly volumes are official rounded values, not raw telemetry',
            ]}
    for site in SITES:
        obs={}
        for case,year in CASES.items():
            src=cases[site][case]
            vs=[_amount(v) for v in src['monthly_km3']]
            annual=sum(vs)
            warm=sum(vs[:5])
            winter=sum(vs[5:])
            pct=lambda v: str((v/annual*100).quantize(Decimal('0.01'),rounding=ROUND_HALF_EVEN))
            most=max(range(12),key=lambda i:vs[i])
            obs[case]={
                'water_year':year,
                'annual_km3':str(annual),
                'monthly_km3':{MONTHS[i]:str(v) for i,v in enumerate(vs)},
                'warm_may_sep_km3':str(warm),'warm_may_sep_pct':pct(warm),
                'winter_oct_apr_km3':str(winter),'winter_oct_apr_pct':pct(winter),
                'peak_month':MONTHS[most],'peak_month_pct':pct(vs[most]),
                'classification':'HISTORICAL_SELECTED_CASE',
            }
        result['observations'][site]=obs
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        result=profile(json.loads(args.reference.read_text(encoding='utf-8')))
        code=0
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        result={'status':'INVALID','reason':str(exc),'forecast_for_2027':None,
                'approved_for_dispatch':False,'approved_for_investment':False}
        code=2
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
    return code

if __name__=='__main__': raise SystemExit(main())