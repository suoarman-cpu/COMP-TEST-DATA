"""사이클 모델 자체의 동작 검증 (엑셀 대조가 아닌 물리적 타당성)."""

from __future__ import annotations

import math

import pytest

from turbochiller import (
    CycleInput,
    Given,
    iplv,
    single_stage,
    size_impeller,
    size_machine,
    solve,
    two_stage,
)


def base() -> CycleInput:
    return CycleInput(refrigerant="R1234ze(E)", capacity_rt=150)


# --- 기본 동작 -------------------------------------------------------------

def test_energy_balance_single_stage() -> None:
    """배관 손실이 없으면 Qc = Qe + W 가 정확히 성립해야 한다."""
    res = single_stage(base().at(dp_suction=0.0, dp_discharge=0.0))
    assert res.qc == pytest.approx(res.qe + res.shaft_power, rel=1e-9)
    assert res.energy_balance_error == pytest.approx(0.0, abs=1e-6)


def test_energy_balance_two_stage() -> None:
    """이코노마이저 유량비를 에너지 밸런스로 구하면 수지가 정확히 맞는다."""
    res = two_stage(
        base().at(t_subcond=None, subcond_mass_ratio=None,
                  dp_suction=0.0, dp_discharge=0.0)
    )
    assert res.qc == pytest.approx(res.qe + res.shaft_power, rel=1e-9)
    assert res.energy_balance_error == pytest.approx(0.0, abs=1e-6)


def test_line_losses_cause_small_imbalance() -> None:
    """배관 압력손실을 등온으로 모델링하면 수지 오차가 조금 생긴다 (0.5% 미만)."""
    res = two_stage(base().at(t_subcond=None, subcond_mass_ratio=None))
    assert 0.0 < abs(res.energy_balance_error) < 0.5


def test_hand_set_mass_ratio_breaks_balance() -> None:
    """유량비를 손으로 지정하면(엑셀 방식) 이코노마이저 수지가 맞지 않는다.

    원본 엑셀이 x=0.2 로 고정해 쓰던 부분이다. 경고용 지표가 이를 잡아낸다.
    """
    res = two_stage(base().at(t_subcond=32.0, subcond_mass_ratio=0.2))
    assert abs(res.energy_balance_error) > 1.0


def test_two_stage_beats_single_stage() -> None:
    """같은 조건이면 2단 + 이코노마이저가 1단보다 COP 가 높다."""
    inp = base()
    assert two_stage(inp).cop > single_stage(inp).cop


def test_auto_intermediate_splits_pressure_ratio() -> None:
    """중간압을 자동으로 잡으면 두 단의 압축비가 거의 같아진다."""
    res = two_stage(base().at(t_subcond=None))
    st1, st2 = res.stage_results
    assert st1.pressure_ratio == pytest.approx(st2.pressure_ratio, rel=0.02)


def test_auto_economizer_mass_ratio() -> None:
    """유량비를 에너지 밸런스로 구하면 양수이고 상식적인 범위에 든다."""
    res = two_stage(base().at(subcond_mass_ratio=None))
    assert 0.0 < res.subcond_mass_ratio < 0.5


def test_enthalpy_mixing_is_default() -> None:
    """기본은 엔탈피 혼합, 호환 모드는 온도 혼합 — 결과가 달라야 한다."""
    from turbochiller import ExcelCompat

    inp = base().at(t_subcond=32.0)
    h_mix = two_stage(inp).state(3).t
    t_mix = two_stage(inp.at(compat=ExcelCompat(temperature_mixing=True))).state(3).t
    assert h_mix != pytest.approx(t_mix, rel=1e-6)


def test_lower_condensing_temperature_improves_cop() -> None:
    """응축온도가 낮아지면 COP 가 올라간다."""
    cold = two_stage(base().at(t_cond=35.0, t_subcond=None))
    hot = two_stage(base().at(t_cond=50.0, t_subcond=None))
    assert cold.cop > hot.cop


def test_capacity_scales_mass_flow() -> None:
    """능력을 2배로 하면 유량과 동력도 2배가 된다."""
    one = two_stage(base())
    two = two_stage(base().at(capacity_rt=300))
    assert two.mass_flow_evap == pytest.approx(2 * one.mass_flow_evap, rel=1e-9)
    assert two.shaft_power == pytest.approx(2 * one.shaft_power, rel=1e-9)
    assert two.cop == pytest.approx(one.cop, rel=1e-9)


@pytest.mark.parametrize("refrigerant", ["R1234ze(E)", "R134a", "R1234yf", "R513A.mix"])
def test_runs_for_common_refrigerants(refrigerant: str) -> None:
    res = two_stage(base().at(refrigerant=refrigerant, t_subcond=None))
    assert res.cop > 1.0
    assert res.stage_results[0].t_out > res.stage_results[0].t_in


def test_refrigerant_alias() -> None:
    """대소문자가 달라도 같은 냉매로 인식한다."""
    a = single_stage(base().at(refrigerant="r1234ze"))
    b = single_stage(base().at(refrigerant="R1234ze(E)"))
    assert a.cop == pytest.approx(b.cop, rel=1e-12)


# --- 입력 검증 -------------------------------------------------------------

def test_rejects_evaporator_above_condenser() -> None:
    with pytest.raises(ValueError, match="증발온도"):
        single_stage(base().at(t_evap=60.0, t_cond=40.0))


def test_rejects_supercritical_condensing() -> None:
    with pytest.raises(ValueError, match="임계온도"):
        single_stage(base().at(t_cond=150.0))


def test_rejects_intermediate_outside_range() -> None:
    with pytest.raises(ValueError, match="서브콘덴서 온도"):
        two_stage(base().at(t_subcond=60.0))


def test_rejects_bad_efficiency() -> None:
    with pytest.raises(ValueError, match="단열효율"):
        single_stage(base().at(eta_is_stage1=1.5))


def test_rejects_unsupported_stage_count() -> None:
    with pytest.raises(ValueError, match="1단 또는 2단"):
        solve(base(), stages=3)


# --- 임펠러 --------------------------------------------------------------

def test_impeller_sizing_consistency() -> None:
    """u2 = psi 로부터, D2 = 2·u2/ω 관계가 일관되어야 한다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(
        res.stage_results[0], res.refrigerant, Given(head_coefficient=0.6)
    )

    omega = sizing.rpm * 2 * math.pi / 60
    assert sizing.diameter == pytest.approx(2 * sizing.tip_speed / omega, rel=1e-9)
    assert sizing.tip_speed**2 * sizing.head_coefficient == pytest.approx(
        sizing.dh_isentropic * 1000, rel=1e-9
    )
    assert sizing.rpm > 0 and sizing.diameter > 0


def test_impeller_fixed_rpm() -> None:
    """회전수를 고정하면 그 값이 그대로 쓰인다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(res.stage_results[0], res.refrigerant, Given(rpm=15000))
    assert sizing.rpm == pytest.approx(15000)


def test_impeller_fixed_diameter_gives_rpm() -> None:
    """외경을 고정하면 회전수가 따라 나온다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(
        res.stage_results[0], res.refrigerant, Given(diameter=0.170)
    )
    assert sizing.diameter_mm == pytest.approx(170.0)
    omega = sizing.rpm * 2 * math.pi / 60
    assert sizing.tip_speed == pytest.approx(omega * 0.170 / 2, rel=1e-9)


def test_impeller_rpm_and_diameter_back_out_psi() -> None:
    """회전수와 외경을 둘 다 주면 psi 가 역산된다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(
        res.stage_results[0], res.refrigerant, Given(rpm=16000, diameter=0.170)
    )
    u2 = 16000 * 2 * math.pi / 60 * 0.170 / 2
    assert sizing.tip_speed == pytest.approx(u2, rel=1e-9)
    assert sizing.head_coefficient == pytest.approx(
        sizing.dh_isentropic * 1000 / u2**2, rel=1e-9
    )


def test_impeller_flags_impossible_head() -> None:
    """너무 느리고 작은 임펠러면 헤드를 못 낸다고 알려줘야 한다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(
        res.stage_results[0], res.refrigerant, Given(rpm=6000, diameter=0.120)
    )
    assert sizing.head_coefficient > 0.7
    assert any("헤드를 못 낸다" in w for w in sizing.warnings)


def test_impeller_fixed_eye_gives_mach() -> None:
    """흡입구 외경을 주면 축방향 마하수가 역산되고, 좁으면 경고가 뜬다."""
    res = two_stage(base().at(t_subcond=None))
    ok = size_impeller(res.stage_results[0], res.refrigerant, Given(eye_diameter=0.090))
    assert ok.eye_diameter_mm == pytest.approx(90.0)
    assert 0.2 < ok.eye_mach < 0.45

    narrow = size_impeller(
        res.stage_results[0], res.refrigerant, Given(eye_diameter=0.045)
    )
    assert narrow.eye_mach > 0.45
    assert any("초킹" in w for w in narrow.warnings)


def test_impeller_warns_outside_usual_range() -> None:
    """설계 범위를 벗어나면 경고가 붙는다."""
    res = two_stage(base().at(t_subcond=None))
    sizing = size_impeller(
        res.stage_results[0], res.refrigerant, Given(head_coefficient=0.20)
    )
    assert any("압력계수" in w for w in sizing.warnings)


# --- 압축기 한 대 (단일축) ------------------------------------------------

def test_single_shaft_uses_one_speed() -> None:
    """단일축 직결이면 모든 단의 회전수가 같아야 한다.

    단마다 최적 비속도를 따로 맞추면 단별 회전수가 달라지는데,
    임펠러 두 개가 한 축에 붙어 있으면 그럴 수가 없다.
    """
    res = two_stage(base().at(t_subcond=None))
    machine = size_machine(res)
    assert machine.drive == "단일축 직결"
    speeds = {round(z.rpm, 6) for z in machine.stages}
    assert len(speeds) == 1, f"단별 회전수가 다르다: {speeds}"
    assert machine.rpm == pytest.approx(machine.stages[0].rpm)


def test_single_shaft_speed_follows_first_stage() -> None:
    """회전수는 체적유량이 가장 큰 1단 기준으로 정해진다."""
    res = two_stage(base().at(t_subcond=None))
    machine = size_machine(res, Given(specific_speed=0.70))
    assert machine.stages[0].specific_speed == pytest.approx(0.70, rel=1e-6)
    # 뒷단은 유량이 적어 같은 회전수에서 비속도가 낮아진다
    assert machine.stages[1].specific_speed < machine.stages[0].specific_speed


def test_geared_allows_different_speeds() -> None:
    """기어 내장형으로 두면 단별 회전수가 달라도 된다."""
    res = two_stage(base().at(t_subcond=None))
    machine = size_machine(res, geared=True)
    assert machine.drive == "기어 내장형"
    assert len({round(z.rpm) for z in machine.stages}) > 1


def test_machine_fixed_rpm_applies_to_all_stages() -> None:
    res = two_stage(base().at(t_subcond=None))
    machine = size_machine(res, Given(rpm=14000))
    assert all(z.rpm == pytest.approx(14000) for z in machine.stages)


def test_machine_per_stage_diameters() -> None:
    """단별 외경을 따로 줄 수 있다."""
    res = two_stage(base().at(t_subcond=None))
    machine = size_machine(res, Given(rpm=16000),
                           stage_diameters=[0.170, 0.150])
    assert machine.stages[0].diameter_mm == pytest.approx(170.0)
    assert machine.stages[1].diameter_mm == pytest.approx(150.0)
    assert all(z.rpm == pytest.approx(16000) for z in machine.stages)


def test_single_stage_machine() -> None:
    res = single_stage(base())
    machine = size_machine(res)
    assert len(machine.stages) == 1


# --- IPLV ----------------------------------------------------------------

def test_iplv_runs_and_improves_at_part_load() -> None:
    result = iplv(base().at(t_subcond=None), stages=2, medium="air")
    assert len(result.points) == 4
    # 공랭 IPLV 조건은 부분부하에서 외기가 낮아지므로 COP 가 올라간다
    assert result.points[-1].cop > result.points[0].cop
    assert result.iplv_cop > result.points[0].cop


def test_iplv_water_cooled() -> None:
    result = iplv(base().at(t_subcond=None), stages=2, medium="water")
    assert result.medium == "water"
    assert result.iplv_kw_per_rt > 0
