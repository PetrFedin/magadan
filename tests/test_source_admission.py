"""Admission regression: docs-only repos must not be reported as accepted."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.check_source_admission import AdmissionBlocked, check
from tools.import_v79_snapshot import recover
from tests.test_import_v79_snapshot import fixture_files


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'source.zip'
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path, content in fixture_files().items():
                z.writestr('hydrokontur-v79/' + path, content)
        self.stage = self.root / 'staged'

    def test_fails_docs_only(self):
        self.stage.mkdir()
        (self.stage / 'README.md').write_text('# Research project')
        with self.assertRaisesRegex(AdmissionBlocked, 'REQUIRED_SOURCE_FILES_MISSING'):
            check(self.stage)

    def test_fixture_staged_source_has_only_manifest_level_status(self):
        recover(self.archive, self.stage)
        r = check(self.stage)
        self.assertEqual(r['status'], 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY')
        self.assertFalse(r['source_tests_executed'])
        self.assertFalse(r['industrial_approval_eligible'])

    def test_tamper_after_recovery_fails(self):
        recover(self.archive, self.stage)
        (self.stage / 'server/hydro_api/main.py').write_text('modified')
        with self.assertRaisesRegex(AdmissionBlocked, 'SOURCE_FILE_.*DRIFT'):
            check(self.stage)

    def test_missing_manifest_fails(self):
        recover(self.archive, self.stage)
        (self.stage / 'SOURCE_RECOVERY_MANIFEST.json').unlink()
        with self.assertRaisesRegex(AdmissionBlocked, 'PROVENANCE_MANIFEST_MISSING'):
            check(self.stage)

    def test_manifest_cannot_upgrade_production_flag(self):
        recover(self.archive, self.stage)
        mf = self.stage / 'SOURCE_RECOVERY_MANIFEST.json'
        data = json.loads(mf.read_text()); data['production_ready'] = True
        mf.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdmissionBlocked, 'MANIFEST_FALSIFIES'):
            check(self.stage)

    def test_migration_sequence_change_fails(self):
        recover(self.archive, self.stage)
        (self.stage / 'server/migrations/090_fixture.sql').unlink()
        with self.assertRaisesRegex(AdmissionBlocked, 'MIGRATION_SEQUENCE_MISMATCH'):
            check(self.stage)

    def test_manifest_path_escape_fails(self):
        recover(self.archive, self.stage)
        mf = self.stage / 'SOURCE_RECOVERY_MANIFEST.json'
        data = json.loads(mf.read_text())
        data['files'][0]['path'] = '../../outside.txt'
        mf.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdmissionBlocked, 'DANGEROUS_MANIFEST_PATH'):
            check(self.stage)


    def test_manifest_file_count_cannot_be_forged(self):
        recover(self.archive, self.stage)
        p = self.stage / 'SOURCE_RECOVERY_MANIFEST.json'
        data = json.loads(p.read_text()); data['file_count'] += 1
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdmissionBlocked, 'MANIFEST_FILE_COUNT_INVALID'):
            check(self.stage)

    def test_casefold_manifest_path_duplication_rejected(self):
        recover(self.archive, self.stage)
        p = self.stage / 'SOURCE_RECOVERY_MANIFEST.json'
        data = json.loads(p.read_text())
        duplicate = dict(data['files'][0])
        duplicate['path'] = duplicate['path'].swapcase()
        data['files'].append(duplicate); data['file_count'] += 1
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdmissionBlocked, 'DUPLICATE_MANIFEST_PATH'):
            check(self.stage)

    def test_unregistered_executable_source_rejected(self):
        recover(self.archive, self.stage)
        p = self.stage / 'server' / 'hydro_api' / 'forged_backend.py'
        p.write_text('def approve(): return True')
        with self.assertRaisesRegex(AdmissionBlocked, 'UNMANIFESTED_EXECUTABLE_SOURCE'):
            check(self.stage)

    def test_recovery_scaffold_docs_and_runner_metadata_are_not_original_source(self):
        recover(self.archive, self.stage)
        p = self.stage / 'docs' / 'REVIEW_NOTES.md'
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text('Do not present lab metrics as actual financial savings.')
        self.assertEqual(check(self.stage)['status'], 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY')

    def test_independent_hash_required_for_strong_provenance(self):
        recover(self.archive, self.stage)
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_ARCHIVE_SHA256_PIN_REQUIRED'):
            check(self.stage, require_external_pin=True)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        admitted = check(self.stage, digest, require_external_pin=True)
        self.assertTrue(admitted['external_source_hash_pinned'])
        self.assertFalse(admitted['source_tests_executed'])
        self.assertFalse(admitted['industrial_approval_eligible'])
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_PIN_MISMATCH'):
            check(self.stage, '0'*64, require_external_pin=True)

    def test_symlink_in_protected_source_rejected(self):
        recover(self.archive, self.stage)
        link = self.stage / 'server' / 'hydro_api' / 'dangerous_link'
        link.symlink_to('../missing', target_is_directory=False)
        with self.assertRaisesRegex(AdmissionBlocked, 'UNMANIFESTED_OR_SYMLINK_SOURCE'):
            check(self.stage)

    def test_pycache_generated_by_tests_not_treated_as_source(self):
        recover(self.archive, self.stage)
        cache = self.stage / 'server' / 'hydro_api' / '__pycache__'
        cache.mkdir()
        (cache / 'compiled.cpython-313.pyc').write_bytes(b'not real bytecode')
        self.assertEqual(check(self.stage)['status'], 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY')


if __name__ == '__main__':
    unittest.main()
