# ГИДРОКОНТУР 360 — МАГАДАН, V7.4 (лабораторный выпуск)

Дата выпуска пакета: 23.10.2026. **Все инженерные величины и финансовые предпосылки в демонстрационном цикле синтетические. Не ТЭО, не согласование, не информация реальных энергетических объектов Магаданской области.**

## Основные результаты

- Сквозное исследовательское досье на 6 направлениях: HydroForecast, CascadeEconomics, TurbineReliability, GridLoss Planner, HeatNet Economics, HydroCAPEX.
- Пять *семантических* направлений связи с проверкой ролей, организаций, источников, версий и строгим указанием, что **физические величины между моделями ещё не передаются**.
- Принимает вычислительный набор из 10 синтетических запусков, проверяет два сетевых и два тепловых варианта, связывает их с условными финансовыми расчётами и трёхлетней WBS.
- Пример: **2 800 000 RUB** условной полной стоимости: 1 800 000 GridLoss + 1 000 000 HeatNet. Это совпадение предпосылок, а не оценка реального строительства.
- Сохраняет версионированный хеш пакета, состав связей и результаты; инженер/аудитор может **повторно выполнить расчёты всех входящих моделей**, повторно вычислить GridLoss-экономику, HeatNet-экономику, WBS и полную структуру досье. Это не независимая инженерная верификация.
- Блокирует стандартное изменение записей в SQLite. Для PostgreSQL подготовлена миграция 080, но PostgreSQL RLS не проверялась на настоящем сервере.
- Отчёт явно устанавливает `field_ready=false` / `eligible_for_industrial_approval=false` и раскрывает обязательные недостающие доказательства.

## Проверки

| Испытание | Факт |
|---|---|
| Python domain + server + HTTP regression | 167 PASS |
| JavaScript унаследованного доменного ядра | 63 PASS |
| Детерминированные синтетические радиальные сети | 64/64 PASS; не независимый отраслевой эталон |
| Сквозное HTTP-исследование (синтетика) | 10 запусков; 5 связей; 2 экономические дорожки; WBS 2,8 млн ₽; replay PASS |
| Контроль статических UI элементов | 69/69 ID присутствуют |
| Статическая визуальная вёрстка Chromium | 1440, 768, 375 px; horizontal overflow 0 |
| Настоящий browser↔API E2E | NOT ACCEPTED; заблокирован окружением |
| PostgreSQL17 RLS concurrency acceptance | `NATIVE_ACCEPTANCE_BLOCKED`; dedicated PG отсутствует |
| Реальный OIDC IdP/MFA | NOT CONNECTED |
| Compliance WORM | NOT CONNECTED |
| Данные магаданского объекта / инженерная подпись | НЕ ПОЛУЧЕНЫ |

## Архитектура

- `server/hydro_api/programme_v74.py` — доменные правила и калькулятор стоимости WBS.
- `server/hydro_api/programme_api_v74.py` — проверка организации, версий и сборка исследовательского пакета.
- `server/hydro_api/heat_economics_v74.py` — сценарная экономика теплопотерь (синтетика).
- `server/migrations/080_research_programme_v74.sql` — **неисполненный** проект SQL, RLS, составные FK, аудит.
- `server/ui` — лабораторная форма сбора и воспроизведения программы.
- `server/tests_v74` — негативные и математические тесты.
- `scripts/reproduce_programme_v74.py` — воспроизводимый HTTP-сценарий без внешней сети.
- `docs/V74_MASTER_ARCHITECTURE_RU.md` — предметные контексты и интеграционные требования.
- `docs/V74_FINANCE_AND_CONSTRUCTION_RU.md` — инженерная и строительная экономика.
- `docs/V74_MAGADAN_PILOT_DESIGN_RU.md` — матрица пилотов и требования к допуску.
- `docs/V74_SECURITY_NATIVE_ACCEPTANCE_RU.md` — RLS / изоляция / внешняя проверка аудита.
- `docs/V74_FEATURE_REGISTER.csv` — 123 требования, ни одно не принято к промышленной эксплуатации.
- `docs/openapi_v74.json` — **47 HTTP-операций** в локальном серверном приложении.

## Воспроизведение

```bash
python -m pip install -r server/requirements-v71.txt
PYTHONPATH=server pytest -q server/tests server/tests_v71 server/tests_v72 server/tests_v73 server/tests_v74 --ignore=server/tests/test_browser.py --ignore=server/tests_v71/test_postgres_native.py
node --test v6-client/tests/domain.test.mjs v6-client/tests/assurance.test.mjs
PYTHONPATH=server python scripts/reproduce_programme_v74.py --output artifacts_v74/showcase_trace_v74.json
python scripts/stress_radial_v73.py --output artifacts_v74/stress_radial_v74.json
```

Нативный PostgreSQL тест: выполняйте **только на отдельной созданной заново тестовой PostgreSQL 17** по инструкции `docs/V74_SECURITY_NATIVE_ACCEPTANCE_RU.md`; при отсутствии тестовой конфигурации команда должна завершаться отказом `NATIVE_ACCEPTANCE_BLOCKED`. Ручной workflow `.github/workflows/native-v74.yml` **не запускался и не публиковался**.

## Ключевое отличие от V7.3

V7.3 проверяла GridLoss→экономика. V7.4 собирает **неизменяемое исследовательское досье между всеми шестью модулями**, добавляет HeatNet→экономика и WBS бюджеты, повторно исполняет исходные модели при запросе аудитора, и сохраняет юридические и инженерные границы применимости.

**Production HOLD.** Изменений в производственных системах, корпоративных данных или GitHub репозиториях не выполнялось.
