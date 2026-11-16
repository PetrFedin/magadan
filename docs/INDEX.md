# Карта документации ГИДРОКОНТУР 360

Единая точка входа. Языковая политика: новые документы — на русском, суффикс `_RU` не обязателен; английские названия файлов сохраняются для исторических документов.

## Действующие (канонические)

| Документ | Назначение |
|---|---|
| [TECH_AUDIT_2026-11-16_RU.md](TECH_AUDIT_2026-11-16_RU.md) | Текущий аудит состояния и программа развития — **начинать отсюда** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Шесть модулей и сквозной процесс |
| [MATHEMATICS_FINANCE.md](MATHEMATICS_FINANCE.md) | Свод формул и экономических правил |
| [ACCEPTANCE_GATES.md](ACCEPTANCE_GATES.md) | Гейты допуска G0–G9 |
| [GOVERNANCE.md](GOVERNANCE.md) | Регламент веток, релизов, миграций |
| [IMPORT_STATUS.md](IMPORT_STATUS.md) | Статус восстановления исходников V7.9→V8 |
| [MAGADAN_PILOT.md](MAGADAN_PILOT.md) | Данные и разрешения Магаданской области |
| [PROJECT_SCOPE_MAGADAN_RUSHYDRO.md](PROJECT_SCOPE_MAGADAN_RUSHYDRO.md) | Границы проекта (исключения, правовой статус) |
| [ROADMAP_V8.md](ROADMAP_V8.md) | Дорожная карта V8 по гейтам |

## Методики по версиям (действующие описания модулей)

- HydroForecast: [V82_HYDROFORECAST_METHODS_RU.md](V82_HYDROFORECAST_METHODS_RU.md)
- CascadeEconomics: [V83_CASCADE_FORECAST_PHYSICS_RU.md](V83_CASCADE_FORECAST_PHYSICS_RU.md), [V832_ENERGY_INTEGRATION_RU.md](V832_ENERGY_INTEGRATION_RU.md)
- Региональный баланс V8.8: [V88_MAGADAN_ENERGY_AVAILABILITY_INVESTMENT_RU.md](V88_MAGADAN_ENERGY_AVAILABILITY_INVESTMENT_RU.md)
- Права/допуск данных V8.9: [V89_MAGADAN_DATA_ADMISSION_RU.md](V89_MAGADAN_DATA_ADMISSION_RU.md), [V89_EVIDENCE_INTEGRITY_RU.md](V89_EVIDENCE_INTEGRITY_RU.md), [V89_STRICT_BASELINE_RECONCILIATION_RU.md](V89_STRICT_BASELINE_RECONCILIATION_RU.md)
- Почасовая идентифицируемость V8.10: [V810_HOURLY_ADEQUACY_IDENTIFIABILITY_RESEARCH_RU.md](V810_HOURLY_ADEQUACY_IDENTIFIABILITY_RESEARCH_RU.md)
- Границы и сериализация V8.1: [V81_GRAPH_SERIALIZATION_ACCEPTANCE_RU.md](V81_GRAPH_SERIALIZATION_ACCEPTANCE_RU.md)
- CI/доказательства: [V84_CI_TEST_EVIDENCE_AND_RELEASE_GATES.md](V84_CI_TEST_EVIDENCE_AND_RELEASE_GATES.md), [V893_CI_RECOVERY_AND_STAGING_GATES_RU.md](V893_CI_RECOVERY_AND_STAGING_GATES_RU.md), [V894_HOSTED_CI_EVIDENCE_AND_DRAFT_HEAD_RU.md](V894_HOSTED_CI_EVIDENCE_AND_DRAFT_HEAD_RU.md)
- Открытые письма владельцам данных: [V89_DRAFT_REQUESTS_TO_DATA_OWNERS_RU.md](V89_DRAFT_REQUESTS_TO_DATA_OWNERS_RU.md), [V89_OWNER_DATA_REQUESTS_RU.md](V89_OWNER_DATA_REQUESTS_RU.md), [V89_OFFICIAL_SOURCE_AND_RIGHTS_REGISTER_2026-11-10_RU.md](V89_OFFICIAL_SOURCE_AND_RIGHTS_REGISTER_2026-11-10_RU.md)

## Исторические (архивные снимки версий)

Документы серий `V7*_…`, `V72…V79_*`, мастер-архитектуры версий, feature-реестры CSV, протоколы приёмки версий, снимки `openapi_v7…v83.json`, инцидент CI 27.10.2026 — хранятся как неизменяемая история проекта. Не редактировать; при противоречии с каноническими документами приоритет у канонических. Корневые `README_V7*.md … README_V832.md` — архивные снимки релизов (используются тестами/скриптами).

Полный архив лабораторных ссылок: [archive_lab_references/](archive_lab_references/).
