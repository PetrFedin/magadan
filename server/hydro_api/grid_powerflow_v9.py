"""V9 multi-bus radial AC power flow (Newton-Raphson) for GridLoss Planner.

Extends the V7 two-bus symmetric model (docs/V7_MATHEMATICAL_BASIS.md) to an
N-bus radial PQ network. Synthetic lab use only; PRODUCTION HOLD. No DB, no
network, no file writes.

Cross-checked against pandapower on the IEEE 33-bus (Baran-Wu) feeder by
scripts/benchmark_grid_ieee33_v9.py; the receipt lives in artifacts_v9/.
Self-executed benchmark is NOT an independent engineering attestation.

Jacobian convention (polar form, unknowns [dtheta; dV/V]):
  H[i,k] = dP_i/dtheta_k, N[i,k] = V_k dP_i/dV_k
  M[i,k] = dQ_i/dtheta_k, L[i,k] = V_k dQ_i/dV_k
  off-diagonal: H = ViVk(G sin th - B cos th), N = ViVk(G cos th + B sin th),
                M = -N, L = H
  diagonal:     H_ii = -Q_i - B_ii Vi^2, N_ii = P_i + G_ii Vi^2,
                M_ii =  P_i - G_ii Vi^2, L_ii = Q_i - B_ii Vi^2
"""
from __future__ import annotations

import cmath
import math
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE = "V9-RADIAL-NR-POWERFLOW-1"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Branch(Strict):
    from_bus: int = Field(ge=0)
    to_bus: int = Field(ge=1)
    r_ohm: float = Field(gt=0)
    x_ohm: float = Field(gt=0)


class PQLoad(Strict):
    bus: int = Field(ge=1)
    p_mw: float = Field(ge=0.0)
    q_mvar: float = Field(ge=0.0)


class RadialNetwork(Strict):
    base_kv: float = Field(gt=0)
    base_mva: float = Field(gt=0)
    slack_voltage_pu: float = Field(default=1.0, gt=0.5, le=1.5)
    branches: List[Branch] = Field(min_length=1)
    loads: List[PQLoad]

    @model_validator(mode="after")
    def require_radial_tree(self):
        buses = {0}
        for b in self.branches:
            buses.add(b.from_bus)
            buses.add(b.to_bus)
        n = len(buses)
        if buses != set(range(n)):
            raise ValueError("BUS_IDS_MUST_BE_CONTIGUOUS_FROM_ZERO")
        if len(self.branches) != n - 1:
            raise ValueError("NOT_A_TREE_BRANCH_COUNT")
        parent: Dict[int, int] = {}
        for b in self.branches:
            if b.to_bus in parent:
                raise ValueError("MULTIPLE_PARENTS_NOT_RADIAL")
            if b.from_bus == b.to_bus:
                raise ValueError("SELF_LOOP")
            parent[b.to_bus] = b.from_bus
        for bus in range(1, n):
            seen = set()
            cur = bus
            while cur != 0:
                if cur in seen or cur not in parent:
                    raise ValueError("CYCLE_OR_DISCONNECTED")
                seen.add(cur)
                cur = parent[cur]
        load_buses = [l.bus for l in self.loads]
        if len(load_buses) != len(set(load_buses)):
            raise ValueError("DUPLICATE_LOAD_BUS")
        if any(l.bus >= n for l in self.loads):
            raise ValueError("LOAD_ON_UNKNOWN_BUS")
        return self


def solve_power_flow(net: RadialNetwork, tol: float = 1e-12, max_iter: int = 100) -> dict:
    """Newton-Raphson polar power flow. Fail-closed on non-convergence."""
    n = len(net.branches) + 1
    zbase = net.base_kv ** 2 / net.base_mva
    y = [[0j] * n for _ in range(n)]
    for b in net.branches:
        yb = 1 / (complex(b.r_ohm, b.x_ohm) / zbase)
        y[b.from_bus][b.from_bus] += yb
        y[b.to_bus][b.to_bus] += yb
        y[b.from_bus][b.to_bus] -= yb
        y[b.to_bus][b.from_bus] -= yb
    g = [[v.real for v in row] for row in y]
    bb = [[v.imag for v in row] for row in y]

    p_spec = [0.0] * n
    q_spec = [0.0] * n
    for l in net.loads:
        p_spec[l.bus] -= l.p_mw / net.base_mva
        q_spec[l.bus] -= l.q_mvar / net.base_mva

    vmag = [net.slack_voltage_pu] + [1.0] * (n - 1)
    vang = [0.0] * n
    pq = list(range(1, n))
    npq = len(pq)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        p = [0.0] * n
        q = [0.0] * n
        for i in range(n):
            for k in range(n):
                vik = vmag[i] * vmag[k]
                th = vang[i] - vang[k]
                p[i] += vik * (g[i][k] * math.cos(th) + bb[i][k] * math.sin(th))
                q[i] += vik * (g[i][k] * math.sin(th) - bb[i][k] * math.cos(th))
        mismatch = [p_spec[i] - p[i] for i in pq] + [q_spec[i] - q[i] for i in pq]
        if max(abs(v) for v in mismatch) < tol:
            converged = True
            break
        h = [[0.0] * npq for _ in range(npq)]
        nm = [[0.0] * npq for _ in range(npq)]
        mm = [[0.0] * npq for _ in range(npq)]
        jl = [[0.0] * npq for _ in range(npq)]
        for a, i in enumerate(pq):
            for c, k in enumerate(pq):
                if i == k:
                    h[a][c] = -q[i] - bb[i][i] * vmag[i] ** 2
                    nm[a][c] = p[i] + g[i][i] * vmag[i] ** 2
                    mm[a][c] = p[i] - g[i][i] * vmag[i] ** 2
                    jl[a][c] = q[i] - bb[i][i] * vmag[i] ** 2
                else:
                    th = vang[i] - vang[k]
                    vik = vmag[i] * vmag[k]
                    h[a][c] = vik * (g[i][k] * math.sin(th) - bb[i][k] * math.cos(th))
                    nm[a][c] = vik * (g[i][k] * math.cos(th) + bb[i][k] * math.sin(th))
                    mm[a][c] = -nm[a][c]
                    jl[a][c] = h[a][c]
        jac = [h[r] + nm[r] for r in range(npq)] + [mm[r] + jl[r] for r in range(npq)]
        x = _gauss(jac, mismatch)
        for a, i in enumerate(pq):
            vang[i] += x[a]
            vmag[i] += x[npq + a] * vmag[i]
    if not converged:
        raise ValueError("NR_NOT_CONVERGED")

    v_phase = net.base_kv * 1e3 / math.sqrt(3)  # phase voltage, volts
    vbus = [vmag[i] * cmath.exp(1j * vang[i]) for i in range(n)]
    total_loss_mw = 0.0
    branch_rows = []
    for b in net.branches:
        i_amp = abs((vbus[b.from_bus] - vbus[b.to_bus]) * v_phase / complex(b.r_ohm, b.x_ohm))
        loss_mw = 3 * i_amp ** 2 * b.r_ohm / 1e6
        total_loss_mw += loss_mw
        branch_rows.append({"from_bus": b.from_bus, "to_bus": b.to_bus,
                            "current_a": round(i_amp, 6), "loss_mw": loss_mw})
    vmin = min(vmag)
    return {
        "engine": ENGINE,
        "converged": True,
        "iterations": iterations,
        "bus_count": n,
        "voltage_pu": [round(v, 10) for v in vmag],
        "angle_rad": [round(a, 10) for a in vang],
        "min_voltage_pu": vmin,
        "min_voltage_bus": vmag.index(vmin),
        "total_loss_mw": total_loss_mw,
        "branches": branch_rows,
        "benchmarked_against_external_solver": False,  # only artifacts_v9 receipt may attest
        "production_ready": False,
    }


def _gauss(a: List[List[float]], b: List[float]) -> List[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-15:
            raise ValueError("SINGULAR_JACOBIAN")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x
