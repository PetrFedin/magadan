"""Admission regression: docs-only repos must not be reported as accepted."""
import json
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


if __name__ == '__main__':
    unittest.main()