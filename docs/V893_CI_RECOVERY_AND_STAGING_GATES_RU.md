# HydroKontur 360 — CI recovery / V8.9.3 engineering checkpoint

**Дата:** 16.11.2026. **Контур:** V8.9 synthetic research, Draft PR #15. **Release:** HOLD.  
**Назначение:** зафиксировать *фактически проверенные* признаки, минимальный CI-fix и следующие условия защищённого staging. Не является сертификатом безопасности, выдачей мощностей или разрешением на эксплуатацию.

## 1. Подтверждённые факты, отдельно от оценок

- GitHub-hosted запуск [V8.9 #43765835368](https://github.com/PetrFedin/magadan/actions/runs/43765835368) на source-pinned commit `f31d777644e45f656bc15bfe5516b1c9027044cb`: job `v89-source-rights-hourly-grain-dedup` завершился `failure` **до выделения runner** (`runner_id=0`, `steps=0`). Это **не падение выполнявшихся тестов**.
- Полный [V8.8+V8.9 #43765835385](https://github.com/PetrFedin/magadan/actions/runs/43765835385): `provenance-and-parser` и `final-check` также `runner_id=0`, `steps=0`; зависимые тестовые jobs `skipped`. **Никакого GREEN на этом SHA нет.**
- Историческая аннотация GitHub указывала на failed payments/spending limit; она описана в [Issue #6](https://github.com/PetrFedin/magadan/issues/6). Текущую причину **не удалось независимо подтвердить через настройки Billing**. Проверять её вручную; никаких платных изменений/расширения лимитов автоматически.
- Mac Desktop Commander при проверке был **offline**, поэтому на данном SHA нельзя подтвердить локальную PostgreSQL17/Chromium/OIDC/restore интеграционную приёмку.

## 2. Исправленный дефект в исходниках CI

В `.github/workflows/v89-source-quarantine.yml` внутри `python - <<'PY'` использовался **shell-оператор `||`**, недопустимый в Python. Он порождал бы `SyntaxError` после запуска runner. Оператор заменён на Python `or`.

Добавлен `scripts/tests/test_v89_inline_workflow_python.py`: стандартный `unittest` извлекает встроенные Python-heredoc в V8.9 и полной V8.8+V8.9 CI-конфигурации, компилирует их через `compile(..., "exec")`, отклоняет пустой/незакрытый блок и содержит отрицательный тест для `||`. Запуск добавлен **до установки зависимостей приложения** в оба workflow.

Локально проверены 4 теста на изолированных workflow-образцах. **Полное исполнение в GitHub / на точном дереве не подтверждено:** GitHub-hosted runner не стартовал. Любое следующее изменение workflow требует свежего source-pinned прогона.

Повторная команда в полноценном checkout:

```bash
python -m unittest discover -s scripts/tests -p 'test_v89_inline_workflow_python.py' -v
python -m unittest discover -s scripts/tests -p 'test_v84_junit_gate.py' -v
```

## 3. Восстановление CI без имитации доказательств

1. Ответственный владелец проверяет GitHub Settings → Billing and licensing / Usage, Actions limits, account payment annotations и политику runner (Issue #6). **Не повышать бюджет без отдельного утверждения.**
2. После устранения причины запускает V8.9, full regression и unified staging workflows **на одном и том же commit SHA**. Каждый job должен иметь назначенный runner, фактически выполненные steps и доступный JUnit/лог. `failure` с `runner_id=0` не классифицировать как дефект тестов; `skipped` не считать PASS.
3. V8.9 focused suite: **не менее 76 PASS, 0 SKIP**, обязательные поимённые кейсы, JUnit SHA-256; full monolithic: **не менее 480 PASS** с только заранее разрешёнными объяснёнными пропусками. Числа — политика gates, **не текущие достижения**.
4. Проверить неизменность источников (`git rev-parse HEAD`, чистое дерево), конкретный `head_sha` и receipt. Все результаты прошлых SHA отделять от нового.
5. При доступном Mac восстановить исходный checkout по SHA, запустить существующие `scripts/run_v87_local_acceptance.sh` и `scripts/run_v88_local_acceptance.sh` **в изолированной тестовой среде** и отдельно проверить V8.9 regression. Точные команды, PostgreSQL и браузерные prerequisites — в V8.7/V8.8 документации. Не использовать production-БД.

## 4. Корпоративный staging: обязательные независимые gates

| Gate | Критерий приёмки | По текущим доказательствам |
| --- | --- | --- |
| Изолированная инфраструктура | Отдельная защищённая площадка, закрытый ingress/TLS, собственная PG17, минимальные роли, воспроизводимый IaC | **HOLD** |
| Identity | Настоящий корпоративный IdP; Authorization Code + PKCE, confidential client, подтверждённая MFA/ACR/AMR, revoke, CSRF, отсутствие лабораторного bypass | **HOLD** |
| Одновременный E2E | Chromium с независимыми корпоративными сессиями шести ролей + PG17 FORCE RLS на **одной** staging-БД; cross-tenant DENY | **HOLD** |
| Аудит | Подписанные события, доставка в **внешнее** WORM, проверка immutability/retention и разделение полномочий | **HOLD** |
| Recovery | Отдельная защищённая restore-среда, реальный backup/PITR, проверенные RPO/RTO, независимый акт и аудит RLS | **HOLD** |
| Реальные источники | Письменные права, signed source bytes и независимая проверка владельца; хранение **вне GitHub** | **HOLD** |
| Энергобаланс / N−1 | Правомерно полученные почасовые и узловые данные, baseline dedup, независимый расчёт, подпись компетентного проверяющего | **HOLD** |
| Деньги / эксплуатация | Независимая экономика и инженерное согласование после всех предыдущих gates | **HOLD** |

Подробные документы: `docs/V87_UNIFIED_STAGING_ACCEPTANCE_RU.md`, `docs/V89_EVIDENCE_INTEGRITY_RU.md`, `docs/V89_INDEPENDENT_N1_AND_BALANCE_ACCEPTANCE_PROTOCOL_RU.md`.

## 5. Неподлежащие снятию ограничения

- Весь лабораторный набор V8.9 **синтетический**; двойная Ed25519-подпись по тестовой политике не доказывает юридические права, корпоративную должность или независимый N−1.
- `real_available_capacity_mw=null`, `investment_decision=HOLD`, `production_ready=false`; никакие расчёты не разрешают SCADA/dispatch, бухгалтерские проводки или инвестиционное утверждение.
- Ни корпоративный staging, ни внешняя WORM, ни реальные контракты потребителей не развёрнуты и не сертифицированы данным изменением.
- PR #15 оставлять **Draft**, без merge; `main` и production не изменять.

**Трекинг:** [PR #15](https://github.com/PetrFedin/magadan/pull/15) · [CI runner #6](https://github.com/PetrFedin/magadan/issues/6) · [Corporate evidence #4](https://github.com/PetrFedin/magadan/issues/4) · [Rights-cleared grid data #14](https://github.com/PetrFedin/magadan/issues/14).
