# ГИДРОКОНТУР 360 — МАГАДАН V7.7

**Выпуск:** 24 октября 2026 года. **Режим:** лаборатория на синтетических данных; `LAB PASS` в испытанных сценариях, `PRODUCTION HOLD`. Не размещено в инфраструктуре «РусГидро». Нет подлинных результатов энергетических объектов Магаданской области.

## Изменения V7.7

- Новый контракт отчёта стороннего электротехнического решателя: `reference_v77.py`, `reference_api_v77.py`, неизменяемая `GridReferenceComparisonV77`.
- Проверка расхождений по всем временным окнам и узлам, полный контроль набора узлов, суммарного баланса и SHA-256 исходного case.
- Обязательное `UNATTESTED` — совпадение не подтверждает запуск pandapower, OpenDSS, RastrWin3 или подпись инженера.
- Дополнительный pure-модуль `sensitivity_v77.py` и API: ±20% выгоды, +20% CAPEX, неблагоприятный OPEX и +3 п.п. ставки; отдельный флаг бюджетного ограничения для каждого сценария.
- Страница 11 пользовательского интерфейса для экспорта входов, импорта сторонних чисел и финансовой чувствительности.
- Новый SQL-кандидат `110_reference_comparisons_v77.sql`, нативно не проверен.
- Отдельный сценарий запуска pandapower для разрешённой изолированной среды. В текущем контейнере pandapower отсутствует.
- Дополнена программа магаданского пилота; документация связывает каждый продукт с инженером, данными и методикой допусков.

## Быстрая проверка

```bash
# Рабочая копия только в тестовом каталоге, после установки зависимостей
PYTHONPATH=server pytest -q server/tests_v77
PYTHONPATH=server pytest -q server/tests --ignore=server/tests/test_browser.py
PYTHONPATH=server pytest -q server/tests_v71 --ignore=server/tests_v71/test_postgres_native.py
PYTHONPATH=server pytest -q server/tests_v72 server/tests_v73 server/tests_v74
PYTHONPATH=server pytest -q server/tests_v75 server/tests_v76
node --test v6-client/tests/domain.test.mjs v6-client/tests/assurance.test.mjs
PYTHONPATH=server python scripts/reproduce_v77_case.py
```

### Отдельный НЕпройденный допуск

```
HYDRO_NATIVE_TESTS_REQUIRED=1 PYTHONPATH=server pytest -q server/tests_v71/test_postgres_native.py
```

Без выделенной PostgreSQL 17 этот тест должен блокироваться, а не превращаться в успешный тест на SQLite. В текущей среде фактический PostgreSQL отсутствует.

## Основные материалы

- `docs/V77_MASTER_ARCHITECTURE_RU.md`
- `docs/V77_EXTERNAL_REFERENCE_PROTOCOL_RU.md`
- `docs/V77_FINANCIAL_SENSITIVITY_RU.md`
- `docs/V77_MAGADAN_FIELD_READINESS_RU.md`
- `docs/V77_POSTGRES_NATIVE_ACCEPTANCE_RU.md`
- `docs/openapi_v77.json`
- `artifacts_v77/reproducible_trace_v77.json`
- `artifacts_v77/ui_static_metrics.json`, `artifacts_v77/reference-layout-*.png`
- `scripts/run_external_pandapower_v77.py`
- `examples/reference_request_v77.json`

## Принципиальные ограничения

НЕТ: разрешённой телеметрии реальной сети Магаданской области, независимого эталонного расчёта на ней, утверждённой сметы, промышленной PostgreSQL RLS-приёмки, корпоративного SSO/MFA, внешнего WORM-аудита, разрешения на строительство или управление оборудованием. НЕТ проведённой проверки `pandapower` на отдельном движке в этой среде. Нет подтверждённой окупаемости проекта.

**Нельзя выдавать:** синтетическую сетевую модель за действующую однолинейную схему, переписанный результат основного решателя за независимый, однофакторные стресс-тесты за вероятности или график CAPEX за разрешение на строительство.
