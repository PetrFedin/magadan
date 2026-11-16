# data/r-arcticnet — реальный измерительный ряд R-ArcticNET v4.0

## Файлы

- `kolyma_ust_srednekan_5858_monthly_m3s.tsv` — **в репозитории**: подмножество
  R-ArcticNET v4.0 для створа PointID 5858 (Колыма — Усть-Среднекан, код Росгидромета 1010,
  62.43N, 152.3E, водосбор 99 400 км²): 68 строк годов (1933–2000, 2000 неполный),
  месячный сток м³/с. SHA-256: `d514cf2eec647db759fd55f256ce004ef5a965204f222272d2cacfaccd64194c`.
- `kolyma_basin_multistation_v4.tsv` — **в репозитории** (V9.5): подмножество того же
  верифицированного файла v4.0 для 11 створов бассейна Колымы (PointID < 6000)
  с >= 35 полными годами наблюдений: 5855, 5857, 5858, 5859, 5865, 5874, 5878,
  5884, 5889, 5897, 5951; 564 строки годов. SHA-256:
  `6df1416267dc17e67e9e2550738a21cafb2ddbf7ba81e7de11ca8547fff1c2b1`.
  Извлечение из полного файла (SHA-256 `c2cad850…f1610a`) детерминировано;
  строка 5858 совпадает с файлом створа V9.2 (расхождение — только хвостовые
  пустые ячейки неполного 2000 года).
- Полный файл `Anadyr_and_Kolyma_Data_m3_s.txt` (все посты бассейнов Анадыря и Колымы)
  **в репозитории не хранится**; получение с проверкой хэша:
  `python3 scripts/fetch_open_hydro_data.py --out data/open`
  (ожидаемый SHA-256 зафиксирован в скрипте: `c2cad850…f1610a`; несовпадение — отказ).

## Provenance

- Источник: R-ArcticNET v4.0, https://www.r-arcticnet.sr.unh.edu/v4.0/AllData/index.html
  (файл `Anadyr_and_Kolyma_Data_m3_s.txt`), UNH Water Systems Analysis Group;
  первичные наблюдения — Росгидромет / ГГИ. Скачано и сверено 2026-11-16.
- Класс данных: **FIELD-OBSERVED-PUBLISHED** — первый натурный измерительный ряд
  в репозитории (НЕ SYNTHETIC). Это публичные наблюдения, а не данные владельца актива:
  production-допуск по-прежнему закрыт (issues #1–#4), HOLD сохраняется.
- Цитирование: Lammers, R.B., Shiklomanov, A.I., Vörösmarty, C.J., Fekete, B.M.,
  Peterson, B.J., 2001. Assessment of contemporary Arctic river runoff based on
  observational discharge records. JGR Atmospheres 106, 3321–3334.
- Задокументированное расхождение портала (не усредняется): station.cgi указывает архив
  «1936-01..1988-12», климатологический график подписан «1936 to 2000», файл v4.0 содержит
  1933–2000. Рабочим считается файл v4.0 с зафиксированным SHA-256.

## Воспроизведение бэктеста

```bash
PYTHONPATH=server python3 scripts/backtest_hydroforecast_rarcticnet.py
# артефакт: artifacts_v9/rarcticnet_backtest_v9.json (с собственным SHA-256)

PYTHONPATH=server python3 scripts/regional_trend_backtest_rarcticnet.py
# артефакт: artifacts_v9/rarcticnet_regional_trend_v9.json (с собственным SHA-256)
```
