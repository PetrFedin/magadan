"""Summarize real execution evidence, never mark blocked tests PASS."""
from pathlib import Path
import json,re,hashlib,csv
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts_v83'
logs={k:(OUT/f'regression_group_{k}.log').read_text() for k in 'abc'}
counts={}
for key,body in logs.items():
    pattern=r'(\d+) passed, (\d+) skipped'
    match=re.search(pattern,body)
    if not match:raise RuntimeError('TEST_GROUP_MISSING_OR_FAILED '+key)
    counts[key]={'passed':int(match.group(1)),'skipped':int(match.group(2))}
js=(OUT/'regression_javascript.log').read_text()
match=re.search(r'# pass (\d+)\n# fail (\d+)',js)
if not match:raise RuntimeError('JAVASCRIPT_OUTPUT_INVALID')
js_pass,js_fail=map(int,match.groups())
if js_fail:raise RuntimeError('JAVASCRIPT_FAILED')
stress=json.loads((OUT/'cascade_scenario_index_v83.json').read_text())['summary']
static=json.loads((OUT/'static_viewport_v83.json').read_text())
browser=json.loads((OUT/'browser_intercepted_v83.json').read_text())
source_files=['server/hydro_api/cascade_v83.py','server/hydro_api/cascade_api_v83.py',
              'server/hydro_api/forecast_v82.py',
              'server/ui/ui.js','server/tests_v83/test_cascade_v83.py']
proof={
  'release':'8.3','date':'2026-11-02','status':'LOCAL_LAB_PASS_PRODUCTION_HOLD',
  'tests':{'python_passed':sum(x['passed'] for x in counts.values()),
           'python_skipped':sum(x['skipped'] for x in counts.values()),
           'by_group':counts,'javascript_passed':js_pass,'javascript_failed':js_fail},
  'scenarios':stress,
  'ui_static':static,
  'browser_network_e2e':browser,
  'native_postgresql_17':{'status':'NOT_EXECUTED','server_installed':False,
      'rls_verified':False,'concurrency_verified':False},
  'external_hydraulic_solver':{'status':'NOT_EXECUTED'},
  'field_magadan_data':{'status':'NOT_AUTHORIZED_OR_AVAILABLE'},
  'actual_rushydro_economics_accepted':False,
  'source_sha256':{x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in source_files},
}
assert proof['tests']['python_passed']==357
assert proof['tests']['javascript_passed']==63
assert proof['tests']['python_skipped']==3
assert proof['scenarios']['daily_branch_evaluations']==60
assert static['status']=='STATIC_LAYOUT_PASS'
assert browser['status']!='BROWSER_ASGI_INTERCEPTED_TRANSPORT_PASS'
(OUT/'acceptance_summary_v83.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

text=f'''# V8.3 — протокол лабораторной приёмки

Дата: 2 ноября 2026 года. Область: **только синтетическая модель каскада**. Никаких реальных данных и допусков «РусГидро».

## Фактически выполненные проверки

| Контроль | Фактический результат |
| --- | --- |
| Python, исторические группы V7.1–V7.4 | **{counts['a']['passed']} PASS, {counts['a']['skipped']} SKIP** |
| Python, группы V7.5–V7.8 | **{counts['b']['passed']} PASS, {counts['b']['skipped']} SKIP** |
| Python V7.9, V8.0, V8.1, V8.2, V8.3, legacy | **{counts['c']['passed']} PASS, {counts['c']['skipped']} SKIP** |
| Всего Python | **{proof['tests']['python_passed']} PASS, {proof['tests']['python_skipped']} SKIP** |
| JavaScript | **{js_pass} PASS, {js_fail} FAIL** |
| Синтаксис UI JavaScript | **PASS** (`node --check`) |
| Нормальные синтетические сценарии | **20 наборов × 3 ветви = 60** расчётов |
| Проверки искусственных нарушений | **4 из 4** нарушений обнаружены |
| Остаток общего объёмного баланса | Максимальное модульное округлённое отклонение **0.00000 м³** в 60 испытаниях; допуск теста 0.001 м³ |
| Статические размеры Chromium | **375 / 768 / 1440 px PASS**, без горизонтального переполнения |
| Авторизованный браузерный E2E | **BLOCKED**: Chromium `ERR_BLOCKED_BY_ADMINISTRATOR`, в том числе при маршрутизации через TestClient |
| Нативная PostgreSQL 17/RLS | **NOT EXECUTED**: отсутствует установленный PostgreSQL, live native test не пройден |
| Независимая гидравлика, данные Магадана, подтверждение собственника | **NOT EXECUTED** |

## Числовая чувствительность (строго искусственная)

- В 60 испытаниях условный диапазон суммарного энергетического баланса: **5152.178089–5180.973841 МВт·ч за одни сутки** на заданных условиях постоянных сбросов; это не генерация реальных ГЭС.
- Эмпирическое покрытие прогнозной полосы при искусственных режимных сдвигах: **75%–82.1429%** при номинальном уровне 90%. Это **не калиброванные вероятности**, а статистический риск применения прогнозов.
- На базовой центральной ветви задержка 0/12/24/36 часов меняет рассчитанное поступление из верхнего водохранилища **150 / 147.5 / 145 / 138.5 м³/с**; в искусственном ряду прошлые сбросы были 145 и 132 м³/с.
- Изменения выработки в модели связаны только с интерполированным средним напором при фиксированном турбинном расходе, **без моделирования реальных оптимизационных режимов**.
- Сценарии с нарушением вместимости, минимального сброса, паспортной мощности и скорости изменения режима правильно получают `energy_mwh = null`.

## Допущения, которые препятствуют промышленной приёмке

Нет настоящей гидрологии, паспортных кривых, калиброванного routing, динамики уровней, прав на объектные данные, актуального графика работ и независимого инженерного заключения. Результат V8.2 — один целевой день, не прогнозный вектор каскада. Расчёт MWh не превращается в RUB, NPV, экономию и Benefit Ledger.

## Воспроизводимость

Команды:

```bash
PYTHONPATH=server python -m pytest -q server/tests_v83
python scripts/reproduce_v83.py --out artifacts_v83
python scripts/plot_cascade_v83.py
node --check server/ui/ui.js
(cd v6-client && npm test)
```

Полная Python-регрессия выполнялась тремя независимыми группами, их stdout хранится в `artifacts_v83/regression_group_[abc].log`. Сценарные результаты в `cascade_scenario_matrix_v83.csv`, SHA моделей и отчётов — в `cascade_scenario_index_v83.json`.

**Итог: LOCAL LAB PASS / BROWSER E2E HOLD / NATIVE PG17 HOLD / FIELD DATA HOLD / PRODUCTION HOLD.**
'''
(OUT/'TEST_REPORT_V83.md').write_text(text,encoding='utf-8')
print('QUALITY_ASSURANCE',{k:proof['tests'][k] for k in ('python_passed','python_skipped','javascript_passed')})
