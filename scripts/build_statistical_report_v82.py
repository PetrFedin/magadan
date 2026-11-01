"""Produce report from measured SYNTHETIC test results, never invented numbers."""
import json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'artifacts_v82'
rows=json.loads((p/'scenario_comparison_v82.json').read_text())
base=next(x for x in rows if x['scenario']=='ordinary' and x['horizon_days']==2)
shift=next(x for x in rows if x['scenario']=='increase_65_cms' and x['horizon_days']==2)


def safe(s):return '—' if s is None else str(s)

doc='''# HydroForecast V8.2 — статистический отчёт по лабораторным сценариям

**Источник:** `scripts/reproduce_v82.py` + точный синтетический ряд. **Никаких данных реальных ГЭС или гидропостов Магаданской области.** Дата выпуска отчёта: 2026-11-01. Все показатели получены выполнением кода, в рублях и МВт·ч расчётов нет.

В каждой строке: 168 суточных наблюдений; 84 ранняя история + 28 выбор модели + 28 калибровка + 28 независимая временная оценка. Номинальная полоса 90%, **эмпирическое** покрытие может отличаться. Режимный сдвиг искусственно добавлен только к последним 28 значениям — расчёт намеренно не способен «знать» его заранее.

## 20 сценариев: горизонт и ухудшение водности

| Сценарий | Горизонт, суток | Модель | MAE, м³/с | RMSE, м³/с | Bias, м³/с | WAPE, % | Покрытие, % | Промахи из 28 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
'''
for r in rows:
 doc+=f"| {r['scenario']} | {r['horizon_days']} | {r['selected_model']} | {r['mae_cms']:.3f} | {r['rmse_cms']:.3f} | {r['bias_cms']:.3f} | {safe(r['wape_percent'])} | {100*r['actual_coverage']:.2f} | {r['interval_misses']} |\n"

mae_pct=100*(shift['mae_cms']/base['mae_cms']-1)
rmse_pct=100*(shift['rmse_cms']/base['rmse_cms']-1)
coverage_pp=100*(shift['actual_coverage']-base['actual_coverage'])
doc+=f'''
## Пример интерпретации: h=2 суток

- В исходном синтетическом режиме: MAE **{base['mae_cms']:.6f} м³/с**, RMSE **{base['rmse_cms']:.6f} м³/с**. Номинал полосы 90%, фактически **{100*base['actual_coverage']:.2f}%**: {28-base['interval_misses']} из 28 значений внутри.
- При искусственном сдвиге на +65 м³/с: MAE **{shift['mae_cms']:.6f} м³/с**, RMSE **{shift['rmse_cms']:.6f} м³/с**, фактическое покрытие **{100*shift['actual_coverage']:.2f}%**: {28-shift['interval_misses']} из 28.
- Относительный рост MAE = `100 × (MAE_shift / MAE_baseline − 1)` = **{mae_pct:.2f}%**. Рост RMSE **{rmse_pct:.2f}%**. Изменение покрытия **{coverage_pp:+.2f} процентного пункта**.
- Отбор выбрал модель **{base['selected_model']}**. На независимом holdout она не лучше простого `persistence` (skill = {safe(base['skill_vs_persistence_percent'])}%). Это **недостаточная модель для прямого принятия решений**. Отбор/подгонка модели не исправляет неизвестную смену физического режима.
- Lag-1 корреляция ошибок базового holdout **{safe(base['lag1'])}**, что сигнализирует о возможной серийной зависимости и несоответствии простым предпосылкам интервального метода; **не** является тестом значимости корреляции.

## Воспроизводимые материалы

- [`scenario_comparison_v82.csv`](scenario_comparison_v82.csv) — 20 строк с числами по всем горизонтам.
- [`scenario_comparison_v82.json`](scenario_comparison_v82.json) — также флаги риска и SHA входных рядов.
- [`single_forecast_report_v82.json`](single_forecast_report_v82.json) — исходные 168 наблюдений и детальный backtest одного кейса.
- [`holdout_forecast_v82.csv`](holdout_forecast_v82.csv) — 28 предсказаний, фактов и границ полосы.
- [`forecast_holdout_v82.png`](forecast_holdout_v82.png) и [`forecast_stress_v82.png`](forecast_stress_v82.png) — визуальная проверка.

**Статус:** лабораторная проверка численных алгоритмов. Без нормативно утверждённого ряда, независимого гидролога, калибровки паводков и проверки за пределами времени настройки **нет объективной основы для прогноза реальной генерации, предотвращённого ущерба или рублевой экономии**.
'''
(p/'STATISTICAL_SCENARIOS_V82_RU.md').write_text(doc)
print('Wrote report',len(doc),'chars')
