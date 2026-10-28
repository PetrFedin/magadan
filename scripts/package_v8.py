"""Create verified lab release without machine-specific temporary files."""
from pathlib import Path
import hashlib, json, zipfile, os
root=Path(__file__).resolve().parents[1]
out=Path('/mnt/data/HydroKontur_360_Magadan_V8_0_Boundary_MV_Engineering_Source_Tests.zip')
manifest=root/'MANIFEST_SHA256_V8.json'
excluded={'.git','.pytest_cache','__pycache__','node_modules','.venv','.mypy_cache'}
files=sorted((p for p in root.rglob('*') if p.is_file() and p!=manifest
             and not any(x in excluded for x in p.relative_to(root).parts)
             and p.suffix not in ('.pyc','.pyo','.db','.sqlite','.sqlite3','.db-journal','.db-wal','.db-shm')),
             key=lambda p:p.relative_to(root).as_posix())
checks={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest.write_text(json.dumps({'release':'V8.0','file_count':len(checks),'files':checks},ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7,allowZip64=True) as z:
 for p in files+[manifest]:z.write(p,p.relative_to(root).as_posix())
with zipfile.ZipFile(out) as z:
 bad=z.testzip()
 if bad is not None:raise RuntimeError('ZIP_BAD_MEMBER:'+bad)
 meta=json.loads(z.read('MANIFEST_SHA256_V8.json'))
 assert len(meta['files'])==len(files)
 for k,digest in meta['files'].items():
  actual=hashlib.sha256(z.read(k)).hexdigest()
  if actual!=digest:raise RuntimeError('MANIFEST_MISMATCH:'+k)
 assert len(z.namelist())==len(files)+1
print(json.dumps({'archive':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'files_total':len(files)+1,'manifest_verified':len(files),'zip_integrity':True},indent=2))
