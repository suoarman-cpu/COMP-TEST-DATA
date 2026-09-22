"""사이클 모델 자체의 동작 검증 (엑셀 대조가 아닌 물리적 타당성)."""

from __future__ import annotations

import pytest

from turbochiller import CycleInput, iplv, single_stage, solve, two_stage


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
