"""터보 냉동기(칠러) 냉동 사이클 해석.

엑셀 `150RT_Cycle_Analysis` 의 계산을 그대로 옮기고, 몇 군데는
열역학적으로 더 정확한 방식을 기본값으로 두었다 (`ExcelCompat` 참고).

지원하는 사이클
    1단 압축           :  single_stage()
    2단 압축 + 이코노마이저(서브콘덴서) :  two_stage()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Optional

from . import props

#: 1 냉동톤(RT) = 3.516 kW (엑셀 시트와 동일)
KW_PER_RT = 3.516


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------

@dataclass
class ExcelCompat:
    """엑셀 원본과 똑같은 결과를 보고 싶을 때 켜는 호환 옵션.

    기본값(False)은 열역학적으로 더 맞는 계산을 쓴다.
    엑셀과 숫자를 한 줄씩 맞춰볼 때만 True 로 두면 된다.
    """

    #: 2단 흡입 혼합을 엔탈피가 아니라 온도로 가중평균한다 (엑셀 방식).
    temperature_mixing: bool = False
    #: 응축 열량을 1단 유량만으로 계산한다 (엑셀의 누락된 (1+x) 항).
    condenser_duty_first_stage_flow: bool = False


@dataclass
class CycleInput:
    """사이클 계산에 필요한 입력값 (단위: °C, kPa, kW)."""

    # --- 기본 사양 ---
    refrigerant: str = "R1234ze(E)"
    capacity_rt: float = 150.0          # 정격 냉동능력 [RT]

    # --- 증발기 측 ---
    chilled_water_in: float = 12.0      # 냉수 입구 [°C]
    chilled_water_out: float = 7.0      # 냉수 출구 [°C]
    evap_approach: float = 1.0          # 증발기 approach [°C] -> Te = 냉수출구 - approach
    superheat: float = 1.0              # 과열도 [°C]

    # --- 응축기 측 ---
    cooling_medium_in: float = 35.0     # 공기(수냉이면 냉각수) 입구 [°C]
    cond_approach: float = 15.0         # 응축기 approach [°C] -> Tc = 입구 + approach
    subcool: float = 3.0                # 과냉도 [°C]

    # --- 온도를 직접 지정하고 싶을 때 (approach 계산보다 우선) ---
    t_evap: Optional[float] = None      # 증발온도 [°C]
    t_cond: Optional[float] = None      # 응축온도 [°C]

    # --- 배관 압력손실 ---
    dp_suction: float = 3.0             # 흡입관 [kPa]
    dp_discharge: float = 5.0           # 토출관 [kPa]

    # --- 압축기 ---
    eta_is_stage1: float = 0.80         # 1단 단열효율
    eta_is_stage2: float = 0.80         # 2단 단열효율
    eta_wire_to_shaft: float = 0.89     # 전기 -> 축 효율 (모터+인버터)
    heat_loss_stage1: float = 0.0       # 1단 방열에 의한 토출온도 하강 [°C]
    heat_loss_stage2: float = 0.0       # 2단 방열에 의한 토출온도 하강 [°C]

    # --- 이코노마이저 / 서브콘덴서 (2단에서만) ---
    t_subcond: Optional[float] = None
    """중간(서브콘덴서) 온도 [°C].

    None 이면 중간압을 흡입·토출 압력의 기하평균 sqrt(P1·P2) 로 잡는다.
    (엑셀 시트의 '√(P1P2)' 셀과 같은 개념. 압축비를 두 단에 고르게 나누는 값)
    부분부하처럼 응축온도가 바뀌는 계산에서는 None 으로 두는 편이 안전하다.
    """
    subcond_mass_ratio: Optional[float] = 0.2
    """중간단 추가 유량비 x = m_eco / m_evap.

    None 으로 두면 이코노마이저 에너지 밸런스로 직접 계산한다.
    """

    # --- 최대 운전조건 (기동/고외기 보호 설계점) ---
    t_cond_max: float = 70.0            # 최대 응축온도 [°C]
    eta_is_max: float = 0.80            # 그때의 단열효율

    # --- 2차측(물) 물성 ---
    water_density: float = 997.0        # [kg/m3]
    water_cp: float = 4.18              # [kJ/kg·K]

    compat: ExcelCompat = field(default_factory=ExcelCompat)

    # -- 유도값 ------------------------------------------------------------
    @property
    def te(self) -> float:
        """증발온도 [°C]."""
        if self.t_evap is not None:
            return self.t_evap
        return self.chilled_water_out - self.evap_approach

    @property
    def tc(self) -> float:
        """응축온도 [°C]."""
        if self.t_cond is not None:
            return self.t_cond
        return self.cooling_medium_in + self.cond_approach

    def intermediate_temp(self, p_evap: float, p_cond: float) -> float:
        """서브콘덴서(중간단) 온도 [°C].

        직접 지정한 값이 있으면 그것을, 없으면 기하평균 중간압에 대응하는
        포화온도를 쓴다.
        """
        if self.t_subcond is not None:
            return self.t_subcond
        return props.t_sat(self.refrigerant, math.sqrt(p_evap * p_cond), q=1)

    @property
    def qe_kw(self) -> float:
        """냉동능력 [kW]."""
        return self.capacity_rt * KW_PER_RT

    def at(self, **changes) -> "CycleInput":
        """일부 값만 바꾼 새 입력을 만든다 (부분부하 계산 등에 쓴다)."""
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

@dataclass
class StatePoint:
    """사이클 상태점 하나."""

    no: int
    name: str
    t: float            # 온도 [°C]
    p: float            # 압력 [kPa]
    h: float            # 엔탈피 [kJ/kg]
    d: Optional[float] = None   # 밀도 [kg/m3]
    s: Optional[float] = None   # 엔트로피 [kJ/kg·K]


@dataclass
class StageResult:
    """압축기 한 단의 성능."""

    name: str
    p_in: float
    p_out: float
    t_in: float
    t_out: float
    t_out_isentropic: float
    dh_isentropic: float        # [kJ/kg]
    dh_actual: float            # [kJ/kg]
    mass_flow: float            # [kg/s]
    power: float                # 축동력 [kW]
    pressure_ratio: float
    eta_isentropic: float
    suction_density: float      # [kg/m3]

    @property
    def volume_flow_m3h(self) -> float:
        """흡입 체적유량 [m3/h]."""
        return self.mass_flow / self.suction_density * 3600.0


@dataclass
class MaxCondition:
    """최대 응축온도에서의 보호 설계점."""

    t_cond: float
    p_cond: float
    t_discharge: float
    dh_isentropic: float
    dh_actual: float
    pressure_ratio: float
    shaft_power: float
    input_power: float


@dataclass
class CycleResult:
    """사이클 해석 결과."""

    stages: int
    refrigerant: str
    inp: CycleInput
    states: list[StatePoint]
    stage_results: list[StageResult]
    qe: float                   # 냉동능력 [kW]
    qc: float                   # 응축(방열) 열량 [kW]
    mass_flow_evap: float       # 증발기 유량 [kg/s]
    mass_flow_total: float      # 응축기 유량 [kg/s]
    volume_flow_m3h: float      # 1단 흡입 체적유량 [m3/h]
    shaft_power: float          # 총 축동력 [kW]
    input_power: float          # 총 입력전력 [kW]
    total_pressure_ratio: float
    cop: float                  # 축동력 기준 COP
    cop_input: float            # 입력전력 기준 COP
    subcond_mass_ratio: Optional[float]
    max_condition: Optional[MaxCondition]

    def state(self, no: int) -> StatePoint:
        """번호로 상태점을 찾는다."""
        for s in self.states:
            if s.no == no:
                return s
        raise KeyError(f"상태점 {no} 없음")

    @property
    def kw_per_rt(self) -> float:
        """냉동톤당 소비전력 [kW/RT]. 작을수록 좋다."""
        return self.input_power / self.inp.capacity_rt

    @property
    def energy_balance_error(self) -> float:
        """에너지 수지 오차 [%]  ->  (Qc - Qe - W) / Qe * 100.

        이상적으로는 0 이어야 한다. 값이 뜨는 이유는 보통 둘 중 하나다.
          - 배관 압력손실을 (원본 엑셀처럼) 등온으로 모델링해서 생기는 작은 오차
          - 2단에서 중간단 유량비 x 를 손으로 지정해 이코노마이저 수지가
            맞지 않는 경우 (subcond_mass_ratio=None 으로 두면 맞는다)
        """
        return (self.qc - self.qe - self.shaft_power) / self.qe * 100.0


# ---------------------------------------------------------------------------
# 압축 과정
# ---------------------------------------------------------------------------

def compress(
    fluid: str,
    name: str,
    t_in: float,
    p_in: float,
    p_out: float,
    eta_is: float,
    mass_flow: float,
    heat_loss: float = 0.0,
) -> StageResult:
    """단열효율을 이용한 한 단의 압축 계산.

    s1 = s(T1,P1) -> 등엔트로피 출구 엔탈피 -> 실제 엔탈피 상승 = 등엔트로피/η
    """
    if not 0.0 < eta_is <= 1.0:
        raise ValueError(f"{name}: 단열효율은 0~1 사이여야 한다 (입력 {eta_is})")
    if p_out <= p_in:
        raise ValueError(
            f"{name}: 토출압력({p_out:.1f} kPa)이 흡입압력({p_in:.1f} kPa)보다 낮다"
        )

    h_in = props.h_tp(fluid, t_in, p_in)
    s_in = props.s_tp(fluid, t_in, p_in)
    d_in = props.d_tp(fluid, t_in, p_in)

    h_out_is = props.h_sp(fluid, s_in, p_out)
    t_out_is = props.t_sp(fluid, s_in, p_out)

    dh_is = h_out_is - h_in
    dh_actual = dh_is / eta_is
    t_out = props.t_hp(fluid, h_in + dh_actual, p_out) - heat_loss

    return StageResult(
        name=name,
        p_in=p_in,
        p_out=p_out,
        t_in=t_in,
        t_out=t_out,
        t_out_isentropic=t_out_is,
        dh_isentropic=dh_is,
        dh_actual=dh_actual,
        mass_flow=mass_flow,
        power=mass_flow * dh_actual,
        pressure_ratio=p_out / p_in,
        eta_isentropic=eta_is,
        suction_density=d_in,
    )


def _max_condition(
    inp: CycleInput, t_suction: float, p_suction: float, mass_flow_total: float
) -> MaxCondition:
    """최대 응축온도 조건에서의 토출온도와 소요동력."""
    fluid = inp.refrigerant
    p_max = props.p_sat(fluid, inp.t_cond_max, q=1)
    stage = compress(
        fluid, "최대조건", t_suction, p_suction, p_max, inp.eta_is_max, mass_flow_total
    )
    return MaxCondition(
        t_cond=inp.t_cond_max,
        p_cond=p_max,
        t_discharge=stage.t_out,
        dh_isentropic=stage.dh_isentropic,
        dh_actual=stage.dh_actual,
        pressure_ratio=stage.pressure_ratio,
        shaft_power=stage.power,
        input_power=stage.power / inp.eta_wire_to_shaft,
    )


# ---------------------------------------------------------------------------
# 1단 압축 사이클
# ---------------------------------------------------------------------------

def single_stage(inp: CycleInput) -> CycleResult:
    """1단 압축 사이클을 푼다."""
    fluid = inp.refrigerant
    te, tc = inp.te, inp.tc
    _check_temperatures(inp, te, tc)

    p_evap = props.p_sat(fluid, te, q=0)
    p_cond = props.p_sat(fluid, tc, q=1)

    # 1 : 압축기 흡입 (증발기 출구에서 흡입관 압력손실만큼 떨어진 곳)
    t1 = te + inp.superheat
    p1 = p_evap - inp.dp_suction
    h1 = props.h_tp(fluid, t1, p1)

    # 2 : 압축기 토출 (응축압력 + 토출관 손실)
    p2 = p_cond + inp.dp_discharge
    stage = compress(
        fluid, "압축기", t1, p1, p2, inp.eta_is_stage1, 1.0, inp.heat_loss_stage1
    )

    # 3 : 응축기 입구
    t3, p3 = stage.t_out, p_cond
    h3 = props.h_tp(fluid, t3, p3)

    # 4 : 응축기 출구 (과냉 액)
    t4 = tc - inp.subcool
    h4 = props.h_tp(fluid, t4, p_cond)

    # 5 : 증발기 입구 (팽창밸브 등엔탈피)
    h5 = h4
    t5, p5 = te, p_evap

    # 6 : 증발기 출구
    t6, p6 = te + inp.superheat, p_evap
    h6 = props.h_tp(fluid, t6, p6)

    qe = inp.qe_kw
    dh_evap = h6 - h5
    if dh_evap <= 0:
        raise ValueError("증발기 엔탈피 차가 0 이하다. 증발/응축 온도를 확인할 것")
    mdot = qe / dh_evap

    stage = replace(stage, mass_flow=mdot, power=mdot * stage.dh_actual)
    h2 = h1 + stage.dh_actual
    qc = mdot * (h3 - h4)

    states = [
        _pt(1, "압축기 흡입", fluid, t1, p1, h1),
        _pt(2, "압축기 토출", fluid, stage.t_out, p2, h2),
        _pt(3, "응축기 입구", fluid, t3, p3, h3),
        _pt(4, "응축기 출구(과냉액)", fluid, t4, p_cond, h4),
        StatePoint(5, "증발기 입구(팽창후)", t5, p5, h5),
        _pt(6, "증발기 출구", fluid, t6, p6, h6),
    ]

    shaft = stage.power
    return CycleResult(
        stages=1,
        refrigerant=fluid,
        inp=inp,
        states=states,
        stage_results=[stage],
        qe=qe,
        qc=qc,
        mass_flow_evap=mdot,
        mass_flow_total=mdot,
        volume_flow_m3h=stage.volume_flow_m3h,
        shaft_power=shaft,
        input_power=shaft / inp.eta_wire_to_shaft,
        total_pressure_ratio=p2 / p1,
        cop=qe / shaft,
        cop_input=qe / (shaft / inp.eta_wire_to_shaft),
        subcond_mass_ratio=None,
        max_condition=_max_condition(inp, t1, p1, mdot),
    )


# ---------------------------------------------------------------------------
# 2단 압축 + 이코노마이저 사이클
# ---------------------------------------------------------------------------

def two_stage(inp: CycleInput) -> CycleResult:
    """2단 압축 + 서브콘덴서(이코노마이저) 사이클을 푼다.

    상태점 번호는 엑셀 시트와 같다.
        1 1단 흡입 / 2 1단 토출 / 3 2단 흡입(혼합후) / 4 2단 토출
        5 응축기 출구 / 6 서브콘덴서 입구 / 7 서브콘덴서 액출구
        8 증발기 입구 / 9 증발기 출구
    """
    fluid = inp.refrigerant
    te, tc = inp.te, inp.tc
    _check_temperatures(inp, te, tc)

    p_evap = props.p_sat(fluid, te, q=0)
    p_cond = props.p_sat(fluid, tc, q=1)
    tm = inp.intermediate_temp(p_evap, p_cond)
    if not te < tm < tc:
        raise ValueError(
            f"서브콘덴서 온도({tm:.2f}°C)는 증발온도({te:.2f}°C)와 "
            f"응축온도({tc:.2f}°C) 사이여야 한다. "
            "t_subcond 를 비워두면 중간압을 자동으로 잡는다"
        )
    p_mid = props.p_sat(fluid, tm, q=1)

    # 9 : 증발기 출구 / 1 : 1단 흡입
    t9, p9 = te + inp.superheat, p_evap
    h9 = props.h_tp(fluid, t9, p9)
    t1, p1 = t9, p9 - inp.dp_suction
    h1 = props.h_tp(fluid, t1, p1)

    # 5 : 응축기 출구 (과냉액)
    t5 = tc - inp.subcool
    h5 = props.h_tp(fluid, t5, p_cond)

    # 7 : 서브콘덴서 액 출구 -> 8 : 증발기 입구 (등엔탈피 팽창)
    t7 = tm - inp.subcool
    if t7 <= te:
        raise ValueError(
            f"서브콘덴서 액 출구온도({t7:.2f}°C)가 증발온도({te:.2f}°C) 이하다. "
            "과냉도를 줄이거나 서브콘덴서 온도를 올릴 것"
        )
    h7 = props.h_tp(fluid, t7, p_mid)
    h8 = h7

    dh_evap = h9 - h8
    if dh_evap <= 0:
        raise ValueError("증발기 엔탈피 차가 0 이하다. 서브콘덴서 온도를 확인할 것")
    mdot1 = inp.qe_kw / dh_evap

    # 중간단으로 빠지는 유량비 x
    h_mid_vapor = props.h_sat(fluid, tm, q=1)
    if inp.subcond_mass_ratio is None:
        # 이코노마이저 에너지 밸런스: (1+x)·h5 = x·hg(tm) + h7
        denom = h_mid_vapor - h5
        if denom <= 0:
            raise ValueError("서브콘덴서 에너지 밸런스를 만족할 수 없다")
        x = (h5 - h7) / denom
    else:
        x = inp.subcond_mass_ratio
    if x < 0:
        raise ValueError(f"중간단 유량비가 음수다 (x={x:.3f})")
    mdot_total = mdot1 * (1.0 + x)

    # 1단 압축 : p1 -> p_mid
    st1 = compress(
        fluid, "1단", t1, p1, p_mid, inp.eta_is_stage1, mdot1, inp.heat_loss_stage1
    )
    t2, p2 = st1.t_out, p_mid
    h2 = h1 + st1.dh_actual

    # 3 : 1단 토출 + 서브콘덴서 증기의 혼합
    if inp.compat.temperature_mixing:
        t3 = (t2 + x * tm) / (1.0 + x)
        h3 = props.h_tp(fluid, t3, p_mid)
    else:
        h3 = (h2 + x * h_mid_vapor) / (1.0 + x)
        t3 = props.t_hp(fluid, h3, p_mid)
    p3 = p_mid

    # 2단 압축 : p_mid -> p_cond
    st2 = compress(
        fluid, "2단", t3, p3, p_cond, inp.eta_is_stage2, mdot_total, inp.heat_loss_stage2
    )
    t4, p4 = st2.t_out, p_cond
    h4 = h3 + st2.dh_actual

    # 6 : 서브콘덴서 입구 (응축기 액이 중간압까지 등엔탈피 팽창)
    t6, p6, h6 = tm, p_mid, h5

    qe = inp.qe_kw
    flow_for_qc = mdot1 if inp.compat.condenser_duty_first_stage_flow else mdot_total
    qc = flow_for_qc * (h4 - h5)

    states = [
        _pt(1, "1단 흡입", fluid, t1, p1, h1),
        _pt(2, "1단 토출", fluid, t2, p2, h2),
        _pt(3, "2단 흡입(혼합후)", fluid, t3, p3, h3),
        _pt(4, "2단 토출", fluid, t4, p4, h4),
        _pt(5, "응축기 출구(과냉액)", fluid, t5, p_cond, h5),
        StatePoint(6, "서브콘덴서 입구", t6, p6, h6),
        _pt(7, "서브콘덴서 액출구", fluid, t7, p_mid, h7),
        StatePoint(8, "증발기 입구(팽창후)", te, p_evap, h8),
        _pt(9, "증발기 출구", fluid, t9, p9, h9),
    ]

    shaft = st1.power + st2.power
    return CycleResult(
        stages=2,
        refrigerant=fluid,
        inp=inp,
        states=states,
        stage_results=[st1, st2],
        qe=qe,
        qc=qc,
        mass_flow_evap=mdot1,
        mass_flow_total=mdot_total,
        volume_flow_m3h=st1.volume_flow_m3h,
        shaft_power=shaft,
        input_power=shaft / inp.eta_wire_to_shaft,
        total_pressure_ratio=p_cond / p1,
        cop=qe / shaft,
        cop_input=qe / (shaft / inp.eta_wire_to_shaft),
        subcond_mass_ratio=x,
        max_condition=_max_condition(inp, t1, p1, mdot_total),
    )


def solve(inp: CycleInput, stages: int = 2) -> CycleResult:
    """단수를 골라 사이클을 푼다."""
    if stages == 1:
        return single_stage(inp)
    if stages == 2:
        return two_stage(inp)
    raise ValueError(f"1단 또는 2단만 지원한다 (입력 {stages})")


# ---------------------------------------------------------------------------
# 내부 도우미
# ---------------------------------------------------------------------------

def _pt(no: int, name: str, fluid: str, t: float, p: float, h: float) -> StatePoint:
    """상태점을 만들면서 밀도·엔트로피까지 채운다."""
    return StatePoint(
        no=no,
        name=name,
        t=t,
        p=p,
        h=h,
        d=props.d_tp(fluid, t, p),
        s=props.s_tp(fluid, t, p),
    )


def _check_temperatures(inp: CycleInput, te: float, tc: float) -> None:
    if te >= tc:
        raise ValueError(f"증발온도({te}°C)가 응축온도({tc}°C)보다 높거나 같다")
    t_crit = props.t_crit(inp.refrigerant)
    if tc >= t_crit:
        raise ValueError(
            f"응축온도({tc}°C)가 {inp.refrigerant} 임계온도({t_crit:.1f}°C) 이상이다"
        )
