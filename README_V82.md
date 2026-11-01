# ГИДРОКОНТУР 360 — МАГАДАН V8.2

**HydroForecast Statistical Research — исследовательский прогноз и проверка на отложенных данных.**

Развитие из V8.1: суточная модель расходов м³/с на 1–7 дней с тремя прозрачными кандидатами, хронологически разделёнными выборками (выбор → калибровка → holdout), ошибками MAE/RMSE/Bias/WAPE, проверкой уровня покрытия полосы, lag-1 и высоководных дней, переводом расхода в условный объём одного дня. Данные синтетические: **никаких гидропостов Магаданской области или реальных расчётов «РусГидро» не подключено.**

## Запустить локально

```bash
python -m pip install -r server/requirements.txt
PYTHONPATH=server python -m pytest -q server/tests_v82
PYTHONPATH=server python scripts/reproduce_v82.py
PYTHONPATH=server python scripts/plot_forecast_v82.py
```

API: `POST /v82/orgs/{org_id}/hydroforecast/evaluate` — только авторизованный `engineer` или `auditor` лабораторной организации. Stateless: расчёт не фиксирует выручку, физическую команду или согласие на использование данных. Исходный код, точная формула и отсутствие утечки будущих измерений проверяются отдельными тестами.

Полная методология и ограничения: [`docs/V82_HYDROFORECAST_METHODS_RU.md`](docs/V82_HYDROFORECAST_METHODS_RU.md). Результаты сценариев: [`artifacts_v82/scenario_comparison_v82.csv`](artifacts_v82/scenario_comparison_v82.csv). Журнал испытаний: [`artifacts_v82/TEST_REPORT_V82.md`](artifacts_v82/TEST_REPORT_V82.md).

**PRODUCTION HOLD:** нет независимых профессиональных протоколов, реальных временных рядов, нативной PostgreSQL 17/RLS-приёмки, корпоративного IdP/MFA, подписанных неизменяемых журналов, независимых инженерных выводов и финансового допуска.
