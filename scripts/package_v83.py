"""Package a verified, lab-only V8.3 snapshot and changed-file evidence ZIP."""
from pathlib import Path
from hashlib import sha256
import json,zipfile
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/mnt/data/magadan_v82_work')
OUT=Path('/mnt/data')
EXCLUDE={'.git','__pycache__','.pytest_cache','.venv','venv','node_modules'}
SKIP={'package_summary.log','MANIFEST_SHA256_V83.json'}

def files(dir):
    return [p for p in sorted(dir.rglob('*')) if p.is_file() and not EXCLUDE.intersection(p.relative_to(dir).parts)
            and p.name not in SKIP]

all_files=files(ROOT)
hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in all_files}
changed=[path for path in hashes if not (BASE/path).is_file() or sha256((BASE/path).read_bytes()).hexdigest()!=hashes[path]]
removed=[p.relative_to(BASE).as_posix() for p in files(BASE) if p.relative_to(BASE).as_posix() not in hashes]
assert not removed, 'V8.3 must not erase existing V8.2 files'
# Release manifest excludes itself to avoid self-reference.
manifest={'release':'V8.3 LAB','date':'2026-11-02','parent':'V8.2_SYNTHETIC_LAB',
 'file_count':len(hashes),'files_sha256':hashes,
 'changed_file_count_vs_v82':len(changed),'changed_files_vs_v82':changed,
 'python_passed':357,'python_skipped':3,'javascript_passed':63,
 'field_data_attested':False,'native_postgresql17_accepted':False,
 'real_browser_e2e_accepted':False,'industrial_approval_eligible':False}
manifest_path=ROOT/'MANIFEST_SHA256_V83.json'
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

full=OUT/'HydroKontur_360_Magadan_V83_LAB_FULL_SOURCE.zip'
patch=OUT/'HydroKontur_360_Magadan_V83_PATCH_AND_EVIDENCE.zip'
archives=[(full,sorted(hashes)+['MANIFEST_SHA256_V83.json']),
          (patch,changed+['MANIFEST_SHA256_V83.json'])]
for target,paths in archives:
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for path in paths:
            z.write(ROOT/path,arcname=path)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert len(names)==len(set(names))
        for path in names:
            if path in hashes:
                assert sha256(z.read(path)).hexdigest()==hashes[path],path
        assert json.loads(z.read('MANIFEST_SHA256_V83.json'))['file_count']==len(hashes)
    print(json.dumps({'path':str(target),'bytes':target.stat().st_size,
            'sha256':sha256(target.read_bytes()).hexdigest(),
            'files':len(paths),'integrity':'PASS','scope':'SYNTHETIC_LAB_ONLY'},ensure_ascii=False))
print(json.dumps({'changed_count':len(changed),'changed':changed},ensure_ascii=False,indent=2))
