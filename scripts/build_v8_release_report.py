"""Produce a deterministic evidence summary from finished V8 test logs; never mark missing native tests passed."""
from __future__ import annotations
import json, re, hashlib, sys
from pathlib import Path
from datetime import datetime, timezone
root=Path(__file__).resolve().parents[1]
art=root/'artifacts_v8'
phases=[('legacy_early_A','legacy_tests_early1.log'),('legacy_early_B','legacy_tests_early2.log'),('late_versions_and_v8','legacy_tests_b_final.log')]
reports=[]
for name,fn in phases:
    data=(art/fn).read_text()
    matches=re.findall(r'(\d+) passed(?:, (\d+) skipped)? in ([\d.]+)s',data)
    if not matches: raise RuntimeError(f'INCOMPLETE_TEST_LOG:{fn}')
    passed, skipped, seconds=matches[-1]
    reports.append(dict(name=name,file=fn,passed=int(passed),skipped=int(skipped or 0),duration_seconds=float(seconds)))
node=(art/'js_tests_final.log').read_text()
js=re.search(r'# pass (\d+)',node)
fail=re.search(r'# fail (\d+)',node)
if not (js and fail and fail.group(1)=='0'):raise RuntimeError('JS_LOG_MISSING_OR_FAILED')
case=json.loads((art/'V8_REPRODUCIBLE_RESEARCH_CASE.json').read_text())
assert case['no_verified_savings'] and case['no_real_measurements']
assert case['quality_diagnostic']['certified_realized_savings'] is False
native=(art/'postgres_native_required.log').read_text()
assert 'NATIVE_ACCEPTANCE_BLOCKED' in native
native_status='BLOCKED_NOT_EXECUTED'
summary={
 'release':'V8.0-LAB','date':'2026-10-25',
 'python_test_groups':reports,
 'python_passed':sum(v['passed'] for v in reports),'python_skipped':sum(v['skipped'] for v in reports),
 'javascript_passed':int(js.group(1)),'javascript_failed':int(fail.group(1)),
 'postgres17_rls_native':native_status,
 'corporate_sso_mfa':'NOT_CONNECTED',
 'externally_anchored_immutable_audit':'NOT_CONNECTED',
 'external_independent_grid_solver':'NOT_EXECUTED',
 'magadan_field_measurements':'NOT_RECEIVED',
 'field_technical_signoff':'NOT_RECEIVED',
 'browser_live_end_to_end':'NOT_EXECUTED',
 'visual_layout_test':'NOT_CERTIFIED_BROWSER_RENDER',
 'verified_annual_savings_rub':None,
 'synthetic_signed_difference_kwh':case['quality_diagnostic']['observed_signed_difference_kwh'],
 'descriptive_holdout_error_envelope_kwh':case['quality_diagnostic']['error_envelope_kwh'],
 'synthetic_joint_support_fraction':case['quality_diagnostic']['post_joint_support_fraction'],
 'synthetic_case_file':'artifacts_v8/V8_REPRODUCIBLE_RESEARCH_CASE.json',
 'feature_scope':['canonical_metering_boundaries','nested_and_explicit_conflicts','sqlite_transactional_benefit_collision_guard','legacy_dossier_inventory_only','joint_covariate_mv_diagnostic','PG17_migration_candidate_only'],
 'release_status':'LAB_PASS_PRODUCTION_HOLD',
 'allowed_claim':'synthetic lab calculations and completed automated tests only',
 'prohibited_claims':['industrial safety passed','PG RLS passed','actual RusHydro savings','real Magadan load profile','independent professional engineering signoff']}
(art/'acceptance_summary_v8.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
md=f'''# V8.0 — Протокол фактической лабораторной приёмки

**Дата:** 25 октября 2026. **Статус:** LAB PASS / PRODUCTION HOLD.

## 1. Выполненные автоматизированные тесты

| Набор | Успешно | Пропущено | Длительность | Основание |
|---|---:|---:|---:|---|
'''
for x in reports:
 md+=f"| {x['name']} | {x['passed']} | {x['skipped']} | {x['duration_seconds']:.2f} с | `{x['file']}` |\n"
md+=f"| JavaScript/node | {summary['javascript_passed']} | 0 | см. журнал | `js_tests_final.log` |\n\n"
md+=f"**Итого:** {summary['python_passed']} успешно завершённых Python-тестов (ещё {summary['python_skipped']} пропущено) и {summary['javascript_passed']} JavaScript-теста без отказов. Python и JS — разные наборы, суммирование приведено только как описание покрытия. Повторный полный монолитный прогон превысил лимит времени; вместо него проведены перечисленные завершённые независимые группы, сохранившие свои журналы.\n\n"
md+='''## 2. Новые функции V8 и границы доказательства

1. Идентичность физической измерительной границы: один поток, несколько asset_id, вложенные и пересекающиеся области; блокировка двойного резервирования по пересекающимся годам и конфликтующим семействам эффекта. Проверено на SQLite и локальном HTTP-клиенте.
2. Неизменяемость лабораторной карты после резервирования; прямое изменение или запись SQLite по недопустимой связи отклоняются в выполненных негативных испытаниях. SQLite не является защищённым WORM-хранилищем.
3. Отдельная инвентаризация старых финансовых досье с запретом их автоматического объединения с новым реестром.
4. Диагностика модели M&V: отложенная историческая ошибка, смещение, lag-1 автокорреляция, двумерная область (нагрузка, температура). Рассчитанная оболочка ошибки не является вероятностным доверительным интервалом и не доказывает причинность.
5. PostgreSQL-миграция 150 написана и статически исследована, но не исполнена. Наличие SQL-файла не считается проверкой RLS, транзакционных блокировок и аудита на PG17.

## 3. Воспроизводимый синтетический пример

'''
md+=f"- Статус датасета: `{case['dataset']}`.\n"
md+=f"- Подписанная разница расчётных и наблюдаемых синтетических потерь: **{summary['synthetic_signed_difference_kwh']:.6f} кВт·ч** за указанные в наборе интервалы, не за год.\n"
md+=f"- Описательная оболочка на основе 95-го процентиля абсолютной holdout-ошибки: **{summary['descriptive_holdout_error_envelope_kwh']:.6f} кВт·ч**; это не CI и не подтверждённая экономия.\n"
md+=f"- Совместная область (нагрузка, температура): **{summary['synthetic_joint_support_fraction']:.3f}** условных наблюдений после.\n"
md+=f"- Входной SHA-256: `{case['source_sha256']}`.\n"
md+='''
## 4. Незакрытые проверки

- **POSTGRESQL NATIVE — BLOCKED:** обязательный запуск завершился `NATIVE_ACCEPTANCE_BLOCKED` из-за отсутствия выделенной PostgreSQL 17. Это зафиксировано в `postgres_native_required.log`. Новые таблицы и триггеры не тестировались нативно.
- **SSO / MFA — NOT CONNECTED:** в проекте есть лабораторная логика OIDC, но корпоративная система не интегрирована и её права/отзыв сессий в производственной среде не проверены.
- **EXTERNAL AUDIT — NOT CONNECTED:** внешний независимый WORM/retention и восстановление после аварии отсутствуют.
- **INDEPENDENT ENGINEERING — NOT EXECUTED:** отдельный промышленный решатель и квалифицированный инженер не выполнили подтверждающее испытание.
- **MAGADAN FIELD DATA — NOT RECEIVED:** нет права использования реальной схемы/параметров объекта и нет подтверждённых метрологических данных.
- **BROWSER E2E — NOT EXECUTED:** статические связи HTML/JS проверены, но браузерный протокол сквозного взаимодействия с авторизацией не засчитан; попытка запуска Chromium в текущей среде не завершилась.
- **LEGACY RECONCILIATION — OPEN:** старые досье лишь учтены в инвентаризации, общий валовый эффект объединять нельзя.
- **CROSS-ORGANIZATION BOUNDARIES — OPEN:** физические пересечения между юрлицами требуют отдельной модели и правового обоснования.

## 5. Коммерческий / инженерный запрет

Нельзя использовать лабораторные результаты в распоряжении оперативным оборудованием, утверждать CAPEX или публиковать «подтверждённую экономию» для Колымской ГЭС, Усть-Среднеканской ГЭС, «Магаданэнерго» и иных организаций. Для снятия HOLD необходимы последовательно независимая инфраструктурная, математическая, метрологическая, финансовая и юридическая приёмки.

Методология M&V: [Efficiency Valuation Organization — IPMVP](https://evo-world.org/en/products-services-mainmenu-en/protocols/ipmvp). PostgreSQL RLS: https://www.postgresql.org/docs/17/ddl-rowsecurity.html.
'''
(art/'TEST_REPORT_V8_RU.md').write_text(md)
print('TESTS',summary['python_passed'],summary['python_skipped'],summary['javascript_passed'])
