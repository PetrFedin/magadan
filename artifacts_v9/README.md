# Артефакты открытой научной линии V9

Здесь хранятся машиночитаемые результаты расчётов. JSON-файлы являются версионированными доказательствами: их нельзя незаметно перезаписывать при изменении методики или входных данных. Новый результат должен сопровождаться новым идентификатором, входными SHA-256 и внутренней квитанцией.

Все результаты относятся к исследовательской лаборатории. `production_ready=false` и решения `HOLD` сохраняются независимо от успешного завершения скриптов.

## Реестр

| Выпуск | Файл | Идентификатор | Квитанция внутри JSON | Скрипт воспроизведения |
|---|---|---|---|---|
| V9.0 | [grid_ieee33_benchmark_v9.json](grid_ieee33_benchmark_v9.json) | `grid_ieee33_benchmark_v9` | `sha256`: `f87cc4f45b0d90928f7828d872a906b53467f48acff0fd721c4f847b6b6554f0` | `benchmark_grid_ieee33_v9.py` |
| V9.2 | [rarcticnet_backtest_v9.json](rarcticnet_backtest_v9.json) | `RARCTICNET-BACKTEST-V9-1` | `cfe4c593443f9c296c9d23de80ac661c44f0ccca4bdcc859e98fb8380409573f` | `backtest_hydroforecast_rarcticnet.py` |
| V9.3 | [rarcticnet_emos_backtest_v9.json](rarcticnet_emos_backtest_v9.json) | `RARCTICNET-EMOS-BACKTEST-V9-1` | `07174a2c71519144ac71affe917bde85de1f1ff661a123ed693f1c1439b9168f` | `emos_backtest_rarcticnet.py` |
| V9.4 | [rarcticnet_trend_backtest_v9.json](rarcticnet_trend_backtest_v9.json) | `RARCTICNET-TREND-ADAPTIVE-BACKTEST-V9-1` | `b1a624b6dee816a1717352e09f68df4772b08489579a3098e7ae1a95455ff756` | `trend_adaptive_backtest_rarcticnet.py` |
| V9.5 | [rarcticnet_regional_trend_v9.json](rarcticnet_regional_trend_v9.json) | `RARCTICNET-REGIONAL-TREND-V9-1` | `cb79734176a4d64b09148854b8994024c221535c59bf57c71282b3825dff1b16` | `regional_trend_backtest_rarcticnet.py` |
| V9.5 | [magadan_system_adequacy_v9.json](magadan_system_adequacy_v9.json) | `MAGADAN-SYSTEM-ADEQUACY-EFORD-V9-1` | `4052617995270c8968ae689efbc770ccd71e11e2bd92268d6cf6b90df5d4ff54` | `magadan_system_adequacy_v9.py` |
| V9.6 | [rarcticnet_lowflow_v9.json](rarcticnet_lowflow_v9.json) | `RARCTICNET-LOWFLOW-FREQUENCY-V9-1` | `a8b92f18c119ed93dcd77e9a80d54c31e51089411c9bae9ba3fce3e886ceed68` | `lowflow_analysis_rarcticnet.py` |
| V9.6 | [magadan_seasonal_adequacy_v9.json](magadan_seasonal_adequacy_v9.json) | `MAGADAN-SEASONAL-ADEQUACY-V9-1` | `744503e0537101d33af36f15c6a39eb7ac93911382a71ececacf4f8a8d0b3315` | `magadan_seasonal_adequacy_v9.py` |

## Воспроизведение

Из корня репозитория:

```bash
python -m pip install -r server/requirements.txt
PYTHONPATH=server python scripts/backtest_hydroforecast_rarcticnet.py
PYTHONPATH=server python scripts/emos_backtest_rarcticnet.py
PYTHONPATH=server python scripts/trend_adaptive_backtest_rarcticnet.py
PYTHONPATH=server python scripts/regional_trend_backtest_rarcticnet.py
PYTHONPATH=server python scripts/magadan_system_adequacy_v9.py
PYTHONPATH=server python scripts/lowflow_analysis_rarcticnet.py
PYTHONPATH=server python scripts/magadan_seasonal_adequacy_v9.py
```

Сетевой бенчмарк:

```bash
python scripts/benchmark_grid_ieee33_v9.py
```

Если `pandapower` не установлен, скрипт возвращает код 3 после внутренней литературной проверки; внешняя сверка при этом не считается выполненной. Полный набор R-ArcticNET не коммитится: в git находятся только зафиксированные подмножества `data/r-arcticnet/`; получение полного исходника описано в `scripts/fetch_open_hydro_data.py` и [досье открытых данных](../docs/V9_OPEN_DATA_DOSSIER_RU.md).

## Семантика контрольных сумм

- `input_sha256` и `input_files` внутри JSON относятся к входным файлам.
- `artifact_sha256` вычисляется от канонической сериализации полезной нагрузки до вставки самой квитанции, а не от сырых байтов итогового файла.
- Для контроля транспортной целостности самого JSON дополнительно используйте `sha256sum artifacts_v9/*.json`; это отдельная сумма, не совпадающая с `artifact_sha256` по построению.
- Методику и численную интерпретацию каждого результата см. в соответствующем документе из [карты документации](../docs/INDEX.md).
