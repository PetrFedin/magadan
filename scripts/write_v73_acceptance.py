#!/usr/bin/env python3
"""Read completed artifact logs; do not turn unexecuted native/browser tests green."""
from collections import Counter
from datetime import date
from pathlib import Path
import csv,json,re
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'artifacts_v73';D=ROOT/'docs'
py=(A/'regression_python.log').read_text()
js=(A/'regression_js.log').read_text()
native=(A/'native_pg17_acceptance.log').read_text()
stress=json.loads((A/'stress_radial_v73.json').read_text())
layout=json.loads((A/'layout_qa_v73.json').read_text())
features=list(csv.DictReader((D/'V73_FEATURE_REGISTER.csv').open()))
openapi=json.loads((D/'openapi_v73.json').read_text())
np=int(re.search(r'([0-9]+) passed in [0-9.]+s',py).group(1))
nj=int(re.search(r'# pass ([0-9]+)',js).group(1))
assert np>=145 and nj==63 and stress['accepted'] and layout['status']=='STATIC_LAYOUT_PASS'
assert 'NATIVE_ACCEPTANCE_BLOCKED' in native
assert all(item['production_accepted']=='NO' for item in features)
states=dict(Counter(x['implementation_status'] for x in features))
operations=sum(len(v) for v in openapi['paths'].values())
status={'release':'V7.3','as_of':'2026-10-23','scope':'ISOLATED_SYNTHETIC_LAB','production_ready':False,
 'server_python_tests':{'status':'PASS','count':np,'log':'artifacts_v73/regression_python.log'},
 'legacy_js_tests':{'status':'PASS','count':nj,'log':'artifacts_v73/regression_js.log'},
 'randomized_synthetic_network_checks':{'status':'PASS','count':stress['case_count'],'seed':stress['seed'],
   'max_active_balance_error_mw':stress['max_active_balance_residual_mw'],
   'max_nodal_solver_difference_v':stress['max_nodal_solver_voltage_difference_v'],
   'artifact':'artifacts_v73/stress_radial_v73.json'},
 'frontend_layout':{'status':'STATIC_ONLY_PASS','widths':[375,768,1440],
   'authenticated_server_browser_E2E':False,'artifact':'artifacts_v73/layout_qa_v73.json'},
 'native_postgresql17_rls':{'status':'BLOCKED_NOT_EXECUTED','failure_code':'NATIVE_ACCEPTANCE_BLOCKED',
   'artifact':'artifacts_v73/native_pg17_acceptance.log'},
 'real_corporate_oidc':{'status':'NOT_CONNECTED'},
 'compliant_external_worm':{'status':'NOT_VALIDATED'},
 'independent_engineering_benchmark':{'status':'NOT_COMPLETED'},
 'authorized_magadan_network_data':{'status':'NOT_AVAILABLE'},
 'source_requirements':{'count':len(features),'status_counts':states,'industrial_accepted_count':0},
 'http_operations_documented':operations,
 'engineering_finance_showcase':'artifacts_v73/showcase_trace_v73.json',
 'production_hold':True}
(A/'acceptance_summary_v73.json').write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
lines=['# ГИДРОКОНТУР 360 — МАГАДАН / Протокол V7.3','',
 '**Дата:** 23 октября 2026 г. **Результат:** LAB PASS / INDUSTRIAL HOLD.','',
 '| Приёмочный блок | Итог | Свидетельство |','|---|---|---|',
 f'| Python: серверная логика и API | **{np} PASS** | `regression_python.log` |',
 f'| JS: унаследованные детерминированные проверки | **{nj} PASS** | `regression_js.log` |',
 f'| Детерминированные 64 синтетические сети | **{stress["case_count"]} PASS** | `stress_radial_v73.json` |',
 '| Физика→экономика, воспроизводимые исходные данные | **PASS в лаборатории** | `showcase_trace_v73.json` |',
 '| UI 1440 / 768 / 375 | **STATIC PASS** (без live HTTP и авторизации) | `layout_qa_v73.json` |',
 '| PostgreSQL 17 / RLS / конкуренция | **BLOCKED / NOT TESTED** | `native_pg17_acceptance.log` |',
 '| Корпоративный OIDC/MFA | **НЕ ПОДКЛЮЧЁН** | Заказчик не предоставлял IdP |',
 '| Внешний WORM с проверенным retention | **НЕ ПРИНЯТ** | Нет целевого хранилища |',
 '| Независимый профессиональный электротехнический эталон | **НЕ ИСПОЛНЕН** | Только сравнение двух учебных численных методов |',
 '| Исходные данные сетей Магаданской области | **НЕТ** | Нет согласования собственника и исторических данных |',
 '',f'**Функциональная матрица:** {len(features)} функций. '+', '.join(f'{k}: {v}' for k,v in sorted(states.items()))+
 '. Ни одна функция не получила промышленную приёмку.','',
 f'**OpenAPI:** {operations} документированных HTTP-операций. Наличие операции не доказывает безопасность её промышленного использования.','',
 '## Синтетический инженерно-экономический пример','',
 'Базовые потери: 2,399290916 МВт·ч; альтернативные: 1,349564646 МВт·ч; за 144 ч — разница 1,049726270 МВт·ч. Учебная годовая экстраполяция — 50 повторов, или 7 200 ч, 52 486,3135 кВт·ч. Цена 2/3/5 ₽/кВт·ч, условный CAPEX 1,8 млн ₽, OPEX 150 тыс. ₽/год, горизонт 8 лет, дисконт 12%. NPV для базового сценария **−1 762 946,67 ₽**, не экономическая выгода. Полные расчёты и hashes — `showcase_trace_v73.json`.','',
 '## Непреодолённые допуски','',
 'Результаты тестов не являются заключением инженера и не подтверждают объект Магаданской области. Перед промышленным пилотом обязательны выделенная PostgreSQL 17 с нативной RLS-приёмкой, независимая электротехническая модель, права на реальные данные, SSO и согласованная внешняя аудиторская инфраструктура.','',
 'Производственный статус: **HOLD**. Рекомендуемый шаг: исполнить `.github/workflows/native-v73.yml` только в разрешённой изолированной среде; затем оформить подписанный нативный протокол и допуск к отдельному сетевому пилоту.']
(A/'TEST_REPORT_V73.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'python':np,'js':nj,'stress':stress['case_count'],'requirements':len(features),'openapi':operations,'native':'BLOCKED_NOT_TESTED'}))
