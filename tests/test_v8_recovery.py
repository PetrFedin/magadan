"""Version-aware V7.9 and V8.0 recovery safety. Synthetic fixtures only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tests.test_import_v79_snapshot import fixture_files
from tools.import_v79_snapshot import ImportBlocked, recover
from tools.check_source_admission import AdmissionBlocked, check


def v8_fixture():
    data = fixture_files()
    data['server/migrations/150_boundary_graph_v8.sql'] = '-- synthetic migration 150\n'
    data['server/hydro_api/boundary_engine_v8.py'] = '# synthetic boundary engine\n'
    data['server/tests_v8/test_boundary.py'] = '# synthetic boundary test\n'
    return data


class V8RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'v8.zip'

    def pack(self, entries):
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, content in entries.items():
                z.writestr('hydrokontur-v8/' + name, content)

    def test_v8_archive_needs_explicit_release_choice(self):
        self.pack(v8_fixture())
        with self.assertRaisesRegex(ImportBlocked, 'MIGRATION_SEQUENCE_MISMATCH'):
            recover(self.archive, self.root/'staged')
        self.assertFalse((self.root/'staged').exists())

    def test_v8_expected_source_integrity_and_exact_version(self):
        self.pack(v8_fixture())
        result = recover(self.archive, self.root/'staged', release='v8.0')
        self.assertEqual(result['source_release'], 'v8.0')
        declared = json.loads((self.root/'staged'/'SOURCE_RECOVERY_MANIFEST.json').read_text())
        self.assertEqual(declared['source_release'], 'v8.0')
        receipt = check(self.root/'staged', expected_release='v8.0')
        self.assertEqual(receipt['status'], 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY')
        self.assertEqual(receipt['source_release'], 'v8.0')
        self.assertFalse(receipt['industrial_approval_eligible'])

    def test_v8_does_not_masquerade_as_v79(self):
        self.pack(v8_fixture())
        recover(self.archive, self.root/'staged', release='v8.0')
        with self.assertRaisesRegex(AdmissionBlocked, 'EXPECTED_SOURCE_RELEASE_MISMATCH'):
            check(self.root/'staged', expected_release='v7.9')

    def test_v8_requires_boundary_engine(self):
        files = v8_fixture()
        del files['server/hydro_api/boundary_engine_v8.py']
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, 'V8_BOUNDARY_ENGINE_NOT_PRESENT'):
            recover(self.archive, self.root/'staged', release='v8.0')

    def test_v8_requires_boundary_tests(self):
        files = v8_fixture()
        del files['server/tests_v8/test_boundary.py']
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, 'V8_TEST_SUITE_NOT_PRESENT'):
            recover(self.archive, self.root/'staged', release='v8.0')

    def test_v8_migration_150_must_be_present(self):
        files = v8_fixture()
        del files['server/migrations/150_boundary_graph_v8.sql']
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, 'REQUIRED_SOURCE_FILES_MISSING'):
            recover(self.archive, self.root/'staged', release='v8.0')

    def test_v8_manifest_cannot_claim_different_version(self):
        self.pack(v8_fixture())
        recover(self.archive, self.root/'staged', release='v8.0')
        p = self.root/'staged'/'SOURCE_RECOVERY_MANIFEST.json'
        data = json.loads(p.read_text())
        data['source_release'] = 'v7.9'
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdmissionBlocked, 'SOURCE_RELEASE_MANIFEST_MISMATCH'):
            check(self.root/'staged', expected_release='v8.0')

    def test_v8_two_pinned_hashes_are_required_for_provenance(self):
        self.pack(v8_fixture())
        sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        recover(self.archive, self.root/'staged', expected_sha256=sha, release='v8.0')
        manifest = self.root/'staged'/'SOURCE_RECOVERY_MANIFEST.json'
        manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_MANIFEST_SHA256_PIN_REQUIRED'):
            check(self.root/'staged', trusted_archive_sha256=sha,
                  require_external_pin=True, require_manifest_pin=True,
                  expected_release='v8.0')
        accepted = check(self.root/'staged', sha, True, manifest_sha, True, 'v8.0')
        self.assertTrue(accepted['external_source_hash_pinned'])
        self.assertTrue(accepted['external_manifest_hash_pinned'])
        self.assertFalse(accepted['source_tests_executed'])
        self.assertFalse(accepted['github_ci_verified'])

    def test_v8_source_code_change_is_detected(self):
        self.pack(v8_fixture())
        recover(self.archive, self.root/'staged', release='v8.0')
        (self.root/'staged'/'server/hydro_api/boundary_engine_v8.py').write_text('tampered')
        with self.assertRaisesRegex(AdmissionBlocked, 'SOURCE_FILE_.*DRIFT'):
            check(self.root/'staged', expected_release='v8.0')

    def test_unrecognized_release_is_blocked(self):
        self.pack(v8_fixture())
        with self.assertRaisesRegex(ImportBlocked, 'UNSUPPORTED_SOURCE_RELEASE'):
            recover(self.archive, self.root/'staged', release='v9.0')


if __name__ == '__main__':
    unittest.main()
