"""Deterministic research-only V8 diagnostics; no field or customer data."""
from pathlib import Path
import json,hashlib,platform
from hydro_api.measurement_v79 import MVScreenV79,evaluate_mv_screen
from hydro_api.measurement_quality_v8 import evaluate_quality
from tests_v79.test_measurement import sample

ROOT=Path(__file__).resolve().parents[1]
case=MVScreenV79.model_validate(sample())
base=evaluate_mv_screen(case)
quality=evaluate_quality(case)
source=case.model_dump(mode='json')
def hash_obj(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
report={
 'release':'V8.0-LAB',
 'dataset':'SYNTHETIC-MAGADAN-MV-DEMONSTRATION-ONLY',
 'source_sha256':hash_obj(source),
 'model_source_sha256':hashlib.sha256((ROOT/'server/hydro_api/measurement_v79.py').read_bytes()).hexdigest(),
 'quality_engine_source_sha256':hashlib.sha256((ROOT/'server/hydro_api/measurement_quality_v8.py').read_bytes()).hexdigest(),
 'python':platform.python_version(),
 'data':source,
 'baseline_report':base,
 'quality_diagnostic':quality,
 'no_real_measurements':True,
 'no_verified_savings':True,
 'no_operational_approval':True,
 'sources':{
   'ipmvp':'https://evo-world.org/en/products-services-mainmenu-en/protocols/ipmvp',
   'postgres_rls':'https://www.postgresql.org/docs/17/ddl-rowsecurity.html'
 }
}
out=ROOT/'artifacts_v8/V8_REPRODUCIBLE_RESEARCH_CASE.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'file':str(out),'source_sha256':report['source_sha256'],
 'signed_difference_kwh':base['signed_normalized_difference_kwh'],
 'quality_envelope':quality['error_envelope_kwh'],
 'joint_support_fraction':quality['post_joint_support_fraction'],
 'realized_savings_certified':False},ensure_ascii=False,indent=2))
