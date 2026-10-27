"""Static assurance: don't accidentally turn the source gate into a decorative check."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RecoveryCIContract(unittest.TestCase):
    def test_admission_requires_real_source_and_independent_release_hash(self):
        script=(ROOT/'.github/workflows/recovery-admission.yml').read_text()
        self.assertIn('source-tree-admission:', script)
        self.assertIn('--require-external-pin', script)
        self.assertIn('HYDRO_TRUSTED_V79_ARCHIVE_SHA256', script)
        self.assertIn('HYDRO_TRUSTED_V79_MANIFEST_SHA256', script)
        self.assertIn('--require-manifest-pin', script)
        self.assertIn('needs: [source-tree-admission]', script)
        self.assertIn('server/tests_v79', script)
        self.assertNotIn('  push:\n', script)

    def test_field_ready_is_not_claimed_from_ci(self):
        wf=(ROOT/'.github/workflows/recovery-admission.yml').read_text()
        docs=(ROOT/'docs/CI_RUNNER_INCIDENT_2026-10-27.md').read_text()
        self.assertIn('separate mandatory gates', wf)
        self.assertIn('RUNNER_NOT_ASSIGNED', docs)
        self.assertIn('PRODUCTION_HOLD', docs)
