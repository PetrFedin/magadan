"""V7.7: strict lab-only comparison with *unattested* externally claimed grid results.

This is a data-exchange and numerical-reconciliation contract, not proof that
pandapower/OpenDSS/RastrWin3 ran, not field engineering acceptance, not a safety
or investment authorization. External inputs are untrusted until signed review.
"""
from __future__ import annotations
from math import isfinite
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class ReferenceNode(Strict):
    node_id: str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    voltage_pu: float=Field(ge=0.01,le=2)
    current_a: float=Field(ge=0,le=100000)
    line_loss_p_mw: float=Field(ge=0,le=1000)

    @field_validator('voltage_pu','current_a','line_loss_p_mw',mode='before')
    @classmethod
    def no_bools(cls,x):
        if isinstance(x,bool):raise ValueError('BOOLEAN_NOT_ENGINEERING_MEASUREMENT')
        return x


class ReferenceWindow(Strict):
    window: str=Field(min_length=1,max_length=60,pattern=r'^[A-Za-z0-9_-]+$')
    line_loss_p_mw:float=Field(ge=0,le=1000)
    nodes:list[ReferenceNode]=Field(min_length=1,max_length=16)

    @field_validator('line_loss_p_mw',mode='before')
    @classmethod
    def no_bool(cls,x):
        if isinstance(x,bool):raise ValueError('BOOLEAN_NOT_ENGINEERING_MEASUREMENT')
        return x

    @model_validator(mode='after')
    def unique_nodes_and_balance(self):
        if len(set(n.node_id for n in self.nodes))!=len(self.nodes):
            raise ValueError('DUPLICATE_REFERENCE_NODE')
        if abs(sum(n.line_loss_p_mw for n in self.nodes)-self.line_loss_p_mw)>max(1e-5,abs(self.line_loss_p_mw)*0.005):
            raise ValueError('REFERENCE_LINE_SUM_DOES_NOT_MATCH_TOTAL')
        return self


class ReferenceSubmission(Strict):
    scope:Literal['SYNTHETIC_UNATTESTED_REFERENCE_ONLY']='SYNTHETIC_UNATTESTED_REFERENCE_ONLY'
    claimed_tool:Literal['pandapower','OpenDSS','RastrWin3','other']
    claimed_tool_version:str=Field(min_length=1,max_length=90)
    calculation_method:str=Field(min_length=16,max_length=500)
    source_reference:str=Field(min_length=20,max_length=150,pattern=r'^SYNTHETIC-[A-Za-z0-9_.-]+$')
    case_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    windows:list[ReferenceWindow]=Field(min_length=1,max_length=48)

    @model_validator(mode='after')
    def unique_windows(self):
        if len(set(w.window for w in self.windows))!=len(self.windows):
            raise ValueError('DUPLICATE_REFERENCE_WINDOW')
        return self


def _diff(a:float,b:float,abs_tolerance:float,rel_tolerance:float)->dict:
    if not (isfinite(float(a)) and isfinite(float(b))):
        raise ValueError('NONFINITE_REFERENCE_COMPARISON')
    gap=abs(float(a)-float(b))
    bound=abs_tolerance+rel_tolerance*max(abs(float(a)),abs(float(b)))
    return {'primary_value':a,'reference_value':b,'absolute_delta':round(gap,12),
            'allowed_delta':round(bound,12),'match':gap<=bound+1e-12}


def compare_reference(primary:dict, request:ReferenceSubmission,expected_case_sha256:str)->dict:
    """Fail closed on missing/extra windows and nodes; compare all windows.

    Primary = validated output of solve_radial() inside study['result']['result'].
    A match is purely numerical, never external-origin attestation.
    """
    if request.case_sha256!=expected_case_sha256:
        raise ValueError('REFERENCE_CASE_HASH_MISMATCH')
    rows=primary.get('windows',[])
    ref_map={w.window:w for w in request.windows}
    main_map={w['window']:w for w in rows}
    if set(ref_map)!=set(main_map):
        raise ValueError('REFERENCE_WINDOW_SET_MISMATCH')
    if not rows:raise ValueError('REFERENCE_PRIMARY_HAS_NO_WINDOWS')
    checked=[];mismatch=[]
    for name in main_map:
        a=main_map[name];b=ref_map[name]
        ours={n['node_id']:n for n in a['nodes']}
        external={n.node_id:n for n in b.nodes}
        if set(ours)!=set(external):
            raise ValueError('REFERENCE_NODE_SET_MISMATCH:'+name)
        line_total=_diff(a['line_loss_p_mw'],b.line_loss_p_mw,0.00001,0.005)
        if not line_total['match']:mismatch.append(f'{name}.line_loss_p_mw')
        node_results=[]
        for node_id in ours:
            x=ours[node_id];y=external[node_id]
            metrics={
                'voltage_pu':_diff(x['voltage_pu'],y.voltage_pu,0.0005,0),
                'current_a':_diff(x['current_a'],y.current_a,0.01,0.005),
                'line_loss_p_mw':_diff(x['line_loss_p_mw'],y.line_loss_p_mw,0.00001,0.005)}
            for field,metric in metrics.items():
                if not metric['match']:mismatch.append(f'{name}.{node_id}.{field}')
            node_results.append({'node_id':node_id,'metrics':metrics})
        checked.append({'window':name,'line_total':line_total,'nodes':node_results})
    # Even perfect matching has zero claim of independent technical or legal acceptance.
    return {'status':('LAB_NUMERICAL_MATCH_UNATTESTED' if not mismatch else 'LAB_NUMERICAL_MISMATCH_UNATTESTED'),
            'mismatch_paths':mismatch,'checked_windows':len(checked),'checked_nodes':sum(len(w['nodes']) for w in checked),
            'measurements':checked,'source_claim_trusted':False,'external_solver_execution_verified':False,
            'independent_engineering_accepted':False,'industrial_approval_eligible':False,
            'limitations':['Reference data provided by a user; solver identity and execution are NOT authenticated',
              'Numerical agreement is not field calibration, independent engineer signoff or proof of regulatory compliance',
              'Balanced radial synthetic PQ feeders only; not actual Magadan infrastructure']}
