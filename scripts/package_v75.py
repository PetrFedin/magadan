#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/mnt/data/HydroKontur_360_Magadan_V7_5_Deep_Engineering_Source_Tests.zip')
MANIFEST=ROOT/'MANIFEST_SHA256_V75.json'
EXCLUDE_DIRS={'.pytest_cache','__pycache__','.git','.venv','node_modules','hydro_v75_tmp'}
EXCLUDE_EXTS={'.pyc','.db','.sqlite','.sqlite3','.db-journal','.db-wal','.db-shm'}

def file_ok(p):
    rel=p.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):return False
    if p.suffix in EXCLUDE_EXTS:return False
    if p.name in {MANIFEST.name} or (p.name.startswith('.env') and p.name!='.env.example'):return False
    return p.is_file()

paths=sorted(p for p in ROOT.rglob('*') if file_ok(p))
files={str(p.relative_to(ROOT)).replace('\\','/'): {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size} for p in paths}
manifest={'release':'V7.5-LAB','manifest_scope':'all packaged project files except this manifest','date':'2026-10-23','files':files,'production_ready':False}
MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for p in paths:z.write(p,arcname='hydrokontur-v75/'+str(p.relative_to(ROOT)).replace('\\','/'))
    z.write(MANIFEST,arcname='hydrokontur-v75/'+MANIFEST.name)
with zipfile.ZipFile(OUT) as z:
    bad=z.testzip()
    if bad:raise RuntimeError(f'CORRUPT_ZIP:{bad}')
    archive_paths=[k for k in z.namelist() if not k.endswith('/')]
    assert len(archive_paths)==len(files)+1
    for rel,m in files.items():
        b=z.read('hydrokontur-v75/'+rel)
        if hashlib.sha256(b).hexdigest()!=m['sha256']:raise RuntimeError(f'SHA_MISMATCH:{rel}')
    m2=json.loads(z.read('hydrokontur-v75/'+MANIFEST.name))
    assert m2==manifest
s={'release':'V7.5-LAB','file_count':len(files)+1,'archive_bytes':OUT.stat().st_size,'archive_mib':round(OUT.stat().st_size/2**20,2),'archive_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'zip_integrity':'PASS','manifest_integrity':'PASS','production_ready':False}
Path('/mnt/data/hydro_v75/v75_package_summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(s,ensure_ascii=False))
