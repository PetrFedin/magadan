"""Threat model: a perfectly correct archive SHA is useless if the manifest is forged.

All examples below are isolated synthetic source fixtures. They do not represent
or validate any actual HydroKontur V7.9 archive or industrial energy data.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.import_v79_snapshot import recover
from tools.check_source_admission import AdmissionBlocked, check
from tests.test_import_v79_snapshot import fixture_files


class ManifestBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='manifest-binding-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.archive = self.root / 'source.zip'
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path, content in fixture_files().items():
                archive.writestr('hydrokontur-v79/' + path, content)
        self.stage = self.root / 'staged'
        self.metadata = recover(self.archive, self.stage)
        self.archive_pin = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.manifest = self.stage / 'SOURCE_RECOVERY_MANIFEST.json'
        self.manifest_pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def strict(self, **kwargs):
        return check(self.stage, self.archive_pin, require_external_pin=True,
                     require_manifest_pin=True, **kwargs)

    def test_importer_discloses_manifest_digest_without_self_referential_hash(self):
        self.assertEqual(self.metadata['manifest_sha256'], self.manifest_pin)
        info = json.loads(self.manifest.read_text())
        self.assertNotIn('manifest_sha256', info)
        self.assertEqual(info['archive_sha256'], self.archive_pin)

    def test_archive_pin_alone_cannot_qualify_source(self):
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_MANIFEST_SHA256_PIN_REQUIRED'):
            self.strict()

    def test_correct_two_pins_admit_only_source_tree(self):
        result = self.strict(trusted_manifest_sha256=self.manifest_pin)
        self.assertEqual(result['status'], 'SOURCE_TREE_AND_MANIFEST_MATCH_ONLY')
        self.assertTrue(result['external_manifest_hash_pinned'])
        self.assertTrue(result['external_source_hash_pinned'])
        self.assertEqual(result['source_manifest_sha256'], self.manifest_pin)
        self.assertFalse(result['source_tests_executed'])
        self.assertFalse(result['industrial_approval_eligible'])

    def test_wrong_manifest_pin_fails(self):
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_MANIFEST_SHA256_PIN_MISMATCH'):
            self.strict(trusted_manifest_sha256='0' * 64)

    def test_source_and_manifest_rehash_forgery_is_blocked(self):
        # This is the critical former bypass: attacker changes the source and
        # rewrites the list of per-file hashes while leaving the archive SHA
        # string intact. The two hashes are unbound unless the manifest also
        # has an independently established digest.
        source = self.stage / 'server' / 'hydro_api' / 'main.py'
        source.write_text('# FORGED SOURCE AFTER IMPORT\n')
        data = json.loads(self.manifest.read_text())
        for entry in data['files']:
            if entry['path'] == 'server/hydro_api/main.py':
                entry['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
                entry['bytes'] = source.stat().st_size
        self.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_MANIFEST_SHA256_PIN_MISMATCH'):
            self.strict(trusted_manifest_sha256=self.manifest_pin)

    def test_missing_external_manifest_value_not_bypassed_by_self_report(self):
        meta = json.loads(self.manifest.read_text())
        meta['manifest_sha256'] = self.manifest_pin
        self.manifest.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
        with self.assertRaisesRegex(AdmissionBlocked, 'EXTERNAL_MANIFEST_SHA256_PIN_REQUIRED'):
            self.strict()


if __name__ == '__main__':
    unittest.main()
