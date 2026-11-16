"""Offline fixture tests; these do not certify the unavailable real V7.9 archive."""
import hashlib
import os
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile

from tools.import_v79_snapshot import ImportBlocked, MIGRATIONS, REQUIRED, recover


def fixture_files():
    entries = {p: "# synthetic fixture\n" for p in REQUIRED}
    for prefix in MIGRATIONS:
        if not any(f"migrations/{prefix}_" in p for p in entries):
            entries[f"server/migrations/{prefix}_fixture.sql"] = "-- synthetic fixture\n"
    return entries


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.zip_path = self.root / "test.zip"

    def pack(self, files, symlink=None):
        with zipfile.ZipFile(self.zip_path, "w", zipfile.ZIP_DEFLATED) as out:
            for name, content in files.items():
                out.writestr("hydrokontur-v79/" + name, content)
            if symlink:
                info = zipfile.ZipInfo("hydrokontur-v79/" + symlink)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                out.writestr(info, "../outside")

    def test_valid_stage_and_manifest(self):
        self.pack(fixture_files())
        dest = self.root / "staged"
        result = recover(self.zip_path, dest)
        self.assertEqual(result["file_count"], len(fixture_files()))
        self.assertTrue((dest / "server/hydro_api/main.py").is_file())
        metadata = json.loads((dest / "SOURCE_RECOVERY_MANIFEST.json").read_text())
        self.assertFalse(metadata["production_ready"])
        self.assertEqual(len(metadata["files"]), len(fixture_files()))

    def test_missing_file_blocks_with_no_partial_destination(self):
        data = fixture_files(); del data[REQUIRED[0]]
        self.pack(data)
        dest = self.root / "staged"
        with self.assertRaisesRegex(ImportBlocked, "REQUIRED_SOURCE_FILES_MISSING"):
            recover(self.zip_path, dest)
        self.assertFalse(dest.exists())

    def test_zip_path_traversal_blocks(self):
        data = fixture_files(); data["../../../escape.txt"] = "bad"
        self.pack(data)
        with self.assertRaises(ImportBlocked):
            recover(self.zip_path, self.root / "staged")

    def test_symlink_blocks(self):
        self.pack(fixture_files(), symlink="bad_link")
        with self.assertRaisesRegex(ImportBlocked, "UNSAFE_ARCHIVE_FILE_TYPE"):
            recover(self.zip_path, self.root / "staged")

    def test_secret_blocks(self):
        data = fixture_files(); data["secrets.txt"] = "-----BEGIN PRIVATE KEY-----\nabc\n"
        self.pack(data)
        with self.assertRaisesRegex(ImportBlocked, "SECRET"):
            recover(self.zip_path, self.root / "staged")

    def test_env_blocks(self):
        data = fixture_files(); data[".env"] = "NO\n"
        self.pack(data)
        with self.assertRaisesRegex(ImportBlocked, "SECRET_FILE"):
            recover(self.zip_path, self.root / "staged")

    def test_wrong_migration_sequence_blocks(self):
        data = fixture_files(); del data["server/migrations/020_fixture.sql"]
        self.pack(data)
        with self.assertRaisesRegex(ImportBlocked, "MIGRATION_SEQUENCE"):
            recover(self.zip_path, self.root / "staged")

    def test_case_collision_blocks(self):
        data = fixture_files(); data["src/A.txt"] = "a"; data["src/a.txt"] = "b"
        self.pack(data)
        with self.assertRaisesRegex(ImportBlocked, "DUPLICATE"):
            recover(self.zip_path, self.root / "staged")

    def test_existing_destination_preserved(self):
        self.pack(fixture_files())
        dest = self.root / "staged"; dest.mkdir()
        with self.assertRaisesRegex(ImportBlocked, "TARGET_MUST_NOT_EXIST"):
            recover(self.zip_path, dest)


    def test_wrong_independent_sha_blocks_and_does_not_create_destination(self):
        self.pack(fixture_files())
        dest = self.root / "staged"
        with self.assertRaisesRegex(ImportBlocked, "ARCHIVE_HASH_NOT_MATCHING"):
            recover(self.zip_path, dest, "0" * 64)
        self.assertFalse(dest.exists())
        good = hashlib.sha256(self.zip_path.read_bytes()).hexdigest()
        result = recover(self.zip_path, dest, good.upper())
        self.assertEqual(result["archive_sha256"], good)

    def test_windows_reserved_device_name_is_blocked(self):
        files = fixture_files(); files["some/CON.txt"] = "unsafe on Windows"
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "CROSS_PLATFORM_INVALID_FILENAME"):
            recover(self.zip_path, self.root / "staged")

    def test_windows_drive_ads_and_trailing_space_are_blocked(self):
        for name in ("docs/report.txt:evil", "some/trailing .", "src/hello "):
            with self.subTest(name=name):
                files = fixture_files(); files[name] = "data"
                self.pack(files)
                with self.assertRaisesRegex(ImportBlocked, "CROSS_PLATFORM_INVALID_FILENAME"):
                    recover(self.zip_path, self.root / "staged")

    def test_unicode_normalization_collision_is_blocked(self):
        files = fixture_files()
        files["docs/caf\u00e9.md"] = "one"
        files["docs/cafe\u0301.md"] = "two"
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "DUPLICATE_ARCHIVE_PATH"):
            recover(self.zip_path, self.root / "staged")

    def test_lfs_pointer_is_not_accepted_as_real_source(self):
        files = fixture_files()
        files["server/hydro_api/main.py"] = (
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "a" * 64 + "\nsize 1290\n"
        )
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "GIT_LFS_POINTER_NOT_SOURCE_CODE"):
            recover(self.zip_path, self.root / "staged")

    def test_reject_compression_ratio_bomb(self):
        files = fixture_files(); files["docs/fill.bin"] = b"0" * (3 * 1024 * 1024)
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "SUSPICIOUS_COMPRESSION_RATIO"):
            recover(self.zip_path, self.root / "staged")

    def test_reject_extra_migration(self):
        files = fixture_files()
        files["server/migrations/145_unreviewed.sql"] = "-- synthetic"
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "MIGRATION_SEQUENCE_MISMATCH"):
            recover(self.zip_path, self.root / "staged")

    def test_reject_high_confidence_token(self):
        files = fixture_files()
        files["tokens.txt"] = "ghp_" + "A" * 36
        self.pack(files)
        with self.assertRaisesRegex(ImportBlocked, "HIGH_CONFIDENCE_SECRET_DETECTED"):
            recover(self.zip_path, self.root / "staged")

    def test_high_confidence_token_inside_large_binary_is_detected(self):
        # Former security gap: source files over 5 MiB bypassed secret scan.
        data = fixture_files()
        data['artifacts_v79/large_binary.bin'] = (os.urandom(5 * 1024 * 1024)
            + b"--test-marker--ghp_" + b'A' * 36)
        self.pack(data)
        with self.assertRaisesRegex(ImportBlocked, 'HIGH_CONFIDENCE_SECRET_DETECTED'):
            recover(self.zip_path, self.root / 'staged')

    def test_manifest_records_whether_independent_archive_digest_was_given(self):
        self.pack(fixture_files())
        expected = hashlib.sha256(self.zip_path.read_bytes()).hexdigest()
        recover(self.zip_path, self.root / 'staged', expected)
        manifest = json.loads((self.root / 'staged' / 'SOURCE_RECOVERY_MANIFEST.json').read_text())
        self.assertTrue(manifest['independent_archive_sha256_parameter_supplied'])

    def test_full_git_bundle_offline(self):
        src = self.root / "repo"; src.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
        subprocess.run(["git", "-C", str(src), "config", "user.name", "Recovery Test"], check=True)
        subprocess.run(["git", "-C", str(src), "config", "user.email", "recovery@example.invalid"], check=True)
        for name, content in fixture_files().items():
            p = src / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
        subprocess.run(["git", "-C", str(src), "add", "."], check=True)
        subprocess.run(["git", "-C", str(src), "commit", "-qm", "fixture"], check=True)
        bundle = self.root / "fixture.bundle"
        subprocess.run(["git", "-C", str(src), "bundle", "create", str(bundle), "--all"], check=True)
        result = recover(bundle, self.root / "staged")
        self.assertGreater(result["file_count"], 20)


if __name__ == "__main__":
    unittest.main()
