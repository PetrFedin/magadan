"""Strict dossier types; acceptance does NOT prove real-world authenticity."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .engineering import GridCase

class Strict(BaseModel): model_config=ConfigDict(extra='forbid')

class EngineeringReport(Strict):
    run_id:str=Field(min_length=10)
    finding:str=Field(min_length=16,max_length=2000)
    methodology_ref:str=Field(min_length=8,max_length=180)
    signed_document_ref:str=Field(min_length=8,max_length=250)

class FinancialReport(Strict):
    run_id:str=Field(min_length=10)
    currency:Literal['RUB']
    initial_capex_rub:Decimal=Field(ge=0,le=Decimal('100000000000000'))
    annual_net_benefit_rub:Decimal=Field(ge=Decimal('-100000000000000'),le=Decimal('100000000000000'))
    discount_rate:Decimal=Field(gt=Decimal('0'),le=Decimal('1'))
    horizon_years:int=Field(ge=1,le=100)
    methodology_ref:str=Field(min_length=8,max_length=180)
    assumption_status:Literal['SYNTHETIC']

class ApprovalMemo(Strict):
    decision_ref:str=Field(min_length=8,max_length=200)
    authorized_body:str=Field(min_length=8,max_length=200)
    decision:Literal['approved']
    approval_date:date

class ExecutionProof(Strict):
    work_package_ref:str=Field(min_length=8,max_length=200)
    completion_date:date
    acceptance_document_ref:str=Field(min_length=8,max_length=200)

class OutcomeReport(Strict):
    run_id:str=Field(min_length=10)
    verification_method:str=Field(min_length=16,max_length=2000)
    observed_loss_mw:Decimal=Field(ge=0,le=Decimal('100000'))
    observation_ref:str=Field(min_length=8,max_length=200)
    period_start:date
    period_end:date
    @model_validator(mode='after')
    def validate_period(self):
        if self.period_end<self.period_start:raise ValueError('Period end before start')
        return self

SCHEMAS={
 'grid_input':GridCase,
 'engineering_report':EngineeringReport,
 'financial_report':FinancialReport,
 'approval_memo':ApprovalMemo,
 'execution_proof':ExecutionProof,
 'outcome_report':OutcomeReport,
}

def validate_payload(kind,payload):
    return SCHEMAS[kind].model_validate(payload).model_dump(mode='json')

def financial_npv(report:FinancialReport):
    capex=report.initial_capex_rub
    ann=report.annual_net_benefit_rub
    r=report.discount_rate
    return str((-capex+sum(ann/(Decimal('1')+r)**i for i in range(1,report.horizon_years+1))).quantize(Decimal('0.01')))
