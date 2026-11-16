"""Регрессионная гигиена навигации, метаданных и артефактов V9."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT_VERSION = "9.6.1"
V9_DOCS = (
    "V9_OPEN_SCIENCE_MODULES_RU.md",
    "V9_OPEN_DATA_DOSSIER_RU.md",
    "V91_OPEN_SCIENCE_EXTENSION_RU.md",
    "V92_REAL_DATA_BACKTEST_RU.md",
    "V93_EMOS_CALIBRATION_RU.md",
    "V94_TREND_ADAPTIVE_AND_FOR_RU.md",
    "V95_REGIONAL_TREND_AND_ADEQUACY_RU.md",
    "V96_LOWFLOW_AND_SEASONAL_ADEQUACY_RU.md",
)


def test_current_version_and_data_description_are_consistent() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"**Версия: {CURRENT_VERSION}" in readme
    assert f"version: {CURRENT_VERSION}" in citation
    assert f"## [{CURRENT_VERSION}]" in changelog
    assert "Все данные в репозитории синтетические" not in readme
    assert "R-ArcticNET" in readme
    assert "объектных эксплуатационных данных РусГидро нет" in citation


def test_every_v9_methodology_is_linked_from_documentation_index() -> None:
    index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    for name in V9_DOCS:
        assert (ROOT / "docs" / name).is_file(), name
        assert f"]({name})" in index, name


def test_artifact_registry_covers_every_v9_json() -> None:
    registry = (ROOT / "artifacts_v9" / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\[([a-z0-9_]+\.json)\]\(", registry))
    actual = {p.name for p in (ROOT / "artifacts_v9").glob("*.json")}
    assert actual
    assert linked == actual


def test_artifact_internal_receipts_are_registered() -> None:
    registry = (ROOT / "artifacts_v9" / "README.md").read_text(encoding="utf-8")
    paths = sorted((ROOT / "artifacts_v9").glob("*.json"))
    assert paths
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        receipt = payload.get("artifact_sha256") or payload.get("sha256")
        assert isinstance(receipt, str) and re.fullmatch(r"[0-9a-f]{64}", receipt)
        assert receipt in registry, path.name


def test_tracked_tree_excludes_caches_secrets_and_bulk_open_data() -> None:
    proc = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    tracked = proc.stdout.splitlines()
    forbidden = [
        path
        for path in tracked
        if path.startswith("data/open/")
        or "__pycache__/" in path
        or ".pytest_cache/" in path
        or "node_modules/" in path
        or path == ".env"
        or path.endswith("-credentials.json")
    ]
    assert forbidden == []
