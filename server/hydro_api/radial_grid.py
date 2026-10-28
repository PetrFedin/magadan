"""V7.3 LAB ONLY: balanced radial multi-node PQ feeder snapshots.

Independent Kirchhoff root check; never an industrial powerflow or N-1 tool.
All parameters and loads must be synthetic. No real-asset ingestion.
"""
from __future__ import annotations
from collections import defaultdict
from math import sqrt, isfinite
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from scipy.optimize import root


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FeederNode(Strict):
    node_id: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    parent_id: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    r_ohm_per_phase: float = Field(ge=0.00001, le=30)
    x_ohm_per_phase: float = Field(ge=0, le=30)
    load_p_mw: float = Field(ge=0, le=100)
    load_q_mvar: float = Field(ge=0, le=100)
    ampacity_a: float = Field(gt=0, le=100000)

    @field_validator('r_ohm_per_phase','x_ohm_per_phase','load_p_mw','load_q_mvar','ampacity_a',mode='before')
    @classmethod
    def reject_boolean_numeric(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_MEASUREMENT')
        return v


class LoadWindow(Strict):
    name: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9_-]+$')
    scale: float = Field(ge=0.01, le=2.5)
    hours: float = Field(gt=0, le=8784)

    @field_validator('scale','hours',mode='before')
    @classmethod
    def reject_boolean_numeric(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_MEASUREMENT')
        return v


class RadialCase(Strict):
    model_kind: Literal['radial_ac_v73'] = 'radial_ac_v73'
    reference_name: str = Field(min_length=3, max_length=120)
    source_voltage_kv_ll: float = Field(gt=1, le=500)
    min_voltage_pu: float = Field(ge=0.7, le=1.0)
    nodes: list[FeederNode] = Field(min_length=1, max_length=16)
    windows: list[LoadWindow] = Field(min_length=1, max_length=48)

    @field_validator('source_voltage_kv_ll','min_voltage_pu',mode='before')
    @classmethod
    def reject_boolean_numeric(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_MEASUREMENT')
        return v

    @model_validator(mode='after')
    def connected_tree_and_time(self):
        ids = [n.node_id for n in self.nodes]
        if 'SOURCE' in ids or len(set(ids)) != len(ids):
            raise ValueError('DUPLICATE_OR_RESERVED_NODE_ID')
        node_ids = set(ids)
        if any(n.parent_id != 'SOURCE' and n.parent_id not in node_ids for n in self.nodes):
            raise ValueError('UNKNOWN_PARENT_NODE')
        if any(n.parent_id == n.node_id for n in self.nodes):
            raise ValueError('SELF_LOOP')
        children = defaultdict(list)
        for n in self.nodes:
            children[n.parent_id].append(n.node_id)
        ordered = []
        queue = list(children['SOURCE'])
        while queue:
            item = queue.pop(0)
            if item in ordered:
                raise ValueError('CYCLIC_TOPOLOGY')
            ordered.append(item)
            queue.extend(children[item])
        if len(ordered) != len(ids):
            raise ValueError('CYCLIC_OR_DISCONNECTED_NETWORK')
        if not any(n.load_p_mw > 0 or n.load_q_mvar > 0 for n in self.nodes):
            raise ValueError('ZERO_NETWORK_LOAD_NOT_IN_SCOPE')
        if len({w.name for w in self.windows}) != len(self.windows):
            raise ValueError('DUPLICATE_WINDOW_NAME')
        if sum(w.hours for w in self.windows) > 8784 + 1e-9:
            raise ValueError('TIME_WINDOW_EXCEEDS_YEAR')
        if len(self.nodes)*len(self.windows)>192:
            raise ValueError('LAB_COMPLEXITY_BUDGET_EXCEEDED')
        return self


def _solve_snapshot(case: RadialCase, scale: float) -> dict:
    """Backward-forward current sweep cross-checked with nodal KCL root.

    Root uses an independent flat-voltage initial guess, not sweep outputs.
    """
    nodes = {n.node_id: n for n in case.nodes}
    children = defaultdict(list)
    for n in case.nodes:
        children[n.parent_id].append(n.node_id)
    order = []
    queue = list(children['SOURCE'])
    while queue:
        item = queue.pop(0)
        order.append(item)
        queue.extend(children[item])
    V0 = case.source_voltage_kv_ll * 1000 / sqrt(3)
    S = {i: complex(nodes[i].load_p_mw, nodes[i].load_q_mvar) * scale * 1e6 / 3 for i in order}
    Z = {i: complex(nodes[i].r_ohm_per_phase, nodes[i].x_ohm_per_phase) for i in order}
    voltages = {i: complex(V0) for i in order}
    currents = {}
    iterations = None
    for k in range(300):
        if any(abs(voltages[i]) < 0.6 * V0 for i in order):
            raise ValueError('LOW_VOLTAGE_SOLUTION_OUTSIDE_LAB_SCOPE')
        for i in reversed(order):
            current = (S[i] / voltages[i]).conjugate()
            currents[i] = current + sum((currents[c] for c in children[i]), 0j)
        forward = {}
        for i in order:
            parent = nodes[i].parent_id
            vparent = complex(V0) if parent == 'SOURCE' else forward[parent]
            forward[i] = vparent - Z[i] * currents[i]
        diff = max(abs(forward[i] - voltages[i]) for i in order)
        voltages = forward
        if diff <= 1e-10 * V0:
            iterations = k + 1
            break
    if iterations is None:
        raise ValueError('SWEEP_FAILED_TO_CONVERGE')

    # Nodal complex KCL: (Vparent-Vnode)/Zparent - sum((Vnode-Vchild)/Zchild) - conj(Snode/Vnode) = 0
    amp_scale = max(1.0, sum(abs(s) for s in S.values()) / V0)
    def kcl(flat):
        vs = {i: complex(flat[2*j], flat[2*j+1]) for j, i in enumerate(order)}
        if any(abs(v) < 0.2*V0 for v in vs.values()):
            return [1e6] * (2 * len(order))
        residual = []
        for i in order:
            parent = nodes[i].parent_id
            incoming = ((complex(V0) if parent == 'SOURCE' else vs[parent]) - vs[i]) / Z[i]
            outgoing = sum(((vs[i] - vs[ch]) / Z[ch] for ch in children[i]), 0j)
            mismatch = (incoming - outgoing - (S[i] / vs[i]).conjugate()) / amp_scale
            residual.extend((mismatch.real, mismatch.imag))
        return residual
    flat = [value for _ in order for value in (V0, 0.0)]
    solution = root(kcl, flat, method='hybr', options={'xtol':1e-11, 'maxfev':6000})
    residual = max(abs(v) for v in kcl(solution.x))
    independent = {i: complex(solution.x[2*j], solution.x[2*j+1]) for j, i in enumerate(order)}
    max_difference_v = max(abs(voltages[i] - independent[i]) for i in order)
    if not isfinite(residual) or residual > 1e-8 or max_difference_v > 0.05:
        raise ValueError('INDEPENDENT_NODAL_KCL_CHECK_FAILED')

    line_p_mw = {i: 3 * abs(currents[i])**2 * Z[i].real / 1e6 for i in order}
    line_q_mvar = {i: 3 * abs(currents[i])**2 * Z[i].imag / 1e6 for i in order}
    total_p = sum(line_p_mw.values())
    total_q = sum(line_q_mvar.values())
    send = sum((V0 * currents[i].conjugate() * 3 for i in children['SOURCE']), 0j)
    load = sum(S.values()) * 3
    balance_p = abs(send.real - load.real - total_p*1e6) / 1e6
    balance_q = abs(send.imag - load.imag - total_q*1e6) / 1e6
    if max(balance_p, balance_q) > 1e-7:
        raise ValueError('NETWORK_POWER_BALANCE_FAILURE')
    thermal = [i for i in order if abs(currents[i]) > nodes[i].ampacity_a + 1e-6]
    voltage = [i for i in order if abs(voltages[i])/V0 < case.min_voltage_pu - 1e-9]
    return {
        'line_loss_p_mw': total_p,
        'line_loss_q_mvar': total_q,
        'min_voltage_pu': min(abs(voltages[i])/V0 for i in order),
        'max_kcl_discrepancy_v': max_difference_v,
        'power_balance_residual_mw': balance_p,
        'power_balance_residual_mvar': balance_q,
        'sweep_iterations': iterations,
        'thermal_violations': thermal,
        'voltage_violations': voltage,
        'nodes': [
            {'node_id':i,'parent_id':nodes[i].parent_id,
             'voltage_pu':round(abs(voltages[i])/V0,9),
             'current_a':round(abs(currents[i]),6),
             'line_loss_p_mw':round(line_p_mw[i],9),
             'line_loss_q_mvar':round(line_q_mvar[i],9)} for i in order]
    }


def solve_radial(case: RadialCase) -> dict:
    rows = []
    energy = 0.0
    all_violations = set()
    for window in case.windows:
        solved = _solve_snapshot(case, window.scale)
        energy += window.hours * solved['line_loss_p_mw']
        all_violations.update(f'thermal:{name}' for name in solved['thermal_violations'])
        all_violations.update(f'voltage:{name}' for name in solved['voltage_violations'])
        rows.append({**solved,'window':window.name,'scale':window.scale,'hours':window.hours})
    return {
        'status': 'LAB_CONSTRAINT_BREACH' if all_violations else 'LAB_ENGINEERING_LIMITS_MET',
        'total_line_energy_loss_mwh':round(energy,9),
        'modelled_hours':round(sum(w.hours for w in case.windows),6),
        'maximum_line_loss_p_mw':round(max(r['line_loss_p_mw'] for r in rows),9),
        'minimum_receiving_voltage_pu':round(min(r['min_voltage_pu'] for r in rows),9),
        'constraint_violations':sorted(all_violations),
        'windows':rows,
        'limitation': 'Synthetic balanced radial constant-PQ network only; no neutral, unbalanced phases, shunts, transformers, protection, N-1, regulatory calibration or field signoff',
        'independent_validation': 'Separate nodal KCL numerical root; not external engineering validation',
        'industrial_decision_eligible':False,
    }


def physical_comparability(base: RadialCase, alt: RadialCase) -> tuple[bool, list[str]]:
    """Only impedance/ampacity may change in this synthetic intervention comparison."""
    reasons=[]
    for label in ('reference_name','source_voltage_kv_ll','min_voltage_pu'):
        if getattr(base,label)!=getattr(alt,label):reasons.append(label)
    if [(w.name,w.scale,w.hours) for w in base.windows] != [(w.name,w.scale,w.hours) for w in alt.windows]:
        reasons.append('load_windows')
    b={n.node_id:n for n in base.nodes}
    a={n.node_id:n for n in alt.nodes}
    if set(b)!=set(a):reasons.append('node_set')
    else:
        for key in sorted(b):
            for field in ('parent_id','load_p_mw','load_q_mvar'):
                if getattr(b[key],field)!=getattr(a[key],field):reasons.append(f'{key}.{field}')
    if all(b[k].r_ohm_per_phase==a[k].r_ohm_per_phase and b[k].x_ohm_per_phase==a[k].x_ohm_per_phase and b[k].ampacity_a==a[k].ampacity_a for k in set(b)&set(a)) and not reasons:
        reasons.append('NO_ENGINEERING_ALTERNATIVE_CHANGED')
    return not reasons,reasons
