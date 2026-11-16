import pytest
from hydro_api.engineering import GridCase,balanced_two_bus
from hydro_api.engineering_reference import reference_sweep

@pytest.mark.parametrize('p,q,r,x,kv',[
 (1,0,.1,.2,10),(1,.3,.5,.2,20),(5,2,.3,.4,20),(10,3,.1,.1,20),
 (10,6,.5,.5,35),(30,10,.3,.2,110),(100,35,1.2,2.1,220),
 (1,.1,.001,0,10),(2,1,.5,.8,35),(8,4,.8,1.1,35)
])
def test_independently_initialized_sweep_matches_root(p,q,r,x,kv):
    case=GridCase(source_voltage_kv_ll=kv,load_p_mw=p,load_q_mvar=q,
        line_r_ohm_per_phase=r,line_x_ohm_per_phase=x,period_hours=100,
        reference_name='Synthetic mathematical check; no Magadan operating measurements')
    numerical=balanced_two_bus(case);independent=reference_sweep(case)
    assert abs(numerical['line_loss_p_mw']-independent['line_loss_p_mw'])<1e-8
    assert abs(numerical['receiving_voltage_kv_ll']-independent['receiving_voltage_kv_ll'])<1e-8
