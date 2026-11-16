#!/usr/bin/env python3
"""Offline recovery of a V7.9 ZIP or Git bundle into a new isolated staging tree.

This does not publish to GitHub, run engineering tests, or claim production safety.
Never extracts symlinks or overwrites a target. Run additional gitleaks and reviews.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

MAX_FILES = 2000
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 160 * 1024 * 1024
MAX_RATIO = 800
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_PATH_BYTES = 512
DOS_DEVICE = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)
REQUIRED = (
    "server/hydro_api/main.py",
    "server/hydro_api/storage.py",
    "server/hydro_api/benefit_ledger_v79.py",
    "server/hydro_api/measurement_v79.py",
    "server/hydro_api/grid_cashflow_v78.py",
    "server/migrations/001_schema.sql",
    "server/migrations/130_benefit_ledger_v79.sql",
    "server/migrations/140_measurement_screen_v79.sql",
    "server/tests_v79/test_benefit_registry.py",
    "v6-client/package.json",
    "scripts/reproduce_v79.py",
)
MIGRATIONS = ("001", "010", "020", "030", "040", "050", "060", "070",
              "080", "090", "100", "110", "120", "130", "140")

RELEASES = {
    "v7.9": {"required": REQUIRED, "migrations": MIGRATIONS},
    "v8.0": {"required": REQUIRED + ("server/migrations/150_boundary_graph_v8.sql",),
             "migrations": MIGRATIONS + ("150",)},
}


def release_spec(release: str) -> dict:
    try:
        return RELEASES[release]
    except (KeyError, TypeError):
        raise ImportBlocked("UNSUPPORTED_SOURCE_RELEASE") from None
REJECT_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
# High-confidence signatures only; use dedicated secret scanning before publication.
SECRETS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{24,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{25,}"),
    re.compile(rb"sk-proj-[A-Za-z0-9_-]{24,}"),
    re.compile(rb"nfp_[A-Za-z0-9]{24,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class ImportBlocked(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def safe_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise ImportBlocked("INVALID_ARCHIVE_PATH")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in name.rstrip("/").split("/")):
        raise ImportBlocked("ARCHIVE_PATH_ESCAPE")
    if any(p in REJECT_DIRS for p in path.parts):
        raise ImportBlocked("UNSAFE_TRACKED_DIRECTORY")
    if len(name.encode("utf-8", errors="surrogatepass")) > MAX_PATH_BYTES:
        raise ImportBlocked("ARCHIVE_PATH_TOO_LONG")
    if any(("\x00" <= c < "\x20") or c == "\x7f" for c in name):
        raise ImportBlocked("ARCHIVE_PATH_CONTROL_CHARACTER")
    if any(part.endswith((".", " ")) or ":" in part or DOS_DEVICE.match(part) for part in path.parts):
        raise ImportBlocked("CROSS_PLATFORM_INVALID_FILENAME")
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        raise ImportBlocked("POTENTIAL_SECRET_FILE")
    return path


def check_secrets(data: bytes):
    if any(pattern.search(data) for pattern in SECRETS):
        raise ImportBlocked("HIGH_CONFIDENCE_SECRET_DETECTED")


def inspect_tree(root: Path, release: str = "v7.9") -> list[dict]:
    spec = release_spec(release)
    records: list[dict] = []
    visited = set()
    total = 0
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ImportBlocked("SYMLINK_NOT_ALLOWED")
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        safe_path(rel)
        folded = unicodedata.normalize("NFC", rel).casefold()
        if folded in visited:
            raise ImportBlocked("CASE_INSENSITIVE_DUPLICATE_PATH")
        visited.add(folded)
        size = p.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or len(records) >= MAX_FILES:
            raise ImportBlocked("SOURCE_TREE_SIZE_LIMIT")
        # Scan EVERY bounded source file, including large assets: the previous
        # <5 MiB shortcut left a simple high-confidence secret bypass.
        content = p.read_bytes()
        check_secrets(content)
        if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            raise ImportBlocked("GIT_LFS_POINTER_NOT_SOURCE_CODE")
        records.append({"path": rel, "bytes": size, "sha256": sha256_file(p)})
    files = {entry["path"] for entry in records}
    missing = sorted(set(spec["required"]) - files)
    if missing:
        raise ImportBlocked("REQUIRED_SOURCE_FILES_MISSING: " + ", ".join(missing))
    migration_paths = [p for p in files if re.fullmatch(r"server/migrations/\d{3}_[^/]+\.sql", p)]
    numbers = [Path(p).name[:3] for p in migration_paths]
    if sorted(numbers) != list(spec["migrations"]):
        raise ImportBlocked("MIGRATION_SEQUENCE_MISMATCH")
    if release == "v8.0":
        if not any(re.fullmatch(r"server/hydro_api/[^/]*boundary[^/]*v8[^/]*\.py", p) for p in files):
            raise ImportBlocked("V8_BOUNDARY_ENGINE_NOT_PRESENT")
        if not any(re.fullmatch(r"server/tests_v8/[^/]+\.py", p) for p in files):
            raise ImportBlocked("V8_TEST_SUITE_NOT_PRESENT")
    return records


def extract_zip(source: Path, temp: Path):
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ImportBlocked("ARCHIVE_CONTAINER_TOO_LARGE")
    with zipfile.ZipFile(source) as archive:
        entries = [x for x in archive.infolist() if not x.is_dir()]
        if len(entries) > MAX_FILES:
            raise ImportBlocked("SOURCE_TREE_SIZE_LIMIT")
        paths = [safe_path(x.filename) for x in entries]
        if not paths:
            raise ImportBlocked("EMPTY_ARCHIVE")
        # One optional root directory, such as hydrokontur-v79/.
        first = {p.parts[0] for p in paths}
        strip = len(first) == 1 and all(len(p.parts) > 1 for p in paths)
        seen = set()
        total = 0
        for info, path in zip(entries, paths):
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                raise ImportBlocked("UNSAFE_ARCHIVE_FILE_TYPE")
            rel = PurePosixPath(*path.parts[1:]) if strip else path
            safe_path(str(rel))
            canonical = unicodedata.normalize("NFC", str(rel)).casefold()
            if canonical in seen:
                raise ImportBlocked("DUPLICATE_ARCHIVE_PATH")
            seen.add(canonical)
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise ImportBlocked("SOURCE_TREE_SIZE_LIMIT")
            if info.file_size > 1024 * 1024 and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise ImportBlocked("SUSPICIOUS_COMPRESSION_RATIO")
            dst = temp / str(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, dst.open("wb") as out:
                copied = 0
                while True:
                    chunk = src.read(min(1024 * 1024, info.file_size - copied + 1))
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > info.file_size or copied > MAX_FILE_BYTES:
                        raise ImportBlocked("EXTRACT_SIZE_MISMATCH")
                    out.write(chunk)
            if dst.stat().st_size != info.file_size:
                raise ImportBlocked("EXTRACT_SIZE_MISMATCH")


def extract_bundle(source: Path, temp: Path):
    if source.stat().st_size > MAX_TOTAL_BYTES:
        raise ImportBlocked("BUNDLE_TOO_LARGE")
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ImportBlocked("ARCHIVE_CONTAINER_TOO_LARGE")
    # Disable ambient Git config and smudge filters for untrusted backup content.
    safe_env = os.environ.copy()
    safe_env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                     "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"})
    with tempfile.TemporaryDirectory(prefix="git-bundle-verify-", dir=temp.parent) as git_check:
        subprocess.run(["git", "init", "--quiet", "--bare", git_check],
                       check=True, timeout=15, capture_output=True, env=safe_env)
        subprocess.run(["git", "-C", git_check, "bundle", "verify", str(source)],
                       check=True, timeout=30, capture_output=True, env=safe_env)
    subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                    "clone", "--quiet", "--no-local", "--", str(source), str(temp)],
                   check=True, timeout=90, capture_output=True, env=safe_env)
    git_dir = temp / ".git"
    if not git_dir.is_dir():
        raise ImportBlocked("BUNDLE_CLONE_MISSING_GIT_METADATA")
    shutil.rmtree(git_dir)


def recover(source: Path, destination: Path, expected_sha256: str | None = None,
            release: str = "v7.9") -> dict:
    release_spec(release)
    if not source.is_file() or source.suffix.lower() not in {".zip", ".bundle"}:
        raise ImportBlocked("EXPECTED_EXISTING_ZIP_OR_GIT_BUNDLE")
    if destination.exists():
        raise ImportBlocked("TARGET_MUST_NOT_EXIST")
    if not destination.parent.is_dir():
        raise ImportBlocked("TARGET_PARENT_MISSING")
    digest = sha256_file(source)
    if expected_sha256 and digest.casefold() != expected_sha256.casefold():
        raise ImportBlocked("ARCHIVE_HASH_NOT_MATCHING_INDEPENDENT_REFERENCE")
    with tempfile.TemporaryDirectory(prefix="magadan-v79-", dir=destination.parent) as tmp:
        stage = Path(tmp) / "source"
        if source.suffix.lower() == ".zip":
            stage.mkdir()
            extract_zip(source, stage)
        else:
            extract_bundle(source, stage)
        records = inspect_tree(stage, release)
        report = {
            "source_release": release,
            "classification": "SOURCE_IMPORT_STAGED_NOT_ACCEPTED",
            "archive_name": source.name,
            "archive_sha256": digest,
            "independent_archive_sha256_parameter_supplied": expected_sha256 is not None,
            "file_count": len(records),
            "files": records,
            "engineering_tests_passed": False,
            "native_postgresql_accepted": False,
            "production_ready": False,
        }
        mf_path = stage / "SOURCE_RECOVERY_MANIFEST.json"
        mf_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # The digest is returned OUTSIDE the manifest to avoid circular hashes.
        # It must be verified through a separate trusted release record; merely
        # computing this value locally does NOT constitute independent approval.
        manifest_sha256 = sha256_file(mf_path)
        os.replace(stage, destination)
    return {**{k: v for k, v in report.items() if k != "files"},
            "manifest_sha256": manifest_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing V7.9 .zip or .bundle")
    parser.add_argument("--destination", required=True, type=Path,
                        help="New, non-existing staging directory, never repository root")
    parser.add_argument("--release", choices=tuple(RELEASES), default="v7.9",
                        help="Exact source version: v7.9 (001-140) or v8.0 (001-150)")
    parser.add_argument("--expected-sha256", metavar="HEX", default=None,
                        help="Optional independently confirmed SHA-256 of original archive")
    args = parser.parse_args()
    if args.expected_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256):
        parser.error("--expected-sha256 must contain exactly 64 hex digits")
    try:
        print(json.dumps(recover(args.source.resolve(), args.destination.resolve(), args.expected_sha256,
                                 release=args.release),
                         ensure_ascii=False, indent=2))
        return 0
    except (ImportBlocked, zipfile.BadZipFile, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("SOURCE_RECOVERY_BLOCKED: " + str(exc).split("\n")[0], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
