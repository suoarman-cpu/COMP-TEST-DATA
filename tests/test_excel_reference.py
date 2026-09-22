"""원본 엑셀(150RT_Cycle_Analysis)의 계산값과 대조하는 검증 테스트.

기대값은 엑셀 셀에 저장된 결과를 그대로 옮긴 것이다.
엑셀은 REFPROP / CoolProp 애드인을 썼고 여기서는 CoolProp 을 쓰므로
물성 라이브러리 차이만큼(대략 0.1% 이내) 오차가 난다.
"""

from __future__ import annotations

import pytest

from turbochiller import CycleInput, ExcelCompat, single_stage, two_stage

#: 엑셀과 맞춰볼 때 쓰는 호환 모드
COMPAT = ExcelCompat(temperature_mixing=True, condenser_duty_first_stage_flow=True)

REL = 2e-3  # 물성 라이브러리 차이를 감안한 허용 오차 0.2%


def approx(expected: float) -> object:
    return pytest.approx(expected, rel=REL)


@pytest.fixture
def stg1_1234ze() -> CycleInput:
    """LG150RT_1STG(AIR_1234ze(E)) 시트의 입력."""
    return CycleInput(
        refrigerant="R1234ze(E)",
        capacity_rt=150,
        chilled_water_in=12.2,
        chilled_water_out=7.0,
        evap_approach=1.0,
        superheat=1.0,
        cooling_medium_in=35.0,
        cond_approach=15.0,
        subcool=3.0,
        dp_suction=3.0,
        dp_discharge=5.0,
        eta_is_stage1=0.80,
        eta_wire_to_shaft=0.89,
        t_cond_max=70.0,
        eta_is_max=0.80,
        compat=COMPAT,
    )


@pytest.fixture
def stg2_1234ze() -> CycleInput:
    """LG150RT_2STG(AIR_1234ze(E)) 시트의 입력."""
    return CycleInput(
        refrigerant="R1234ze(E)",
        capacity_rt=150,
        chilled_water_in=12.0,
        chilled_water_out=7.0,
        evap_approach=1.0,
        superheat=1.0,
        cooling_medium_in=35.0,
        cond_approach=15.0,
        subcool=3.0,
        dp_suction=3.0,
        dp_discharge=5.0,
        eta_is_stage1=0.80,
        eta_is_stage2=0.80,
        eta_wire_to_shaft=0.89,
        t_subcond=32.0,
        subcond_mass_ratio=0.2,
        t_cond_max=70.0,
        eta_is_max=0.80,
        compat=COMPAT,
    )


@pytest.fixture
def stg2_134a() -> CycleInput:
    """LG150RT_2STG(AIR_134a) 시트의 입력 (200RT)."""
    return CycleInput(
        refrigerant="R134a",
        capacity_rt=200,
        chilled_water_in=12.2,
        chilled_water_out=7.0,
        evap_approach=1.0,
        superheat=1.0,
        cooling_medium_in=35.0,
        cond_approach=15.0,
        subcool=1.0,
        dp_suction=5.0,
        dp_discharge=13.0,
        eta_is_stage1=0.80,
        eta_is_stage2=0.80,
        eta_wire_to_shaft=0.89,
        t_subcond=30.0,
        subcond_mass_ratio=0.1,
        t_cond_max=70.0,
        eta_is_max=0.80,
        compat=COMPAT,
    )


# --- 1단 압축 시트 ---------------------------------------------------------

def test_single_stage_matches_excel(stg1_1234ze: CycleInput) -> None:
    res = single_stage(stg1_1234ze)
    stage = res.stage_results[0]

    assert res.state(1).p == approx(265.5882248893751)   # C18
    assert res.state(1).h == approx(389.249412735823)    # D18
    assert res.state(1).d == approx(14.154582187383777)  # E18
    assert res.state(3).p == approx(997.0908976944405)   # C20
    assert res.state(4).h == approx(265.1886476461105)   # D21

    assert res.mass_flow_evap == approx(4.253593143588363)   # E29
    assert res.volume_flow_m3h == approx(1081.83591109929)   # E30
    assert stage.t_out_isentropic == approx(50.19647995279121)   # E35
    assert stage.dh_isentropic == approx(25.04952531869708)      # E36
    assert stage.t_out == approx(54.809433468711006)             # E38/E41
    assert stage.pressure_ratio == approx(3.7730998733540964)    # E39
    assert res.shaft_power == approx(133.18811152821766)         # E33
    assert res.input_power == approx(149.6495635148513)          # E44
    assert res.qc == approx(661.3475330359893)                   # E28
    assert res.cop == approx(3.959812883811806)                  # E63


def test_single_stage_max_condition(stg1_1234ze: CycleInput) -> None:
    mc = single_stage(stg1_1234ze).max_condition
    assert mc is not None
    assert mc.p_cond == approx(1610.7689225258491)       # E48
    assert mc.dh_isentropic == approx(33.59332726398014) # E51
    assert mc.t_discharge == approx(75.24888961789452)   # E53
    assert mc.pressure_ratio == approx(6.064910909347653)  # E54
    assert mc.shaft_power == approx(178.61543315048243)    # E55
    assert mc.input_power == approx(200.69149792189037)    # E56


# --- 2단 압축 + 서브콘덴서 시트 --------------------------------------------

def test_two_stage_1234ze_matches_excel(stg2_1234ze: CycleInput) -> None:
    res = two_stage(stg2_1234ze)
    st1, st2 = res.stage_results

    assert res.state(1).p == approx(265.63099677793)     # C18
    assert res.state(2).p == approx(612.8081412929654)   # C19
    assert res.state(4).p == approx(997.221401621696)    # C21
    assert res.state(5).h == approx(265.1893716594813)   # D22
    assert res.state(7).h == approx(239.3792853220103)   # D24

    assert res.mass_flow_evap == approx(3.5208872759576306)  # E31
    assert res.mass_flow_total == approx(4.225064731149157)  # E58
    assert res.volume_flow_m3h == approx(895.3278009652261)  # E32
    assert st1.t_out == approx(35.9335403952029)             # E40/E43
    assert st1.power == approx(69.62978419699992)            # E35
    assert st1.pressure_ratio == approx(2.306990331423101)   # E41
    assert st2.pressure_ratio == approx(1.627297900314536)   # E52
    assert res.total_pressure_ratio == approx(3.7541605223707473)  # E57
    assert res.cop == approx(4.439192085488099)              # E78


def test_two_stage_134a_matches_excel(stg2_134a: CycleInput) -> None:
    res = two_stage(stg2_134a)
    st1, st2 = res.stage_results

    assert res.state(1).h == approx(403.1264064492008)   # D18
    assert res.state(2).p == approx(770.1963030768845)   # C19
    assert res.state(4).p == approx(1317.9054900373355)  # C21
    assert res.state(3).t == approx(37.282938864180075)  # B20 (온도 혼합)

    assert res.mass_flow_evap == approx(4.321836050305632)  # E31
    assert res.mass_flow_total == approx(4.7540196553361955)  # E57
    assert st1.t_out == approx(38.01123275059808)           # E43
    assert st2.t_out == approx(61.24635797850698)           # E54
    assert st1.power == approx(86.74688202659554)           # E35
    assert st2.power == approx(68.37277442447683)           # E46
    assert res.qc == approx(720.7418436941209)              # E30 (1단 유량 기준)
    assert res.cop == approx(4.533274609345221)             # E63


def test_two_stage_134a_heat_exchangers(stg2_134a: CycleInput) -> None:
    """엑셀 134a 시트의 2차측 LMTD/UA 블록."""
    from turbochiller import condenser_side, evaporator_side

    res = two_stage(stg2_134a)

    cond = condenser_side(res.qc, stg2_134a.tc, 35.0, 0.054, 995.67, 4.18)
    assert cond.volume_flow_m3h == approx(140.1122144141371)   # E71
    assert cond.mass_flow == approx(38.751535701589965)        # E72
    assert cond.delta_t == approx(4.449534070688407)           # E73
    assert cond.lmtd == approx(12.645026193147507)             # E76
    assert cond.ua == approx(56.99805067107727)                # E77

    evap = evaporator_side(res.qe, stg2_134a.te, 12.2, 0.043, 999.45, 4.19)
    assert evap.volume_flow_m3h == approx(108.85536)           # E86
    assert evap.delta_t == approx(5.5533679450877855)          # E88
    assert evap.lmtd == approx(2.45666944911747)               # E91
    assert evap.ua == approx(286.2411954740661)                # E92
