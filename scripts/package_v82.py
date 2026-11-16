"""Package validated LAB snapshot with manifest; never a production approval."""
from __future__ import annotations
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/mnt/data')
EXCLUDE={'.git','__pycache__','.pytest_cache','node_modules','.venv','venv'}
EXCLUDE_FILES={'package_summary.log'}

def files():
    return [p for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in EXCLUDE_FILES and not EXCLUDE.intersection(p.relative_to(ROOT).parts)]

# Manifest excludes itself to avoid circular hashing.
items=[p for p in files() if p.name!='MANIFEST_SHA256_V82.json']
hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in items}
manifest={'release':'V8.2 LAB','date':'2026-11-01','source':'V8.1_LOCAL_SOURCE_PLUS_V82_RESEARCH',
          'file_count':len(hashes),'sha256':hashes,
          'real_magadan_data':False,'native_postgresql_accepted':False,
          'industrial_approval_eligible':False}
(ROOT/'MANIFEST_SHA256_V82.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

full=OUT/'HydroKontur_360_Magadan_V82_LAB_FULL_SOURCE.zip'
with zipfile.ZipFile(full,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for p in files():z.write(p,p.relative_to(ROOT).as_posix())

# New and changed files compared to the local V8.0 base, preserving old migrations.
patches=[
'README_V81.md','README_V82.md','MANIFEST_SHA256_V82.json',
'server/migrations/160_boundary_claim_serialization_v81.sql',
'server/tests_v81/test_pg_graph_freeze_native_v81.py',
'server/tests_v81/test_sql_graph_serialization_v81.py',
'server/tests_v72/test_migration_contract.py','server/tests_v76/test_sql_contract.py',
'server/tests_v77/test_sql_contract.py','server/tests_v78/test_sql_and_integrity.py',
'docs/V81_GRAPH_SERIALIZATION_ACCEPTANCE_RU.md',
'artifacts_v81/TEST_REPORT_V81.md','artifacts_v81/acceptance_summary_v81.json',
'server/hydro_api/main.py','server/hydro_api/forecast_api_v82.py','server/hydro_api/forecast_v82.py',
'server/ui/index.html','server/ui/ui.css','server/ui/ui.js',
'server/tests_v82/__init__.py','server/tests_v82/fixture.py',
'server/tests_v82/test_forecast_v82.py','server/tests_v82/test_forecast_http_v82.py',
'server/tests_v82/test_ui_contract_v82.py',
'scripts/reproduce_v82.py','scripts/plot_forecast_v82.py',
'scripts/build_statistical_report_v82.py','scripts/browser_qa_v82.py',
'scripts/package_v82.py','docs/V82_HYDROFORECAST_METHODS_RU.md',
'.github/workflows/native-v82.yml',
] + [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'artifacts_v82').glob('*')) if p.is_file() and p.name not in EXCLUDE_FILES]
assert len(patches)==len(set(patches))
for p in patches:
    if not (ROOT/p).is_file():raise FileNotFoundError(p)
patch=OUT/'HydroKontur_360_Magadan_V82_PATCH_AND_EVIDENCE.zip'
with zipfile.ZipFile(patch,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for name in patches:z.write(ROOT/name,name)

for archive in (full,patch):
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in z.namelist():
            if name in hashes:assert hashlib.sha256(z.read(name)).hexdigest()==hashes[name],name
    print(json.dumps({'filename':archive.name,'bytes':archive.stat().st_size,
          'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
          'files':len(zipfile.ZipFile(archive).namelist()),'integrity':'PASS'},ensure_ascii=False))
