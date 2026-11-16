#!/usr/bin/env python3
"""Скачивание открытых гидрологических данных по Колыме с фиксацией provenance.

Запускается ЛОКАЛЬНО владельцем проекта (не в CI):
    python scripts/fetch_open_hydro_data.py --out data/open

Источники и статус URL верифицированы 16.11.2026 (docs/V9_OPEN_DATA_DOSSIER_RU.md):
  * посадочные страницы станций R-ArcticNET/ArcticRIMS проверены точно;
  * прямые файловые URL перебираются из списка кандидатов — успешные
    скачивания фиксируются в манифесте, неуспешные не маскируются.

Каждый скачанный файл: SHA-256 + запись в data/open/MANIFEST.sha256.json.
GRDC (заявка) и ERA5-Land (API-ключ CDS) скрипт не скачивает — см. досье.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "magadan-hydrokontur-research/9.0 (scientific, non-commercial)"}

# Верифицированные станции Колымы (R-ArcticNET / ArcticRIMS)
STATIONS = [
    {"rims_id": "5858", "code": "1010", "name": "Kolyma at Ust'-Srednekan",
     "note": "створ у Колымского каскада; в файле v4.0 ряд 1933-01..2000-09 (67 полных лет)"},
    {"rims_id": "5855", "code": None, "name": "Kolyma at Orotuk",
     "note": "следующий апстрим-створ"},
    {"rims_id": "5951", "code": None, "name": "Kolyma downstream of Ust'-Srednekan",
     "note": "следующий даунстрим-створ"},
]

# ТОЧНО верифицированные файлы (URL + ожидаемый SHA-256, скачано и сверено 16.11.2026).
# Несовпадение хэша => отказ (fail-closed), а не тихое использование.
VERIFIED_DOWNLOADS = [
    {
        "url": "https://www.r-arcticnet.sr.unh.edu/v4.0/AllData/Anadyr_and_Kolyma_Data_m3_s.txt",
        "filename": "Anadyr_and_Kolyma_Data_m3_s.txt",
        "sha256": "c2cad85039b3163fa59bea51ce2ca8ac026aa4ffaf62f1610a6a43f73a4ce4f0",
        "note": "R-ArcticNET v4.0: месячный сток всех постов бассейнов Анадыря и Колымы (включая створ 5858 Усть-Среднекан)",
    },
]

# Кандидаты прямых файловых URL постов (структура ArcticRIMS может меняться;
# скрипт перебирает и честно сообщает, что сработало)
MONTHLY_URL_CANDIDATES = [
    "https://rims.unh.edu/data/station/monthly/{sid}.txt",
    "https://rims.unh.edu/data/station/monthly/{sid}.mon",
    "https://rims.unh.edu/data/station/download.cgi?station={sid}&type=monthly",
]
STATION_PAGE = "https://rims.unh.edu/data/station/station.cgi?station={sid}"


def _try_download(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
        # текстовые данные ArcticRIMS компактны; отбрасываем HTML-страницы ошибок
        if payload.lstrip()[:15].lower().startswith(b"<!doctype html"):
            return None
        return payload if len(payload) > 200 else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/open", help="каталог для данных")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/fetch_open_hydro_data.py",
        "files": [],
        "failed": [],
    }
    for vd in VERIFIED_DOWNLOADS:
        url = vd["url"]
        print(f"[..] проверенный файл: {url}")
        got = _try_download(url)
        if got is None:
            manifest["failed"].append({"url": url, "instruction": "повторите вручную; файл также индексируется с https://www.r-arcticnet.sr.unh.edu/v4.0/AllData/index.html"})
            print("[FAIL] недоступен")
            continue
        digest = hashlib.sha256(got).hexdigest()
        if digest != vd["sha256"]:
            manifest["failed"].append({"url": url, "sha256_actual": digest,
                                       "instruction": "SHA-256 не совпал с зафиксированным — файл НЕ используется (fail-closed)"})
            print(f"[FAIL-CLOSED] SHA-256 {digest[:12]}… != ожидаемого; файл отклонён")
            continue
        (out / vd["filename"]).write_bytes(got)
        manifest["files"].append({
            "source_id": "OPEN-RARCTICNET-V40-ANADYR-KOLYMA-MONTHLY",
            "url": url,
            "filename": vd["filename"],
            "sha256": digest,
            "bytes": len(got),
            "note": vd["note"],
            "license": "научное использование с цитированием R-ArcticNET (Lammers et al., 2001, JGR)",
        })
        print(f"[OK] {len(got):>10} байт -> {vd['filename']} (SHA-256 совпал)")

    for st in STATIONS:
        sid = st["rims_id"]
        got = None
        for tmpl in MONTHLY_URL_CANDIDATES:
            url = tmpl.format(sid=sid)
            print(f"[..] {st['name']}: пробуем {url}")
            got = _try_download(url)
            if got is not None:
                fname = f"rims_kolyma_{sid}_monthly.txt"
                (out / fname).write_bytes(got)
                manifest["files"].append({
                    "source_id": f"OPEN-RARCTICNET-{st['code'] or sid}-MONTHLY",
                    "station": st["name"],
                    "url": url,
                    "station_page": STATION_PAGE.format(sid=sid),
                    "filename": fname,
                    "sha256": hashlib.sha256(got).hexdigest(),
                    "bytes": len(got),
                    "license": "научное использование с цитированием R-ArcticNET",
                })
                print(f"[OK] {len(got):>10} байт -> {fname}")
                break
        if got is None:
            manifest["failed"].append({
                "station": st["name"],
                "station_page": STATION_PAGE.format(sid=sid),
                "instruction": "откройте station_page вручную, ссылка 'Monthly' "
                               "в таблице Available Data Downloads",
            })
            print(f"[РУЧНОЙ РЕЖИМ] {st['name']}: см. {STATION_PAGE.format(sid=sid)}")

    (out / "MANIFEST.sha256.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nМанифест: {out / 'MANIFEST.sha256.json'}")
    print("ArcticGRO (ежегодный сток Колымы) — ручное скачивание: "
          "https://arcticgreatrivers.org/discharge/")
    print("GRDC (заявка) и ERA5-Land (API-ключ CDS): см. досье, раздел 4.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
