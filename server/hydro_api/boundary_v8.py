"""V8 laboratory boundary register: conservative canonical identity, not a field metering attestation."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from .radial_grid import Strict

Quantity = Literal['ELECTRIC_ENERGY','HEAT_ENERGY','EQUIPMENT_MAINTENANCE','FINANCIAL_PROCESS']

class NewBoundary(Strict):
    id: str = Field(pattern=r'^SYNTHETIC-[A-Za-z0-9_-]{7,80}$')
    parent_id: str | None = None
    quantity_class: Quantity
    source_ref: str = Field(pattern=r'^SYNTHETIC-[A-Za-z0-9_-]{12,120}$')

    @model_validator(mode='after')
    def self_parent(self):
        if self.parent_id == self.id:
            raise ValueError('BOUNDARY_CANNOT_CONTAIN_ITSELF')
        return self

class AssignAsset(Strict):
    asset_id: str = Field(min_length=1,max_length=120)
    boundary_id: str = Field(min_length=18,max_length=100)
    evidence_ref: str = Field(pattern=r'^SYNTHETIC-[A-Za-z0-9_-]{12,120}$')

class ExplicitOverlap(Strict):
    boundary_a: str = Field(min_length=18,max_length=100)
    boundary_b: str = Field(min_length=18,max_length=100)
    evidence_ref: str = Field(pattern=r'^SYNTHETIC-[A-Za-z0-9_-]{12,120}$')
    @model_validator(mode='after')
    def check(self):
        if self.boundary_a == self.boundary_b:
            raise ValueError('OVERLAP_NEEDS_TWO_DISTINCT_BOUNDARIES')
        return self


def boundary_safety_statement():
    return {
      'status':'LAB_ONLY_CANONICAL_BOUNDARY_RECONCILIATION',
      'field_metering_attested':False,'cross_organisation_reconciliation':False,
      'legacy_dossiers_auto_imported':False,'physical_overlap_source_verified':False,
      'industrial_approval_eligible':False,
      'scope_policy':'CONSERVATIVE_MATERIALIZED_CONFLICTS; ADDITIONS_FROZEN_AFTER_FIRST_RESERVATION'
    }
