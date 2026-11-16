#!/usr/bin/env python3
"""Reproducible content-manifest ZIP for the V7.3 SYNTHETIC laboratory release."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/mnt/data/HydroKontur_360_Magadan_V7_3_Engineering_Finance_Source_Tests.zip')
manifest=ROOT/'MANIFEST_SHA256_V73.json'
exclude_names={'.DS_Store','MANIFEST_SHA256_V73.json'}
rows={}
files=[]
for f in sorted(ROOT.rglob('*')):
    if not f.is_file():continue
    if f.name in exclude_names or f.name.endswith('.pyc') or f.name.endswith('.pyo') or any(x in ('__pycache__','.pytest_cache','node_modules','.git','_scratch','tmp') for x in f.relative_to(ROOT).parts):continue
    if f.is_symlink():raise RuntimeError('Refusing release containing symlink: '+str(f))
    relative=f.relative_to(ROOT).as_posix()
    data=f.read_bytes()
    rows[relative]={'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
    files.append((relative,f))
assert len(files)>170,len(files)
output={'release':'V7.3','date':'2026-10-23','production_accepted':False,
        'scope':'SYNTHETIC_LAB_ONLY','file_count_excluding_manifest':len(files),'files':rows}
manifest.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with ZipFile(OUT,'w',ZIP_DEFLATED,compresslevel=8) as z:
    z.write(manifest,arcname='hydrokontur-v73/MANIFEST_SHA256_V73.json')
    for rel,f in files:
        z.write(f,arcname='hydrokontur-v73/'+rel)
with ZipFile(OUT,'r') as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)+1
    assert json.loads(z.read('hydrokontur-v73/MANIFEST_SHA256_V73.json'))['files']==rows
    for rel,record in rows.items():
        assert hashlib.sha256(z.read('hydrokontur-v73/'+rel)).hexdigest()==record['sha256'],rel
print(json.dumps({'zip':str(OUT),'bytes':OUT.stat().st_size,'source_files':len(files),'archive_files':len(files)+1,
    'zip_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'integrity':'PASS'},ensure_ascii=False))
