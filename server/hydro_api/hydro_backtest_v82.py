#!/usr/bin/env python3
"""Evidence-gated, leakage-proof public/research HydroForecast benchmark, NOT dispatch.

Input is an owner-authorized, byte-attested DAILY CSV (not annual exceedance data).
The baselines are deliberately frozen: persistence and a 365-day lag.
Historical scores do not constitute predictive skill or safety authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import sqrt
from pathlib import Path

SITES = ('KOLYMA_UPSTREAM', 'UST_SREDNEKAN_DOWNSTREAM')
HORIZONS = (1, 7, 30)
METHODS = ('persistence', 'lag365')
REQUIRED_COLUMNS = {'site_id', 'observation_date', 'available_at', 'natural_inflow_cms', 'quality_flag'}


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError('timezone-aware ISO timestamp required')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('naive timestamp prohibited')
    return dt.astimezone(timezone.utc)


def decimal_flow(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('exact decimal string required')
    try:
        x = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid flow') from exc
    if not x.is_finite() or x < 0 or x > Decimal('100000') or x.as_tuple().exponent < -3:
        raise ValueError('invalid flow magnitude/precision')
    return x


def load_attested(payload, directory):
    """Verify local source bytes and provenance claims; NOT legal/signature authentication."""
    if not isinstance(payload, dict) or payload.get('schema_version') != 'HYDRO_V82':
        raise ValueError('invalid schema')
    as_of = timestamp(payload.get('as_of'))
    src = payload.get('source')
    if not isinstance(src, dict) or directory is None:
        raise ValueError('source authorization and root are required')
    rel = src.get('relative_path')
    if (not isinstance(rel, str) or not rel or '\\' in rel or '\x00' in rel
            or Path(rel).is_absolute() or '..' in Path(rel).parts):
        raise ValueError('invalid source path')
    if src.get('scope') != 'AUTHORISED_RESEARCH_ONLY':
        raise ValueError('owner-authorized research scope required')
    if not isinstance(src.get('authorization_ref'), str) or len(src['authorization_ref'].strip()) < 8:
        raise ValueError('missing authorization ref')
    sub, review = src.get('submitted_by'), src.get('reviewed_by')
    if (not isinstance(sub, str) or not sub.strip() or not isinstance(review, str)
            or not review.strip() or sub.strip().casefold() == review.strip().casefold()):
        raise ValueError('independent source reviewer required')
    if timestamp(src.get('reviewed_at')) > as_of:
        raise ValueError('future reviewer attestation')
    if timestamp(src.get('authorization_expires_at')) < as_of:
        raise ValueError('source usage authorization expired')
    root = Path(directory).resolve(strict=True)
    candidate = root / rel
    if candidate.is_symlink():
        raise ValueError('symlink source prohibited')
    source_path = candidate.resolve(strict=True)
    if not source_path.is_relative_to(root) or not source_path.is_file():
        raise ValueError('source outside authorized directory')
    raw = source_path.read_bytes()
    digest = src.get('sha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid SHA256')
    if not raw or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('original source bytes failed SHA256')
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED_COLUMNS:
        raise ValueError('CSV schema mismatch')
    data = {s: {} for s in SITES}
    for i, row in enumerate(reader, 2):
        if None in row or row['site_id'] not in SITES or row['quality_flag'] != 'ACCEPTED_ACTUAL':
            raise ValueError(f'row {i}: unknown section, bad row or unaccepted quality')
        day = date.fromisoformat(row['observation_date'])
        if day.isoformat() != row['observation_date']:
            raise ValueError(f'row {i}: non-canonical YYYY-MM-DD date')
        available = timestamp(row['available_at'])
        if available < datetime.combine(day, time.min, timezone.utc) or available > as_of:
            raise ValueError(f'row {i}: impossible/as_of-later availability')
        if day in data[row['site_id']]:
            raise ValueError(f'row {i}: duplicate daily observation')
        data[row['site_id']][day] = (decimal_flow(row['natural_inflow_cms']), available)
    return as_of, data, digest


def score(actual, guesses):
    n = len(actual)
    if n < 20:
        return None
    errors = [p - y for y, p in zip(actual, guesses)]
    total = sum(actual)
    if total <= 0:
        return None
    return {'n': n, 'mae_cms': round(sum(abs(x) for x in errors) / n, 6),
            'rmse_cms': round(sqrt(sum(x*x for x in errors) / n), 6),
            'bias_cms': round(sum(errors) / n, 6),
            'wape_pct': round(100 * sum(abs(x) for x in errors) / total, 6)}


def benchmark(payload, directory=None):
    base = {'schema_version':'HYDRO_V82', 'status':'HOLD', 'stations':{},
            'forecast_to_cascade':None, 'actual_dispatch_approved':False,
            'investment_approved':False, 'validated_future_skill':False,
            'warnings':['Research benchmark only; source bytes/reviewer do not prove legal rights or model accuracy']}
    try:
        as_of, data, digest = load_attested(payload, directory)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
        base['hold_reason'] = str(exc)
        return base
    last = as_of.date() - timedelta(days=1)
    # Require a *complete* trailing three-year (1095 day) panel; no imputed zeros.
    start = last - timedelta(days=1094)
    for site in SITES:
        rows = data[site]
        needed = [start + timedelta(days=i) for i in range(1095)]
        if not all(d in rows for d in needed):
            base['hold_reason'] = f'{site}: missing complete 1095-day window'
            return base
        # As-of lag can make the most recent observation unavailable before the next day.
        if rows[last][1] > as_of:
            base['hold_reason'] = f'{site}: last observation not available at as_of'
            return base
        holdout_start = last - timedelta(days=364)
        results = {}
        for h in HORIZONS:
            vals = {m:([],[]) for m in METHODS}
            for offset in range(0, 365-h, 7):
                origin = holdout_start - timedelta(days=1) + timedelta(days=offset)
                target = origin + timedelta(days=h)
                issue_at = datetime.combine(origin + timedelta(days=1), time.min, timezone.utc)
                if issue_at > as_of or target > last:
                    continue
                past, lag = origin, target - timedelta(days=365)
                if rows[past][1] > issue_at or rows[lag][1] > issue_at:
                    continue
                actual, actual_available = rows[target]
                if actual_available > as_of:
                    continue
                # Each benchmark uses *exactly* data available at prediction origin.
                for m, predictor in [('persistence', past), ('lag365', lag)]:
                    vals[m][0].append(float(actual))
                    vals[m][1].append(float(rows[predictor][0]))
            metrics={m:score(*vals[m]) for m in METHODS}
            if any(v is None for v in metrics.values()):
                base['hold_reason'] = f'{site}: insufficient held-out origin points at h{h}'
                return base
            results[str(h)] = metrics
        base['stations'][site] = {'backtests_by_horizon_days':results,
                                  'unverified_candidate_reference_points_cms': {
                                      str(h): {'persistence':str(rows[last][0]),
                                               'lag365':str(rows[last+timedelta(days=h-365)][0])}
                                      for h in HORIZONS},
                                  'evaluation':'RETROSPECTIVE_ONLY',
                                  'holdout_start':holdout_start.isoformat(),
                                  'holdout_end':last.isoformat(),
                                  'station_source_sha256':digest}
    base['status']='REVIEW_ONLY'
    base['warnings'].extend([
        'Review-only status does not certify ownership/authorization despite asserted document metadata',
        'The downstream gauging section contains upstream water: no addition of both flows',
        'Source availability is checked at every historical prediction origin',
        'No calibrated storage/routing/head/turbine constraints: cascade handoff prohibited',
        'Holdout skill is measured ONLY after independently authenticated real daily data',
    ])
    return base


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--source-root',type=Path)
    p.add_argument('--output',type=Path)
    opts=p.parse_args()
    result=benchmark(json.loads(opts.input.read_text(encoding='utf-8')),opts.source_root)
    rendered=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if opts.output: opts.output.write_text(rendered,encoding='utf-8')
    print(rendered)
    return 0 if result['status']=='REVIEW_ONLY' else 3


if __name__=='__main__':
    raise SystemExit(main())
