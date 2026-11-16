"""Deterministic 3-phase balanced, 2-bus steady-state AC power flow.
Lab benchmark ONLY: one PQ consumer, one series R+jX feeder, ideal slack source.
No dynamics, protection, harmonics, tap controls or weather; NOT Magadan field data.
"""
from math import sqrt, isfinite
from pydantic import BaseModel, Field, ConfigDict
from scipy.optimize import root

class GridCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_voltage_kv_ll: float = Field(gt=1, le=500)
    load_p_mw: float = Field(gt=0, le=200)
    load_q_mvar: float = Field(ge=0, le=200)
    line_r_ohm_per_phase: float = Field(gt=0, le=100)
    line_x_ohm_per_phase: float = Field(ge=0, le=100)
    period_hours: float = Field(gt=0, le=8784)
    reference_name: str = Field(min_length=3, max_length=100)

class CalculationError(ValueError):
    pass


def balanced_two_bus(case: GridCase):
    Vs = case.source_voltage_kv_ll*1000/sqrt(3)  # source phase voltage V
    Z = complex(case.line_r_ohm_per_phase, case.line_x_ohm_per_phase)
    S = complex(case.load_p_mw, case.load_q_mvar)*1e6/3  # per-phase VA
    # Independent closed-form high-voltage branch for squared receiving |V|.
    a = Vs**2 - 2 * (Z*S.conjugate()).real
    discriminant = a*a - 4 * abs(Z)**2 * abs(S)**2
    if discriminant <= 0 or a <= 0:
        raise CalculationError('NO_VALID_HIGH_VOLTAGE_SOLUTION')
    vr_squared = (a + sqrt(discriminant)) / 2
    if vr_squared <= 0:
        raise CalculationError('INVALID_RECEIVING_VOLTAGE')
    Vr_reference = sqrt(vr_squared)
    # Independent nonlinear calculation: solve two real AC Kirchhoff equations.
    def equations(v):
        vr = complex(v[0], v[1]); denom=abs(vr)**2
        if denom < 1e-16: return [1e15, 1e15]
        I = (S/vr).conjugate()
        res = (vr + Z*I - Vs)/Vs
        return [res.real, res.imag]
    sol = root(equations, [Vr_reference, -0.001*Vs], method='hybr', tol=1e-11)
    if not sol.success and max(abs(v) for v in equations(sol.x)) > 1e-9:
        raise CalculationError('NUMERICAL_SOLVER_DID_NOT_CONVERGE')
    Vr = complex(*sol.x)
    I = (S/Vr).conjugate()
    S_send = 3 * Vs * I.conjugate()
    loss = 3 * (abs(I)**2) * Z
    p_loss_mw = loss.real/1e6
    q_loss_mvar = loss.imag/1e6
    balance_residual_mw = abs(S_send.real - 3*S.real - loss.real) / 1e6
    equation_residual = max(abs(v) for v in equations(sol.x))
    independent_difference_v = abs(abs(Vr)-Vr_reference)
    if not all(isfinite(v) for v in (p_loss_mw,balance_residual_mw,independent_difference_v)):
        raise CalculationError('NON_FINITE_RESULT')
    if equation_residual>1e-8 or balance_residual_mw>1e-7 or independent_difference_v>0.01:
        raise CalculationError('INDEPENDENT_CHECK_FAILED')
    return {
        'method': 'balanced_two_bus_AC_PQ_lab_v1',
        'reference_name': case.reference_name,
        'receiving_voltage_kv_ll': round(abs(Vr)*sqrt(3)/1000, 9),
        'receiving_voltage_pu': round(abs(Vr)/Vs, 9),
        'sending_p_mw': round(S_send.real/1e6, 9),
        'load_p_mw': case.load_p_mw,
        'line_loss_p_mw': round(p_loss_mw, 9),
        'line_loss_q_mvar': round(q_loss_mvar, 9),
        'line_energy_loss_mwh': round(p_loss_mw*case.period_hours, 9),
        'active_power_balance_residual_mw': round(balance_residual_mw, 12),
        'solver_residual_pu': round(equation_residual, 12),
        'independent_closed_form_voltage_difference_v': round(independent_difference_v, 9),
        'validation': 'numerical AC nodal equations cross-checked with closed-form high-voltage root; NOT independent third-party field validation',
        'limitations': 'Balanced one-line two-bus, constant PQ, no shunt/capacitance, no voltage control, no dynamics or N-1, no loss calibration',
        'data_classification': 'SYNTHETIC_LAB_ONLY',
    }
