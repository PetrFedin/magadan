"""V8.9 synthetic rights/quarantine, grain, dedup and fail-closed admission tests."""
import calendar
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from hydro_api.data_admission_v89 import MonthlyIntake, assess_v89


def synthetic_month(year=2031, month=1, node_count=1):
    hours = calendar.monthrange(year, month)[1] * 24
    sources = [
        {"source_id": "SYNTHETIC-hourly-v89", "source_type": "HOURLY_ENERGY", "owner_name": "Synthetic Engineering QA", "permission_basis": "SYNTHETIC_TEST", "owner_document_ref": "SYNTHETIC-TEST-METADATA", "digest_sha256_declared": "a"*64},
        {"source_id": "SYNTHETIC-nodes-v89", "source_type": "NODE_CONSTRAINT", "owner_name": "Synthetic Engineering QA", "permission_basis": "SYNTHETIC_TEST", "owner_document_ref": "SYNTHETIC-TEST-METADATA", "digest_sha256_declared": "b"*64},
        {"source_id": "SYNTHETIC-loads-v89", "source_type": "NEW_CONNECTIONS", "owner_name": "Synthetic Engineering QA", "permission_basis": "SYNTHETIC_TEST", "owner_document_ref": "SYNTHETIC-TEST-METADATA", "digest_sha256_declared": "c"*64},
    ]
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    nodes = [{"node_id": f"lab_node_{n}", "constraint_source_id": "SYNTHETIC-nodes-v89", "firm_n1_limit_mw": "120", "baseline_coincident_peak_mw": "60", "operating_reserve_mw": "10"} for n in range(node_count)]
    hourly = [{"node_id": f"lab_node_{n}", "source_id": "SYNTHETIC-hourly-v89", "timestamp_utc": (start+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M:%SZ'), "supply_mwh": "100", "baseline_load_mwh": "60"} for n in range(node_count) for i in range(hours)]
    connections = [{"project_id": "synthetic_project_A", "connection_contract_id": "synthetic_contract_A", "canonical_consumer_id": "synthetic_consumer_A", "node_id": "lab_node_0", "source_id": "SYNTHETIC-loads-v89", "baseline_inclusion": "ADDITIONAL", "baseline_reconciliation_ref": "SYNTHETIC-NOT-IN-BASELINE", "rated_mw": "20", "utilization_fraction": "0.85"}]
    return {"mode": "SYNTHETIC_ONLY", "year": year, "month": month, "region": "MAGADAN", "sources": sources, "nodes": nodes, "connections": connections, "hourly": hourly}


def codes(report):
    return {x['code'] for x in report['quality_issues']}


def report(payload):
    return assess_v89(MonthlyIntake.model_validate(payload))


def test_clean_synthetic_month_is_quality_pass_but_not_approved():
    r = report(synthetic_month())
    assert r['status'] == 'SYNTHETIC_QUALITY_PASS_ONLY'
    assert r['quality_pass'] and not r['quality_issues']
    assert r['hourly_rows_expected'] == 744
    assert r['new_project_mw_synthetic_total'] == '20'
    assert r['real_available_capacity_mw'] is None
    assert r['investment_decision'] == 'HOLD'
    assert not r['owner_rights_independently_verified']
    assert not r['declared_digests_independently_matched']
    assert not r['industrial_dispatch_eligible']
    assert not r['production_ready']
    assert r['nodal_synthetic_results'][0]['illustrative_peak_headroom_mw'] == '50'
    assert r['nodal_synthetic_results'][0]['incremental_energy_shortfall_mwh_synthetic'] == '0'
    assert r == report(synthetic_month())


def test_in_baseline_connection_does_not_count_as_additional():
    d = synthetic_month()
    d['connections'][0]['baseline_inclusion'] = 'IN_BASELINE'
    d['connections'][0]['baseline_reconciliation_ref'] = 'SYNTHETIC-ALREADY-COUNTED-IN-BASELINE'
    r = report(d)
    assert r['quality_pass'] and r['new_project_mw_synthetic_total'] == '0'


def test_in_baseline_without_proof_is_blocked_not_silently_excluded():
    d=synthetic_month()
    d['connections'][0]['baseline_inclusion']='IN_BASELINE'
    d['connections'][0]['baseline_reconciliation_ref']=None
    r=report(d)
    assert not r['quality_pass']
    assert 'IN_BASELINE_PROJECT_MISSING_RECONCILIATION' in codes(r)
    assert r['new_project_mw_synthetic_total'] is None


def test_unknown_baseline_requires_reconciliation_without_silent_zero():
    d = synthetic_month()
    d['connections'][0]['baseline_inclusion'] = 'UNKNOWN'
    r = report(d)
    assert not r['quality_pass']
    assert r['new_project_mw_synthetic_total'] is None
    assert 'UNKNOWN_BASELINE_INCLUSION_REQUIRES_OWNER_RECONCILIATION' in codes(r)


def test_missing_reconciliation_prevents_additional_project_inclusion():
    d = synthetic_month()
    d['connections'][0]['baseline_reconciliation_ref'] = None
    r = report(d)
    assert 'ADDITIONAL_PROJECT_MISSING_BASELINE_RECONCILIATION' in codes(r)


def test_duplicates_by_project_contract_and_canonical_consumer_fail():
    d = synthetic_month()
    d['connections'].append(deepcopy(d['connections'][0]))
    r = report(d)
    assert {'DUPLICATE_PROJECT_ID','DUPLICATE_CONNECTION_CONTRACT','CANONICAL_CONSUMER_MULTIPLE_ROWS_NEEDS_ALLOCATION_PROOF'} <= codes(r)
    assert r['new_project_mw_synthetic_total'] is None


def test_duplicate_hour_is_blocking_even_if_coverage_full():
    d = synthetic_month()
    d['hourly'].append(deepcopy(d['hourly'][0]))
    r = report(d)
    assert r['duplicate_hour_count'] == 1
    assert 'DUPLICATE_NODE_UTC_HOUR' in codes(r)
    assert r['nodal_synthetic_results'] == []


def test_missing_hour_is_blocking_and_completeness_is_counted():
    d = synthetic_month()
    d['hourly'].pop()
    r = report(d)
    assert r['missing_hour_count'] == 1
    assert 'MISSING_NODE_UTC_HOURS' in codes(r)


def test_cross_month_hour_does_not_replace_missing_month_hour():
    d = synthetic_month()
    d['hourly'][0]['timestamp_utc'] = '2031-02-01T00:00:00Z'
    r = report(d)
    assert 'HOUR_OUTSIDE_DECLARED_MONTH' in codes(r)
    assert 'MISSING_NODE_UTC_HOURS' in codes(r)


def test_leap_year_uses_696_february_hours():
    r = report(synthetic_month(year=2032,month=2))
    assert r['monthly_hours_expected_per_node'] == 696
    assert r['hourly_rows_expected'] == 696
    assert r['quality_pass']


def test_missing_node_and_wrong_source_fail():
    d = synthetic_month()
    d['connections'][0]['node_id'] = 'phantom_node'
    d['hourly'][0]['source_id'] = 'PUBLIC-fake-source'
    r = report(d)
    assert 'PROJECT_UNKNOWN_GRID_NODE' in codes(r)
    assert 'HOURLY_SOURCE_MISSING_OR_WRONG_TYPE' in codes(r)


def test_baseline_peak_inconsistency_blocks():
    d = synthetic_month()
    d['nodes'][0]['baseline_coincident_peak_mw'] = '49'
    r = report(d)
    assert 'HOURLY_BASELINE_EXCEEDS_DECLARED_PEAK' in codes(r)


def test_firm_n1_reserve_inconsistency_blocks():
    d = synthetic_month()
    d['nodes'][0]['firm_n1_limit_mw'] = '65'
    r = report(d)
    assert 'BASELINE_PEAK_AND_RESERVE_EXCEED_N1_LIMIT' in codes(r)


def test_cannot_smuggle_actual_field_rows_through_metadata_mode():
    d = synthetic_month()
    d['mode'] = 'PROPOSED_METADATA_ONLY'
    with pytest.raises(ValidationError,match='FIELD_METADATA_MODE_MUST_NOT_CONTAIN_OPERATIONAL_MEASUREMENTS'):
        MonthlyIntake.model_validate(d)


def test_public_reference_metadata_is_quarantined_even_when_stated_permission_public():
    d = {'mode':'PROPOSED_METADATA_ONLY','year':2031,'month':1,'region':'MAGADAN',
         'sources':[{'source_id':'PUBLIC-sipr-26-31','source_type':'PUBLIC_FORECAST','owner_name':'Ministry of Energy of Russia','permission_basis':'PUBLIC_METADATA','owner_document_ref':'Minenergo order 1553 from 2025-11-28','digest_sha256_declared':'1'*64}],
         'nodes':[],'connections':[],'hourly':[]}
    r = report(d)
    assert r['status']=='QUARANTINED_METADATA_ONLY'
    assert 'OWNER_PERMISSION_AND_DATASETS_NOT_INDEPENDENTLY_VERIFIED' in codes(r)
    assert r['real_available_capacity_mw'] is None


@pytest.mark.parametrize('field,value', [('rated_mw',True),('utilization_fraction',True)])
def test_boolean_project_measurements_rejected(field,value):
    d = synthetic_month()
    d['connections'][0][field] = value
    with pytest.raises(ValidationError,match='BOOLEAN_NOT_A_QUANTITY'):
        MonthlyIntake.model_validate(d)


def test_boolean_calendar_and_negative_hourly_rejected():
    d = synthetic_month()
    d['month'] = True
    with pytest.raises(ValidationError): MonthlyIntake.model_validate(d)
    d = synthetic_month()
    d['hourly'][0]['supply_mwh'] = -1
    with pytest.raises(ValidationError): MonthlyIntake.model_validate(d)


def test_declared_source_digest_is_metadata_not_independent_proof():
    d = synthetic_month()
    d['sources'][0]['digest_sha256_declared'] = 'bad'
    with pytest.raises(ValidationError): MonthlyIntake.model_validate(d)
    assert report(synthetic_month())['declared_digests_independently_matched'] is False


def test_multiple_nodes_complete_and_node_hour_pairs_unique():
    d = synthetic_month(node_count=2)
    r = report(d)
    assert r['hourly_rows_expected'] == 1488
    assert r['quality_pass']
    assert len(r['nodal_synthetic_results']) == 2


def test_additional_demand_shortfall_only_incremental_not_old_deficit():
    d=synthetic_month()
    for row in d['hourly']:
        row['supply_mwh']='55'  # baseline=60; existing shortage=5 per hour
    r=report(d)
    assert r['quality_pass']
    n=r['nodal_synthetic_results'][0]
    assert n['baseline_energy_shortfall_mwh_synthetic']=='3720'
    assert n['incremental_energy_shortfall_mwh_synthetic']=='12648.00'
    assert r['investment_decision']=='HOLD'
