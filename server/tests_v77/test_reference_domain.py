"""Contract tests; test data simulate a reported external result, NOT external execution."""
import copy
import pytest
from pydantic import ValidationError
from hydro_api.radial_grid import RadialCase, solve_radial
from hydro_api.main import sha
from hydro_api.reference_v77 import ReferenceSubmission,compare_reference
from tests_v73.test_radial_and_finance import feeder


def case():
    return RadialCase.model_validate(feeder())


def reported_reference(c=None):
    c=c or case()
    result=solve_radial(c)
    return {'scope':'SYNTHETIC_UNATTESTED_REFERENCE_ONLY','claimed_tool':'other',
      'claimed_tool_version':'TEST-FIXTURE-NOT-EXTERNAL',
      'calculation_method':'TEST GENERATED FROM PRIMARY SOLVER; NO CLAIM OF INDEPENDENT EXECUTION',
      'source_reference':'SYNTHETIC-TEST-UNTRUSTED-COMPARISON',
      'case_sha256':sha(c.model_dump(mode='json')),
      'windows':[{'window':w['window'],'line_loss_p_mw':w['line_loss_p_mw'],
         'nodes':[{'node_id':n['node_id'],'voltage_pu':n['voltage_pu'],
                   'current_a':n['current_a'],'line_loss_p_mw':n['line_loss_p_mw']} for n in w['nodes']]}
                  for w in result['windows']]}


def test_identical_report_matches_but_is_not_attested():
    c=case();report=ReferenceSubmission.model_validate(reported_reference(c))
    r=compare_reference(solve_radial(c),report,sha(c.model_dump(mode='json')))
    assert r['status']=='LAB_NUMERICAL_MATCH_UNATTESTED'
    assert r['checked_nodes']==6 and r['checked_windows']==2
    assert r['industrial_approval_eligible'] is False
    assert r['external_solver_execution_verified'] is False
    assert r['independent_engineering_accepted'] is False


def test_mismatch_is_reported_by_window_node_and_metric():
    c=case();r=reported_reference(c)
    r['windows'][0]['nodes'][1]['voltage_pu']-=0.02
    result=compare_reference(solve_radial(c),ReferenceSubmission.model_validate(r),sha(c.model_dump(mode='json')))
    assert result['status']=='LAB_NUMERICAL_MISMATCH_UNATTESTED'
    assert 'normal.n2.voltage_pu' in result['mismatch_paths']


@pytest.mark.parametrize('mutation,reason',[
    (lambda x: x['windows'].pop(), 'REFERENCE_WINDOW_SET_MISMATCH'),
    (lambda x: x['windows'][0]['nodes'][2].update(node_id='n4'), 'REFERENCE_NODE_SET_MISMATCH'),
    (lambda x: x.update(case_sha256='0'*64), 'REFERENCE_CASE_HASH_MISMATCH'),
])
def test_incomplete_or_rebased_report_fails_closed(mutation,reason):
    c=case();x=reported_reference(c);mutation(x)
    with pytest.raises(ValueError,match=reason):
        compare_reference(solve_radial(c),ReferenceSubmission.model_validate(x),sha(c.model_dump(mode='json')))


def test_invalid_reference_fails_schema():
    x=reported_reference();x['windows'][0]['nodes'][1]['voltage_pu']=True
    with pytest.raises(ValidationError):ReferenceSubmission.model_validate(x)
    x=reported_reference();x['windows'][0]['nodes'][0]['line_loss_p_mw']+=0.02
    with pytest.raises(ValidationError,match='REFERENCE_LINE_SUM_DOES_NOT_MATCH_TOTAL'):
        ReferenceSubmission.model_validate(x)
    x=reported_reference();x['industrial_approval_eligible']=True
    with pytest.raises(ValidationError):ReferenceSubmission.model_validate(x)
    x=reported_reference();x['windows'].append(copy.deepcopy(x['windows'][0]))
    with pytest.raises(ValidationError,match='DUPLICATE_REFERENCE_WINDOW'):
        ReferenceSubmission.model_validate(x)
