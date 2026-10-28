"""Independent implementation of a fixed-point backward/forward sweep.
No scipy root and no use of the closed-form voltage as initial guess.
Only a mathematical cross-check for the synthetic balanced two-bus model.
"""
from math import sqrt
from .engineering import GridCase,CalculationError

def reference_sweep(case:GridCase):
    slack=case.source_voltage_kv_ll*1000/sqrt(3)
    z=complex(case.line_r_ohm_per_phase,case.line_x_ohm_per_phase)
    demand=complex(case.load_p_mw,case.load_q_mvar)*1e6/3
    voltage=complex(slack,0)
    for iteration in range(1,10001):
        if abs(voltage)<1e-6:raise CalculationError('REFERENCE_COLLAPSE')
        current=(demand/voltage).conjugate()
        updated=slack-z*current
        if abs(updated-voltage)<1e-9:
            voltage=updated;break
        voltage=updated
    else:raise CalculationError('REFERENCE_DID_NOT_CONVERGE')
    current=(demand/voltage).conjugate()
    return {'receiving_voltage_kv_ll':abs(voltage)*sqrt(3)/1000,
            'line_loss_p_mw':3*abs(current)**2*z.real/1e6,
            'iterations':iteration,'classification':'SYNTHETIC_MATHEMATICAL_REFERENCE_ONLY'}
