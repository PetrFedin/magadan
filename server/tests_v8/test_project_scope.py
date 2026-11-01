"""Prevent accidental cross-project contamination of HydroKontur's active runtime.

The domain boundary is RusHydro-relevant energy infrastructure research in
Magadan Oblast. This is not a representation of a signed relationship with any
operator and does not constitute operational control of energy infrastructure.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = (
    ROOT / 'server/hydro_api',
    ROOT / 'server/ui',
    ROOT / 'server/migrations',
    ROOT / 'v6-client',
    ROOT / 'scripts',
)
SCANNABLE_SUFFIXES = {'.py', '.sql', '.js', '.jsx', '.ts', '.tsx', '.json', '.html', '.css', '.sh'}
UNRELATED_NAMES = re.compile(r'беринг[а-яё]*|b[ée]ring[a-z]*', re.IGNORECASE)
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.pytest_cache', 'venv', '.venv'}


def test_canonical_project_identity_and_production_hold():
    # The original V8 ZIP retained an older root README; V8's authoritative
    # research scope lives in README_V8.md. The integration branch has an
    # updated top-level README. Both layouts are legitimate source snapshots.
    readmes = ((ROOT / 'README.md').read_text(encoding='utf-8') + '\n' +
               (ROOT / 'README_V8.md').read_text(encoding='utf-8'))
    assert 'ГИДРОКОНТУР 360' in readmes or 'HYDROKONTUR 360' in readmes
    assert 'МАГАДАН' in readmes or 'MAGADAN' in readmes
    assert 'РусГидро' in readmes or 'RusHydro' in readmes
    assert 'PRODUCTION HOLD' in readmes or 'Production HOLD' in readmes
    assert (ROOT / 'server/hydro_api/boundary_v8.py').is_file()
    assert (ROOT / 'server/hydro_api/benefit_ledger_v79.py').is_file()
    assert (ROOT / 'server/migrations/150_boundary_graph_v8.sql').is_file()


def test_no_unrelated_project_is_embedded_in_active_code():
    matches = []
    for folder in SOURCE_ROOTS:
        assert folder.exists(), f'Missing source root: {folder.relative_to(ROOT)}'
        for path in folder.rglob('*'):
            if not path.is_file() or set(path.parts) & SKIP_DIRS:
                continue
            if path.suffix.lower() not in SCANNABLE_SUFFIXES:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if UNRELATED_NAMES.search(rel):
                matches.append(f'path: {rel}')
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if UNRELATED_NAMES.search(line):
                    matches.append(f'{rel}:{lineno}')
    assert not matches, ('Unapproved cross-project reference in live code; '
                         'handle any addition through an explicit, independently '
                         'reviewed scope change: ' + ', '.join(matches[:30]))


def test_expansions_require_an_explicit_scope_record():
    boundary = (ROOT / 'docs/PROJECT_SCOPE_MAGADAN_RUSHYDRO.md').read_text(encoding='utf-8')
    assert 'Беринг' in boundary  # names the excluded project in a non-runtime document
    assert 'Магаданской области' in boundary
    assert 'РусГидро' in boundary
    assert 'PRODUCTION HOLD' in boundary
