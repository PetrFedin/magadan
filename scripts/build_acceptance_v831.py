"""Build V8.3.1 laboratory evidence from executed test logs, no inferred PASS."""
from __future__ import annotations
from pathlib import Path
import json, re, hashlib

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v83'
GROUPS={'a':'regression_group_a_v831.log',
        'b1':'regression_group_b1_v831.log',
        'b2':'regression_group_b2_v831.log',
        'c':'regression_group_c_v831.log'}
results={}
for key,name in GROUPS.items():
    data=(OUT/name).read_text()
    match=re.search(r'(?m)^(\d+) passed(?:, (\d+) skipped)? in [\d.]+s$',data.strip())
    if not match:
        raise RuntimeError('SOURCE_TEST_LOG_INCOMPLETE_OR_FAILED: '+name)
    results[key]={'pass':int(match.group(1)), 'skip':int(match.group(2) or '0')}
js=(OUT/'regression_js_v831.log').read_text()
js_pass=re.search(r'(?m)^# pass (\d+)$',js)
js_fail=re.search(r'(?m)^# fail (\d+)$',js)
if not js_pass or not js_fail or int(js_fail.group(1))!=0:
    raise RuntimeError('JAVASCRIPT_TEST_REPORT_NOT_PASS')
route=json.loads((OUT/'independent_hourly_route_v83.json').read_text())
stress=json.loads((OUT/'cascade_scenario_index_v83.json').read_text())['summary']
static=json.loads((OUT/'static_viewport_v83.json').read_text())
browser=json.loads((OUT/'browser_intercepted_v83.json').read_text())
total=sum(x['pass'] for x in results.values())
skipped=sum(x['skip'] for x in results.values())
assert (total,skipped,int(js_pass.group(1)),route['scenarios']) == (363,3,63,438)
assert route['conservation_check_passed'] and not route['external_hydraulic_solver_executed']
assert stress['release']=='8.3.1' and stress['daily_branch_evaluations']==60
assert static['status']=='STATIC_LAYOUT_PASS'
assert browser['status']=='BROWSER_ASGI_INTERCEPTED_TRANSPORT_BLOCKED_OR_FAILED'
files=['server/hydro_api/cascade_v83.py','server/hydro_api/cascade_api_v83.py',
       'server/hydro_api/forecast_v82.py','server/tests_v83/test_cascade_v83.py',
       'scripts/verify_route_independent_v83.py','.github/workflows/native-v83.yml',
       'server/ui/ui.js','server/tests_v83/fixture.py']
proof={'release':'8.3.1','date':'2026-11-02','classification':'SYNTHETIC_RESEARCH_ONLY',
       'python_test_groups':results,'python_pass':total,'python_skip':skipped,
       'javascript_pass':int(js_pass.group(1)),'javascript_fail':int(js_fail.group(1)),
       'scenario_summary':stress,'separate_integer_hour_reference':route,
       'static_ui':static,'network_browser_e2e':browser,
       'field_data_authorized':False,'real_reservoir_curves_attested':False,
       'independent_hydraulic_solver_passed':False,'native_postgresql17_rls_passed':False,
       'forecast_to_real_generation_validated':False,'benefit_ledger_touched':False,
       'production_ready':False,
       'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
(OUT/'acceptance_summary_v831.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

report=f'''# V8.3.1 — дополнительные испытания и исправление каузальности входных данных

**Дата:** 2 ноября 2026 года. **Сфера:** синтетическая гидрологическая/энергетическая исследовательская модель. **PRODUCTION HOLD**.

## Что исправлено после V8.3

При выпуске прогноза в **D 10:00 UTC** расчётные будущие сутки — [D+1 00:00,D+2 00:00); до начала 14 часов. При этом **начальный объём водохранилища на D+1 00:00 и полностью известный суточный сброс за день D** частично являются *будущими предположениями*, а НЕ измерениями, доступными уже в D 10:00. В V8.3.1 вход обязан явно содержать `SYNTHETIC_CONDITIONAL_FUTURE_ASSUMPTIONS_NOT_KNOWN_AT_FORECAST_ISSUE`. Отсутствующий или ложно названный известным источник приводит к Pydantic 422. В отчёте это отдельный risk flag. Результаты остаются **условным расчётом**, а не безусловным прогнозом генерации.

## Дополнительная численная проверка

Отдельный алгоритм `scripts/verify_route_independent_v83.py` делит сутки на 24 **отдельных часа**, генерирует шестёрки случайных прошлых и текущих сбросов на **каждом целочасовом лаге 0–72 часа**, заново подсчитывает поступление, начальную/конечную воду в пути и сохранение массы. Итого **73 × 6 = {route['scenarios']} синтетических испытаний**. Seed {route['seed']} воспроизводим. Максимальное расхождение после перевода разности объёмов в расход — **{route['max_flow_equivalent_error_cms']:.3g} м³/с**. Это независимая программная реализация *сдвига расхода во времени*, **не** независимый отраслевой решатель динамической гидравлики и **не** калибровка времени добегания реального объекта.

Проверены также масштабирование мощности по плотности воды (ровно пропорционально rho), реальное нулевое энергопроизводство при Q_turb=0, отрицательный напор (energy=null), и запрет скрывать нарушение локальных ограничений общим нулевым остатком массы. Два новых теста проверяют явность будущих условных допущений.

## Повторная регрессия

| Исполненная группа | PASS | SKIP | Источник stdout |
|---|---:|---:|---|
| V7.1–V7.4 | {results['a']['pass']} | {results['a']['skip']} | `regression_group_a_v831.log` |
| V7.5–V7.6 | {results['b1']['pass']} | {results['b1']['skip']} | `regression_group_b1_v831.log` |
| V7.7–V7.8 | {results['b2']['pass']} | {results['b2']['skip']} | `regression_group_b2_v831.log` |
| V7.9–V8.3.1 + legacy | {results['c']['pass']} | {results['c']['skip']} | `regression_group_c_v831.log` |
| **Всего Python** | **{total}** | **{skipped}** | Выполнено локально |
| **JavaScript** | **{int(js_pass.group(1))}** | **0** | `regression_js_v831.log`; ошибок 0 |

Синтетический сценарный набор: {stress['synthetic_cases']} условий × 3 ветви = **{stress['daily_branch_evaluations']}**; 4 искусственных нарушения ограничений обнаружены; общий округлённый остаток объёмного баланса 0 в этих случаях. Статический Chromium 375/768/1440 — PASS (вёрстка и отсутствие переполнения). **Настоящий авторизованный браузерный HTTP-E2E НЕ выполнен**: Chromium вернул `ERR_BLOCKED_BY_ADMINISTRATOR`, в том числе при перехвате транспорта. Native PostgreSQL 17/RLS и конкурентные транзакции **не запускались**: нет серверного PG17 в среде. GitHub CI рассматривается отдельно по точному SHA; результаты локальных тестов к нему не приравниваются.

## Невозможные выводы из лабораторного расчёта

**Нельзя выводить** фактическую приточность, генерацию, безопасность реальных режимов каскада, гидравлическое время добегания, вероятность риска, суммы в рублях, NPV или новую запись признанного Benefit Ledger. Нет подтверждённых разрешений на данные Магаданской области, паспортных кривых, реальных правил водопользования, внешнего гидравлического решателя, WORM/корпоративного IdP и независимого инженерного заключения.

**Статус:** `V8.3.1 LOCAL LAB PASS / CI PENDING OR BLOCKED / NATIVE PG HOLD / AUTHENTICATED BROWSER HOLD / FIELD HOLD / PRODUCTION HOLD`.
'''
(OUT/'TEST_REPORT_V831.md').write_text(report,encoding='utf-8')
print(json.dumps({'python_pass':total,'python_skip':skipped,'javascript_pass':int(js_pass.group(1)),
                  'hourly_reference_cases':route['scenarios'],'status':'LOCAL_LAB_PASS_PRODUCTION_HOLD'}))
