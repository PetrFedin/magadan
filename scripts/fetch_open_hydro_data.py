#!/usr/bin/env python3
"""Загрузка открытых гидрометеорологических данных с контролем целостности.

Использование:
    python scripts/fetch_open_hydro_data.py --dataset rarcticnet_kolyma

Принципы:
  - только публичные URL из data/reference/kolyma_magadan_open_sources.json;
  - SHA-256 файла сверяется с VERIFIED_DOWNLOADS (fail-closed при расхождении);
  - сырые файлы НЕ коммитятся в git (см. data/r-arcticnet/README.md);
    в репозитории хранится только подмножество по створу 5858.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "data" / "reference" / "kolyma_magadan_open_sources.json"

# Проверенные загрузки: sha256 вычислен по фактически скачанному файлу
# (дата первой верифицированной загрузки: 2026-11-16, протокол HTTPS).
VERIFIED_DOWNLOADS = {
    "rarcticnet_kolyma": {
        "url": "https://www.r-arcticnet.sr.unh.edu/v4.0/AllData/Anadyr_and_Kolyma_Data_m3_s.txt",
        "sha256": "c2cad85039b3163fa59bea51ce2ca8ac026aa4ffaf62f1610a6a43f73a4ce4f0",
        "dest": REPO / "data" / "r-arcticnet" / "raw_Anadyr_and_Kolyma_Data_m3_s.txt",
        "source_id": "SRC-RARCTICNET-V40-ALLDATA",
    },
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str) -> int:
    spec = VERIFIED_DOWNLOADS.get(name)
    if spec is None:
        print("FETCH_UNKNOWN_DATASET: %s (доступно: %s)"
              % (name, ", ".join(sorted(VERIFIED_DOWNLOADS))), file=sys.stderr)
        return 2

    ref = json.loads(REF.read_text(encoding="utf-8"))
    known_urls = {s.get("url") for s in ref.get("sources", [])}
    if spec["url"] not in known_urls:
        print("FETCH_URL_NOT_IN_REFERENCE: URL отсутствует в реестре источников",
              file=sys.stderr)
        return 2

    dest: Path = spec["dest"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        digest = sha256_of(dest)
        if digest == spec["sha256"]:
            print("OK: файл уже на месте, sha256 совпадает: %s" % digest)
            return 0
        print("FETCH_HASH_MISMATCH: существующий файл не совпадает по sha256 "
              "(%s != %s); удалите и повторите" % (digest, spec["sha256"]),
              file=sys.stderr)
        return 3

    print("Загрузка %s" % spec["url"])
    try:
        with urllib.request.urlopen(spec["url"], timeout=120) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        print("FETCH_DOWNLOAD_FAILED: %s" % exc, file=sys.stderr)
        return 4

    digest = sha256_of(dest)
    if digest != spec["sha256"]:
        dest.unlink(missing_ok=True)
        print("FETCH_HASH_MISMATCH: скачанный файл не совпадает по sha256 "
              "(%s != %s); файл удалён" % (digest, spec["sha256"]),
              file=sys.stderr)
        return 3

    print("OK: %s (%d байт), sha256 %s" % (dest, dest.stat().st_size, digest))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True,
                    help="имя набора из VERIFIED_DOWNLOADS")
    args = ap.parse_args(argv)
    return fetch(args.dataset)


if __name__ == "__main__":
    raise SystemExit(main())
