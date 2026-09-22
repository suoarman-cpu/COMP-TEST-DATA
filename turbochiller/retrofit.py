"""같은 압축기에 냉매만 바꿔 넣으면 어떻게 되는지 계산한다.

냉매 교체 검토에는 두 가지 질문이 있고, 답이 전혀 다르다.

  (가) 새로 설계    — 같은 능력을 내려면 기계가 얼마나 달라져야 하나
  (나) 기존 기계 유지 — 기계는 그대로 두고 냉매만 바꾸면 능력이 어떻게 되나

여기서 다루는 것은 (나) 다. 실제 냉매 전환에서 먼저 묻는 질문이다.

압축기를 형상(임펠러 외경 등)이 아니라 **사이클 관점의 능력** 두 개로 잡는다.

  1. 흡입 체적유량 Q [m3/s]
     회전수와 유로가 그대로면 삼키는 부피는 거의 같다.
     냉매가 바뀌면 밀도가 달라지므로 질량유량이 달라지고, 능력이 달라진다.

  2. 단별 실제 일 w [kJ/kg]
     주속이 그대로면 단위질량당 하는 일도 거의 같다 (w = lambda * u2^2).
     냉매가 바뀌면 그 일로 도달할 수 있는 압력(=응축온도)이 달라진다.

주의: 이 가정은 설계점 근처에서만 맞다. 냉매가 바뀌면 마하수와 레이놀즈수가
달라져 성능맵이 이동하므로, 실제로는 효율도 조금 변한다.
여기서는 효율을 그대로 두고 본다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from . import props
from .cycle import KW_PER_RT, CycleInput, CycleResult, solve


@dataclass
class MachineSpec:
    """기존 압축기를 사이클 관점에서 표현한 것."""

    suction_volume_flow: float      # 1단 흡입 체적유량 [m3/s]
    stage_works: list[float]        # 단별 실제 엔탈피 상승 [kJ/kg]
    eta_is: list[float]             # 단별 단열효율
    eta_wire_to_shaft: float
    stages: int
    source_refrigerant: str

    @classmethod
    def from_result(cls, res: CycleResult) -> "MachineSpec":
        """설계 계산 결과에서 기계 사양을 뽑아낸다."""
        first = res.stage_results[0]
        return cls(
            suction_volume_flow=first.mass_flow / first.suction_density,
            stage_works=[st.dh_actual for st in res.stage_results],
            eta_is=[st.eta_isentropic for st in res.stage_results],
            eta_wire_to_shaft=res.inp.eta_wire_to_shaft,
            stages=res.stages,
            source_refrigerant=res.refrigerant,
        )

    @property
    def total_work(self) -> float:
        """단위질량당 총 일 [kJ/kg]."""
        return sum(self.stage_works)

    @property
    def suction_volume_flow_m3h(self) -> float:
        return self.suction_volume_flow * 3600.0


@dataclass
class RetrofitPoint:
    """냉매 하나를 기존 기계에 넣었을 때의 결과.

    운전조건(증발온도·응축온도)은 설계 그대로 두고 본다.
    응축온도는 압축기가 아니라 응축기와 외기가 정하는 값이기 때문이다.
    기계에서 고정되는 것은 '삼키는 부피' 와 '단위질량당 하는 일' 두 가지다.
    """

    refrigerant: str
    ok: bool
    message: str = ""

    # 운전조건 (설계와 동일)
    t_evap: float = 0.0
    t_cond: float = 0.0
    p_evap: float = 0.0
    p_cond: float = 0.0
    pressure_ratio: float = 0.0

    # 기계가 삼키는 부피는 같고, 밀도가 달라져 질량유량이 달라진다
    suction_density: float = 0.0        # [kg/m3]
    mass_flow: float = 0.0              # [kg/s]
    refrigerating_effect: float = 0.0   # 냉동효과 [kJ/kg]
    volumetric_capacity: float = 0.0    # 체적 냉동능력 [kJ/m3]

    # 능력과 동력
    capacity_kw: float = 0.0
    capacity_rt: float = 0.0
    capacity_ratio: float = 0.0         # 기준 냉매 대비
    shaft_power: float = 0.0
    input_power: float = 0.0
    cop: float = 0.0
    cop_ratio: float = 0.0
    discharge_temp: float = 0.0

    # 헤드(일) 여유 — 이 조건을 만들 수 있는가
    work_required: float = 0.0          # 이 조건에 필요한 일 [kJ/kg]
    work_available: float = 0.0         # 기계가 하는 일 [kJ/kg]
    head_margin: float = 0.0            # 여유율 [-] (0.1 이면 10% 여유)
    reachable_t_cond: Optional[float] = None   # 이 일로 갈 수 있는 최대 응축온도

    result: Optional[CycleResult] = None

    @property
    def head_ok(self) -> bool:
        return self.head_margin >= 0.0


def _required_work(inp: CycleInput, t_cond: float, stages: int) -> Optional[float]:
    """그 응축온도까지 올리는 데 필요한 단위질량당 일 [kJ/kg]."""
    try:
        res = solve(inp.at(t_cond=t_cond, t_evap=inp.te), stages=stages)
    except (ValueError, RuntimeError):
        return None
    return sum(st.dh_actual for st in res.stage_results)


def _solve_reachable_cond(
    inp: CycleInput, machine: MachineSpec, stages: int,
) -> tuple[Optional[float], str]:
    """기계가 낼 수 있는 일로 도달 가능한 응축온도를 찾는다.

    필요한 일은 응축온도가 올라갈수록 커진다. 다만 응축온도가 너무 낮으면
    서브콘덴서나 과냉 조건이 성립하지 않아 계산 자체가 안 되는 구간이 있다.
    그래서 먼저 계산 가능한 구간을 훑어 찾고, 그 안에서 이분법을 쓴다.
    """
    te = inp.te
    hi_limit = min(props.t_crit(inp.refrigerant) - 3.0, 130.0)
    lo_limit = te + 1.0
    if hi_limit <= lo_limit:
        return None, "증발온도가 임계온도에 너무 가깝다"

    target = machine.total_work

    # 1) 계산 가능한 (응축온도, 필요한 일) 을 훑는다
    samples: list[tuple[float, float]] = []
    steps = 18
    for i in range(steps + 1):
        t = lo_limit + (hi_limit - lo_limit) * i / steps
        w = _required_work(inp, t, stages)
        if w is not None:
            samples.append((t, w))
    if not samples:
        return None, "이 냉매로는 주어진 조건에서 사이클이 성립하지 않는다"

    lowest_t, lowest_w = samples[0]
    highest_t, highest_w = samples[-1]

    if lowest_w > target:
        return None, (
            f"기계의 일({target:.1f} kJ/kg)로는 가장 낮은 응축온도"
            f"({lowest_t:.0f}°C, {lowest_w:.1f} kJ/kg 필요)조차 만들지 못한다"
        )
    if highest_w < target:
        return highest_t, (
            f"임계점 부근({highest_t:.0f}°C)까지 여유가 있다. "
            "실제로는 다른 조건이 먼저 걸린다"
        )

    # 2) 필요한 일이 기계의 일을 넘어서는 지점을 찾는다
    lo, hi = lowest_t, highest_t
    for (t_a, w_a), (t_b, w_b) in zip(samples, samples[1:]):
        if w_a <= target <= w_b:
            lo, hi = t_a, t_b
            break

    for _ in range(24):
        mid = 0.5 * (lo + hi)
        w = _required_work(inp, mid, stages)
        if w is None:
            lo = mid          # 계산이 안 되는 구간은 위로 밀어낸다
            continue
        if w < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.02:
            break
    return 0.5 * (lo + hi), ""


def retrofit_one(
    machine: MachineSpec,
    base: CycleInput,
    refrigerant: str,
    stages: Optional[int] = None,
    baseline: Optional[RetrofitPoint] = None,
) -> RetrofitPoint:
    """냉매 하나를 기존 기계에 넣어 본다 (운전조건은 설계 그대로)."""
    stages = stages or machine.stages
    inp = base.at(refrigerant=refrigerant)

    try:
        t_crit = props.t_crit(refrigerant)
    except Exception as exc:
        return RetrofitPoint(refrigerant, False, f"물성을 읽을 수 없다: {exc}")
    if inp.tc >= t_crit - 1.0:
        return RetrofitPoint(
            refrigerant, False,
            f"응축온도({inp.tc:.0f}°C)가 임계온도({t_crit:.0f}°C)를 넘거나 붙는다",
        )

    try:
        res = solve(inp, stages=stages)
    except (ValueError, RuntimeError) as exc:
        return RetrofitPoint(refrigerant, False, f"사이클 계산 실패: {exc}")

    # 기계가 삼키는 부피는 그대로, 밀도가 달라져 질량유량이 달라진다
    first = res.stage_results[0]
    rho1 = first.suction_density
    mdot = rho1 * machine.suction_volume_flow

    dh_evap = (
        res.state(9).h - res.state(8).h if stages == 2
        else res.state(6).h - res.state(5).h
    )
    qe = mdot * dh_evap
    mdot_total = mdot * (1.0 + (res.subcond_mass_ratio or 0.0))

    work_required = sum(st.dh_actual for st in res.stage_results)
    work_available = machine.total_work
    margin = work_available / work_required - 1.0 if work_required > 0 else 0.0

    shaft = sum(
        st.dh_actual * (mdot if i == 0 else mdot_total)
        for i, st in enumerate(res.stage_results)
    )

    # 도달 가능 응축온도는 탐색 비용이 커서, 헤드가 모자랄 때만 구한다
    reachable: Optional[float] = None
    note = ""
    if margin < 0:
        reachable, _ = _solve_reachable_cond(inp, machine, stages)
        note = (
            f"헤드가 {abs(margin) * 100:.0f}% 모자란다. 이 기계로는 "
            f"응축 {inp.tc:.0f}°C 를 만들 수 없다"
        )
        if reachable is not None:
            note += f" (갈 수 있는 최대 응축온도 약 {reachable:.0f}°C)"

    point = RetrofitPoint(
        refrigerant=refrigerant,
        ok=True,
        message=note,
        t_evap=inp.te,
        t_cond=inp.tc,
        p_evap=res.state(1).p,
        p_cond=res.stage_results[-1].p_out,
        pressure_ratio=res.total_pressure_ratio,
        suction_density=rho1,
        mass_flow=mdot,
        refrigerating_effect=dh_evap,
        volumetric_capacity=rho1 * dh_evap,
        capacity_kw=qe,
        capacity_rt=qe / KW_PER_RT,
        shaft_power=shaft,
        input_power=shaft / machine.eta_wire_to_shaft,
        cop=qe / shaft if shaft > 0 else 0.0,
        discharge_temp=res.stage_results[-1].t_out,
        work_required=work_required,
        work_available=work_available,
        head_margin=margin,
        reachable_t_cond=reachable,
        result=res,
    )
    if baseline is not None and baseline.ok:
        point.capacity_ratio = point.capacity_kw / baseline.capacity_kw
        point.cop_ratio = point.cop / baseline.cop
    else:
        point.capacity_ratio = 1.0
        point.cop_ratio = 1.0
    return point


def retrofit(
    base: CycleInput,
    refrigerants: Sequence[str],
    stages: int = 2,
    machine: Optional[MachineSpec] = None,
) -> tuple[MachineSpec, list[RetrofitPoint]]:
    """기준 냉매로 설계한 기계에 여러 냉매를 넣어 비교한다.

    base         : 기준 냉매와 운전조건이 담긴 입력
    refrigerants : 비교할 냉매 목록 (기준 냉매를 맨 앞에 두면 보기 좋다)
    machine      : 기계 사양을 직접 줄 때. 없으면 base 로 설계 계산해서 뽑는다
    """
    if machine is None:
        machine = MachineSpec.from_result(solve(base, stages=stages))

    points: list[RetrofitPoint] = []
    baseline: Optional[RetrofitPoint] = None
    for ref in refrigerants:
        pt = retrofit_one(machine, base, ref, stages, baseline)
        if baseline is None and pt.ok:
            baseline = pt
            pt.capacity_ratio = 1.0
            pt.cop_ratio = 1.0
        points.append(pt)
    return machine, points
