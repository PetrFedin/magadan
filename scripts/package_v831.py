"""Package verified V8.3.1 reproducible lab source without rewriting V8.3."""
from pathlib import Path
from hashlib import sha256
import json,zipfile

ROOT=Path(__file__).resolve().parents[1]
OLD=Path('/mnt/data/HydroKontur_360_Magadan_V83_LAB_FULL_SOURCE.zip')
OUT=Path('/mnt/data')
EXCLUDE={'.git','__pycache__','.pytest_cache','node_modules','venv','.venv'}
SKIP={'MANIFEST_SHA256_V831.json','package_summary.log','regression_group_b_v831.log'}

source={p.relative_to(ROOT).as_posix():p for p in ROOT.rglob('*')
        if p.is_file() and not any(x in EXCLUDE for x in p.relative_to(ROOT).parts)
        and p.name not in SKIP}
old_archive_sha=sha256(OLD.read_bytes()).hexdigest()
with zipfile.ZipFile(OLD) as z:
    baseline={name:sha256(z.read(name)).hexdigest() for name in z.namelist()}
    assert z.testzip() is None

sha={name:sha256(p.read_bytes()).hexdigest() for name,p in source.items()}
removed=set(baseline)-set(sha)
assert not removed, f'Removed historical V8.3 source paths: {removed}'
changed=sorted(name for name,s in sha.items() if baseline.get(name)!=s)
manifest={'release':'V8.3.1 SYNTHETIC LAB','date':'2026-11-02',
          'parent_zip_sha256':old_archive_sha,
          'source_file_count_excluding_self':len(sha),
          'sha256':sha,
          'changed_vs_v83':changed,
          'changed_count_vs_v83':len(changed),
          'local_python_pass':363,'native_skips':3,'javascript_pass':63,
          'hourly_independent_reference_cases':438,
          'hydraulic_external_solver_verified':False,
          'field_measurements_authorized':False,
          'native_postgresql17_rls_verified':False,
          'authenticated_browser_e2e_passed':False,
          'industrial_approval_eligible':False}
manifest_path=ROOT/'MANIFEST_SHA256_V831.json'
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
full=OUT/'HydroKontur_360_Magadan_V83_1_LAB_FULL_SOURCE.zip'
patch=OUT/'HydroKontur_360_Magadan_V83_1_PROOF_AND_PATCH.zip'
for filename,paths in ((full,sorted(sha)+['MANIFEST_SHA256_V831.json']),
                       (patch,changed+['MANIFEST_SHA256_V831.json'])):
    with zipfile.ZipFile(filename,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for name in paths:z.write(ROOT/name,arcname=name)
    with zipfile.ZipFile(filename) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
        assert len(z.namelist())==len(paths)
        for name in z.namelist():
            if name in sha:assert sha256(z.read(name)).hexdigest()==sha[name],name
    print(json.dumps({'name':filename.name,'bytes':filename.stat().st_size,
                      'sha256':sha256(filename.read_bytes()).hexdigest(),
                      'files':len(paths),'zip_verify':'PASS',
                      'original_v83_zip_sha256':old_archive_sha,
                      'scope':'SYNTHETIC_LAB_ONLY'},ensure_ascii=False))
print(json.dumps({'total_source_files_excluding_new_manifest':len(sha),
                  'changed_vs_v83':len(changed),'paths':changed},indent=2,ensure_ascii=False))
