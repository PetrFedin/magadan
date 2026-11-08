# HYDROKONTUR 360 / МАГАДАН — V8.6: локальная инженерная приёмка

**Назначение:** воспроизводимая проверка на одном Git SHA, без SCADA, production, реальных гидрологических данных и денежных эффектов. Рабочая ветка: feature/v84-full-regression-gates; Draft PR #13.

## Выявленные и устранённые технические проблемы

1. PostgreSQL миграция 030: выражение IS DISTINCT FROM CASE в триггере завершается синтаксической ошибкой; добавлены скобки вокруг CASE.
2. PostgreSQL миграция 040: strict — зарезервированный идентификатор PL/pgSQL; заменён на v_require_compliance.
3. PostgreSQL миграция 110: составной tenant FK требует UNIQUE (org_id,asset_id,id) в study_runs. Композитная целостность усилена, а не ослаблена.
4. Python tests_v81: импортированы обе фикстуры n, native — исключён сбой fixture native not found.
5. pytest.ini: режим importlib исключает коллизии исторических test_migration_contract.py в одном процессе.
6. JUnit validator: совместимые коды ошибок, строгая вложенная сверка не снята.
7. Chromium Playwright: реальные отдельные контексты ролей, CSP-совместимые локаторы, ширины 375/390/768/1440, локальный Chromium, локальные логи и скриншоты.
8. UI: личный кабинет становится видимым только после завершения загрузки контекста авторизации, предотвращая гонку в уведомлениях.

## Исполненные предварительные проверки на Mac до итогового коммита

- Javascript Node 22: 63/63 PASS.
- JUnit parser unit: 23/23 PASS.
- HTTP role journeys: 3/3 PASS.
- Монолитный Python: 380/380 PASS (6 мин 35 сек) с режимом importlib.
- Нативный PG17.10: 17/17 миграций на пустой изолированной базе (001...160).
- PostgreSQL17 native: 40/40 PASS в другом свежем локальном кластере, включая RLS и конкурентные операции.
- Настоящий Chromium: 1 сквозной browser PASS, отдельные сессии engineer/economist/manager/auditor/viewer/other-tenant, 4 ширины и отсутствие горизонтального overflow.

Эти результаты НЕ являются source-pinned релизной приёмкой: перед записью коммита рабочее дерево изменялось.

## Новый единый source-pinned скрипт

Файл scripts/run_v86_local_ci.sh требует чистое рабочее дерево, точный 40-символьный SHA, активную виртуальную среду .venv, путь HYDRO_NATIVE_CONFIG к НОВОЙ подготовленной PG17 базе и установленный Chromium (через HYDRO_BROWSER_EXECUTABLE). Выполняет исходный исторический SHA манифест 452/452, unit JUnit, 63 JS, 256 synthetic integral, 438 hourly route, 60 cascade branches, 380 Python, 40 PG17 native, браузерный E2E и создаёт JUnit SHA256 receipt.

Пример команды после checkout и bootstrap отдельного локального PG17:

    cd ~/Projects/magadan
    git status --short
    export HYDRO_NATIVE_CONFIG="$PWD/runtime/qa-v85/native-config-v86.json"
    export HYDRO_BROWSER_EXECUTABLE="$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell"
    bash scripts/run_v86_local_ci.sh "$(git rev-parse HEAD)"

Доказательства остаются в ignored runtime/qa-v86-FULL_SHA/acceptance-receipt.json. Демо только localhost. На серверы других проектов не заходить.

## Главные HOLD

- **GitHub Actions**: GitHub Check annotation из прямого запроса GitHub API сообщает: 'The job was not started because recent account payments have failed or your spending limit needs to be increased.' Github-hosted runner_id=0, steps=[]. Не менять платёжные лимиты без пользователя. Issue #6: https://github.com/PetrFedin/magadan/issues/6
- **Корпоративный staging**: не подтверждены browser+PG17 вместе с реальным OIDC/MFA, внешним WORM, полноценным backup/restore и независимым ревью.
- **Инженерия**: отсутствуют разрешённые реальные суточные данные, калиброванные curves, независимая гидравлическая экспертиза, корректная подтверждённая экономия.

Статус: LOCAL SYNTHETIC QA (после pinned прогона) / PRODUCTION HOLD. Не объединять с main и не объявлять промышленную готовность.
