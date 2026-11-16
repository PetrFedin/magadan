#!/usr/bin/env python3
"""Build and independently recheck V7.9 delivery ZIP and hash manifest."""
import hashlib,json,zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=Path('/mnt/data/HydroKontur_360_Magadan_V7_9_Evidence_MV_Benefit_Ledger_Source_Tests.zip')
manifest=root/'MANIFEST_SHA256_V79.json'
excluded={'__pycache__','.pytest_cache','.git','.venv','node_modules'}
files=[]
for p in sorted(root.rglob('*')):
    if not p.is_file() or any(x in excluded for x in p.relative_to(root).parts):continue
    if p==manifest or p.suffix in ('.pyc','.pyo'):continue
    files.append(p)
entries={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest.write_text(json.dumps({'version':'V7.9','file_count_excluding_manifest':len(entries),'files_sha256':entries},indent=2)+'\n')
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for p in files+[manifest]: z.write(p,'hydrokontur-v79/'+str(p.relative_to(root)))
with zipfile.ZipFile(out,'r') as z:
    bad=z.testzip()
    if bad:raise RuntimeError('bad zip entry:'+bad)
    if len(z.namelist())!=len(files)+1:raise RuntimeError('zip file count mismatch')
    for rel,digest in entries.items():
        actual=hashlib.sha256(z.read('hydrokontur-v79/'+rel)).hexdigest()
        if actual!=digest:raise RuntimeError('SHA_MISMATCH:'+rel)
    actual_manifest=json.loads(z.read('hydrokontur-v79/MANIFEST_SHA256_V79.json'))
    if actual_manifest['files_sha256']!=entries:raise RuntimeError('manifest mismatch')
digest=hashlib.sha256(out.read_bytes()).hexdigest()
out.with_name(out.name+'.sha256').write_text(digest+'  '+out.name+'\n')
print(json.dumps({'archive':str(out),'sha256':digest,'bytes':out.stat().st_size,'files_hashed':len(files),'file_count_total':len(files)+1,'zip_verified':True},indent=2))
