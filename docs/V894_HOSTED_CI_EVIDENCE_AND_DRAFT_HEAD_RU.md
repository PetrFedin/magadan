# HydroKontur 360 — V8.9.4: независимая проверка GitHub Actions и контроль текущего PR

**Контрольная дата:** 16.11.2026. **Контур:** только синтетическая QA-лаборатория V8.9.4. **Статус:** Draft / HOLD.

## 1. Изменение

Создан read-only скрипт `scripts/v894_hosted_ci_evidence.py`, который запрашивает у GitHub Actions сведения о **трёх** фактических запусках и проверяет их в одном commit SHA:

| Ключ | Workflow | Минимальная проверяемая матрица jobs |
| --- | --- | --- |
| `v89` | `.github/workflows/v89-source-quarantine.yml` | `v89-source-rights-hourly-grain-dedup` |
| `full` | `.github/workflows/v84-full-regression.yml` | `provenance-and-parser`; четыре `python-regression`; `monolithic-python-order-probe`, `javascript`, `engineering-synthetic`, `chromium-browser-lab`, `final-check` |
| `unified` | `.github/workflows/v87-unified-staging.yml` | `unified-pg17-oidc-chromium-backup` |

Для каждой группы требуется `status=completed`, `conclusion=success`, фактически назначенный `runner_id>0`, выполненные успешные `steps`, обязательные имена тестовых операций, отсутствие дубликатов и полная загрузка всех страниц jobs. Количество выполненных jobs должно совпадать с заявленной политикой, а каждый run и job — с указанным commit SHA.

**Дополнительное ограничение старого SHA:** скрипт дважды считывает текущий Draft PR #15 и требует `state=open`, `draft=true`, `merged=false`, точного `head.sha`, нужного `head.ref` и целевой ветки `feature/v84-full-regression-gates`. При изменении HEAD, base или статуса PR во время аудита — отказ. Это лишь проверка snapshot до/после, не распределённая транзакция и не блокировка GitHub PR.

## 2. Интеграция с CI

- V8.9 workflow дополнительно отслеживает `baseline_reconcile_v89.py`, `baseline_reconciliation_api_v89.py`, проверяющий скрипт и его тест, а также изменения смежной конфигурации workflow. Ранее изменения этих двух baseline-файлов не гарантировали запуск сфокусированного V8.9 gate.
- Перед установкой зависимостей основного приложения как в V8.9, так и в полном regression workflow запускается `python -m unittest discover -s scripts/tests -p 'test_v894_hosted_ci_evidence.py' -v`.
- Тесты основаны **только на искусственных ответах GitHub API**. Они проверяют логику отказа и не свидетельствуют о фактическом запуске GitHub-hosted runner.

## 3. Как самостоятельно подтвердить фактические GitHub Actions

После устранения инфраструктурного блокера получить **три уникальных run ID на одном точном SHA**, запуская соответствующие workflow на текущем Draft PR #15. Инженер с доступом только на чтение к metadata Actions применяет:

```bash
# GH_TOKEN вводится из внешнего защищённого секретного хранилища.
# Не вставлять токен в командную строку, документацию или git.
export GH_TOKEN='<read-only secret managed outside Git>'
python scripts/v894_hosted_ci_evidence.py \
  --repo PetrFedin/magadan \
  --pr 15 \
  --branch feature/v89-provenance-and-load-reconciliation \
  --sha '<current exact 40-hex head SHA>' \
  --run v89='<run id>' \
  --run full='<run id>' \
  --run unified='<run id>' \
  --out runtime/v894-hosted-metadata-receipt.json
unset GH_TOKEN
```

Без `GH_TOKEN`/`GITHUB_TOKEN` скрипт **не обращается** к API и возвращает `HOSTED_CI_HOLD:GITHUB_READ_TOKEN_REQUIRED`, exit code 2. Токен не сохраняется в квитанции. Файл квитанции создаётся как новый с правами 0600, существующий файл не перезаписывается. Содержимое `runtime/` не коммитить.

Проверка `--run` на старых успешных запусках корректно откажет при несовпадении текущего PR HEAD. Никакое зелёное состояние **одного** workflow не заменяет остальные два.

## 4. Автономная проверка кода

```bash
python -m unittest discover -s scripts/tests -p 'test_v894_hosted_ci_evidence.py' -v
python -m unittest discover -s scripts/tests -p 'test_v89_inline_workflow_python.py' -v
```

В независимом Python 3.13 контейнере проверены **18/18** синтетических тестов auditor gate и отдельно прежние **4/4** inline-Python теста. Среди отрицательных сценариев: `runner_id=0`, нет steps, skipped step, отсутствующий shard, чужой SHA, неправильный branch, новый PR HEAD, PR уже merged, retarget PR на `main`, дубликат job ID, отсутствие обязательного test-step, усечённые ответы. Проверка реального GitHub API этим результатом **не подтверждена**.

## 5. Фактический CI и доступность Mac

При последней внешней проверке предыдущего source SHA `923537e1f1ac3dcdc0b0d685f875690c9eaf0888`:

- [V8.9 #43765933395](https://github.com/PetrFedin/magadan/actions/runs/43765933395): `runner_id=0`, `steps=0`, завершение `failure` до исполнения.
- [Full #43765933472](https://github.com/PetrFedin/magadan/actions/runs/43765933472): entry job `runner_id=0`, `steps=0`, зависимые тесты skipped.
- Mac Desktop Commander по внешней проверке **offline**.

Этот результат **не** означает, что тесты упали из-за изменения бизнес-кода, но и не является PASS. Для V8.9.4 нужен новый полный запуск на новом SHA. Предыдущие отчёты V8.6/V8.7 и отдельные локальные 18 тестов его не заменяют.

## 6. Невыполненные требования и запреты

- Текущая metadata-квитанция **не сверяет содержимое JUnit/логи/артефакты по внешнему SHA** и не заменяет независимый аудит происхождения исходников и артефактов. Даже `GITHUB_HOSTED_METADATA_SUCCESS_ONLY` — свидетельство метаданных успешного исполнения, а не технический sign-off.
- Реальный корпоративный IdP с MFA, защищённый staging ingress, PostgreSQL 17/RLS под корпоративной авторизацией, независимые сеансы, внешнее WORM-хранилище и независимый backup/PITR-акт — **HOLD**.
- Реальные данные энергосистемы, письменные разрешения правообладателей, подписанная инженерная N−1 валидация, действительная доступная мощность, инвестиционные выводы и промышленный запуск — **HOLD**.
- Никаких команд SCADA/dispatch, финансовых проводок или заявлений о реальной мощности. `real_available_capacity_mw=null`, `investment_decision=HOLD`, `production_ready=false`.
- `main` и production **не изменять**. PR #15 — Draft. Отдельный [Issue #16](https://github.com/PetrFedin/magadan/issues/16) напоминает о включении защиты `main`.

**Источники:** [Draft PR #15](https://github.com/PetrFedin/magadan/pull/15), [CI runner Issue #6](https://github.com/PetrFedin/magadan/issues/6), [корпоративная приёмка Issue #4](https://github.com/PetrFedin/magadan/issues/4), [права на данные Issue #14](https://github.com/PetrFedin/magadan/issues/14), [V8.9.3 предшествующий протокол](V893_CI_RECOVERY_AND_STAGING_GATES_RU.md).
