#!/usr/bin/env python3
"""Auditable LAB case. Does not connect to real Magadan assets, networks, or tariffs."""
from __future__ import annotations
import json,sys,hashlib
from pathlib import Path
from decimal import Decimal as D, localcontext
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'server'))
from hydro_api.grid_cashflow_v78 import evaluate_grid_dcf_v78
from tests_v78.test_grid_dcf_domain import inputs,dcf,wbs


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def make():
    bc,ac,br,ar,cap,param=inputs()
    outcome=evaluate_grid_dcf_v78(bc,ac,br,ar,cap,param)
    # Independent financial arithmetic from individual rows in the published trace.
    cross={}
    with localcontext() as ctx:
        ctx.prec=42
        for kind,calc in outcome['scenario_results'].items():
            own=D('0')
            for row in calc['yearly_cashflows']:
                net=D(row['gross_rub'])-D(row['opex_delta_rub'])-D(row['capex_from_wbs_rub'])
                assert net==D(row['net_rub'])
                own+=net/(D('1')+param.nominal_discount_rate)**int(row['t_year_end'])
            disclosed=D(calc['npv_rub'])
            difference=abs(own-disclosed)
            if difference>D('0.05'):
                raise ValueError('INDEPENDENT_NPV_ARITHMETIC_MISMATCH')
            cross[kind]={'own_recalculated_npv_rub':str(own.quantize(D('0.01'))),
                         'difference_before_rounding_rub':str(difference),
                         'within_5_kopeck_tolerance':True}
    raw={'version':'V7.8','classification':'SYNTHETIC_LAB_ONLY',
         'baseline_case':bc.model_dump(mode='json'),'alternative_case':ac.model_dump(mode='json'),
         'baseline_grid_result':br,'alternative_grid_result':ar,
         'exclusive_wbs':cap.model_dump(mode='json'),'financial_input':param.model_dump(mode='json'),
         'result':outcome,'arithmetic_crosscheck':cross,
         'not_verified':['actual tariffs','real Magadan measurements','project construction quantities',
             'independent powerflow solver','PostgreSQL RLS','independent engineering certification'],
         'industrial_approval_eligible':False}
    raw['trace_sha256_without_self_hash']=sha(raw)
    art=root/'artifacts_v78';art.mkdir(exist_ok=True)
    (art/'showcase_trace_v78.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2))
    lines=['# ГИДРОКОНТУР 360 — МАГАДАН · V7.8: воспроизводимый расчёт',
           '', '**Статус:** только синтетическая лаборатория, не данные «РусГидро».',
           '', '## Исходный технический сценарий',
           f"- Нагрузка: три узла, {bc.source_voltage_kv_ll} кВ; окно normal 120 ч и winter_peak 24 ч.",
           '- Альтернатива отличается только сопротивлением первого участка: 0,25 → 0,13 Ом на фазу.',
           f"- Базовые потери за цикл: {br['total_line_energy_loss_mwh']:.9f} МВт·ч.",
           f"- Потери альтернативы: {ar['total_line_energy_loss_mwh']:.9f} МВт·ч.",
           f"- Сокращение за один цикл: {(br['total_line_energy_loss_mwh']-ar['total_line_energy_loss_mwh']):.9f} МВт·ч.",
           '', '## Годовые физические и денежные результаты',
           '| Год | Смоделировано часов | Сэкономлено, кВт·ч | Расчётная стоимость экономии, ₽ | OPEX, ₽ | CAPEX, ₽ |',
           '|---|---:|---:|---:|---:|---:|']
    for y in outcome['annual_physical_economics']:
        lines.append(f"| {y['year']} | {y['modeled_hours']} | {y['signed_saved_energy_kwh']} | {y['gross_avoided_cost_rub']} | {y['opex_delta_rub']} | {y['wbs_capex_rub']} |")
    lines+=['','## NPV и независимая арифметическая сверка',
            '| Сценарий | NPV, ₽ | Независимый пересчёт, ₽ |', '|---|---:|---:|']
    for name,val in outcome['scenario_results'].items():
        lines.append(f"| {name} | {val['npv_rub']} | {cross[name]['own_recalculated_npv_rub']} |")
    lines+=['','Формула: `Loss_saved_kWh(y,w)= [P_loss_base(w)-P_loss_alt(w)] × hours(w) × cycles(y) × 1000 × retention(y)`.',
            '`Annual_gross(y)=Σ_w Loss_saved_kWh(y,w) × cost_rub_per_kWh(y,w)`.',
            '`NPV_s=Σ_y [gross(y) × scenario_factor_s − OPEX(y) − CAPEX_WBS(y)] / (1+r)^(y−discount_anchor_year)`.',
            '', '### Ограничения и предупреждения',
            '- 7 200 ч в год — это **частичный модельный профиль**, не 8 760 часов и не наблюдение всех часов года.',
            '- CAPEX: одна синтетическая WBS с этапом ввода; не сертифицированная смета.',
            '- Все цены — **условная стоимость предотвращённых потерь**, не тарифы.',
            '- Налоги, НДС, финансирование, гранты, многолетняя инфляция, несимметрия сети, N-1, защита, реальная топология не рассчитаны.',
            '- Положительный NPV, если он появится при иных допущениях, не разрешает строительство или эксплуатацию.',
            '- Отсутствуют согласованные данные Магаданской области и независимый инженерный протокол.']
    (art/'CALCULATION_WALKTHROUGH_V78_RU.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'trace':str(art/'showcase_trace_v78.json'),
                      'baseline_mwh':br['total_line_energy_loss_mwh'],
                      'proposed_mwh':ar['total_line_energy_loss_mwh'],
                      'npv':{k:v['npv_rub'] for k,v in outcome['scenario_results'].items()},
                      'wbs_rub':outcome['wbs_total_capex_rub'],
                      'independent_crosscheck':cross},ensure_ascii=False,indent=2))

if __name__=='__main__':make()
