"""터보 냉동기 사이클 해석 — 파일 하나로 합친 배포판.

이 파일 하나만 있으면 돌아간다. 폴더 구조가 필요 없다.

쓰는 법
    화면으로 보기 :  python 터보냉동기_사이클해석.py
                     (브라우저가 자동으로 열린다)
    계산만 찍기   :  python 터보냉동기_사이클해석.py --text

설치할 것은 하나뿐이다
    pip install CoolProp

화면은 파이썬에 처음부터 들어 있는 기능(http.server)으로 만들었다.
streamlit / pandas / matplotlib 이 필요 없어서, 32비트나 ARM 윈도우처럼
pyarrow 가 깔리지 않는 PC 에서도 그대로 돌아간다.

원본은 turbochiller 패키지다 (github: suoarman-cpu/COMP-TEST-DATA).
이 파일은 tools/build_single_file.py 가 자동으로 만든 것이라,
고칠 일이 있으면 원본 패키지를 고치고 다시 빌드하는 편이 좋다.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Optional

from CoolProp.CoolProp import PropsSI


# --- 모듈 별칭 -------------------------------------------------------------
# 원래는 turbochiller.props 처럼 모듈로 나뉘어 있었다.
# 한 파일로 합치면서, 코드 안의 `props.xxx` 호출이 그대로 동작하도록
# 이 파일 자신을 props 라는 이름으로도 가리키게 해 둔다.


class _SelfModule:
    """`props.h_tp(...)` 같은 호출을 이 파일 안의 같은 이름 함수로 연결한다."""

    def __getattr__(self, name: str):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(f"{name} 을(를) 찾을 수 없다") from None


props = _SelfModule()



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
# svg.py
# ==========================================================================

# 검증된 색 (light / dark 두 벌)
COLORS_LIGHT = {
    "cycle": "#2a78d6",
    "compression": "#eb6834",
    "dome": "#b8b7b0",
    "grid": "#e5e4df",
    "axis": "#d8d7d1",
    "text": "#52514e",
    "text_strong": "#0b0b0b",
    "surface": "#fcfcfb",
}
COLORS_DARK = {
    "cycle": "#3987e5",
    "compression": "#d95926",
    "dome": "#6b6a64",
    "grid": "#2c2c2a",
    "axis": "#3a3a37",
    "text": "#c3c2b7",
    "text_strong": "#ffffff",
    "surface": "#1a1a19",
}


@dataclass
class _Box:
    """그림 좌표계. 데이터 좌표를 화면 좌표로 옮긴다."""

    width: float
    height: float
    pad_left: float
    pad_right: float
    pad_top: float
    pad_bottom: float
    h_min: float
    h_max: float
    log_p_min: float
    log_p_max: float

    def x(self, h: float) -> float:
        span = self.h_max - self.h_min or 1.0
        inner = self.width - self.pad_left - self.pad_right
        return self.pad_left + (h - self.h_min) / span * inner

    def y(self, p: float) -> float:
        span = self.log_p_max - self.log_p_min or 1.0
        inner = self.height - self.pad_top - self.pad_bottom
        frac = (math.log10(max(p, 1e-6)) - self.log_p_min) / span
        return self.height - self.pad_bottom - frac * inner


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _nice_pressure_ticks(p_min: float, p_max: float) -> list[float]:
    """로그 축에 찍을 눈금 값을 고른다 (1·2·5 × 10^n)."""
    ticks: list[float] = []
    exp = math.floor(math.log10(p_min))
    while True:
        base = 10.0**exp
        for m in (1, 2, 5):
            v = m * base
            if p_min <= v <= p_max:
                ticks.append(v)
        if base > p_max:
            break
        exp += 1
    return ticks


def _nice_enthalpy_ticks(h_min: float, h_max: float, target: int = 6) -> list[float]:
    """가로축 눈금을 보기 좋은 간격으로 고른다."""
    span = h_max - h_min
    if span <= 0:
        return [h_min]
    raw = span / target
    exp = math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * 10.0**exp
        if step >= raw:
            break
    start = math.ceil(h_min / step) * step
    ticks = []
    v = start
    while v <= h_max:
        ticks.append(v)
        v += step
    return ticks


def _label_offsets(res: CycleResult, box: _Box) -> list[tuple[float, float]]:
    """상태점 번호가 겹치지 않게 흩어 놓는다."""
    offsets: list[tuple[float, float]] = []
    placed: list[tuple[float, float]] = []
    for s in res.states:
        px, py = box.x(s.h), box.y(s.p)
        crowded = sum(1 for qx, qy in placed if abs(qx - px) < 14 and abs(qy - py) < 14)
        offsets.append([(9, -7), (9, 15), (-15, -7), (-15, 15)][crowded % 4])
        placed.append((px, py))
    return offsets


def ph_diagram_svg(
    res: CycleResult,
    width: float = 720,
    height: float = 520,
    dark: bool = False,
) -> str:
    """사이클을 P-h 선도 SVG 문자열로 만든다."""
    c = COLORS_DARK if dark else COLORS_LIGHT
    fluid = res.refrigerant

    # --- 포화선 ---
    dome_liq: list[tuple[float, float]] = []
    dome_vap: list[tuple[float, float]] = []
    t_top = props.t_crit(fluid) - 0.5
    t_bot = max(-80.0, t_top - 160.0)
    steps = 100
    for i in range(steps + 1):
        t = t_bot + (t_top - t_bot) * i / steps
        try:
            p = props.p_sat(fluid, t, q=1)
            dome_liq.append((props.h_sat(fluid, t, 0), p))
            dome_vap.append((props.h_sat(fluid, t, 1), p))
        except Exception:
            continue

    cycle_pts = [(s.h, s.p) for s in res.states]
    closed = cycle_pts + cycle_pts[:1]

    # --- 표시 범위: 사이클이 가운데 오도록 여유를 준다 ---
    hs = [h for h, _ in cycle_pts]
    ps = [p for _, p in cycle_pts]
    h_margin = (max(hs) - min(hs)) * 0.30
    h_min, h_max = min(hs) - h_margin, max(hs) + h_margin
    p_min, p_max = min(ps) * 0.5, max(ps) * 2.0

    box = _Box(width, height, 74, 24, 46, 52, h_min, h_max,
               math.log10(p_min), math.log10(p_max))

    out: list[str] = []
    add = out.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="100%" role="img" aria-label="P-h 선도" '
        f'style="max-width:{width:.0f}px;font-family:system-ui,sans-serif">'
    )
    add(f'<rect width="{width}" height="{height}" fill="{c["surface"]}"/>')

    # 그래프 영역 밖으로 선이 삐져나오지 않게 잘라낸다
    plot_w = width - box.pad_left - box.pad_right
    plot_h = height - box.pad_top - box.pad_bottom
    add(
        f'<clipPath id="plot"><rect x="{box.pad_left}" y="{box.pad_top}" '
        f'width="{plot_w}" height="{plot_h}"/></clipPath>'
    )

    # --- 격자와 눈금 ---
    for p in _nice_pressure_ticks(p_min, p_max):
        y = box.y(p)
        add(f'<line x1="{box.pad_left}" y1="{y:.1f}" x2="{width - box.pad_right}" '
            f'y2="{y:.1f}" stroke="{c["grid"]}" stroke-width="1"/>')
        add(f'<text x="{box.pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{c["text"]}">{p:,.0f}</text>')
    for h in _nice_enthalpy_ticks(h_min, h_max):
        x = box.x(h)
        add(f'<line x1="{x:.1f}" y1="{box.pad_top}" x2="{x:.1f}" '
            f'y2="{height - box.pad_bottom}" stroke="{c["grid"]}" stroke-width="1"/>')
        add(f'<text x="{x:.1f}" y="{height - box.pad_bottom + 18:.1f}" '
            f'text-anchor="middle" font-size="11" fill="{c["text"]}">{h:,.0f}</text>')

    # --- 축 ---
    add(f'<line x1="{box.pad_left}" y1="{box.pad_top}" x2="{box.pad_left}" '
        f'y2="{height - box.pad_bottom}" stroke="{c["axis"]}" stroke-width="1"/>')
    add(f'<line x1="{box.pad_left}" y1="{height - box.pad_bottom}" '
        f'x2="{width - box.pad_right}" y2="{height - box.pad_bottom}" '
        f'stroke="{c["axis"]}" stroke-width="1"/>')

    add('<g clip-path="url(#plot)">')

    # --- 포화선 ---
    for pts in (dome_liq, dome_vap):
        d = _path(pts, box, h_min, h_max, p_min, p_max)
        if d:
            add(f'<path d="{d}" fill="none" stroke="{c["dome"]}" stroke-width="2" '
                f'stroke-linejoin="round"/>')

    # --- 사이클 경로 ---
    d = " ".join(
        ("M" if i == 0 else "L") + f"{box.x(h):.1f},{box.y(p):.1f}"
        for i, (h, p) in enumerate(closed)
    )
    add(f'<path d="{d}" fill="none" stroke="{c["cycle"]}" stroke-width="2" '
        f'stroke-linejoin="round"/>')

    # --- 압축 구간 강조 ---
    segments = ((1, 2),) if res.stages == 1 else ((1, 2), (3, 4))
    for a, b in segments:
        sa, sb = res.state(a), res.state(b)
        add(f'<line x1="{box.x(sa.h):.1f}" y1="{box.y(sa.p):.1f}" '
            f'x2="{box.x(sb.h):.1f}" y2="{box.y(sb.p):.1f}" '
            f'stroke="{c["compression"]}" stroke-width="3.5" stroke-linecap="round"/>')

    add('</g>')

    # --- 상태점 ---
    for s, (dx, dy) in zip(res.states, _label_offsets(res, box)):
        px, py = box.x(s.h), box.y(s.p)
        add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{c["cycle"]}" '
            f'stroke="{c["surface"]}" stroke-width="2"/>')
        add(f'<title>{_esc(f"{s.no}. {s.name} — {s.t:.2f}°C, {s.p:.1f} kPa, {s.h:.2f} kJ/kg")}</title>')
        add(f'<text x="{px + dx:.1f}" y="{py + dy:.1f}" font-size="12" '
            f'font-weight="600" fill="{c["text_strong"]}">{s.no}</text>')

    # --- 축 제목과 범례 ---
    add(f'<text x="{width / 2:.0f}" y="{height - 8:.0f}" text-anchor="middle" '
        f'font-size="12" fill="{c["text"]}">엔탈피 h [kJ/kg]</text>')
    add(f'<text x="16" y="{height / 2:.0f}" text-anchor="middle" font-size="12" '
        f'fill="{c["text"]}" transform="rotate(-90 16 {height / 2:.0f})">'
        f'압력 P [kPa] (로그)</text>')
    add(f'<text x="{box.pad_left}" y="24" font-size="13" font-weight="600" '
        f'fill="{c["text_strong"]}">{_esc(fluid)} · {res.stages}단 · COP {res.cop:.2f}</text>')

    lx, ly = width - box.pad_right - 150, box.pad_top + 14
    for i, (color, name) in enumerate(
        ((c["dome"], "포화선"), (c["cycle"], "사이클"), (c["compression"], "압축"))
    ):
        y = ly + i * 17
        add(f'<line x1="{lx}" y1="{y}" x2="{lx + 22}" y2="{y}" stroke="{color}" '
            f'stroke-width="3" stroke-linecap="round"/>')
        add(f'<text x="{lx + 28}" y="{y + 4}" font-size="11" fill="{c["text"]}">'
            f'{name}</text>')

    add("</svg>")
    return "".join(out)


def _path(
    pts: list[tuple[float, float]],
    box: _Box,
    h_min: float,
    h_max: float,
    p_min: float,
    p_max: float,
) -> str:
    """보이는 범위 안의 점들만 이어 경로를 만든다."""
    d: list[str] = []
    pen_down = False
    for h, p in pts:
        visible = (h_min - 200 <= h <= h_max + 200) and (p_min * 0.2 <= p <= p_max * 5)
        if not visible:
            pen_down = False
            continue
        cmd = "L" if pen_down else "M"
        d.append(f"{cmd}{box.x(h):.1f},{box.y(p):.1f}")
        pen_down = True
    return " ".join(d)


# ==========================================================================
# webui.py
# ==========================================================================

import html as html_mod
import socket
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REFRIGERANTS = [
    "R1234ze(E)",
    "R134a",
    "R1234yf",
    "R513A.mix",
    "R1233zd(E)",
    "R245fa",
    "R1336mzz(Z)",
]


@dataclass
class Field:
    """입력 칸 하나의 정의."""

    key: str
    label: str
    default: Any
    kind: str = "number"          # number | select | check
    step: str = "0.1"
    choices: tuple = ()
    group: str = ""
    hint: str = ""


FIELDS: tuple[Field, ...] = (
    Field("stages", "압축 단수", 2, "select", choices=((2, "2단 압축"), (1, "1단 압축")),
          group="기본 사양"),
    Field("refrigerant", "냉매", "R1234ze(E)", "select",
          choices=tuple((r, r) for r in REFRIGERANTS), group="기본 사양"),
    Field("capacity_rt", "냉동능력 [RT]", 150.0, step="1", group="기본 사양"),

    Field("chilled_water_in", "냉수 입구온도 [°C]", 12.0, group="증발기 (냉수)"),
    Field("chilled_water_out", "냉수 출구온도 [°C]", 7.0, group="증발기 (냉수)"),
    Field("evap_approach", "증발기 approach [K]", 1.0, group="증발기 (냉수)"),
    Field("superheat", "과열도 [K]", 1.0, group="증발기 (냉수)"),

    Field("cooling_medium_in", "냉각 공기/물 입구온도 [°C]", 35.0, step="0.5",
          group="응축기"),
    Field("cond_approach", "응축기 approach [K]", 15.0, step="0.5", group="응축기"),
    Field("subcool", "과냉도 [K]", 3.0, group="응축기"),

    Field("eta_is_stage1", "1단 단열효율", 0.80, step="0.01", group="압축기"),
    Field("eta_is_stage2", "2단 단열효율", 0.80, step="0.01", group="압축기"),
    Field("eta_wire_to_shaft", "wire-to-shaft 효율", 0.89, step="0.01", group="압축기"),
    Field("dp_suction", "흡입관 압력손실 [kPa]", 3.0, step="0.5", group="압축기"),
    Field("dp_discharge", "토출관 압력손실 [kPa]", 5.0, step="0.5", group="압축기"),

    Field("t_subcond", "서브콘덴서 온도 [°C]", "", step="0.5", group="서브콘덴서",
          hint="비워두면 중간압을 √(P1·P2) 로 자동"),
    Field("subcond_mass_ratio", "중간단 유량비 x", "", step="0.01", group="서브콘덴서",
          hint="비워두면 에너지 밸런스로 계산"),

    Field("t_cond_max", "최대 응축온도 [°C]", 70.0, step="1", group="기타"),
    Field("psi", "임펠러 압력계수 ψ", 0.60, step="0.01", group="기타"),
    Field("specific_speed", "임펠러 비속도 Ns", 0.70, step="0.01", group="기타"),
    Field("excel_compat", "엑셀 호환 모드", False, "check", group="기타",
          hint="원본 엑셀과 똑같이 계산"),
    Field("show_iplv", "IPLV 계산 (조금 느림)", False, "check", group="기타"),
)

FIELD_BY_KEY = {f.key: f for f in FIELDS}


# ---------------------------------------------------------------------------
# 입력 해석
# ---------------------------------------------------------------------------

def parse_query(query: dict[str, list[str]]) -> dict[str, Any]:
    """주소창의 값들을 읽어 필드 값 사전으로 만든다."""
    values: dict[str, Any] = {}
    first_visit = not query

    for f in FIELDS:
        raw = query.get(f.key, [None])[0]

        if f.kind == "check":
            # 체크박스는 꺼져 있으면 아예 전송되지 않는다
            values[f.key] = f.default if first_visit else (raw is not None)
            continue

        if raw is None or raw == "":
            values[f.key] = f.default if first_visit else ("" if f.default == "" else f.default)
            if raw == "":
                values[f.key] = ""
            continue

        if f.kind == "select":
            values[f.key] = int(raw) if f.key == "stages" else raw
        else:
            try:
                values[f.key] = float(raw)
            except ValueError:
                values[f.key] = f.default
    return values


def build_input(values: dict[str, Any]) -> tuple[CycleInput, int]:
    """필드 값으로 CycleInput 을 만든다."""

    def num(key: str) -> float:
        v = values.get(key, FIELD_BY_KEY[key].default)
        return float(v) if v != "" else float(FIELD_BY_KEY[key].default)

    def opt(key: str) -> Optional[float]:
        v = values.get(key, "")
        return None if v == "" or v is None else float(v)

    compat = bool(values.get("excel_compat"))
    inp = CycleInput(
        refrigerant=str(values.get("refrigerant", "R1234ze(E)")),
        capacity_rt=num("capacity_rt"),
        chilled_water_in=num("chilled_water_in"),
        chilled_water_out=num("chilled_water_out"),
        evap_approach=num("evap_approach"),
        superheat=num("superheat"),
        cooling_medium_in=num("cooling_medium_in"),
        cond_approach=num("cond_approach"),
        subcool=num("subcool"),
        dp_suction=num("dp_suction"),
        dp_discharge=num("dp_discharge"),
        eta_is_stage1=num("eta_is_stage1"),
        eta_is_stage2=num("eta_is_stage2"),
        eta_wire_to_shaft=num("eta_wire_to_shaft"),
        t_subcond=opt("t_subcond"),
        subcond_mass_ratio=opt("subcond_mass_ratio"),
        t_cond_max=num("t_cond_max"),
        eta_is_max=num("eta_is_stage1"),
        compat=ExcelCompat(
            temperature_mixing=compat, condenser_duty_first_stage_flow=compat
        ),
    )
    return inp, int(values.get("stages", 2))


# ---------------------------------------------------------------------------
# HTML 만들기
# ---------------------------------------------------------------------------

def esc(text: Any) -> str:
    return html_mod.escape(str(text), quote=True)


STYLE = """
:root{
  color-scheme: light dark;
  --bg:#f6f6f4; --panel:#fcfcfb; --line:#e0dfd9;
  --ink:#0b0b0b; --ink2:#52514e; --ink3:#86857e;
  --accent:#2a78d6; --warn:#eb6834; --ok:#1baf7a;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#121211; --panel:#1a1a19; --line:#2f2f2c;
         --ink:#ffffff; --ink2:#c3c2b7; --ink3:#8b8a82; --accent:#3987e5; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;
     font-size:14px;line-height:1.55}
.wrap{display:flex;gap:18px;align-items:flex-start;padding:18px;max-width:1500px;margin:0 auto}
aside{flex:0 0 288px;position:sticky;top:18px}
main{flex:1;min-width:0}
h1{font-size:21px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 16px;font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
      padding:16px;margin-bottom:16px}
fieldset{border:0;padding:0;margin:0 0 14px}
legend{font-weight:700;font-size:12px;color:var(--ink2);padding:0 0 6px;
       text-transform:none;letter-spacing:.02em}
label{display:block;margin-bottom:9px}
label .t{display:block;font-size:12px;color:var(--ink2);margin-bottom:3px}
label .hint{display:block;font-size:11px;color:var(--ink3);margin-top:2px}
input[type=number],select{width:100%;padding:7px 9px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--ink);font-size:14px;
  font-family:inherit}
input[type=checkbox]{margin-right:6px;vertical-align:-1px}
button{width:100%;padding:11px;border:0;border-radius:9px;background:var(--accent);
  color:#fff;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}
button:hover{filter:brightness(1.07)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.metric .k{font-size:12px;color:var(--ink2)}
.metric .v{font-size:25px;font-weight:700;letter-spacing:-.02em}
.metric .u{font-size:14px;font-weight:600;color:var(--ink2);margin-left:3px}
h2{font-size:15px;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 9px;text-align:right;border-bottom:1px solid var(--line);
      font-variant-numeric:tabular-nums}
th{color:var(--ink2);font-weight:600;font-size:12px;white-space:nowrap}
td:nth-child(2),th:nth-child(2){text-align:left}
tbody tr:last-child td{border-bottom:0}
.msg{padding:12px 14px;border-radius:9px;margin-bottom:14px;font-size:13px}
.msg.err{background:#fdecea;color:#8a1d18;border:1px solid #f5c2bd}
.msg.warn{background:#fdf2e6;color:#7a3c12;border:1px solid #f3d3b0}
@media (prefers-color-scheme: dark){
  .msg.err{background:#3a1512;color:#ffb3ab;border-color:#5e241e}
  .msg.warn{background:#38230f;color:#ffca92;border-color:#5b3a1a}
}
.note{color:var(--ink3);font-size:12px;margin-top:8px}
@media (max-width:900px){
  .wrap{flex-direction:column}
  aside{position:static;flex:1 1 auto;width:100%}
}
"""


def render_form(values: dict[str, Any]) -> str:
    out = ['<form method="get" action="/">']
    groups: list[str] = []
    for f in FIELDS:
        if f.group not in groups:
            groups.append(f.group)

    for group in groups:
        out.append(f"<fieldset><legend>{esc(group)}</legend>")
        for f in (x for x in FIELDS if x.group == group):
            v = values.get(f.key, f.default)
            hint = f'<span class="hint">{esc(f.hint)}</span>' if f.hint else ""
            if f.kind == "check":
                checked = " checked" if v else ""
                out.append(
                    f'<label><input type="checkbox" name="{f.key}" value="1"{checked}>'
                    f'{esc(f.label)}{hint}</label>'
                )
            elif f.kind == "select":
                opts = "".join(
                    f'<option value="{esc(cv)}"'
                    f'{" selected" if str(cv) == str(v) else ""}>{esc(cl)}</option>'
                    for cv, cl in f.choices
                )
                out.append(
                    f'<label><span class="t">{esc(f.label)}</span>'
                    f'<select name="{f.key}">{opts}</select>{hint}</label>'
                )
            else:
                out.append(
                    f'<label><span class="t">{esc(f.label)}</span>'
                    f'<input type="number" step="{f.step}" name="{f.key}" '
                    f'value="{esc(v)}">{hint}</label>'
                )
        out.append("</fieldset>")

    out.append("<button type=\"submit\">다시 계산</button></form>")
    return "".join(out)


def _metric(key: str, value: str, unit: str = "") -> str:
    u = f'<span class="u">{esc(unit)}</span>' if unit else ""
    return (
        f'<div class="metric"><div class="k">{esc(key)}</div>'
        f'<div class="v">{esc(value)}{u}</div></div>'
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_results(res: CycleResult, values: dict[str, Any]) -> str:
    inp = res.inp
    out: list[str] = []

    out.append('<div class="card"><div class="metrics">')
    out.append(_metric("COP (입력전력 기준)", f"{res.cop_input:.3f}"))
    out.append(_metric("소비전력", f"{res.input_power:.1f}", " kW"))
    out.append(_metric("냉동톤당 전력", f"{res.kw_per_rt:.4f}", " kW/RT"))
    out.append(_metric("총 압축비", f"{res.total_pressure_ratio:.3f}"))
    out.append(_metric("증발온도", f"{inp.te:.2f}", " °C"))
    out.append(_metric("응축온도", f"{inp.tc:.2f}", " °C"))
    out.append(_metric("냉매 유량", f"{res.mass_flow_evap:.3f}", " kg/s"))
    out.append(_metric("1단 흡입 체적유량", f"{res.volume_flow_m3h:.0f}", " m³/h"))
    out.append("</div>")

    err = res.energy_balance_error
    if abs(err) >= 0.5:
        out.append(
            f'<div class="msg warn" style="margin-top:14px">'
            f"에너지 수지 오차 {err:+.2f} % — 이코노마이저 유량비를 직접 넣었거나 "
            f"배관 손실이 큽니다. '중간단 유량비 x' 를 비워두면 수지가 맞습니다.</div>"
        )
    out.append("</div>")

    # P-h 선도
    out.append('<div class="card"><h2>P-h 선도</h2>')
    out.append(ph_diagram_svg(res, width=760, height=520))
    out.append(
        '<p class="note">점 위에 마우스를 올리면 상태점 값이 보입니다. '
        "주황색이 압축 구간입니다.</p></div>"
    )

    # 상태점
    out.append('<div class="card"><h2>상태점</h2>')
    out.append(_table(
        ["No", "위치", "온도 [°C]", "압력 [kPa]", "엔탈피 [kJ/kg]", "밀도 [kg/m³]"],
        [
            [
                s.no, s.name, f"{s.t:.2f}", f"{s.p:.2f}", f"{s.h:.2f}",
                f"{s.d:.2f}" if s.d is not None else "-",
            ]
            for s in res.states
        ],
    ))
    out.append("</div>")

    # 압축기
    out.append('<div class="card"><h2>압축기</h2>')
    out.append(_table(
        ["단", "압축비", "흡입 [°C]", "토출 [°C]", "단열헤드 [kJ/kg]",
         "유량 [kg/s]", "흡입체적 [m³/h]", "축동력 [kW]"],
        [
            [
                st.name, f"{st.pressure_ratio:.3f}", f"{st.t_in:.2f}",
                f"{st.t_out:.2f}", f"{st.dh_isentropic:.3f}",
                f"{st.mass_flow:.4f}", f"{st.volume_flow_m3h:.1f}",
                f"{st.power:.2f}",
            ]
            for st in res.stage_results
        ],
    ))
    mc = res.max_condition
    if mc is not None:
        out.append(
            f'<p class="note">최대 조건 (응축 {mc.t_cond:.0f}°C): '
            f"토출온도 {mc.t_discharge:.1f}°C, 압축비 {mc.pressure_ratio:.2f}, "
            f"입력전력 {mc.input_power:.1f} kW</p>"
        )
    out.append("</div>")

    # 열교환기
    hx = [
        evaporator_side(res.qe, inp.te, inp.chilled_water_in),
        condenser_side(res.qc, inp.tc, inp.cooling_medium_in),
    ]
    out.append('<div class="card"><h2>열교환기 2차측</h2>')
    out.append(_table(
        ["열교환기", "열량 [kW]", "입구 [°C]", "출구 [°C]", "유량 [m³/h]",
         "LMTD [K]", "UA [kW/K]"],
        [
            [
                x.name, f"{x.duty:.1f}", f"{x.t_in:.2f}", f"{x.t_out:.2f}",
                f"{x.volume_flow_m3h:.1f}", f"{x.lmtd:.3f}", f"{x.ua:.2f}",
            ]
            for x in hx
        ],
    ))
    out.append("</div>")

    # 임펠러
    psi = float(values.get("psi") or 0.60)
    ns = float(values.get("specific_speed") or 0.70)
    sizings = [
        size_impeller(st, inp.refrigerant, head_coefficient=psi, specific_speed=ns)
        for st in res.stage_results
    ]
    out.append('<div class="card"><h2>임펠러 개략 치수</h2>')
    out.append(_table(
        ["단", "회전수 [rpm]", "외경 [mm]", "주속 [m/s]", "마하수",
         "흡입구 [mm]", "일계수 λ", "유량계수 φ"],
        [
            [
                z.stage_name, f"{z.rpm:,.0f}", f"{z.diameter_mm:.1f}",
                f"{z.tip_speed:.1f}", f"{z.tip_mach:.3f}",
                f"{z.eye_diameter_mm:.1f}", f"{z.work_coefficient:.3f}",
                f"{z.flow_coefficient:.4f}",
            ]
            for z in sizings
        ],
    ))
    for z in sizings:
        for w in z.warnings:
            out.append(f'<div class="msg warn">{esc(z.stage_name)}: {esc(w)}</div>')
    out.append(
        '<p class="note">무차원수로 잡은 1차 근사입니다. '
        "실제 설계는 깃 형상·확산기·CFD 로 다시 확인해야 합니다.</p></div>"
    )

    # IPLV
    if values.get("show_iplv"):
        out.append('<div class="card"><h2>IPLV (부분부하 효율)</h2>')
        try:
            r = iplv(inp, stages=res.stages, medium="air")
        except (ValueError, RuntimeError) as exc:
            out.append(f'<div class="msg err">IPLV 계산 실패: {esc(exc)}</div>')
        else:
            out.append(_table(
                ["부하 [%]", "냉각 입구 [°C]", "응축온도 [°C]", "능력 [kW]",
                 "입력전력 [kW]", "COP", "kW/RT"],
                [
                    [
                        f"{p.load * 100:.0f}", f"{p.condition.medium_in:.1f}",
                        f"{p.condition.t_cond:.1f}", f"{p.result.qe:.1f}",
                        f"{p.result.input_power:.2f}", f"{p.cop:.3f}",
                        f"{p.kw_per_rt:.4f}",
                    ]
                    for p in r.points
                ],
            ))
            out.append(
                f'<p class="note">IPLV: COP {r.iplv_cop:.3f} / '
                f"{r.iplv_kw_per_rt:.4f} kW/RT — 부분부하 단열효율은 가정값입니다.</p>"
            )
        out.append("</div>")

    return "".join(out)


def render_page(query: dict[str, list[str]]) -> str:
    values = parse_query(query)
    try:
        inp, stages = build_input(values)
        res = solve(inp, stages=stages)
        body = render_results(res, values)
    except (ValueError, RuntimeError) as exc:
        body = (
            f'<div class="msg err"><b>계산할 수 없는 조건입니다.</b><br>{esc(exc)}</div>'
        )

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>터보 냉동기 사이클 해석</title>
<style>{STYLE}</style>
</head><body>
<div class="wrap">
  <aside><div class="card">{render_form(values)}</div></aside>
  <main>
    <h1>터보 냉동기 사이클 해석</h1>
    <p class="sub">왼쪽 값을 고치고 '다시 계산'을 누르세요.
      끝내려면 검은 창에서 Ctrl+C 를 누릅니다.</p>
    {body}
  </main>
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# 서버
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    server_version = "turbochiller"

    def do_GET(self) -> None:  # noqa: N802  (내장 클래스가 정한 이름)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        try:
            page = render_page(query)
        except Exception as exc:  # 어떤 오류든 화면에 보여준다
            page = (
                "<!doctype html><meta charset='utf-8'><body style='font-family:sans-serif'>"
                f"<h2>오류가 났습니다</h2><pre>{html_mod.escape(repr(exc))}</pre></body>"
            )
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        """요청 로그는 찍지 않는다 (검은 창을 깨끗하게)."""


def _free_port(preferred: int = 8765) -> int:
    """쓸 수 있는 포트를 고른다."""
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port: Optional[int] = None, open_browser: bool = True) -> None:
    """웹 화면을 띄운다. Ctrl+C 로 끝낸다."""
    port = port or _free_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)

    print("=" * 46)
    print("  터보 냉동기 사이클 해석")
    print("=" * 46)
    print()
    print(f"  브라우저에서 열렸습니다: {url}")
    print("  (자동으로 안 열리면 위 주소를 직접 입력하세요)")
    print()
    print("  끝내려면 이 창에서 Ctrl+C 를 누르세요.")
    print()

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        server.server_close()


# ==========================================================================
# 실행 진입점
# ==========================================================================

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="터보 냉동기 사이클 해석 (파일 하나 배포판)"
    )
    parser.add_argument(
        "--text", action="store_true",
        help="화면 대신 계산 결과를 글자로만 찍는다",
    )
    parser.add_argument("--port", type=int, help="웹 화면 포트 (기본: 8765부터 빈 곳)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument("--refrigerant", default="R1234ze(E)", help="냉매")
    parser.add_argument("--capacity", type=float, default=150.0, help="냉동능력 [RT]")
    parser.add_argument("--stages", type=int, choices=(1, 2), default=2, help="압축 단수")
    parser.add_argument("--t-evap", type=float, help="증발온도 [°C]")
    parser.add_argument("--t-cond", type=float, help="응축온도 [°C]")
    args = parser.parse_args()

    if args.text:
        inp = CycleInput(
            refrigerant=args.refrigerant,
            capacity_rt=args.capacity,
            t_evap=args.t_evap,
            t_cond=args.t_cond,
        )
        print(format_report(solve(inp, stages=args.stages)))
        return

    serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    _main()

