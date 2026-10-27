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
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        raise ImportBlocked("POTENTIAL_SECRET_FILE")
    return path


def check_secrets(data: bytes):
    if any(pattern.search(data) for pattern in SECRETS):
        raise ImportBlocked("HIGH_CONFIDENCE_SECRET_DETECTED")


def inspect_tree(root: Path) -> list[dict]:
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
        folded = rel.casefold()
        if folded in visited:
            raise ImportBlocked("CASE_INSENSITIVE_DUPLICATE_PATH")
        visited.add(folded)
        size = p.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or len(records) >= MAX_FILES:
            raise ImportBlocked("SOURCE_TREE_SIZE_LIMIT")
        if size < 5 * 1024 * 1024:
            check_secrets(p.read_bytes())
        records.append({"path": rel, "bytes": size, "sha256": sha256_file(p)})
    files = {entry["path"] for entry in records}
    missing = sorted(set(REQUIRED) - files)
    if missing:
        raise ImportBlocked("REQUIRED_SOURCE_FILES_MISSING: " + ", ".join(missing))
    migration_paths = [p for p in files if re.fullmatch(r"server/migrations/\d{3}_[^/]+\.sql", p)]
    numbers = [Path(p).name[:3] for p in migration_paths]
    if sorted(numbers) != list(MIGRATIONS):
        raise ImportBlocked("MIGRATION_SEQUENCE_MISMATCH")
    return records


def extract_zip(source: Path, temp: Path):
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
            if str(rel).casefold() in seen:
                raise ImportBlocked("DUPLICATE_ARCHIVE_PATH")
            seen.add(str(rel).casefold())
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise ImportBlocked("SOURCE_TREE_SIZE_LIMIT")
            if info.file_size > 1024 * 1024 and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise ImportBlocked("SUSPICIOUS_COMPRESSION_RATIO")
            dst = temp / str(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, dst.open("wb") as out:
                copied = shutil.copyfileobj(src, out, length=1024 * 1024)
            if dst.stat().st_size != info.file_size:
                raise ImportBlocked("EXTRACT_SIZE_MISMATCH")


def extract_bundle(source: Path, temp: Path):
    if source.stat().st_size > MAX_TOTAL_BYTES:
        raise ImportBlocked("BUNDLE_TOO_LARGE")
    subprocess.run(["git", "clone", "--quiet", "--no-local", "--", str(source), str(temp)],
                   check=True, timeout=90, capture_output=True)
    git_dir = temp / ".git"
    if not git_dir.is_dir():
        raise ImportBlocked("BUNDLE_CLONE_MISSING_GIT_METADATA")
    shutil.rmtree(git_dir)


def recover(source: Path, destination: Path) -> dict:
    if not source.is_file() or source.suffix.lower() not in {".zip", ".bundle"}:
        raise ImportBlocked("EXPECTED_EXISTING_ZIP_OR_GIT_BUNDLE")
    if destination.exists():
        raise ImportBlocked("TARGET_MUST_NOT_EXIST")
    if not destination.parent.is_dir():
        raise ImportBlocked("TARGET_PARENT_MISSING")
    digest = sha256_file(source)
    with tempfile.TemporaryDirectory(prefix="magadan-v79-", dir=destination.parent) as tmp:
        stage = Path(tmp) / "source"
        if source.suffix.lower() == ".zip":
            stage.mkdir()
            extract_zip(source, stage)
        else:
            extract_bundle(source, stage)
        records = inspect_tree(stage)
        report = {
            "classification": "SOURCE_IMPORT_STAGED_NOT_ACCEPTED",
            "archive_name": source.name,
            "archive_sha256": digest,
            "file_count": len(records),
            "files": records,
            "engineering_tests_passed": False,
            "native_postgresql_accepted": False,
            "production_ready": False,
        }
        (stage / "SOURCE_RECOVERY_MANIFEST.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(stage, destination)
    return {k: v for k, v in report.items() if k != "files"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing V7.9 .zip or .bundle")
    parser.add_argument("--destination", required=True, type=Path,
                        help="New, non-existing staging directory, never repository root")
    args = parser.parse_args()
    try:
        print(json.dumps(recover(args.source.resolve(), args.destination.resolve()),
                         ensure_ascii=False, indent=2))
        return 0
    except (ImportBlocked, zipfile.BadZipFile, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print("SOURCE_RECOVERY_BLOCKED: " + str(exc).split("\n")[0], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())