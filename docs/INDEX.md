# Карта документации ГИДРОКОНТУР 360

Единая точка входа. Языковая политика: новые документы — на русском, суффикс `_RU` не обязателен; английские названия файлов сохраняются для исторических документов.

## Действующие (канонические)

| Документ | Назначение |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | **Начинать отсюда:** текущая версия, выпуски, проверки, артефакты, HOLD и следующие шаги |
| [TECH_AUDIT_2026-11-16_RU.md](TECH_AUDIT_2026-11-16_RU.md) | Базовый аудит на 16.11.2026; исторический снимок, закрытые позже пробелы сверять с PROJECT_STATUS |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Шесть модулей и сквозной процесс |
| [MATHEMATICS_FINANCE.md](MATHEMATICS_FINANCE.md) | Свод формул и экономических правил |
| [ACCEPTANCE_GATES.md](ACCEPTANCE_GATES.md) | Гейты допуска G0–G9 |
| [GOVERNANCE.md](GOVERNANCE.md) | Регламент веток, релизов, миграций |
| [IMPORT_STATUS.md](IMPORT_STATUS.md) | Статус восстановления исходников V7.9→V8 |
| [MAGADAN_PILOT.md](MAGADAN_PILOT.md) | Данные и разрешения Магаданской области |
| [PROJECT_SCOPE_MAGADAN_RUSHYDRO.md](PROJECT_SCOPE_MAGADAN_RUSHYDRO.md) | Границы проекта (исключения, правовой статус) |
| [ROADMAP_V8.md](ROADMAP_V8.md) | Дорожная карта V8 по гейтам |
| [../artifacts_v9/README.md](../artifacts_v9/README.md) | Реестр артефактов V9, квитанции и команды воспроизведения |
| [../data/reference/README.md](../data/reference/README.md) | Правила provenance опорных открытых параметров |

## Открытая научная линия V9

| Выпуск | Методика и результат |
|---|---|
| V9.0 | [Открытые научные модули: Newton–Raphson, Маскингам—Кундж, CRPS/PIT, ISO 20816 + Weibull](V9_OPEN_SCIENCE_MODULES_RU.md) |
| V9.0 | [Досье открытых данных Колымы](V9_OPEN_DATA_DOSSIER_RU.md) |
| V9.1 | [Опорные параметры, снеготаяние, адекватность, CRPS-декомпозиция, теплосеть](V91_OPEN_SCIENCE_EXTENSION_RU.md) |
| V9.2 | [Первый наблюдательный ряд R-ArcticNET и бэктест HydroForecast](V92_REAL_DATA_BACKTEST_RU.md) |
| V9.3 | [EMOS-калибровка ансамбля, включая частично отрицательный результат](V93_EMOS_CALIBRATION_RU.md) |
| V9.4 | [Тренд-адаптивная климатология и FOR/EFOR/EFORd](V94_TREND_ADAPTIVE_AND_FOR_RU.md) |
| V9.5 | [Региональные тренды на 11 створах и системная адекватность](V95_REGIONAL_TREND_AND_ADEQUACY_RU.md) |
| V9.6 | [Меженные Q80/Q90/Q95 и сезонная адекватность](V96_LOWFLOW_AND_SEASONAL_ADEQUACY_RU.md) |

## Методики V8 (историческая основа действующих модулей)

- HydroForecast: [V82_HYDROFORECAST_METHODS_RU.md](V82_HYDROFORECAST_METHODS_RU.md)
- CascadeEconomics: [V83_CASCADE_FORECAST_PHYSICS_RU.md](V83_CASCADE_FORECAST_PHYSICS_RU.md), [V832_ENERGY_INTEGRATION_RU.md](V832_ENERGY_INTEGRATION_RU.md)
- Региональный баланс V8.8: [V88_MAGADAN_ENERGY_AVAILABILITY_INVESTMENT_RU.md](V88_MAGADAN_ENERGY_AVAILABILITY_INVESTMENT_RU.md)
- Права/допуск данных V8.9: [V89_MAGADAN_DATA_ADMISSION_RU.md](V89_MAGADAN_DATA_ADMISSION_RU.md), [V89_EVIDENCE_INTEGRITY_RU.md](V89_EVIDENCE_INTEGRITY_RU.md), [V89_STRICT_BASELINE_RECONCILIATION_RU.md](V89_STRICT_BASELINE_RECONCILIATION_RU.md)
- Почасовая идентифицируемость V8.10: [V810_HOURLY_ADEQUACY_IDENTIFIABILITY_RESEARCH_RU.md](V810_HOURLY_ADEQUACY_IDENTIFIABILITY_RESEARCH_RU.md)
- Границы и сериализация V8.1: [V81_GRAPH_SERIALIZATION_ACCEPTANCE_RU.md](V81_GRAPH_SERIALIZATION_ACCEPTANCE_RU.md)
- CI/доказательства: [V84_CI_TEST_EVIDENCE_AND_RELEASE_GATES.md](V84_CI_TEST_EVIDENCE_AND_RELEASE_GATES.md), [V893_CI_RECOVERY_AND_STAGING_GATES_RU.md](V893_CI_RECOVERY_AND_STAGING_GATES_RU.md), [V894_HOSTED_CI_EVIDENCE_AND_DRAFT_HEAD_RU.md](V894_HOSTED_CI_EVIDENCE_AND_DRAFT_HEAD_RU.md)
- Черновики обращений владельцам данных (**не отправлены**): [V89_DRAFT_REQUESTS_TO_DATA_OWNERS_RU.md](V89_DRAFT_REQUESTS_TO_DATA_OWNERS_RU.md), [V89_OWNER_DATA_REQUESTS_RU.md](V89_OWNER_DATA_REQUESTS_RU.md), [V89_OFFICIAL_SOURCE_AND_RIGHTS_REGISTER_2026-11-10_RU.md](V89_OFFICIAL_SOURCE_AND_RIGHTS_REGISTER_2026-11-10_RU.md)

## Исторические (архивные снимки версий)

Документы серий `V7*_…`, `V72…V79_*`, мастер-архитектуры версий, feature-реестры CSV, протоколы приёмки версий, снимки `openapi_v7…v83.json`, инцидент CI 27.10.2026 — хранятся как неизменяемая история проекта. Не редактировать; при противоречии с каноническими документами приоритет у канонических. Корневые `README_V7*.md … README_V832.md` — архивные снимки релизов (используются тестами/скриптами). Корневые `MANIFEST*`, `SOURCE_RECOVERY_MANIFEST.json` и каталоги `artifacts_v*` также сохраняются как версионированные доказательства, а не как подлежащий удалению мусор.

Полный архив лабораторных ссылок: [archive_lab_references/](archive_lab_references/).
