"""Deterministic source bundle with SHA-256 inventory; never includes secrets/DB."""
import hashlib, json, os, zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
archive=Path('/mnt/data/HydroKontur_360_Magadan_V7_2_Engineering_Source_Tests.zip')
ignore={'.pytest_cache','__pycache__','node_modules','.git','.venv'}
files=[]
for f in root.rglob('*'):
    if not f.is_file() or f.is_symlink():continue
    relative=f.relative_to(root)
    if any(segment in ignore for segment in relative.parts):continue
    if relative.name in {'.env','native-local-credentials.json','MANIFEST_SHA256_V72.json'}:continue
    if f.suffix in {'.db','.sqlite','.pyc','.pyo'}:continue
    files.append((relative,f))
files.sort(key=lambda t:t[0].as_posix())
manifest={rel.as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for rel,f in files}
manifest_path=root/'MANIFEST_SHA256_V72.json'
manifest_path.write_text(json.dumps({'release':'0.7.2-laboratory','files':manifest},indent=2))
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for rel,f in files:z.write(f,'hydrokontur-v72/'+rel.as_posix())
    z.write(manifest_path,'hydrokontur-v72/MANIFEST_SHA256_V72.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for rel,digest in manifest.items():
        assert hashlib.sha256(z.read('hydrokontur-v72/'+rel)).hexdigest()==digest,rel
print(json.dumps({'bundle':str(archive),'files':len(manifest)+1,'size_bytes':archive.stat().st_size,
                  'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'manifest_verified':True},indent=2))
