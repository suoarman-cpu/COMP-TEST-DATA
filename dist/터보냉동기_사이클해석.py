"""터보 냉동기 사이클 해석 — 파일 하나로 합친 배포판.

이 파일 하나만 있으면 돌아간다. 폴더 구조가 필요 없다.

쓰는 법
    화면으로 보기 :  streamlit run 터보냉동기_사이클해석.py
    바로 계산만   :  python 터보냉동기_사이클해석.py

필요한 라이브러리
    pip install CoolProp streamlit pandas matplotlib

원본은 turbochiller 패키지다 (github: suoarman-cpu/COMP-TEST-DATA).
이 파일은 tools/build_single_file.py 가 자동으로 만든 것이라,
고칠 일이 있으면 원본 패키지를 고치고 다시 빌드하는 편이 좋다.
"""

from __future__ import annotations

import argparse
import io
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable, Literal, Optional, Sequence

from CoolProp.CoolProp import PropsSI


# --- 모듈 별칭 -------------------------------------------------------------
# 원래는 turbochiller.props 처럼 모듈로 나뉘어 있었다.
# 한 파일로 합치면서, 코드 안의 `props.xxx` 호출이 그대로 동작하도록
# 이 파일 자신을 props 라는 이름으로도 가리키게 해 둔다.
import sys as _sys

props = _sys.modules[__name__]



# ==========================================================================
# props.py
# ==========================================================================

#: 섭씨 -> 켈빈 환산
T0 = 273.15

#: 자주 쓰는 냉매의 별칭. 왼쪽 이름으로도 부를 수 있게 한다.
ALIASES = {
    "R1234ZE": "R1234ze(E)",
    "R1234ZE(E)": "R1234ze(E)",
    "HFO1234ZE": "R1234ze(E)",
    "R1234YF": "R1234yf",
    "R134A": "R134a",
    "R513A": "R513A.mix",
    "R454B": "R454B.mix",
    "R1233ZD": "R1233zd(E)",
    "R1233ZD(E)": "R1233zd(E)",
}


def normalize(refrigerant: str) -> str:
    """사용자가 적은 냉매 이름을 CoolProp 이름으로 바꾼다."""
    key = refrigerant.strip().upper()
    return ALIASES.get(key, refrigerant.strip())


def _props(output: str, n1: str, v1: float, n2: str, v2: float, fluid: str) -> float:
    try:
        return PropsSI(output, n1, v1, n2, v2, normalize(fluid))
    except ValueError as exc:  # CoolProp 은 물성 범위를 벗어나면 ValueError 를 낸다
        raise PropertyError(
            f"{fluid} 물성 계산 실패: {output} @ {n1}={v1}, {n2}={v2}\n  ({exc})"
        ) from exc


class PropertyError(RuntimeError):
    """냉매 물성을 구하지 못했을 때."""


# --- 포화 물성 -------------------------------------------------------------

def p_sat(fluid: str, t_c: float, q: int = 1) -> float:
    """포화 압력 [kPa]. t_c [°C] 에서의 포화 온도 대응 압력."""
    return _props("P", "T", t_c + T0, "Q", q, fluid) / 1000.0


def t_sat(fluid: str, p_kpa: float, q: int = 1) -> float:
    """포화 온도 [°C]. p_kpa [kPa] 에서."""
    return _props("T", "P", p_kpa * 1000.0, "Q", q, fluid) - T0


def h_sat(fluid: str, t_c: float, q: int) -> float:
    """포화 엔탈피 [kJ/kg]. q=0 포화액, q=1 포화증기."""
    return _props("H", "T", t_c + T0, "Q", q, fluid) / 1000.0


def s_sat(fluid: str, t_c: float, q: int) -> float:
    """포화 엔트로피 [kJ/kg·K]."""
    return _props("S", "T", t_c + T0, "Q", q, fluid) / 1000.0


# --- 온도·압력 기준 --------------------------------------------------------

def h_tp(fluid: str, t_c: float, p_kpa: float) -> float:
    """엔탈피 [kJ/kg] (T, P 기준)."""
    return _props("H", "T", t_c + T0, "P", p_kpa * 1000.0, fluid) / 1000.0


def s_tp(fluid: str, t_c: float, p_kpa: float) -> float:
    """엔트로피 [kJ/kg·K] (T, P 기준)."""
    return _props("S", "T", t_c + T0, "P", p_kpa * 1000.0, fluid) / 1000.0


def d_tp(fluid: str, t_c: float, p_kpa: float) -> float:
    """밀도 [kg/m3] (T, P 기준)."""
    return _props("D", "T", t_c + T0, "P", p_kpa * 1000.0, fluid)


# --- 엔트로피·엔탈피 기준 --------------------------------------------------

def t_sp(fluid: str, s: float, p_kpa: float) -> float:
    """온도 [°C] (s, P 기준). 등엔트로피 압축 후 온도를 구할 때 쓴다."""
    return _props("T", "S", s * 1000.0, "P", p_kpa * 1000.0, fluid) - T0


def h_sp(fluid: str, s: float, p_kpa: float) -> float:
    """엔탈피 [kJ/kg] (s, P 기준)."""
    return _props("H", "S", s * 1000.0, "P", p_kpa * 1000.0, fluid) / 1000.0


def t_hp(fluid: str, h: float, p_kpa: float) -> float:
    """온도 [°C] (h, P 기준). 실제 압축 후 토출온도를 구할 때 쓴다."""
    return _props("T", "H", h * 1000.0, "P", p_kpa * 1000.0, fluid) - T0


def d_hp(fluid: str, h: float, p_kpa: float) -> float:
    """밀도 [kg/m3] (h, P 기준)."""
    return _props("D", "H", h * 1000.0, "P", p_kpa * 1000.0, fluid)


def q_hp(fluid: str, h: float, p_kpa: float) -> float:
    """건도 [-] (h, P 기준). 2상 영역이 아니면 -1 또는 범위 밖 값이 나온다."""
    return _props("Q", "H", h * 1000.0, "P", p_kpa * 1000.0, fluid)


def t_crit(fluid: str) -> float:
    """임계온도 [°C].

    혼합냉매(R513A.mix 등)는 CoolProp 이 임계점을 내주지 못하므로
    환산온도(T_reducing)를 대신 쓴다. 운전 범위 확인용으로는 충분하다.
    """
    from CoolProp.CoolProp import PropsSI as _P

    name = normalize(fluid)
    for key in ("Tcrit", "T_reducing"):
        try:
            return _P(key, "", 0, "", 0, name) - T0
        except ValueError:
            continue
    raise PropertyError(f"{fluid}: 임계온도를 구할 수 없다")


def a_tp(fluid: str, t_c: float, p_kpa: float) -> float:
    """음속 [m/s] (T, P 기준). 임펠러 마하수 계산에 쓴다."""
    return _props("A", "T", t_c + T0, "P", p_kpa * 1000.0, fluid)


def molar_mass(fluid: str) -> float:
    """분자량 [kg/kmol]."""
    from CoolProp.CoolProp import PropsSI as _P

    return _P("M", "", 0, "", 0, normalize(fluid)) * 1000.0


# ==========================================================================
# cycle.py
# ==========================================================================

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
    subcond_mass_ratio: Optional[float] = None
    """중간단 추가 유량비 x = m_eco / m_evap.

    기본값 None 은 이코노마이저 에너지 밸런스로 직접 계산한다는 뜻이다.
    숫자를 직접 넣으면 (원본 엑셀처럼) 그 값을 그대로 쓰는데,
    그러면 이코노마이저 에너지 수지가 맞지 않을 수 있다.
    결과의 energy_balance_error 로 확인할 것.
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


# ==========================================================================
# hx.py
# ==========================================================================

@dataclass
class HXResult:
    """열교환기 2차측 계산 결과."""

    name: str
    duty: float             # 교환 열량 [kW]
    t_refrigerant: float    # 냉매측 포화온도 [°C]
    t_in: float             # 2차측 입구 [°C]
    t_out: float            # 2차측 출구 [°C]
    delta_t: float          # 2차측 온도변화 [°C]
    volume_flow_m3h: float  # 2차측 체적유량 [m3/h]
    mass_flow: float        # 2차측 질량유량 [kg/s]
    td_in: float            # 입구측 온도차 [°C]
    td_out: float           # 출구측 온도차 [°C]
    lmtd: float             # 대수평균온도차 [°C]
    ua: float               # UA [kW/K]

    def __str__(self) -> str:
        return (
            f"{self.name}: Q={self.duty:.1f} kW, "
            f"{self.t_in:.2f} -> {self.t_out:.2f}°C, "
            f"{self.volume_flow_m3h:.1f} m3/h, LMTD={self.lmtd:.2f}K, "
            f"UA={self.ua:.1f} kW/K"
        )


def _lmtd(td_in: float, td_out: float) -> float:
    """대수평균온도차. 두 온도차가 같으면 그 값을 그대로 쓴다."""
    if td_in <= 0 or td_out <= 0:
        raise ValueError(
            f"온도차가 0 이하다 (입구 {td_in:.2f}K, 출구 {td_out:.2f}K). "
            "approach 나 유량 설정을 확인할 것"
        )
    if math.isclose(td_in, td_out, rel_tol=1e-9):
        return td_in
    return (td_in - td_out) / math.log(td_in / td_out)


def _side(
    name: str,
    duty: float,
    t_ref: float,
    t_in: float,
    spec_volume: float,
    density: float,
    cp: float,
    heating: bool,
) -> HXResult:
    """2차측 공통 계산.

    spec_volume : 단위 열량당 유량 [liter/s per kW] (AHRI 550/590 기준값)
    heating     : True 면 2차측이 데워진다(응축기), False 면 식는다(증발기)
    """
    volume_flow_m3h = spec_volume * duty / 1000.0 * 3600.0
    mass_flow = density * volume_flow_m3h / 3600.0
    delta_t = duty / (mass_flow * cp)

    if heating:
        t_out = t_in + delta_t
        td_in, td_out = t_ref - t_in, t_ref - t_out
    else:
        t_out = t_in - delta_t
        td_in, td_out = t_in - t_ref, t_out - t_ref

    lmtd = _lmtd(td_in, td_out)
    return HXResult(
        name=name,
        duty=duty,
        t_refrigerant=t_ref,
        t_in=t_in,
        t_out=t_out,
        delta_t=delta_t,
        volume_flow_m3h=volume_flow_m3h,
        mass_flow=mass_flow,
        td_in=td_in,
        td_out=td_out,
        lmtd=lmtd,
        ua=duty / lmtd,
    )


def condenser_side(
    duty: float,
    t_cond: float,
    t_in: float,
    spec_volume: float = 0.054,
    density: float = 995.67,
    cp: float = 4.18,
) -> HXResult:
    """응축기 2차측(냉각수). spec_volume 기본값은 AHRI 550 의 0.054 L/s·kW."""
    return _side("응축기", duty, t_cond, t_in, spec_volume, density, cp, heating=True)


def evaporator_side(
    duty: float,
    t_evap: float,
    t_in: float,
    spec_volume: float = 0.043,
    density: float = 999.45,
    cp: float = 4.19,
) -> HXResult:
    """증발기 2차측(냉수). spec_volume 기본값은 AHRI 550 의 0.043 L/s·kW."""
    return _side("증발기", duty, t_evap, t_in, spec_volume, density, cp, heating=False)


# ==========================================================================
# impeller.py
# ==========================================================================

#: 원심 압축기 1단의 통상 설계 범위 (경고 판정용)
LIMITS = {
    "psi": (0.45, 0.70),
    "specific_speed": (0.4, 1.0),
    "flow_coefficient": (0.01, 0.16),
    "tip_mach": (0.0, 1.5),
    "tip_speed": (0.0, 420.0),   # [m/s] 알루미늄 임펠러 기준 대략적인 상한
}


@dataclass
class ImpellerSizing:
    """임펠러 개략 치수."""

    stage_name: str
    dh_isentropic: float        # 단열 헤드 [kJ/kg]
    dh_actual: float            # 실제 엔탈피 상승 [kJ/kg]
    volume_flow: float          # 흡입 체적유량 [m3/s]
    rpm: float                  # 회전수 [rpm]
    tip_speed: float            # 임펠러 선단 주속 u2 [m/s]
    diameter: float             # 임펠러 외경 D2 [m]
    eye_diameter: float         # 흡입구(아이) 외경 추정 [m]
    head_coefficient: float     # psi
    work_coefficient: float     # lambda = dh_actual / u2^2
    specific_speed: float       # Ns
    specific_diameter: float    # Ds
    flow_coefficient: float     # phi
    tip_mach: float             # Mu2
    inlet_sound_speed: float    # [m/s]
    warnings: list[str]

    @property
    def diameter_mm(self) -> float:
        return self.diameter * 1000.0

    @property
    def eye_diameter_mm(self) -> float:
        return self.eye_diameter * 1000.0


def size_impeller(
    stage: StageResult,
    refrigerant: str,
    head_coefficient: float = 0.60,
    specific_speed: float = 0.70,
    rpm: Optional[float] = None,
    eye_hub_ratio: float = 0.35,
    inlet_axial_mach: float = 0.30,
) -> ImpellerSizing:
    """한 단의 임펠러 치수를 개략 산정한다.

    stage             : cycle.compress() 가 돌려준 단 성능
    head_coefficient  : psi. 후향깃 임펠러는 0.55~0.62 가 흔하다
    specific_speed    : Ns. rpm 을 직접 주면 무시한다
    rpm               : 회전수를 고정하고 싶을 때 [rpm]
    eye_hub_ratio     : 흡입구 허브/팁 비 (보통 0.3~0.45)
    inlet_axial_mach  : 흡입구 축방향 마하수 목표 (보통 0.25~0.35)
    """
    if head_coefficient <= 0:
        raise ValueError("압력계수(psi)는 0보다 커야 한다")

    dh_is_j = stage.dh_isentropic * 1000.0      # [J/kg]
    q = stage.mass_flow / stage.suction_density  # [m3/s]
    if q <= 0:
        raise ValueError("흡입 체적유량이 0 이하다")

    # 주속은 헤드계수로 정해진다.  dh_is = psi * u2^2
    u2 = math.sqrt(dh_is_j / head_coefficient)

    # 회전수: 직접 주거나 비속도로 정한다.
    if rpm is not None:
        omega = rpm * 2.0 * math.pi / 60.0
        ns = omega * math.sqrt(q) / dh_is_j**0.75
    else:
        ns = specific_speed
        omega = ns * dh_is_j**0.75 / math.sqrt(q)
        rpm = omega * 60.0 / (2.0 * math.pi)

    d2 = 2.0 * u2 / omega
    ds = d2 * dh_is_j**0.25 / math.sqrt(q)
    phi = q / (u2 * d2**2)

    a1 = props.a_tp(refrigerant, stage.t_in, stage.p_in)
    mu2 = u2 / a1

    # 흡입구(아이) 외경: 축방향 속도를 마하수 목표로 잡고 환상 면적에서 역산
    c_axial = inlet_axial_mach * a1
    area = q / c_axial
    d_eye = math.sqrt(4.0 * area / (math.pi * (1.0 - eye_hub_ratio**2)))

    warnings: list[str] = []
    _check(warnings, "압력계수 psi", head_coefficient, *LIMITS["psi"])
    _check(warnings, "비속도 Ns", ns, *LIMITS["specific_speed"])
    _check(warnings, "유량계수 phi", phi, *LIMITS["flow_coefficient"])
    _check(warnings, "선단 마하수 Mu2", mu2, *LIMITS["tip_mach"])
    _check(warnings, "선단 주속 u2 [m/s]", u2, *LIMITS["tip_speed"])
    if d_eye >= d2:
        warnings.append(
            f"흡입구 외경({d_eye * 1000:.0f} mm)이 임펠러 외경"
            f"({d2 * 1000:.0f} mm)보다 크다 — 단수를 늘리거나 유량을 나눌 것"
        )

    return ImpellerSizing(
        stage_name=stage.name,
        dh_isentropic=stage.dh_isentropic,
        dh_actual=stage.dh_actual,
        volume_flow=q,
        rpm=rpm,
        tip_speed=u2,
        diameter=d2,
        eye_diameter=d_eye,
        head_coefficient=head_coefficient,
        work_coefficient=stage.dh_actual * 1000.0 / u2**2,
        specific_speed=ns,
        specific_diameter=ds,
        flow_coefficient=phi,
        tip_mach=mu2,
        inlet_sound_speed=a1,
        warnings=warnings,
    )


def _check(bucket: list[str], label: str, value: float, low: float, high: float) -> None:
    if value < low:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 아래")
    elif value > high:
        bucket.append(f"{label} = {value:.3f} : 통상 범위({low}~{high}) 초과")


# ==========================================================================
# standards.py
# ==========================================================================

#: AHRI 550/590 IPLV 가중치 (100 / 75 / 50 / 25 % 부하)
IPLV_WEIGHTS = (0.01, 0.42, 0.45, 0.12)


@dataclass(frozen=True)
class LoadCondition:
    """부분부하 한 점의 조건."""

    load: float              # 부하율 [0~1]
    medium_in: float         # 냉각 공기/물 입구온도 [°C]
    approach: float          # 응축기 approach [°C]

    @property
    def t_cond(self) -> float:
        """해당 부하에서의 응축온도 [°C]."""
        return self.medium_in + self.approach


#: 공랭식 (엑셀 '규격' C71:G75) — 95/80/65/55°F 를 °C 로 환산한 값
AIR_COOLED = (
    LoadCondition(1.00, 35.0, 15.0),
    LoadCondition(0.75, 27.0, 10.0),
    LoadCondition(0.50, 19.0, 7.0),
    LoadCondition(0.25, 13.0, 7.0),
)

#: 수냉식 (엑셀 '규격' C78:G82) — 85/75/65/65°F, approach 6°C 가정
WATER_COOLED = (
    LoadCondition(1.00, 30.0, 6.0),
    LoadCondition(0.75, 24.5, 6.0),
    LoadCondition(0.50, 19.0, 6.0),
    LoadCondition(0.25, 19.0, 6.0),
)

IPLV_CONDITIONS = {"air": AIR_COOLED, "water": WATER_COOLED}


def default_part_load_efficiency(load: float, rated_eta: float) -> float:
    """부하에 따른 단열효율 보정(기본 가정).

    터보 압축기는 IGV/인버터로 용량을 줄이면 효율이 떨어진다.
    실측 데이터가 있으면 이 함수 대신 직접 만든 함수를 넘겨 쓰면 된다.
    여기서는 50% 부하까지는 거의 유지되고 그 아래에서 떨어지는 형태로 잡았다.
    """
    factor = 1.0 - 0.45 * (1.0 - load) ** 2
    return max(0.25, rated_eta * factor)


@dataclass
class LoadPoint:
    """부분부하 한 점의 계산 결과."""

    load: float
    condition: LoadCondition
    result: CycleResult

    @property
    def cop(self) -> float:
        return self.result.cop_input

    @property
    def kw_per_rt(self) -> float:
        return self.result.kw_per_rt


@dataclass
class IplvResult:
    """IPLV 계산 결과."""

    points: list[LoadPoint]
    iplv_cop: float
    iplv_kw_per_rt: float
    medium: str

    def __str__(self) -> str:
        return f"IPLV (COP 기준) = {self.iplv_cop:.3f}, {self.iplv_kw_per_rt:.4f} kW/RT"


def iplv(
    inp: CycleInput,
    stages: int = 2,
    medium: Literal["air", "water"] = "air",
    conditions: Optional[tuple[LoadCondition, ...]] = None,
    eta_curve: Callable[[float, float], float] = default_part_load_efficiency,
    float_intermediate: bool = True,
) -> IplvResult:
    """AHRI 550/590 방식의 IPLV 를 계산한다.

    각 부하점마다 냉동능력과 응축온도를 바꿔 사이클을 다시 푼다.
    eta_curve(load, rated_eta) 로 부분부하 단열효율을 준다.

    float_intermediate=True 면 부분부하에서 서브콘덴서 온도를 고정하지 않고
    중간압(sqrt(P1·P2))을 따라가게 한다. 응축온도가 내려가면 정격 중간온도가
    응축온도보다 높아져 계산이 불가능해지므로 기본값을 True 로 두었다.
    """
    table = conditions if conditions is not None else IPLV_CONDITIONS[medium]
    rated_rt = inp.capacity_rt

    points: list[LoadPoint] = []
    for cond in table:
        case = inp.at(
            capacity_rt=rated_rt * cond.load,
            cooling_medium_in=cond.medium_in,
            cond_approach=cond.approach,
            t_cond=None,
            eta_is_stage1=eta_curve(cond.load, inp.eta_is_stage1),
            eta_is_stage2=eta_curve(cond.load, inp.eta_is_stage2),
            **({"t_subcond": None} if float_intermediate else {}),
        )
        points.append(LoadPoint(cond.load, cond, solve(case, stages=stages)))

    if len(points) != len(IPLV_WEIGHTS):
        raise ValueError(
            f"IPLV 는 부하점 {len(IPLV_WEIGHTS)}개가 필요하다 (입력 {len(points)}개)"
        )

    # kW/RT 기준은 가중 조화평균, COP 기준은 가중 산술평균으로 합산한다.
    kw_per_rt = sum(w * p.kw_per_rt for w, p in zip(IPLV_WEIGHTS, points))
    cop = sum(w * p.cop for w, p in zip(IPLV_WEIGHTS, points))

    return IplvResult(points=points, iplv_cop=cop, iplv_kw_per_rt=kw_per_rt, medium=medium)


# ==========================================================================
# report.py
# ==========================================================================

LINE = "=" * 78
THIN = "-" * 78


def format_report(res: CycleResult) -> str:
    """사이클 결과 전체를 문자열로 만든다."""
    inp = res.inp
    out: list[str] = []
    add = out.append

    add(LINE)
    add(f" 터보 냉동기 사이클 해석 — {res.refrigerant} / {res.stages}단 압축")
    add(LINE)

    add("")
    add("[ 운전 조건 ]")
    add(f"  냉동능력        : {inp.capacity_rt:8.1f} RT   ({res.qe:.1f} kW)")
    add(f"  증발온도 Te     : {inp.te:8.2f} °C   (냉수 {inp.chilled_water_in:.1f} -> "
        f"{inp.chilled_water_out:.1f}°C, approach {inp.evap_approach:.1f}K)")
    add(f"  응축온도 Tc     : {inp.tc:8.2f} °C   (냉각 입구 {inp.cooling_medium_in:.1f}°C, "
        f"approach {inp.cond_approach:.1f}K)")
    add(f"  과열도 / 과냉도 : {inp.superheat:8.2f} / {inp.subcool:.2f} K")
    if res.stages == 2:
        tm = res.state(6).t
        auto = " (중간압 자동)" if inp.t_subcond is None else ""
        add(f"  서브콘덴서 온도 : {tm:8.2f} °C{auto}   "
            f"(중간단 유량비 x = {res.subcond_mass_ratio:.4f})")

    add("")
    add("[ 상태점 ]")
    add(f"  {'No':>2}  {'위치':<20} {'T[°C]':>9} {'P[kPa]':>10} "
        f"{'h[kJ/kg]':>10} {'d[kg/m3]':>10}")
    add(f"  {THIN[:72]}")
    for s in res.states:
        d = f"{s.d:10.2f}" if s.d is not None else " " * 10
        add(f"  {s.no:>2}  {s.name:<20} {s.t:9.2f} {s.p:10.2f} {s.h:10.2f} {d}")

    add("")
    add("[ 압축기 ]")
    for stage in res.stage_results:
        add(f"  - {stage.name}")
        add(f"      흡입/토출 압력   : {stage.p_in:9.2f} -> {stage.p_out:.2f} kPa "
            f"(압축비 {stage.pressure_ratio:.3f})")
        add(f"      흡입/토출 온도   : {stage.t_in:9.2f} -> {stage.t_out:.2f} °C "
            f"(등엔트로피 {stage.t_out_isentropic:.2f}°C)")
        add(f"      단열 헤드        : {stage.dh_isentropic:9.3f} kJ/kg "
            f"(실제 {stage.dh_actual:.3f}, η_is {stage.eta_isentropic:.3f})")
        add(f"      질량/체적 유량   : {stage.mass_flow:9.4f} kg/s, "
            f"{stage.volume_flow_m3h:.1f} m3/h")
        add(f"      축동력           : {stage.power:9.2f} kW")

    add("")
    add("[ 종합 성능 ]")
    add(f"  총 압축비       : {res.total_pressure_ratio:8.3f}")
    add(f"  냉매 유량       : 증발기 {res.mass_flow_evap:.4f} kg/s, "
        f"응축기 {res.mass_flow_total:.4f} kg/s")
    add(f"  1단 흡입 체적유량: {res.volume_flow_m3h:7.1f} m3/h")
    add(f"  응축 열량 Qc    : {res.qc:8.2f} kW")
    add(f"  총 축동력       : {res.shaft_power:8.2f} kW")
    add(f"  총 입력전력     : {res.input_power:8.2f} kW "
        f"(wire-to-shaft {inp.eta_wire_to_shaft:.3f})")
    add(f"  COP (축동력)    : {res.cop:8.3f}")
    add(f"  COP (입력전력)  : {res.cop_input:8.3f}   ({res.kw_per_rt:.4f} kW/RT)")
    err = res.energy_balance_error
    mark = "" if abs(err) < 0.5 else "   <- 확인 필요"
    add(f"  에너지 수지 오차: {err:8.3f} %   (Qc - Qe - W){mark}")

    if res.max_condition is not None:
        mc = res.max_condition
        add("")
        add(f"[ 최대 조건 (응축 {mc.t_cond:.1f}°C) ]")
        add(f"  최대 응축압력   : {mc.p_cond:8.2f} kPa (압축비 {mc.pressure_ratio:.3f})")
        add(f"  최대 토출온도   : {mc.t_discharge:8.2f} °C")
        add(f"  최대 축동력     : {mc.shaft_power:8.2f} kW")
        add(f"  최대 입력전력   : {mc.input_power:8.2f} kW")

    add(LINE)
    return "\n".join(out)


def format_hx(results: list[HXResult]) -> str:
    """열교환기 2차측 결과."""
    out = ["", "[ 열교환기 2차측 ]"]
    for r in results:
        out.append(f"  - {r.name}")
        out.append(f"      열량             : {r.duty:9.2f} kW")
        out.append(f"      2차측 온도       : {r.t_in:9.2f} -> {r.t_out:.2f} °C "
                   f"(Δ{r.delta_t:.2f}K)")
        out.append(f"      유량             : {r.volume_flow_m3h:9.2f} m3/h "
                   f"({r.mass_flow:.2f} kg/s)")
        out.append(f"      온도차 입구/출구 : {r.td_in:9.2f} / {r.td_out:.2f} K")
        out.append(f"      LMTD / UA        : {r.lmtd:9.3f} K / {r.ua:.2f} kW/K")
    return "\n".join(out)


def format_impeller(sizings: list[ImpellerSizing]) -> str:
    """임펠러 개략 설계 결과."""
    out = ["", "[ 임펠러 개략 설계 (1차 근사) ]"]
    for s in sizings:
        out.append(f"  - {s.stage_name}")
        out.append(f"      회전수 N         : {s.rpm:10.0f} rpm")
        out.append(f"      임펠러 외경 D2   : {s.diameter_mm:10.1f} mm")
        out.append(f"      선단 주속 u2     : {s.tip_speed:10.1f} m/s "
                   f"(마하수 {s.tip_mach:.3f})")
        out.append(f"      흡입구 외경 D_eye: {s.eye_diameter_mm:10.1f} mm")
        out.append(f"      헤드/일 계수     : psi {s.head_coefficient:.3f} / "
                   f"lambda {s.work_coefficient:.3f}")
        out.append(f"      비속도 / 비직경  : Ns {s.specific_speed:.3f} / "
                   f"Ds {s.specific_diameter:.3f}")
        out.append(f"      유량계수 phi     : {s.flow_coefficient:10.4f}")
        for w in s.warnings:
            out.append(f"      ! {w}")
    return "\n".join(out)


def format_iplv(res: IplvResult) -> str:
    """IPLV 결과 표."""
    out = ["", f"[ IPLV — {'공랭' if res.medium == 'air' else '수냉'} 기준 ]"]
    out.append(f"  {'부하':>6} {'냉각입구':>9} {'응축온도':>9} {'능력[kW]':>10} "
               f"{'입력[kW]':>10} {'COP':>7} {'kW/RT':>8}")
    out.append("  " + THIN[:64])
    for p in res.points:
        out.append(
            f"  {p.load * 100:5.0f}% {p.condition.medium_in:9.1f} "
            f"{p.condition.t_cond:9.1f} {p.result.qe:10.1f} "
            f"{p.result.input_power:10.2f} {p.cop:7.3f} {p.kw_per_rt:8.4f}"
        )
    out.append("  " + THIN[:64])
    out.append(f"  IPLV : COP {res.iplv_cop:.3f} / {res.iplv_kw_per_rt:.4f} kW/RT")
    return "\n".join(out)


# ==========================================================================
# plot.py
# ==========================================================================

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.figure import Figure

# 색은 dataviz 기준 팔레트의 categorical 1·2번 슬롯을 쓴다 (CVD 검증 통과).
COLOR_CYCLE = "#2a78d6"     # 사이클 경로
COLOR_COMPRESSION = "#eb6834"  # 압축 구간
COLOR_DOME_LIGHT = "#b8b7b0"   # 포화선 (배경 참조선이라 무채색)
COLOR_TEXT = "#52514e"
COLOR_SURFACE = "#fcfcfb"

#: 윈도우/맥/리눅스에서 흔한 한글 폰트 후보
KOREAN_FONTS = (
    "Malgun Gothic",        # 윈도우
    "AppleGothic",          # 맥
    "Apple SD Gothic Neo",  # 맥
    "NanumGothic",
    "Noto Sans CJK KR",
    "Noto Sans KR",
)

#: 한글 폰트가 없을 때 쓰는 영문 라벨
LABELS = {
    "saturation": ("포화선 (saturation)", "Saturation"),
    "cycle": ("사이클 경로", "Cycle"),
    "compression": ("압축", "compression"),
    "stage1": ("1단", "1st stage"),
    "stage2": ("2단", "2nd stage"),
}


def setup_korean_font() -> bool:
    """한글이 깨지지 않게 폰트를 잡아준다. 잡았으면 True.

    설치된 한글 폰트가 없으면 그대로 두고 False 를 돌려준다.
    (그 경우 그래프 글자는 영문으로 나간다)
    """
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return True
    return False


def saturation_dome(
    refrigerant: str, points: int = 120
) -> tuple[list[float], list[float], list[float], list[float]]:
    """포화액·포화증기 선을 (h, P) 로 돌려준다.

    반환: (h_liquid, p_liquid, h_vapor, p_vapor)
    """
    t_max = props.t_crit(refrigerant) - 0.5
    t_min = max(-80.0, t_max - 160.0)
    step = (t_max - t_min) / (points - 1)

    hl: list[float] = []
    pl: list[float] = []
    hv: list[float] = []
    pv: list[float] = []
    for i in range(points):
        t = t_min + i * step
        try:
            p = props.p_sat(refrigerant, t, q=1)
            hl.append(props.h_sat(refrigerant, t, 0))
            pl.append(p)
            hv.append(props.h_sat(refrigerant, t, 1))
            pv.append(p)
        except Exception:  # 임계점 근처에서는 계산이 안 될 수 있다
            continue
    return hl, pl, hv, pv


def _cycle_path(res: CycleResult) -> tuple[list[float], list[float]]:
    """상태점을 순서대로 이어 닫힌 경로를 만든다."""
    h = [s.h for s in res.states]
    p = [s.p for s in res.states]
    return h + h[:1], p + p[:1]


def ph_diagram(
    res: CycleResult,
    figsize: tuple[float, float] = (8.0, 6.0),
    title: Optional[str] = None,
) -> "Figure":
    """사이클을 P-h 선도 위에 그린다."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - 안내용
        raise SystemExit(
            "P-h 선도를 그리려면 matplotlib 이 필요하다: pip install matplotlib"
        ) from exc

    korean = setup_korean_font()

    def label(key: str) -> str:
        ko, en = LABELS[key]
        return ko if korean else en

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)

    hl, pl, hv, pv = saturation_dome(res.refrigerant)
    ax.plot(hl, pl, color=COLOR_DOME_LIGHT, linewidth=2, zorder=1)
    ax.plot(hv, pv, color=COLOR_DOME_LIGHT, linewidth=2, zorder=1,
            label=label("saturation"))

    h, p = _cycle_path(res)
    ax.plot(h, p, color=COLOR_CYCLE, linewidth=2, zorder=3, label=label("cycle"))

    # 압축 구간만 따로 강조한다 (터보 압축기 설계에서 제일 관심 있는 부분)
    first = res.stage_results[0]
    for stage, (a, b) in zip(res.stage_results, _compression_segments(res)):
        ax.plot(
            [res.state(a).h, res.state(b).h],
            [res.state(a).p, res.state(b).p],
            color=COLOR_COMPRESSION,
            linewidth=3,
            zorder=4,
            solid_capstyle="round",
            label=label("compression").capitalize() if stage is first else None,
        )

    for s, offset in zip(res.states, _label_offsets(res)):
        ax.plot(s.h, s.p, "o", color=COLOR_CYCLE, markersize=8,
                markeredgecolor=COLOR_SURFACE, markeredgewidth=2, zorder=5)
        ax.annotate(
            str(s.no),
            (s.h, s.p),
            textcoords="offset points",
            xytext=offset,
            fontsize=10,
            fontweight="bold",
            color=COLOR_TEXT,
            zorder=6,
        )

    ax.set_yscale("log")
    ax.set_xlabel("Enthalpy  h [kJ/kg]", color=COLOR_TEXT)
    ax.set_ylabel("Pressure  P [kPa]", color=COLOR_TEXT)
    ax.set_title(
        title or f"{res.refrigerant}  |  {res.stages}-stage  |  COP {res.cop:.2f}",
        color=COLOR_TEXT,
    )
    ax.grid(True, which="both", color="#e5e4df", linewidth=0.8, zorder=0)
    ax.tick_params(colors=COLOR_TEXT)
    for spine in ax.spines.values():
        spine.set_color("#d8d7d1")
    ax.legend(frameon=False, labelcolor=COLOR_TEXT, loc="best")

    # 사이클이 화면 가운데 오게 여유를 둔다
    hmin, hmax = min(h), max(h)
    margin = (hmax - hmin) * 0.35
    ax.set_xlim(hmin - margin, hmax + margin)
    pmin, pmax = min(p), max(p)
    ax.set_ylim(pmin * 0.55, pmax * 1.9)

    fig.tight_layout()
    return fig


def _label_offsets(res: CycleResult) -> list[tuple[float, float]]:
    """상태점 번호가 서로 겹치지 않게 라벨 위치를 흩어 놓는다.

    P-h 선도에서는 1-9 번(증발기 출구/압축기 흡입)이나 2-3 번(혼합 전후)처럼
    거의 같은 자리에 오는 점들이 있어서, 가까운 점끼리는 위아래로 나눠 찍는다.
    """
    h_span = max(s.h for s in res.states) - min(s.h for s in res.states) or 1.0
    import math as _math

    p_span = _math.log10(
        max(s.p for s in res.states) / min(s.p for s in res.states)
    ) or 1.0

    offsets: list[tuple[float, float]] = []
    placed: list[tuple[float, float]] = []   # 정규화 좌표
    for s in res.states:
        x = s.h / h_span
        y = _math.log10(s.p) / p_span
        crowded = sum(
            1
            for px, py in placed
            if abs(px - x) < 0.02 and abs(py - y) < 0.02
        )
        # 붐비는 자리면 위/아래/오른쪽으로 번갈아 밀어낸다
        offsets.append([(8, 6), (8, -14), (-16, 6), (-16, -14)][crowded % 4])
        placed.append((x, y))
    return offsets


def _compression_segments(res: CycleResult) -> Sequence[tuple[int, int]]:
    """각 단의 압축 구간 상태점 번호."""
    if res.stages == 1:
        return ((1, 2),)
    return ((1, 2), (3, 4))


def save_ph_diagram(res: CycleResult, path: str, **kwargs) -> str:
    """P-h 선도를 파일로 저장한다."""
    fig = ph_diagram(res, **kwargs)
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    return path


# ==========================================================================
# app.py — streamlit 화면
# ==========================================================================

import pandas as pd
import streamlit as st




REFRIGERANTS = [
    "R1234ze(E)",
    "R134a",
    "R1234yf",
    "R513A.mix",
    "R1233zd(E)",
    "R245fa",
    "R1336mzz(Z)",
]


# ---------------------------------------------------------------------------
# 입력 (왼쪽 사이드바)
# ---------------------------------------------------------------------------

def read_inputs() -> tuple[CycleInput, int, dict]:
    sb = st.sidebar
    sb.title("입력 조건")

    sb.subheader("기본 사양")
    stages = sb.radio("압축 단수", (2, 1), format_func=lambda n: f"{n}단 압축")
    refrigerant = sb.selectbox("냉매", REFRIGERANTS)
    capacity = sb.number_input("냉동능력 [RT]", 10.0, 2000.0, 150.0, step=10.0)

    sb.subheader("증발기 (냉수)")
    cw_in = sb.number_input("냉수 입구온도 [°C]", 0.0, 30.0, 12.0, step=0.1)
    cw_out = sb.number_input("냉수 출구온도 [°C]", -5.0, 25.0, 7.0, step=0.1)
    evap_app = sb.number_input("증발기 approach [K]", 0.1, 10.0, 1.0, step=0.1)
    superheat = sb.number_input("과열도 [K]", 0.0, 15.0, 1.0, step=0.1)

    sb.subheader("응축기")
    medium_in = sb.number_input("냉각 공기/물 입구온도 [°C]", 0.0, 55.0, 35.0, step=0.5)
    cond_app = sb.number_input("응축기 approach [K]", 0.5, 25.0, 15.0, step=0.5)
    subcool = sb.number_input("과냉도 [K]", 0.0, 15.0, 3.0, step=0.1)

    sb.subheader("압축기")
    eta1 = sb.slider("1단 단열효율", 0.40, 0.95, 0.80, step=0.01)
    eta2 = sb.slider("2단 단열효율", 0.40, 0.95, 0.80, step=0.01) if stages == 2 else eta1
    eta_wts = sb.slider("wire-to-shaft 효율", 0.70, 1.00, 0.89, step=0.01)

    dp_s = sb.number_input("흡입관 압력손실 [kPa]", 0.0, 50.0, 3.0, step=0.5)
    dp_d = sb.number_input("토출관 압력손실 [kPa]", 0.0, 50.0, 5.0, step=0.5)

    t_sub = None
    x = None
    if stages == 2:
        sb.subheader("서브콘덴서 (이코노마이저)")
        auto_p = sb.checkbox(
            "중간압 자동 (√(P1·P2))", value=True,
            help="끄면 서브콘덴서 온도를 직접 지정한다",
        )
        if not auto_p:
            t_sub = sb.number_input("서브콘덴서 온도 [°C]", -10.0, 60.0, 32.0, step=0.5)
        auto_x = sb.checkbox(
            "중간단 유량비 자동 (에너지 밸런스)", value=True,
            help="끄면 유량비를 직접 지정한다 (원본 엑셀 방식)",
        )
        if not auto_x:
            x = sb.number_input("중간단 유량비 x", 0.0, 1.0, 0.20, step=0.01)

    sb.subheader("최대 운전조건")
    t_cond_max = sb.number_input("최대 응축온도 [°C]", 40.0, 100.0, 70.0, step=1.0)

    sb.subheader("추가 계산")
    opts = {
        "hx": sb.checkbox("열교환기 2차측 (LMTD / UA)", value=True),
        "impeller": sb.checkbox("임펠러 개략 치수", value=True),
        "iplv": sb.checkbox("IPLV (부분부하 효율)", value=False),
        "psi": sb.slider("임펠러 압력계수 ψ", 0.40, 0.75, 0.60, step=0.01),
        "ns": sb.slider("임펠러 비속도 Ns", 0.40, 1.00, 0.70, step=0.01),
        "medium": sb.selectbox("IPLV 기준", ("air", "water"),
                               format_func=lambda m: "공랭" if m == "air" else "수냉"),
    }

    excel_compat = sb.checkbox(
        "엑셀 호환 모드", value=False,
        help="원본 엑셀과 똑같이 계산한다 (온도 혼합 + 응축열량을 1단 유량으로)",
    )

    inp = CycleInput(
        refrigerant=refrigerant,
        capacity_rt=capacity,
        chilled_water_in=cw_in,
        chilled_water_out=cw_out,
        evap_approach=evap_app,
        superheat=superheat,
        cooling_medium_in=medium_in,
        cond_approach=cond_app,
        subcool=subcool,
        dp_suction=dp_s,
        dp_discharge=dp_d,
        eta_is_stage1=eta1,
        eta_is_stage2=eta2,
        eta_wire_to_shaft=eta_wts,
        t_subcond=t_sub,
        subcond_mass_ratio=x,
        t_cond_max=t_cond_max,
        eta_is_max=eta1,
        compat=ExcelCompat(
            temperature_mixing=excel_compat,
            condenser_duty_first_stage_flow=excel_compat,
        ),
    )
    return inp, stages, opts


# ---------------------------------------------------------------------------
# 결과 표시
# ---------------------------------------------------------------------------

def show_summary(res) -> None:
    c = st.columns(4)
    c[0].metric("COP (입력전력 기준)", f"{res.cop_input:.3f}")
    c[1].metric("소비전력", f"{res.input_power:.1f} kW")
    c[2].metric("냉동톤당 전력", f"{res.kw_per_rt:.4f} kW/RT")
    c[3].metric("총 압축비", f"{res.total_pressure_ratio:.3f}")

    c = st.columns(4)
    c[0].metric("증발온도", f"{res.inp.te:.2f} °C")
    c[1].metric("응축온도", f"{res.inp.tc:.2f} °C")
    c[2].metric("냉매 유량 (증발기)", f"{res.mass_flow_evap:.3f} kg/s")
    c[3].metric("1단 흡입 체적유량", f"{res.volume_flow_m3h:.0f} m³/h")

    err = res.energy_balance_error
    if abs(err) >= 0.5:
        st.warning(
            f"에너지 수지 오차 {err:+.2f} % — 이코노마이저 유량비를 손으로 지정했거나 "
            "배관 손실이 큰 경우다. '중간단 유량비 자동'을 켜면 수지가 맞는다."
        )


def states_table(res) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "No": s.no,
                "위치": s.name,
                "온도 [°C]": round(s.t, 2),
                "압력 [kPa]": round(s.p, 2),
                "엔탈피 [kJ/kg]": round(s.h, 2),
                "밀도 [kg/m³]": round(s.d, 2) if s.d is not None else None,
                "엔트로피 [kJ/kg·K]": round(s.s, 4) if s.s is not None else None,
            }
            for s in res.states
        ]
    )


def stages_table(res) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "단": stage.name,
                "흡입압력 [kPa]": round(stage.p_in, 2),
                "토출압력 [kPa]": round(stage.p_out, 2),
                "압축비": round(stage.pressure_ratio, 3),
                "흡입온도 [°C]": round(stage.t_in, 2),
                "토출온도 [°C]": round(stage.t_out, 2),
                "단열헤드 [kJ/kg]": round(stage.dh_isentropic, 3),
                "실제헤드 [kJ/kg]": round(stage.dh_actual, 3),
                "유량 [kg/s]": round(stage.mass_flow, 4),
                "흡입체적 [m³/h]": round(stage.volume_flow_m3h, 1),
                "축동력 [kW]": round(stage.power, 2),
            }
            for stage in res.stage_results
        ]
    )


def main() -> None:
    st.set_page_config(
        page_title="터보 냉동기 사이클 해석", page_icon="❄", layout="wide"
    )
    st.title("❄ 터보 냉동기 사이클 해석")
    st.caption(
        "원본 엑셀(150RT_Cycle_Analysis)의 계산을 그대로 옮기고, "
        "이코노마이저 에너지 밸런스와 임펠러 개략 설계를 더했다."
    )

    inp, stages, opts = read_inputs()

    try:
        res = solve(inp, stages=stages)
    except (ValueError, RuntimeError) as exc:
        st.error(f"계산할 수 없는 조건이다.\n\n{exc}")
        st.stop()

    show_summary(res)

    tabs = st.tabs(["P-h 선도", "상태점", "압축기", "열교환기", "임펠러", "IPLV"])

    with tabs[0]:
        st.pyplot(ph_diagram(res, figsize=(9, 6.5)))
        st.caption(
            "가로축 엔탈피, 세로축 압력(로그). 회색은 포화선, 주황색이 압축 구간이다."
        )

    with tabs[1]:
        st.dataframe(states_table(res), width="stretch", hide_index=True)
        buf = io.StringIO()
        states_table(res).to_csv(buf, index=False)
        st.download_button(
            "상태점 CSV 내려받기", buf.getvalue(),
            file_name="상태점.csv", mime="text/csv",
        )

    with tabs[2]:
        st.dataframe(stages_table(res), width="stretch", hide_index=True)
        mc = res.max_condition
        if mc is not None:
            st.subheader(f"최대 조건 (응축 {mc.t_cond:.0f}°C)")
            c = st.columns(4)
            c[0].metric("최대 응축압력", f"{mc.p_cond:.0f} kPa")
            c[1].metric("최대 토출온도", f"{mc.t_discharge:.1f} °C")
            c[2].metric("최대 압축비", f"{mc.pressure_ratio:.2f}")
            c[3].metric("최대 입력전력", f"{mc.input_power:.1f} kW")

    with tabs[3]:
        if not opts["hx"]:
            st.info("왼쪽에서 '열교환기 2차측'을 켜면 계산한다.")
        else:
            rows = []
            for hx in (
                evaporator_side(res.qe, inp.te, inp.chilled_water_in),
                condenser_side(res.qc, inp.tc, inp.cooling_medium_in),
            ):
                rows.append(
                    {
                        "열교환기": hx.name,
                        "열량 [kW]": round(hx.duty, 1),
                        "2차측 입구 [°C]": round(hx.t_in, 2),
                        "2차측 출구 [°C]": round(hx.t_out, 2),
                        "유량 [m³/h]": round(hx.volume_flow_m3h, 1),
                        "온도차 입구 [K]": round(hx.td_in, 2),
                        "온도차 출구 [K]": round(hx.td_out, 2),
                        "LMTD [K]": round(hx.lmtd, 3),
                        "UA [kW/K]": round(hx.ua, 2),
                    }
                )
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with tabs[4]:
        if not opts["impeller"]:
            st.info("왼쪽에서 '임펠러 개략 치수'를 켜면 계산한다.")
        else:
            st.caption(
                "무차원수로 잡은 1차 근사다. 깃 형상·확산기·CFD 로 다시 확인해야 한다."
            )
            rows = []
            warns: list[str] = []
            for stage in res.stage_results:
                sz = size_impeller(
                    stage, inp.refrigerant,
                    head_coefficient=opts["psi"], specific_speed=opts["ns"],
                )
                rows.append(
                    {
                        "단": sz.stage_name,
                        "회전수 [rpm]": round(sz.rpm),
                        "임펠러 외경 [mm]": round(sz.diameter_mm, 1),
                        "선단 주속 [m/s]": round(sz.tip_speed, 1),
                        "선단 마하수": round(sz.tip_mach, 3),
                        "흡입구 외경 [mm]": round(sz.eye_diameter_mm, 1),
                        "일계수 λ": round(sz.work_coefficient, 3),
                        "유량계수 φ": round(sz.flow_coefficient, 4),
                        "비직경 Ds": round(sz.specific_diameter, 3),
                    }
                )
                warns += [f"{sz.stage_name}: {w}" for w in sz.warnings]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            for w in warns:
                st.warning(w)

    with tabs[5]:
        if not opts["iplv"]:
            st.info("왼쪽에서 'IPLV'를 켜면 계산한다. (부하점 4개를 다시 풀어서 조금 걸린다)")
        else:
            try:
                r = iplv(inp, stages=stages, medium=opts["medium"])
            except (ValueError, RuntimeError) as exc:
                st.error(f"IPLV 계산 실패: {exc}")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "부하 [%]": round(p.load * 100),
                                "냉각 입구 [°C]": p.condition.medium_in,
                                "응축온도 [°C]": p.condition.t_cond,
                                "능력 [kW]": round(p.result.qe, 1),
                                "입력전력 [kW]": round(p.result.input_power, 2),
                                "COP": round(p.cop, 3),
                                "kW/RT": round(p.kw_per_rt, 4),
                            }
                            for p in r.points
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
                c = st.columns(2)
                c[0].metric("IPLV (COP 기준)", f"{r.iplv_cop:.3f}")
                c[1].metric("IPLV (kW/RT 기준)", f"{r.iplv_kw_per_rt:.4f}")
                st.caption(
                    "부분부하 단열효율은 가정값이다 (standards.default_part_load_efficiency). "
                    "실측 성능곡선이 있으면 그 함수를 바꿔 쓰면 된다."
                )


# ==========================================================================
# 실행 진입점
# ==========================================================================

def _streamlit_is_running() -> bool:
    """`streamlit run` 으로 실행됐는지 확인한다."""
    try:
        from streamlit.runtime import exists

        return exists()
    except Exception:
        return False


def _print_default_report() -> None:
    """화면 없이 그냥 실행했을 때 기본 조건으로 한 번 계산해 보여준다."""
    parser = argparse.ArgumentParser(
        description="터보 냉동기 사이클 해석 (파일 하나 배포판)"
    )
    parser.add_argument("--refrigerant", default="R1234ze(E)", help="냉매")
    parser.add_argument("--capacity", type=float, default=150.0, help="냉동능력 [RT]")
    parser.add_argument("--stages", type=int, choices=(1, 2), default=2, help="압축 단수")
    parser.add_argument("--t-evap", type=float, help="증발온도 [°C]")
    parser.add_argument("--t-cond", type=float, help="응축온도 [°C]")
    args = parser.parse_args()

    inp = CycleInput(
        refrigerant=args.refrigerant,
        capacity_rt=args.capacity,
        t_evap=args.t_evap,
        t_cond=args.t_cond,
    )
    print(format_report(solve(inp, stages=args.stages)))
    print()
    print("화면으로 보시려면:  streamlit run 터보냉동기_사이클해석.py")


if __name__ == "__main__":
    if _streamlit_is_running():
        main()
    else:
        _print_default_report()

