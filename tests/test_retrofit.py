"""같은 압축기에 냉매만 바꿔 넣는 검토 검증."""

from __future__ import annotations

import pytest

from turbochiller import CycleInput, solve
from turbochiller.retrofit import MachineSpec, retrofit, retrofit_one


def base(refrigerant: str = "R134a") -> CycleInput:
    return CycleInput(
        refrigerant=refrigerant,
        capacity_rt=150,
        chilled_water_out=7.0,
        evap_approach=1.0,
        cooling_medium_in=35.0,
        cond_approach=15.0,
        superheat=1.0,
        subcool=3.0,
    )


def test_machine_spec_from_design() -> None:
    """설계 결과에서 뽑은 기계 사양이 그 결과와 맞아야 한다."""
    res = solve(base(), stages=2)
    machine = MachineSpec.from_result(res)
    first = res.stage_results[0]
    assert machine.suction_volume_flow == pytest.approx(
        first.mass_flow / first.suction_density, rel=1e-12
    )
    assert machine.total_work == pytest.approx(
        sum(st.dh_actual for st in res.stage_results), rel=1e-12
    )
    assert machine.stages == 2


def test_same_refrigerant_reproduces_design_point() -> None:
    """설계에 쓴 냉매를 그대로 넣으면 설계 능력이 그대로 나와야 한다."""
    inp = base()
    machine, points = retrofit(inp, ["R134a"], stages=2)
    pt = points[0]
    assert pt.ok
    assert pt.capacity_rt == pytest.approx(inp.capacity_rt, rel=1e-6)
    assert pt.capacity_ratio == pytest.approx(1.0, rel=1e-9)
    assert pt.head_margin == pytest.approx(0.0, abs=1e-9)


def test_capacity_follows_volumetric_capacity() -> None:
    """같은 기계면 능력이 체적 냉동능력에 비례해야 한다.

    능력 = (흡입밀도 x 흡입체적유량) x 냉동효과 = 체적능력 x 체적유량
    """
    machine, points = retrofit(base(), ["R134a", "R1234ze(E)", "R1234yf"], stages=2)
    for pt in points:
        assert pt.ok
        assert pt.capacity_kw == pytest.approx(
            pt.volumetric_capacity * machine.suction_volume_flow, rel=1e-9
        )
        assert pt.volumetric_capacity == pytest.approx(
            pt.suction_density * pt.refrigerating_effect, rel=1e-9
        )


def test_r1234ze_loses_capacity_in_r134a_machine() -> None:
    """R134a 기계에 R1234ze 를 넣으면 능력이 눈에 띄게 준다.

    R1234ze 는 흡입밀도가 낮아 체적 냉동능력이 작다.
    문헌에서 말하는 20~30% 감소와 같은 방향이어야 한다.
    """
    _, points = retrofit(base(), ["R134a", "R1234ze(E)"], stages=2)
    r134a, r1234ze = points
    assert r1234ze.suction_density < r134a.suction_density
    assert r1234ze.volumetric_capacity < r134a.volumetric_capacity
    assert 0.65 < r1234ze.capacity_ratio < 0.85


def test_low_pressure_refrigerant_needs_much_bigger_machine() -> None:
    """저압 냉매는 같은 기계에서 능력이 크게 떨어진다."""
    _, points = retrofit(base(), ["R134a", "R1233zd(E)"], stages=2)
    assert points[1].capacity_ratio < 0.4


def test_head_shortfall_is_flagged() -> None:
    """헤드가 모자라면 알려주고, 도달 가능한 응축온도를 함께 준다."""
    _, points = retrofit(base(), ["R134a", "R1233zd(E)"], stages=2)
    low = points[1]
    assert low.head_margin < 0
    assert not low.head_ok
    assert "헤드가" in low.message
    assert low.reachable_t_cond is not None
    assert low.reachable_t_cond < low.t_cond


def test_head_margin_matches_work_ratio() -> None:
    machine, points = retrofit(base(), ["R134a", "R1234ze(E)"], stages=2)
    for pt in points:
        assert pt.work_available == pytest.approx(machine.total_work, rel=1e-12)
        assert pt.head_margin == pytest.approx(
            pt.work_available / pt.work_required - 1.0, rel=1e-9
        )


def test_operating_conditions_are_unchanged() -> None:
    """운전조건(증발·응축온도)은 냉매가 바뀌어도 설계 그대로여야 한다.

    응축온도는 압축기가 아니라 응축기와 외기가 정하는 값이다.
    """
    inp = base()
    _, points = retrofit(inp, ["R134a", "R1234ze(E)", "R1234yf"], stages=2)
    for pt in points:
        assert pt.t_evap == pytest.approx(inp.te)
        assert pt.t_cond == pytest.approx(inp.tc)


def test_each_point_carries_full_cycle() -> None:
    """P-h 선도를 그릴 수 있게 사이클 결과가 함께 와야 한다."""
    _, points = retrofit(base(), ["R134a", "R1234ze(E)"], stages=2)
    for pt in points:
        assert pt.result is not None
        assert len(pt.result.states) == 9
        assert pt.pressure_ratio > 1.0
        assert pt.shaft_power > 0


def test_single_stage_machine() -> None:
    _, points = retrofit(base(), ["R134a", "R1234ze(E)"], stages=1)
    assert all(p.ok for p in points)
    assert all(p.result.stages == 1 for p in points)


def test_unknown_refrigerant_is_reported_not_raised() -> None:
    """모르는 냉매는 예외가 아니라 메시지로 알려야 한다."""
    _, points = retrofit(base(), ["R134a", "존재하지않는냉매"], stages=2)
    assert points[0].ok
    assert not points[1].ok
    assert points[1].message


def test_retrofit_one_without_baseline() -> None:
    machine = MachineSpec.from_result(solve(base(), stages=2))
    pt = retrofit_one(machine, base(), "R1234ze(E)")
    assert pt.ok
    assert pt.capacity_ratio == 1.0     # 기준이 없으면 1 로 둔다
