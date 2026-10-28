from pathlib import Path
import hashlib,json,re,zipfile
root=Path(__file__).resolve().parents[1]
outdir=Path('/mnt/data')
pytestlog=(root/'artifacts/pytest_v7.txt').read_text()
node=(root/'artifacts/node_v6.txt').read_text()
pr=re.search(r'(\d+) passed, (\d+) skipped',pytestlog)
nr=re.search(r'# pass (\d+)',node)
assert pr and nr,(pytestlog[-1000:],node[-1000:])
qa={'report_date':'2026-10-20','branch':'uncommitted isolated V7 package','status':'LAB / PRODUCTION HOLD',
    'v7_server_tests_passed':int(pr.group(1)), 'browser_e2e_skipped':int(pr.group(2)),
    'v6_regression_tests_passed':int(nr.group(1)),
    'browser_qa_reason':'Chromium ERR_BLOCKED_BY_ADMINISTRATOR for loopback HTTP; not an application validation pass',
    'ui_static_check':'1440 and 375px layouts displayed without horizontal overflow, synthetic mock state',
    'physical_solver':'AC two-bus scipy root crosschecked against algebraic high-voltage solution, synthetic data only',
    'db':'SQLite lab; PostgreSQL RLS blueprint unexecuted',
    'audit':'tamper-evident HMAC chain and local triggers, no external WORM anchors',
    'real_magadan_field_data':False,'independent_industry_expert_approval':False,
    'production_deployed':False,'server_browser_e2e_passed':False}
(root/'artifacts/qa_result.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2))
files=[]
for p in root.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(root)
    if any(x in rel.parts for x in ('__pycache__','.pytest_cache','.git','node_modules')):continue
    if p.suffix in ('.pyc','.db','.wal','.shm'):continue
    if p.name in ('.lab.env','V7_MANIFEST_SHA256.json'):continue
    files.append(p)
manifest={'version':'7.0-lab','created':'2026-10-20','status':'PRODUCTION_HOLD','files':[
  {'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(files)]}
(root/'V7_MANIFEST_SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
files.append(root/'V7_MANIFEST_SHA256.json')
name='HydroKontur_360_Magadan_V7_Server_Source_Tests.zip'
archive=outdir/name
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as zipf:
    for p in sorted(files):zipf.write(p,arcname='hydrokontur-v7/'+str(p.relative_to(root)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)
    for item in manifest['files']:
        assert hashlib.sha256(z.read('hydrokontur-v7/'+item['path'])).hexdigest()==item['sha256']
archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
(outdir/(name+'.sha256')).write_text(archive_sha+'  '+name+'\n')
print(json.dumps({'archive':str(archive),'files':len(files),'size_bytes':archive.stat().st_size,
'archive_sha256':archive_sha,'qa':qa},ensure_ascii=False,indent=2))
