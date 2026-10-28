#!/usr/bin/env python3
"""Reproduce deterministic lab-only reference comparison + sensitivity.
The fixture deliberately recycles this code's own result. It is NOT an
independent solver result or validation of a real Magadan network.
"""
import json,hashlib
from pathlib import Path
from hydro_api.radial_grid import RadialCase,solve_radial
from hydro_api.reference_v77 import ReferenceSubmission,compare_reference
from hydro_api.sensitivity_v77 import evaluate_sensitivity
from tests_v73.test_radial_and_finance import feeder
from tests_v76.test_assurance_domain import value,budget

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def main():
    c=RadialCase.model_validate(feeder())
    d=c.model_dump(mode='json');primary=solve_radial(c)
    reported={'scope':'SYNTHETIC_UNATTESTED_REFERENCE_ONLY','claimed_tool':'other',
      'claimed_tool_version':'FIRST_PARTY_TEST_FIXTURE',
      'calculation_method':'Primary-model data duplicated for transport test; NOT a separate solver run',
      'source_reference':'SYNTHETIC-UNATTESTED-V77-TRANSPORT-FIXTURE',
      'case_sha256':sha(d),
      'windows':[{'window':r['window'],'line_loss_p_mw':r['line_loss_p_mw'],
        'nodes':[{'node_id':n['node_id'],'voltage_pu':n['voltage_pu'],
                  'current_a':n['current_a'],'line_loss_p_mw':n['line_loss_p_mw']} for n in r['nodes']]}
                  for r in primary['windows']]}
    comparison=compare_reference(primary,ReferenceSubmission.model_validate(reported),sha(d))
    economics=evaluate_sensitivity(value(),budget())
    body={'release':'V7.7-LAB','source':'SYNTHETIC_TEST_FIXTURE_NO_EXTERNAL_VERIFICATION',
          'case_sha256':sha(d),'internal_primary_model':primary,
          'reference_transport_contract':reported,'unattested_numerical_comparison':comparison,
          'synthetic_wbs_sensitivity':economics,
          'real_magadan_asset_data':False,'industrial_approval_eligible':False}
    body['trace_sha256']=sha(body)
    path=Path(__file__).resolve().parents[1]/'artifacts_v77/reproducible_trace_v77.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(body,indent=2,ensure_ascii=False,allow_nan=False))
    print('Synthetic trace:',path,'sha256:',body['trace_sha256'])
if __name__=='__main__':main()
