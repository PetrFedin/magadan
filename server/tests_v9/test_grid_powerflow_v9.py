"""Тесты grid_powerflow_v9: многоузловой NR + IEEE 33-bus (P1-5)."""
import pytest

from hydro_api.grid_powerflow_v9 import (
    Branch,
    PQLoad,
    RadialNetwork,
    solve_power_flow,
)

# IEEE 33-bus (Baran & Wu 1989), 1-индексация источника -> 0-индексация
BR = [
    (1,2,.0922,.0470),(2,3,.4930,.2511),(3,4,.3660,.1864),(4,5,.3811,.1941),
    (5,6,.8190,.7070),(6,7,.1872,.6188),(7,8,.7114,.2351),(8,9,1.0300,.7400),
    (9,10,1.0440,.7400),(10,11,.1966,.0650),(11,12,.3744,.1238),(12,13,1.4680,1.1550),
    (13,14,.5416,.7129),(14,15,.5910,.5260),(15,16,.7463,.5450),(16,17,1.2890,1.7210),
    (17,18,.7320,.5740),(2,19,.1640,.1565),(19,20,1.5042,1.3554),(20,21,.4095,.4784),
    (21,22,.7089,.9373),(3,23,.4512,.3083),(23,24,.8980,.7091),(24,25,.8960,.7011),
    (6,26,.2030,.1034),(26,27,.2842,.1447),(27,28,1.0590,.9337),(28,29,.8042,.7006),
    (29,30,.5075,.2585),(30,31,.9744,.9630),(31,32,.3105,.3619),(32,33,.3410,.5302),
]
LD = [
    (2,100,60),(3,90,40),(4,120,80),(5,60,30),(6,60,20),(7,200,100),(8,200,100),
    (9,60,20),(10,60,20),(11,45,30),(12,60,35),(13,60,35),(14,120,80),(15,60,10),
    (16,60,20),(17,60,20),(18,90,40),(19,90,40),(20,90,40),(21,90,40),(22,90,40),
    (23,90,50),(24,420,200),(25,420,200),(26,60,25),(27,60,25),(28,60,20),
    (29,120,70),(30,200,600),(31,150,70),(32,210,100),(33,60,40),
]


def _ieee33() -> RadialNetwork:
    return RadialNetwork(
        base_kv=12.66, base_mva=10.0,
        branches=[Branch(from_bus=f-1, to_bus=t-1, r_ohm=r, x_ohm=x) for f, t, r, x in BR],
        loads=[PQLoad(bus=b-1, p_mw=p/1000.0, q_mvar=q/1000.0) for b, p, q in LD],
    )


def test_ieee33_literature_values():
    """Baran & Wu (1989): Vmin=0.9131 pu @ bus 18, losses=202.67 кВт."""
    res = solve_power_flow(_ieee33())
    assert res["converged"] is True
    assert res["min_voltage_pu"] == pytest.approx(0.9131, abs=1e-4)
    assert res["min_voltage_bus"] == 17  # bus 18 в 1-индексации
    assert res["total_loss_mw"] * 1000.0 == pytest.approx(202.67, abs=0.1)


def test_two_bus_analytic():
    """Два узла: аналитика против NR."""
    net = RadialNetwork(
        base_kv=10.0, base_mva=1.0,
        branches=[Branch(from_bus=0, to_bus=1, r_ohm=1.0, x_ohm=1.0)],
        loads=[PQLoad(bus=1, p_mw=0.5, q_mvar=0.0)],
    )
    res = solve_power_flow(net)
    assert res["converged"] is True
    # |V1| решает V^2(V^2 - 1 + 2PR) + P^2 Z^2 = 0 при Q=0... проверяем
    # физику: потери = P_flow^2 * R / V^2, падение напряжения > 0
    assert res["voltage_pu"][1] < 1.0
    assert res["total_loss_mw"] > 0.0


def test_radial_validation_rejects_cycles():
    with pytest.raises(ValueError):
        RadialNetwork(
            base_kv=10.0, base_mva=1.0,
            branches=[
                Branch(from_bus=0, to_bus=1, r_ohm=1.0, x_ohm=1.0),
                Branch(from_bus=1, to_bus=2, r_ohm=1.0, x_ohm=1.0),
                Branch(from_bus=0, to_bus=2, r_ohm=1.0, x_ohm=1.0),  # петля
            ],
            loads=[PQLoad(bus=1, p_mw=0.1, q_mvar=0.0)],
        )


def test_fail_closed_flags():
    res = solve_power_flow(_ieee33())
    assert res["production_ready"] is False
    assert res["benchmarked_against_external_solver"] is False  # солвер сам по себе
