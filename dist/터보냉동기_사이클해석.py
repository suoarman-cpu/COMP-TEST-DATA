"""터보 냉동기 사이클 해석 — 파일 하나로 합친 배포판.

이 파일 하나만 있으면 돌아간다. 폴더 구조가 필요 없다.

쓰는 법
    화면으로 보기 :  python 터보냉동기_사이클해석.py
                     (브라우저가 자동으로 열린다)
    계산만 찍기   :  python 터보냉동기_사이클해석.py --text
    게이지 R&R    :  화면 위쪽 '게이지 R&R' 메뉴, 또는
                     python 터보냉동기_사이클해석.py --gagerr 데이터.csv --lsl .. --usl ..

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
import re
import sys
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Literal, Optional, Sequence

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
gagerr = _SelfModule()



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


#: 냉매별 상태 계산기를 재사용한다. 만드는 비용이 제법 크다.
_STATES: dict = {}


def _state(fluid: str):
    """그 냉매의 CoolProp 상태 계산기를 돌려준다 (만들어 두고 재사용)."""
    from CoolProp import AbstractState

    name = normalize(fluid)
    st = _STATES.get(name)
    if st is None:
        st = AbstractState("HEOS", name)
        _STATES[name] = st
    return st


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
    """음속 [m/s] (T, P 기준). 마하수 계산에 쓴다."""
    return _props("A", "T", t_c + T0, "P", p_kpa * 1000.0, fluid)


def molar_mass(fluid: str) -> float:
    """분자량 [kg/kmol]."""
    from CoolProp.CoolProp import PropsSI as _P

    return _P("M", "", 0, "", 0, normalize(fluid)) * 1000.0


def h_dp(fluid: str, density: float, p_kpa: float) -> float:
    """엔탈피 [kJ/kg] (밀도, P 기준). 등비체적선을 그릴 때 쓴다."""
    return _props("H", "D", density, "P", p_kpa * 1000.0, fluid) / 1000.0


def t_dp(fluid: str, density: float, p_kpa: float) -> float:
    """온도 [°C] (밀도, P 기준)."""
    return _props("T", "D", density, "P", p_kpa * 1000.0, fluid) - T0


def s_hp(fluid: str, h: float, p_kpa: float) -> float:
    """엔트로피 [kJ/kg·K] (h, P 기준)."""
    return _props("S", "H", h * 1000.0, "P", p_kpa * 1000.0, fluid) / 1000.0


def q_sp(fluid: str, s: float, p_kpa: float) -> float:
    """건도 [-] (s, P 기준). 2상 영역이 아니면 -1 또는 범위 밖 값이 나온다."""
    return _props("Q", "S", s * 1000.0, "P", p_kpa * 1000.0, fluid)


def q_dp(fluid: str, density: float, p_kpa: float) -> float:
    """건도 [-] (밀도, P 기준)."""
    return _props("Q", "D", density, "P", p_kpa * 1000.0, fluid)


def in_two_phase(q: float) -> bool:
    """CoolProp 이 돌려준 건도가 2상 영역을 뜻하는지."""
    return 0.0 <= q <= 1.0


def vapor_grid(
    fluid: str,
    p_values: list[float],
    t_span: float,
    n_t: int = 16,
) -> list[tuple[float, list[tuple[float, float, float, float]]]]:
    """과열증기 영역의 (P, T) 격자에서 h·s·밀도를 한 번에 구한다.

    등엔트로피선·등비체적선을 그릴 때 쓴다.
    (s,P) 나 (밀도,P) 로 물성을 구하는 호출은 혼합냉매에서 대단히 느려서
    (한 번에 90ms 가까이 걸린다), 빠른 (T,P) 호출로 격자를 한 번 만들고
    그 안에서 보간해 쓴다. 혼합냉매 기준 30배 넘게 빨라진다.

    p_values : 압력 목록 [kPa]
    t_span   : 각 압력에서 포화온도로부터 몇 도까지 볼지 [K]
    반환     : [(압력, [(온도, 엔탈피, 엔트로피, 밀도), ...]), ...]
    """
    import CoolProp

    try:
        state = _state(fluid)
    except Exception as exc:
        raise PropertyError(f"{fluid} 상태 계산기를 만들 수 없다: {exc}") from exc

    columns: list[tuple[float, list[tuple[float, float, float, float]]]] = []
    for p_kpa in p_values:
        try:
            t_start = t_sat(fluid, p_kpa, q=1) + 0.05
        except PropertyError:
            continue
        rows: list[tuple[float, float, float, float]] = []
        for i in range(n_t):
            t_c = t_start + t_span * i / (n_t - 1)
            try:
                state.update(CoolProp.PT_INPUTS, p_kpa * 1000.0, t_c + T0)
                rows.append(
                    (t_c, state.hmass() / 1000.0, state.smass() / 1000.0,
                     state.rhomass())
                )
            except Exception:
                continue
        if len(rows) >= 2:
            columns.append((p_kpa, rows))
    return columns


def h_tp_many(fluid: str, pairs: list[tuple[float, float]]) -> list[float]:
    """여러 (온도, 압력) 에서의 엔탈피를 한꺼번에 구한다 [kJ/kg].

    한 점씩 PropsSI 를 부르는 것보다 훨씬 빠르다. 특히 혼합냉매에서 차이가 크다.
    계산이 안 되는 점은 nan 으로 돌려준다.
    """
    import CoolProp

    try:
        state = _state(fluid)
    except Exception:
        # 상태 계산기를 못 만들면 한 점씩이라도 구한다
        out = []
        for t_c, p_kpa in pairs:
            try:
                out.append(h_tp(fluid, t_c, p_kpa))
            except PropertyError:
                out.append(float("nan"))
        return out

    out: list[float] = []
    for t_c, p_kpa in pairs:
        try:
            state.update(CoolProp.PT_INPUTS, p_kpa * 1000.0, t_c + T0)
            out.append(state.hmass() / 1000.0)
        except Exception:
            out.append(float("nan"))
    return out


def saturation_table(
    fluid: str, t_min: float, t_max: float, n: int = 140
) -> list[tuple[float, float, float, float]]:
    """포화 물성표를 한 번에 만든다.

    반환: [(온도, 포화압력, 포화액 엔탈피, 포화증기 엔탈피), ...]
    포화선과 등건도선이 같은 표를 나눠 쓰게 해서 중복 계산을 없앤다.
    """
    import CoolProp

    try:
        state = _state(fluid)
    except Exception:
        state = None

    rows: list[tuple[float, float, float, float]] = []
    for i in range(n):
        t_c = t_min + (t_max - t_min) * i / (n - 1)
        try:
            if state is not None:
                state.update(CoolProp.QT_INPUTS, 0.0, t_c + T0)
                p_kpa = state.p() / 1000.0
                h_f = state.hmass() / 1000.0
                state.update(CoolProp.QT_INPUTS, 1.0, t_c + T0)
                h_g = state.hmass() / 1000.0
            else:
                p_kpa = p_sat(fluid, t_c, q=1)
                h_f = h_sat(fluid, t_c, 0)
                h_g = h_sat(fluid, t_c, 1)
        except Exception:
            continue
        rows.append((t_c, p_kpa, h_f, h_g))
    return rows


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
# retrofit.py
# ==========================================================================

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


def format_retrofit(machine, points) -> str:
    """같은 압축기에 냉매만 바꿨을 때의 비교표."""
    out = ["", LINE, " 냉매 교체 검토 — 같은 압축기, 같은 운전조건", LINE, ""]
    out.append(f"  기준 냉매        : {machine.source_refrigerant}")
    out.append(f"  흡입 체적유량    : {machine.suction_volume_flow_m3h:9.1f} m3/h  (고정)")
    out.append(f"  단위질량당 일    : {machine.total_work:9.2f} kJ/kg  (고정)")
    out.append("")
    out.append(
        f"  {'냉매':<12}{'흡입밀도':>9}{'체적능력':>10}{'능력':>11}{'능력비':>8}"
        f"{'압축비':>8}{'축동력':>10}{'COP':>7}{'COP비':>7}{'헤드여유':>9}"
    )
    out.append(
        f"  {'':<12}{'kg/m3':>9}{'kJ/m3':>10}{'RT':>11}{'':>8}{'':>8}{'kW':>10}"
        f"{'':>7}{'':>7}{'':>9}"
    )
    out.append("  " + THIN[:90])
    for p in points:
        if not p.ok:
            out.append(f"  {p.refrigerant:<12}  {p.message}")
            continue
        out.append(
            f"  {p.refrigerant:<12}{p.suction_density:>9.2f}"
            f"{p.volumetric_capacity:>10.0f}{p.capacity_rt:>11.1f}"
            f"{p.capacity_ratio * 100:>7.0f}%{p.pressure_ratio:>8.2f}"
            f"{p.shaft_power:>10.1f}{p.cop:>7.3f}{p.cop_ratio * 100:>6.0f}%"
            f"{p.head_margin * 100:>8.0f}%"
        )
    out.append("  " + THIN[:90])
    for p in points:
        if p.ok and p.message:
            out.append(f"  ! {p.refrigerant}: {p.message}")
    out.append("")
    out.append("  읽는 법")
    out.append("    체적능력 : 흡입 1 m3 당 낼 수 있는 냉동능력. 같은 기계면")
    out.append("               능력이 이 값에 비례한다")
    out.append("    헤드여유 : 이 운전조건에 필요한 일 대비 기계가 하는 일의 여유.")
    out.append("               음수면 그 응축온도를 만들지 못한다")
    out.append(LINE)
    return "\n".join(out)


# ==========================================================================
# svg.py
# ==========================================================================

# ---------------------------------------------------------------------------
# 색
# ---------------------------------------------------------------------------
# 사이클(파랑·주황)은 눈에 띄게, 보조선은 뒤로 물러나게 잡았다.
# 보조선끼리는 색만이 아니라 '선 모양'과 '라벨'로도 구분되므로
# 색을 못 알아봐도 읽을 수 있다.

COLORS_LIGHT = {
    "cycle": "#2a78d6",
    "compression": "#eb6834",
    "dome": "#6f6e68",
    "isotherm": "#5d9c74",
    "quality": "#9a9992",
    "isentrope": "#8b82bb",
    "isochore": "#a98a5e",
    "grid": "#ebeae5",
    "axis": "#cfcec8",
    "text": "#52514e",
    "text_strong": "#0b0b0b",
    "surface": "#fcfcfb",
}
COLORS_DARK = {
    "cycle": "#3987e5",
    "compression": "#d95926",
    "dome": "#9b9a92",
    "isotherm": "#5fa87b",
    "quality": "#6f6e68",
    "isentrope": "#9085e9",
    "isochore": "#b08f5c",
    "grid": "#262625",
    "axis": "#3a3a37",
    "text": "#c3c2b7",
    "text_strong": "#ffffff",
    "surface": "#1a1a19",
}

#: 보조선의 선 모양 (색을 못 구분해도 알아볼 수 있게)
DASH = {
    "isotherm": "",
    "quality": "1.5 3",
    "isentrope": "6 3",
    "isochore": "8 2.5 1.5 2.5",
}


@dataclass
class ChartOptions:
    """선도에 무엇을 그릴지."""

    isotherms: bool = True
    quality: bool = True
    isentropes: bool = True
    isochores: bool = True
    labels: bool = True
    width: float = 900.0
    height: float = 640.0
    dark: bool = False
    #: 사이클 주변을 얼마나 넓게 보여줄지 (0.3 이면 양옆 30% 여유)
    margin: float = 0.32
    legend: bool = True


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
        frac = (math.log10(max(p, 1e-9)) - self.log_p_min) / span
        return self.height - self.pad_bottom - frac * inner

    @property
    def p_min(self) -> float:
        return 10.0**self.log_p_min

    @property
    def p_max(self) -> float:
        return 10.0**self.log_p_max

    def inside(self, h: float, p: float) -> bool:
        return self.h_min <= h <= self.h_max and self.p_min <= p <= self.p_max


def _sig(value: float, digits: int = 2) -> str:
    """유효숫자 몇 자리로 짧게 적는다 (0.01147 -> 0.011)."""
    if value == 0:
        return "0"
    exp = math.floor(math.log10(abs(value)))
    rounded = round(value, -(exp - digits + 1))
    text = f"{rounded:.{max(0, digits - 1 - exp)}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _esc(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# 눈금
# ---------------------------------------------------------------------------

def _pressure_ticks(p_min: float, p_max: float) -> list[float]:
    """로그 축 눈금 (1·2·3·5 × 10^n)."""
    ticks: list[float] = []
    exp = math.floor(math.log10(p_min))
    while 10.0**exp <= p_max * 10:
        for m in (1, 2, 3, 5):
            v = m * 10.0**exp
            if p_min <= v <= p_max:
                ticks.append(v)
        exp += 1
    return ticks


def _enthalpy_ticks(h_min: float, h_max: float, target: int = 8) -> list[float]:
    span = h_max - h_min
    if span <= 0:
        return [h_min]
    raw = span / target
    exp = math.floor(math.log10(raw))
    step = 10.0**exp
    for m in (1, 2, 2.5, 5, 10):
        if m * 10.0**exp >= raw:
            step = m * 10.0**exp
            break
    ticks: list[float] = []
    v = math.ceil(h_min / step) * step
    while v <= h_max:
        ticks.append(v)
        v += step
    return ticks


def _nice_step(span: float, target: int) -> float:
    """보조선 간격을 보기 좋은 값으로 고른다."""
    if span <= 0:
        return 1.0
    raw = span / max(target, 1)
    exp = math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * 10.0**exp >= raw:
            return m * 10.0**exp
    return 10.0**(exp + 1)


# ---------------------------------------------------------------------------
# 보조선 계산
# ---------------------------------------------------------------------------

def _p_grid(box: _Box, n: int = 46) -> list[float]:
    """압력 축을 로그로 균등 분할한다."""
    lo, hi = box.log_p_min, box.log_p_max
    return [10.0 ** (lo + (hi - lo) * i / (n - 1)) for i in range(n)]


def _sat_table(fluid: str, box: _Box, n: int = 140):
    """화면 범위를 덮는 포화 물성표. 포화선과 등건도선이 함께 쓴다."""
    t_crit = props.t_crit(fluid)
    t_hi = t_crit - 0.15
    t_lo = props.t_sat(fluid, box.p_min, q=1) - 25.0
    return props.saturation_table(fluid, t_lo, t_hi, n)


def _saturation(table) -> tuple[list, list]:
    """포화액선·포화증기선을 (h, p) 목록으로."""
    liq = [(h_f, p) for _, p, h_f, _ in table]
    vap = [(h_g, p) for _, p, _, h_g in table]
    return liq, vap


def _isotherm(fluid: str, t: float, box: _Box) -> list[tuple[float, float]]:
    """등온선 하나. 액 -> 2상(수평) -> 과열증기 순으로 이어 붙인다.

    과냉액 구간은 거의 수직, 2상 구간은 수평, 과열 구간은 오른쪽 아래로
    휘는 곡선이 된다. 실제 냉매 선도의 등온선 모양이다.
    """
    t_crit = props.t_crit(fluid)

    if t >= t_crit:
        pressures = list(reversed(_p_grid(box, 40)))
        hs = props.h_tp_many(fluid, [(t, p) for p in pressures])
        return [(h, p) for h, p in zip(hs, pressures)]

    try:
        p_sat = props.p_sat(fluid, t, q=1)
        h_f = props.h_sat(fluid, t, 0)
        h_g = props.h_sat(fluid, t, 1)
    except Exception:
        return []

    # 1) 과냉 액 구간 : 높은 압력에서 포화압까지 (거의 수직)
    liquid_p = sorted((p for p in _p_grid(box, 16) if p > p_sat), reverse=True)
    # 3) 과열 증기 구간 : 포화압에서 낮은 압력으로
    vapor_p = sorted(p for p in _p_grid(box, 30) if p < p_sat)

    hs = props.h_tp_many(fluid, [(t, p) for p in liquid_p + vapor_p])
    n_liq = len(liquid_p)

    pts: list[tuple[float, float]] = []
    for h, p in zip(hs[:n_liq], liquid_p):
        if h == h:
            pts.append((h, p))
    pts.append((h_f, p_sat))      # 2) 2상 구간 : 포화압에서 수평
    pts.append((h_g, p_sat))
    for h, p in zip(hs[n_liq:], vapor_p):
        if h == h:
            pts.append((h, p))
    return pts


def _quality_line(table, x: float) -> list[tuple[float, float]]:
    """등건도선 (포화 영역 안). 포화표를 그대로 쓴다."""
    return [(h_f + x * (h_g - h_f), p) for _, p, h_f, h_g in table]


def _grid_line(
    grid: list[tuple[float, list[tuple[float, float, float, float]]]],
    index: int,
    value: float,
) -> list[tuple[float, float]]:
    """격자에서 어떤 물성이 주어진 값이 되는 자리를 찾아 선을 만든다.

    index 3 은 엔트로피, 4 는 밀도 (격자 한 칸은 (T, h, s, d) 순서다).
    압력마다 한 줄씩 훑으면서 값이 걸치는 구간을 선형보간한다.
    """
    pts: list[tuple[float, float]] = []
    col = index - 1          # (T, h, s, d) 에서의 위치
    for p_kpa, rows in grid:
        hit = None
        for a, b in zip(rows, rows[1:]):
            va, vb = a[col], b[col]
            if (va - value) * (vb - value) <= 0 and va != vb:
                f = (value - va) / (vb - va)
                hit = a[1] + f * (b[1] - a[1])      # 엔탈피 보간
                break
        pts.append((hit if hit is not None else float("nan"), p_kpa))
    return pts


def _grid_range(
    grid: list[tuple[float, list[tuple[float, float, float, float]]]],
    index: int,
) -> tuple[float, float]:
    """격자 안에서 그 물성이 갖는 최소·최대."""
    col = index - 1
    values = [row[col] for _, rows in grid for row in rows]
    return (min(values), max(values)) if values else (0.0, 0.0)


# -----------------------------------------------------------------------# ---------------------------------------------------------------------------
# 그리기 도우미
# ---------------------------------------------------------------------------

def _polyline(pts: Iterable[tuple[float, float]], box: _Box) -> str:
    """보이는 구간만 이어서 path 문자열을 만든다.

    엔탈피가 nan 이면 그 자리에서 선을 끊는다 (2상 영역을 건너뛸 때 쓴다).
    """
    d: list[str] = []
    pen = False
    prev_inside = False
    for h, p in pts:
        if h != h:            # nan
            pen = False
            prev_inside = False
            continue
        inside = box.inside(h, p)
        if not inside and not prev_inside:
            pen = False
            prev_inside = False
            continue
        # 경계를 넘나드는 점은 한 번 더 찍어 선이 끊기지 않게 한다
        d.append(("L" if pen else "M") + f"{box.x(h):.1f},{box.y(p):.1f}")
        pen = True
        prev_inside = inside
    return " ".join(d)


@dataclass
class _Labeller:
    """라벨이 서로 겹치지 않게 놓는다."""

    placed: list[tuple[float, float]] = field(default_factory=list)
    min_gap: float = 26.0

    def try_place(self, x: float, y: float) -> bool:
        for px, py in self.placed:
            if abs(px - x) < self.min_gap and abs(py - y) < 13:
                return False
        self.placed.append((x, y))
        return True


def _label_at_edge(
    pts: list[tuple[float, float]], box: _Box, side: str
) -> Optional[tuple[float, float]]:
    """선이 화면 가장자리에 닿는 지점을 찾아 라벨 자리로 준다."""
    inside = [(h, p) for h, p in pts if box.inside(h, p)]
    if not inside:
        return None
    if side == "bottom":
        h, p = min(inside, key=lambda hp: hp[1])
    elif side == "top":
        h, p = max(inside, key=lambda hp: hp[1])
    elif side == "right":
        h, p = max(inside, key=lambda hp: hp[0])
    else:
        h, p = min(inside, key=lambda hp: hp[0])
    return box.x(h), box.y(p)


# ---------------------------------------------------------------------------
# 본체
# ---------------------------------------------------------------------------

def ph_diagram_svg(
    res: CycleResult,
    width: Optional[float] = None,
    height: Optional[float] = None,
    dark: bool = False,
    options: Optional[ChartOptions] = None,
) -> str:
    """사이클을 실제 냉매 선도 모양의 P-h 선도로 그린다."""
    opt = options or ChartOptions()
    if width is not None:
        opt.width = width
    if height is not None:
        opt.height = height
    opt.dark = dark or opt.dark

    c = COLORS_DARK if opt.dark else COLORS_LIGHT
    fluid = res.refrigerant
    W, H = opt.width, opt.height

    # --- 표시 범위 ---
    hs = [s.h for s in res.states]
    ps = [s.p for s in res.states]
    h_pad = (max(hs) - min(hs)) * opt.margin
    box = _Box(
        W, H, 78, 30, 74 if opt.legend else 46, 56,
        min(hs) - h_pad, max(hs) + h_pad,
        math.log10(min(ps) * 0.42), math.log10(max(ps) * 2.6),
    )

    out: list[str] = []
    add = out.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'width="100%" role="img" aria-label="P-h 선도" '
        f'style="max-width:{W:.0f}px;height:auto;'
        f'font-family:system-ui,-apple-system,sans-serif">'
    )
    add(f'<rect width="{W}" height="{H}" fill="{c["surface"]}"/>')
    pw = W - box.pad_left - box.pad_right
    ph = H - box.pad_top - box.pad_bottom
    add(
        f'<clipPath id="pl"><rect x="{box.pad_left}" y="{box.pad_top}" '
        f'width="{pw}" height="{ph}"/></clipPath>'
    )

    # --- 격자 ---
    for p in _pressure_ticks(box.p_min, box.p_max):
        y = box.y(p)
        add(f'<line x1="{box.pad_left}" y1="{y:.1f}" x2="{W - box.pad_right}" '
            f'y2="{y:.1f}" stroke="{c["grid"]}" stroke-width="1"/>')
        add(f'<text x="{box.pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{c["text"]}">{p:,.0f}</text>')
    for h in _enthalpy_ticks(box.h_min, box.h_max):
        x = box.x(h)
        add(f'<line x1="{x:.1f}" y1="{box.pad_top}" x2="{x:.1f}" '
            f'y2="{H - box.pad_bottom}" stroke="{c["grid"]}" stroke-width="1"/>')
        add(f'<text x="{x:.1f}" y="{H - box.pad_bottom + 18:.1f}" '
            f'text-anchor="middle" font-size="11" fill="{c["text"]}">{h:,.0f}</text>')

    add('<g clip-path="url(#pl)">')
    labeller = _Labeller()
    label_bits: list[str] = []

    def draw(pts, color, dash, wdt=1.0, opacity=1.0):
        d = _polyline(pts, box)
        if d:
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{wdt}"'
                f'{dash_attr} stroke-opacity="{opacity}" stroke-linejoin="round"/>')
        return d

    def put_label(pts, side, text, color, dx=0.0, dy=0.0, anchor="middle"):
        if not opt.labels:
            return
        spot = _label_at_edge(pts, box, side)
        if spot is None:
            return
        x, y = spot[0] + dx, spot[1] + dy
        # 글자가 그래프 밖으로 삐져나가지 않게 가둔다
        half = len(str(text)) * 3.2
        x = min(max(x, box.pad_left + half + 2), W - box.pad_right - half - 2)
        y = min(max(y, box.pad_top + 11), H - box.pad_bottom - 4)
        if not labeller.try_place(x, y):
            return
        label_bits.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="10" '
            f'fill="{color}" paint-order="stroke" stroke="{c["surface"]}" '
            f'stroke-width="3" stroke-linejoin="round">{_esc(text)}</text>'
        )

    t_crit = props.t_crit(fluid)
    sat_table = _sat_table(fluid, box)

    # --- 등온선 ---
    if opt.isotherms:
        t_lo = props.t_sat(fluid, box.p_min, q=1)
        t_hi = min(t_crit + 10.0, props.t_hp(fluid, box.h_max, box.p_min))
        step = _nice_step(t_hi - t_lo, 11)
        t = math.ceil(t_lo / step) * step
        while t <= t_hi:
            pts = _isotherm(fluid, t, box)
            if draw(pts, c["isotherm"], DASH["isotherm"], 0.9, 0.85):
                put_label(pts, "bottom", f"{t:g}°C", c["isotherm"], 0, -5)
            t += step

    # --- 등건도선 ---
    if opt.quality:
        for x_q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            pts = _quality_line(sat_table, x_q)
            if draw(pts, c["quality"], DASH["quality"], 0.9, 0.9):
                put_label(pts, "bottom", f"{x_q:.1f}", c["quality"], 0, -5)

    # --- 과열증기 격자 (등엔트로피선·등비체적선에 쓴다) ---
    grid = []
    if opt.isentropes or opt.isochores:
        try:
            p_grid = _p_grid(box, 26)
            t_top = props.t_hp(fluid, box.h_max, box.p_min)
            t_bot = props.t_sat(fluid, box.p_min, q=1)
            grid = props.vapor_grid(
                fluid, p_grid, max(30.0, min(t_top - t_bot, 160.0)), 16
            )
        except Exception:
            grid = []

    # --- 등엔트로피선 ---
    if opt.isentropes and grid:
        try:
            # 화면에 보이는 '과열증기 영역' 안에서만 s 범위를 잡는다.
            # 과냉액까지 포함하면 범위가 지나치게 넓어져,
            # 정작 압축 구간 주변에는 선이 한 줄도 안 그려진다.
            lo, hi = _grid_range(grid, 3)
            step = _nice_step(hi - lo, 9)
            sv = math.ceil(lo / step) * step
            while sv <= hi + 1e-9:
                pts = _grid_line(grid, 3, sv)
                if draw(pts, c["isentrope"], DASH["isentrope"], 0.9, 0.85):
                    put_label(pts, "top", f"s={sv:g}", c["isentrope"], 0, 13)
                sv += step
        except Exception:
            pass

    # --- 등비체적선 ---
    if opt.isochores and grid:
        try:
            d_lo, d_hi = _grid_range(grid, 4)
            steps = 5
            for i in range(steps + 1):
                dens = d_lo * (d_hi / d_lo) ** (i / steps)
                pts = _grid_line(grid, 4, dens)
                if draw(pts, c["isochore"], DASH["isochore"], 0.9, 0.8):
                    put_label(pts, "right", f"v={_sig(1 / dens)}", c["isochore"],
                              -4, -5, "end")
        except Exception:
            pass

    # --- 포화선 ---
    liq, vap = _saturation(sat_table)
    draw(liq, c["dome"], "", 2.2)
    draw(vap, c["dome"], "", 2.2)

    # --- 임계점 ---
    try:
        from CoolProp.CoolProp import PropsSI as _P

        name = props.normalize(fluid)
        p_crit = _P("Pcrit", "", 0, "", 0, name) / 1000.0
        h_crit = props.h_tp(fluid, t_crit + 0.05, p_crit)
        if box.inside(h_crit, p_crit):
            add(f'<circle cx="{box.x(h_crit):.1f}" cy="{box.y(p_crit):.1f}" r="3.5" '
                f'fill="none" stroke="{c["dome"]}" stroke-width="1.6"/>')
            label_bits.append(
                f'<text x="{box.x(h_crit):.1f}" y="{box.y(p_crit) - 8:.1f}" '
                f'text-anchor="middle" font-size="10" fill="{c["text"]}" '
                f'paint-order="stroke" stroke="{c["surface"]}" stroke-width="3">'
                f'임계점</text>'
            )
    except Exception:
        pass

    # --- 사이클 ---
    cycle = [(s.h, s.p) for s in res.states]
    d = " ".join(
        ("M" if i == 0 else "L") + f"{box.x(h):.1f},{box.y(p):.1f}"
        for i, (h, p) in enumerate(cycle + cycle[:1])
    )
    add(f'<path d="{d}" fill="none" stroke="{c["cycle"]}" stroke-width="2.4" '
        f'stroke-linejoin="round"/>')

    for a, b in (((1, 2),) if res.stages == 1 else ((1, 2), (3, 4))):
        sa, sb = res.state(a), res.state(b)
        add(f'<line x1="{box.x(sa.h):.1f}" y1="{box.y(sa.p):.1f}" '
            f'x2="{box.x(sb.h):.1f}" y2="{box.y(sb.p):.1f}" '
            f'stroke="{c["compression"]}" stroke-width="4" stroke-linecap="round"/>')

    add("".join(label_bits))
    add("</g>")

    # --- 상태점 ---
    for s, (dx, dy) in zip(res.states, _state_offsets(res, box)):
        px, py = box.x(s.h), box.y(s.p)
        add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.8" fill="{c["cycle"]}" '
            f'stroke="{c["surface"]}" stroke-width="2">'
            f'<title>{_esc(f"{s.no}. {s.name} / {s.t:.2f}°C / {s.p:.1f} kPa / {s.h:.2f} kJ/kg")}'
            f'</title></circle>')
        add(f'<text x="{px + dx:.1f}" y="{py + dy:.1f}" font-size="12.5" '
            f'font-weight="700" fill="{c["text_strong"]}" paint-order="stroke" '
            f'stroke="{c["surface"]}" stroke-width="3.5" stroke-linejoin="round">'
            f'{s.no}</text>')

    # --- 축 ---
    add(f'<line x1="{box.pad_left}" y1="{box.pad_top}" x2="{box.pad_left}" '
        f'y2="{H - box.pad_bottom}" stroke="{c["axis"]}" stroke-width="1"/>')
    add(f'<line x1="{box.pad_left}" y1="{H - box.pad_bottom}" '
        f'x2="{W - box.pad_right}" y2="{H - box.pad_bottom}" '
        f'stroke="{c["axis"]}" stroke-width="1"/>')
    add(f'<text x="{W / 2:.0f}" y="{H - 10:.0f}" text-anchor="middle" font-size="12" '
        f'fill="{c["text"]}">엔탈피 h [kJ/kg]</text>')
    add(f'<text x="17" y="{H / 2:.0f}" text-anchor="middle" font-size="12" '
        f'fill="{c["text"]}" transform="rotate(-90 17 {H / 2:.0f})">'
        f'압력 P [kPa] (로그)</text>')
    add(f'<text x="{box.pad_left}" y="26" font-size="13.5" font-weight="700" '
        f'fill="{c["text_strong"]}">{_esc(fluid)} · {res.stages}단 압축 · '
        f'COP {res.cop:.2f}</text>')

    # --- 범례 ---
    if opt.legend:
        add(_legend(c, opt, W, box))


    add("</svg>")
    return "".join(out)


def _legend(c: dict, opt: ChartOptions, W: float, box: _Box) -> str:
    """범례를 그래프 위쪽 바깥에 가로로 한 줄 놓는다.

    그래프 안에 두면 포화선이나 보조선을 가려서 밖으로 뺐다.
    """
    rows = [
        (c["cycle"], "", "사이클"),
        (c["compression"], "", "압축"),
        (c["dome"], "", "포화선"),
    ]
    if opt.isotherms:
        rows.append((c["isotherm"], DASH["isotherm"], "등온선 [°C]"))
    if opt.quality:
        rows.append((c["quality"], DASH["quality"], "등건도선 x"))
    if opt.isentropes:
        rows.append((c["isentrope"], DASH["isentrope"], "등엔트로피선 s [kJ/kg·K]"))
    if opt.isochores:
        rows.append((c["isochore"], DASH["isochore"], "등비체적선 v [m³/kg]"))

    out: list[str] = []
    x = box.pad_left
    y = 46.0
    line_h = 17.0
    avail = W - box.pad_left - box.pad_right

    for color, dash, name in rows:
        w = 30 + len(name) * 6.6 + 14   # 글자 폭 어림
        if x - box.pad_left + w > avail:   # 줄이 넘치면 다음 줄로
            x = box.pad_left
            y += line_h
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + 22:.1f}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="2.2"{dash_attr} stroke-linecap="round"/>'
        )
        out.append(
            f'<text x="{x + 27:.1f}" y="{y + 3.5:.1f}" font-size="10.5" '
            f'fill="{c["text"]}">{_esc(name)}</text>'
        )
        x += w
    return "".join(out)


def _state_offsets(res: CycleResult, box: _Box) -> list[tuple[float, float]]:
    """상태점 번호가 겹치지 않게 흩어 놓는다."""
    offsets: list[tuple[float, float]] = []
    placed: list[tuple[float, float]] = []
    for s in res.states:
        px, py = box.x(s.h), box.y(s.p)
        crowded = sum(1 for qx, qy in placed if abs(qx - px) < 15 and abs(qy - py) < 15)
        offsets.append([(9, -8), (9, 16), (-16, -8), (-16, 16)][crowded % 4])
        placed.append((px, py))
    return offsets


# ==========================================================================
# gagerr.py
# ==========================================================================

import csv

# ---------------------------------------------------------------------------
# 관리도 상수 (부분군 크기 m = 2..15)
# ---------------------------------------------------------------------------

#: 범위의 기대값 d2, 표준편차 d3 (정규분포)
_D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847,
       9: 2.970, 10: 3.078, 11: 3.173, 12: 3.258, 13: 3.336, 14: 3.407, 15: 3.472}
_D3 = {2: 0.853, 3: 0.888, 4: 0.880, 5: 0.864, 6: 0.848, 7: 0.833, 8: 0.820,
       9: 0.808, 10: 0.797, 11: 0.787, 12: 0.778, 13: 0.770, 14: 0.763, 15: 0.756}

#: R 관리도 상·하한 계수
_D4 = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864,
       9: 1.816, 10: 1.777, 11: 1.744, 12: 1.716, 13: 1.692, 14: 1.671, 15: 1.652}
_D3_CHART = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.076, 8: 0.136,
             9: 0.184, 10: 0.223, 11: 0.256, 12: 0.284, 13: 0.308, 14: 0.329,
             15: 0.348}

#: X̄ 관리도 한계 계수
_A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373,
       9: 0.337, 10: 0.308, 11: 0.285, 12: 0.266, 13: 0.249, 14: 0.235, 15: 0.223}

#: AIAG MSA 4판 표의 K1 (반복 횟수 2, 3). 나머지는 1/d2 로 계산한다.
_K1_AIAG = {2: 0.8862, 3: 0.5908}

#: AIAG MSA 4판 표의 K2(측정자 수)·K3(부품 수). 11 이상은 1/d2* 로 계산한다.
_K23_AIAG = {2: 0.7071, 3: 0.5231, 4: 0.4467, 5: 0.4030, 6: 0.3742, 7: 0.3534,
             8: 0.3375, 9: 0.3249, 10: 0.3146}

#: 판정 경계 [%]
LIMIT_OK = 10.0
LIMIT_NG = 30.0
NDC_MIN = 5

#: 연구변동 배수. AIAG 4판·Minitab 기본값이 6σ 다 (옛 3판은 5.15σ).
STUDY_VAR_K = 6.0


def k1(trials: int) -> float:
    """반복성 상수 K1 = 1/d2 (부분군이 많을 때)."""
    if trials in _K1_AIAG:
        return _K1_AIAG[trials]
    return 1.0 / _D2[trials]


def k_single(m: int) -> float:
    """K2·K3 = 1/d2* (부분군 1개). d2* = √(d2² + d3²)."""
    if m in _K23_AIAG:
        return _K23_AIAG[m]
    return 1.0 / math.sqrt(_D2[m] ** 2 + _D3[m] ** 2)


# ---------------------------------------------------------------------------
# F 분포 (p 값) — 불완전 베타 함수로 직접 계산
# ---------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """불완전 베타 함수의 연분수 (Lentz 법)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """정규화 불완전 베타 함수 I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def f_pvalue(f: float, df1: float, df2: float) -> float:
    """F 분포의 위쪽 꼬리 확률 P(F > f)."""
    if math.isnan(f):
        return float("nan")
    if math.isinf(f):
        return 0.0
    if f <= 0.0:
        return 1.0
    return betainc(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------

@dataclass
class Study:
    """측정 데이터. data[(부품, 측정자)] = [1회, 2회, ...]"""

    parts: list[str]
    operators: list[str]
    data: dict[tuple[str, str], list[float]]

    @property
    def trials(self) -> int:
        return len(next(iter(self.data.values())))

    @property
    def n_parts(self) -> int:
        return len(self.parts)

    @property
    def n_operators(self) -> int:
        return len(self.operators)

    def values(self) -> list[float]:
        return [v for vs in self.data.values() for v in vs]

    def cell_mean(self, part: str, op: str) -> float:
        vs = self.data[(part, op)]
        return sum(vs) / len(vs)

    def cell_range(self, part: str, op: str) -> float:
        vs = self.data[(part, op)]
        return max(vs) - min(vs)

    def part_mean(self, part: str) -> float:
        vs = [v for op in self.operators for v in self.data[(part, op)]]
        return sum(vs) / len(vs)

    def operator_mean(self, op: str) -> float:
        vs = [v for p in self.parts for v in self.data[(p, op)]]
        return sum(vs) / len(vs)


def build_study(rows: Sequence[tuple[str, str, float]]) -> Study:
    """(부품, 측정자, 값) 목록으로 Study 를 만들고 모양을 검사한다."""
    parts: list[str] = []
    operators: list[str] = []
    data: dict[tuple[str, str], list[float]] = {}
    for part, op, value in rows:
        if part not in parts:
            parts.append(part)
        if op not in operators:
            operators.append(op)
        data.setdefault((part, op), []).append(float(value))

    if len(parts) < 2:
        raise ValueError("부품이 2개 이상 있어야 합니다 (보통 10개).")
    if len(operators) < 2:
        raise ValueError("측정자가 2명 이상 있어야 합니다 (보통 3명).")

    missing = [f"{p}/{o}" for p in parts for o in operators if (p, o) not in data]
    if missing:
        raise ValueError(
            "모든 측정자가 모든 부품을 재야 합니다. 빠진 조합: "
            + ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        )

    counts = {len(v) for v in data.values()}
    if len(counts) != 1:
        detail = ", ".join(
            f"{p}/{o}={len(v)}회" for (p, o), v in list(data.items())[:6]
        )
        raise ValueError(
            "모든 부품·측정자 조합의 반복 횟수가 같아야 합니다 "
            f"(지금은 {sorted(counts)}회가 섞여 있음: {detail} ...)."
        )
    n = counts.pop()
    if n < 2:
        raise ValueError("같은 부품을 2회 이상 반복해서 재야 반복성을 알 수 있습니다.")
    if n > 15:
        raise ValueError("반복 횟수는 15회까지 받습니다.")

    return Study(parts=parts, operators=operators, data=data)


#: 긴 표(한 줄에 측정값 하나)의 머리글로 알아보는 이름들
_PART_KEYS = ("부품", "시료", "샘플", "품번", "제품", "part", "sample", "item")
_OP_KEYS = ("측정자", "작업자", "검사자", "평가자", "operator", "appraiser", "inspector")
_VALUE_KEYS = ("측정값", "측정치", "값", "결과", "value", "measurement", "result", "data")
_TRIAL_KEYS = ("반복", "횟수", "회차", "trial", "replicate", "rep")


def _find_col(header: list[str], keys: Sequence[str]) -> Optional[int]:
    norm = [h.strip().lower() for h in header]
    for key in keys:
        for i, h in enumerate(norm):
            if h == key or h.startswith(key):
                return i
    return None


def _to_float(text: str, where: str) -> float:
    t = text.strip().replace(" ", "")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"{where} 의 '{text}' 를 숫자로 읽을 수 없습니다.") from None


#: 넓은 표 머리글 "A-1", "A_2", "측정자1 3", "B1" -> (측정자, 회차)
_WIDE_HEAD = re.compile(r"^(.+?)\s*[-_/#.\s]\s*(\d+)$|^(.*?\D)(\d+)$")


def parse_table(text: str) -> Study:
    """CSV 나 엑셀에서 복사해 붙인 표를 읽는다.

    두 가지 모양을 받는다.

    긴 표 — 한 줄에 측정값 하나 ::

        부품,측정자,반복,측정값
        1,A,1,250.012
        1,A,2,250.010

    넓은 표 — 한 줄에 부품 하나, 칸마다 '측정자-회차' ::

        부품,A-1,A-2,A-3,B-1,B-2,B-3
        1,250.012,250.010,...
    """
    text = text.strip().lstrip("﻿")
    if not text:
        raise ValueError("데이터가 비어 있습니다.")
    first = text.splitlines()[0]
    if "\t" in first:
        delim = "\t"
    elif ";" in first and "," not in first:
        delim = ";"
    else:
        delim = ","
    table = [
        [c.strip() for c in row]
        for row in csv.reader(text.splitlines(), delimiter=delim)
        if any(c.strip() for c in row)
    ]
    if len(table) < 2:
        raise ValueError("머리글 한 줄과 데이터가 있어야 합니다.")
    header, body = table[0], table[1:]

    i_part = _find_col(header, _PART_KEYS)
    i_op = _find_col(header, _OP_KEYS)
    i_val = _find_col(header, _VALUE_KEYS)

    rows: list[tuple[str, str, float]] = []

    if i_part is not None and i_op is not None and i_val is not None:
        i_trial = _find_col(header, _TRIAL_KEYS)
        keyed = []
        for n, r in enumerate(body, start=2):
            if max(i_part, i_op, i_val) >= len(r) or not r[i_val]:
                continue
            trial = (_to_float(r[i_trial], f"{n}번째 줄")
                     if i_trial is not None and i_trial < len(r) and r[i_trial] else 0)
            keyed.append((trial, n, r[i_part], r[i_op],
                          _to_float(r[i_val], f"{n}번째 줄")))
        # 회차 칸이 있으면 회차 순서대로 (없으면 적힌 순서)
        keyed.sort(key=lambda k: (k[0], k[1]))
        rows = [(p, o, v) for _, _, p, o, v in keyed]
    else:
        # 넓은 표: 첫 칸이 부품, 나머지 머리글이 '측정자-회차'
        cols: list[tuple[int, str]] = []
        for j, h in enumerate(header[1:], start=1):
            m = _WIDE_HEAD.match(h)
            if not m:
                raise ValueError(
                    f"머리글 '{h}' 를 알아볼 수 없습니다. "
                    "긴 표는 '부품, 측정자, 측정값' 칸이, 넓은 표는 'A-1, A-2, B-1 …' "
                    "처럼 '측정자-회차' 머리글이 있어야 합니다."
                )
            op = (m.group(1) or m.group(3)).strip()
            cols.append((j, op))
        for n, r in enumerate(body, start=2):
            part = r[0]
            for j, op in cols:
                if j < len(r) and r[j]:
                    rows.append((part, op, _to_float(r[j], f"{n}번째 줄")))

    if not rows:
        raise ValueError("읽을 수 있는 측정값이 없습니다.")
    return build_study(rows)


def read_csv(path: str) -> Study:
    """CSV 파일을 읽는다. 엑셀이 저장한 CP949(ANSI) 파일도 받는다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc) as f:
                return parse_table(f.read())
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path} 의 글자 인코딩을 읽을 수 없습니다 (UTF-8 이나 CP949 로 저장).")


# ---------------------------------------------------------------------------
# 결과
# ---------------------------------------------------------------------------

@dataclass
class AnovaRow:
    source: str
    df: int
    ss: float
    ms: float
    f: Optional[float] = None
    p: Optional[float] = None


@dataclass
class GageResult:
    """분산 성분으로 정리한 결과. 단위는 측정값과 같다 (분산은 제곱)."""

    method: str                      # "ANOVA" | "평균·범위"
    study: Study
    var_ev: float                    # 반복성 σ²
    var_operator: float              # 측정자 σ²
    var_interaction: float           # 측정자×부품 σ²
    var_part: float                  # 부품간 σ²
    tolerance: Optional[float] = None
    process_sd: Optional[float] = None   # 공정 표준편차를 따로 알 때 (TV 대신)
    anova: list[AnovaRow] = field(default_factory=list)
    interaction_p: Optional[float] = None
    interaction_pooled: bool = False

    # --- 성분 -------------------------------------------------------------
    @property
    def var_av(self) -> float:
        return self.var_operator + self.var_interaction

    @property
    def var_grr(self) -> float:
        return self.var_ev + self.var_av

    @property
    def var_tv(self) -> float:
        if self.process_sd is not None:
            return self.process_sd ** 2
        return self.var_grr + self.var_part

    @property
    def ev(self) -> float:
        return math.sqrt(self.var_ev)

    @property
    def av(self) -> float:
        return math.sqrt(self.var_av)

    @property
    def grr(self) -> float:
        return math.sqrt(self.var_grr)

    @property
    def pv(self) -> float:
        if self.process_sd is not None:
            return math.sqrt(max(self.var_tv - self.var_grr, 0.0))
        return math.sqrt(self.var_part)

    @property
    def tv(self) -> float:
        return math.sqrt(self.var_tv)

    def components(self) -> list[tuple[str, float]]:
        """(이름, σ²) — 표와 그래프에 쓰는 순서."""
        out = [
            ("게이지 R&R", self.var_grr),
            ("  반복성 (EV)", self.var_ev),
            ("  재현성 (AV)", self.var_av),
        ]
        if self.method == "ANOVA" and not self.interaction_pooled:
            out += [("    측정자", self.var_operator),
                    ("    측정자×부품", self.var_interaction)]
        out += [("부품간 (PV)", self.pv ** 2), ("총변동 (TV)", self.var_tv)]
        return out

    # --- 비율 -------------------------------------------------------------
    def pct_study(self, var: float) -> float:
        """%연구변동 = σ / σ_TV."""
        return 100.0 * math.sqrt(var) / self.tv if self.tv > 0 else float("nan")

    def pct_contribution(self, var: float) -> float:
        """%기여도 = σ² / σ²_TV."""
        return 100.0 * var / self.var_tv if self.var_tv > 0 else float("nan")

    def pct_tolerance(self, var: float) -> Optional[float]:
        """%공차 = 6σ / (USL − LSL)."""
        if not self.tolerance:
            return None
        return 100.0 * STUDY_VAR_K * math.sqrt(var) / self.tolerance

    @property
    def pct_grr(self) -> float:
        return self.pct_study(self.var_grr)

    @property
    def pct_grr_tol(self) -> Optional[float]:
        return self.pct_tolerance(self.var_grr)

    @property
    def ndc(self) -> int:
        """구별 범주 수. AIAG: 1.41 × PV/GRR 를 버림, 최소 1."""
        if self.grr <= 0:
            return 99
        return max(1, int(math.floor(1.41 * self.pv / self.grr)))


def verdict_of(pct: Optional[float]) -> str:
    if pct is None or math.isnan(pct):
        return "-"
    if pct < LIMIT_OK:
        return "적합"
    if pct <= LIMIT_NG:
        return "조건부"
    return "부적합"


def overall_verdict(res: GageResult) -> tuple[str, list[str]]:
    """종합 판정과 그 이유. 가장 나쁜 항목을 따른다."""
    order = {"적합": 0, "조건부": 1, "부적합": 2}
    items = [("총변동 대비 %GRR", res.pct_grr)]
    if res.pct_grr_tol is not None:
        items.append(("공차 대비 %GRR", res.pct_grr_tol))
    worst = "적합"
    reasons = []
    for name, pct in items:
        v = verdict_of(pct)
        reasons.append(f"{name} {pct:.1f}% → {v}")
        if order[v] > order[worst]:
            worst = v
    if res.ndc < NDC_MIN:
        reasons.append(f"구별 범주 수 ndc = {res.ndc} (< {NDC_MIN}) → 제품 차이를 가르기 부족")
        if worst == "적합":
            worst = "조건부"
    else:
        reasons.append(f"구별 범주 수 ndc = {res.ndc} (≥ {NDC_MIN})")
    return worst, reasons


# ---------------------------------------------------------------------------
# ANOVA 법
# ---------------------------------------------------------------------------

def anova_method(
    study: Study,
    tolerance: Optional[float] = None,
    alpha_interaction: float = 0.05,
    process_sd: Optional[float] = None,
) -> GageResult:
    """2원 랜덤효과 ANOVA (부품 × 측정자, 교호작용 포함).

    교호작용의 p 값이 alpha_interaction 보다 크면 교호작용을 오차에 합쳐
    (pooling) 다시 계산한다. Minitab 의 기본값과 같은 0.05 를 쓴다.
    """
    p, o, n = study.n_parts, study.n_operators, study.trials
    vals = study.values()
    grand = sum(vals) / len(vals)

    pm = {pt: study.part_mean(pt) for pt in study.parts}
    om = {op: study.operator_mean(op) for op in study.operators}
    cm = {k: sum(v) / n for k, v in study.data.items()}

    ss_part = o * n * sum((m - grand) ** 2 for m in pm.values())
    ss_op = p * n * sum((m - grand) ** 2 for m in om.values())
    ss_cells = n * sum((m - grand) ** 2 for m in cm.values())
    ss_int = max(ss_cells - ss_part - ss_op, 0.0)
    ss_err = sum((v - cm[k]) ** 2 for k, vs in study.data.items() for v in vs)
    ss_tot = sum((v - grand) ** 2 for v in vals)

    df_part, df_op = p - 1, o - 1
    df_int, df_err = df_part * df_op, p * o * (n - 1)
    ms_part, ms_op = ss_part / df_part, ss_op / df_op
    ms_int, ms_err = ss_int / df_int, ss_err / df_err

    def ratio(a: float, b: float) -> float:
        if b > 0:
            return a / b
        return float("inf") if a > 0 else float("nan")

    f_int = ratio(ms_int, ms_err)
    p_int = f_pvalue(f_int, df_int, df_err)
    pooled = not (p_int <= alpha_interaction)   # nan 이어도 합친다

    if not pooled:
        f_part, f_op = ratio(ms_part, ms_int), ratio(ms_op, ms_int)
        table = [
            AnovaRow("부품", df_part, ss_part, ms_part, f_part,
                     f_pvalue(f_part, df_part, df_int)),
            AnovaRow("측정자", df_op, ss_op, ms_op, f_op,
                     f_pvalue(f_op, df_op, df_int)),
            AnovaRow("부품×측정자", df_int, ss_int, ms_int, f_int, p_int),
            AnovaRow("반복성(오차)", df_err, ss_err, ms_err),
            AnovaRow("합계", p * o * n - 1, ss_tot, float("nan")),
        ]
        var_ev = ms_err
        var_int = max((ms_int - ms_err) / n, 0.0)
        var_op = max((ms_op - ms_int) / (p * n), 0.0)
        var_part = max((ms_part - ms_int) / (o * n), 0.0)
    else:
        ss_e2, df_e2 = ss_err + ss_int, df_err + df_int
        ms_e2 = ss_e2 / df_e2
        f_part, f_op = ratio(ms_part, ms_e2), ratio(ms_op, ms_e2)
        table = [
            AnovaRow("부품", df_part, ss_part, ms_part, f_part,
                     f_pvalue(f_part, df_part, df_e2)),
            AnovaRow("측정자", df_op, ss_op, ms_op, f_op,
                     f_pvalue(f_op, df_op, df_e2)),
            AnovaRow("반복성(오차)", df_e2, ss_e2, ms_e2),
            AnovaRow("합계", p * o * n - 1, ss_tot, float("nan")),
        ]
        var_ev = ms_e2
        var_int = 0.0
        var_op = max((ms_op - ms_e2) / (p * n), 0.0)
        var_part = max((ms_part - ms_e2) / (o * n), 0.0)

    return GageResult(
        method="ANOVA", study=study, var_ev=var_ev, var_operator=var_op,
        var_interaction=var_int, var_part=var_part, tolerance=tolerance,
        process_sd=process_sd, anova=table, interaction_p=p_int,
        interaction_pooled=pooled,
    )


# ---------------------------------------------------------------------------
# 평균·범위 법 (AIAG MSA 4판 양식)
# ---------------------------------------------------------------------------

def xbar_r_method(
    study: Study,
    tolerance: Optional[float] = None,
    process_sd: Optional[float] = None,
) -> GageResult:
    """평균·범위 법. 측정자 수·부품 수가 15 를 넘으면 상수표가 없어 쓸 수 없다."""
    p, o, n = study.n_parts, study.n_operators, study.trials
    if p > 15 or o > 15:
        raise ValueError("평균·범위 법은 부품·측정자 15 이하에서만 계산합니다 (ANOVA 를 보세요).")

    r_bar_op = [
        sum(study.cell_range(pt, op) for pt in study.parts) / p
        for op in study.operators
    ]
    r_dbar = sum(r_bar_op) / o
    ev = r_dbar * k1(n)

    op_means = [study.operator_mean(op) for op in study.operators]
    x_diff = max(op_means) - min(op_means)
    av_sq = (x_diff * k_single(o)) ** 2 - ev ** 2 / (n * p)
    av_sq = max(av_sq, 0.0)

    part_means = [study.part_mean(pt) for pt in study.parts]
    rp = max(part_means) - min(part_means)
    pv = rp * k_single(p)

    return GageResult(
        method="평균·범위", study=study, var_ev=ev ** 2, var_operator=av_sq,
        var_interaction=0.0, var_part=pv ** 2, tolerance=tolerance,
        process_sd=process_sd,
    )


# ---------------------------------------------------------------------------
# 관리도 점검
# ---------------------------------------------------------------------------

@dataclass
class ChartCheck:
    r_bar: float
    ucl_r: float
    lcl_r: float
    x_bar: float
    ucl_x: float
    lcl_x: float
    out_r: list[tuple[str, str, float]]       # (부품, 측정자, 범위) — UCL 넘은 것
    pct_x_outside: float                      # X̄ 관리도 밖에 있는 점의 비율 [%]


def chart_check(study: Study) -> ChartCheck:
    """R 관리도: 점이 UCL 을 넘으면 그 반복 측정이 튄 것이다 (재측정 대상).
    X̄ 관리도: 점이 한계 '밖' 에 많을수록 좋다 (부품 차이를 잘 가른다는 뜻,
    AIAG 는 절반 이상을 권한다)."""
    n = study.trials
    ranges = {k: max(v) - min(v) for k, v in study.data.items()}
    r_bar = sum(ranges.values()) / len(ranges)
    means = {k: sum(v) / n for k, v in study.data.items()}
    x_bar = sum(means.values()) / len(means)
    ucl_r, lcl_r = _D4[n] * r_bar, _D3_CHART[n] * r_bar
    ucl_x, lcl_x = x_bar + _A2[n] * r_bar, x_bar - _A2[n] * r_bar
    out_r = [(p, o, r) for (p, o), r in ranges.items() if r > ucl_r + 1e-12]
    outside = sum(1 for m in means.values() if m > ucl_x or m < lcl_x)
    return ChartCheck(
        r_bar=r_bar, ucl_r=ucl_r, lcl_r=lcl_r, x_bar=x_bar, ucl_x=ucl_x,
        lcl_x=lcl_x, out_r=out_r, pct_x_outside=100.0 * outside / len(means),
    )


# ---------------------------------------------------------------------------
# 글자 보고서
# ---------------------------------------------------------------------------

def _fmt(x: Optional[float], digits: int = 5) -> str:
    if x is None or math.isnan(x):
        return ""
    if math.isinf(x):
        return "∞"
    return f"{x:.{digits}g}"


def format_gagerr_report(res: GageResult, xr: Optional[GageResult] = None) -> str:
    s = res.study
    lines = [
        "=" * 64,
        f" 게이지 R&R ({res.method} 법)",
        "=" * 64,
        f" 부품 {s.n_parts}개 × 측정자 {s.n_operators}명 × 반복 {s.trials}회"
        f" = {s.n_parts * s.n_operators * s.trials}개 측정값",
    ]
    if res.tolerance:
        lines.append(f" 공차 (USL−LSL) = {_fmt(res.tolerance)}")
    lines.append("")

    if res.anova:
        lines.append(" ANOVA 표")
        lines.append(f" {'요인':<12}{'자유도':>6}{'SS':>13}{'MS':>13}{'F':>10}{'p':>9}")
        for r in res.anova:
            p_txt = "" if r.p is None else f"{r.p:.3f}"
            lines.append(
                f" {r.source:<12}{r.df:>6}{_fmt(r.ss):>13}{_fmt(r.ms):>13}"
                f"{_fmt(r.f, 4):>10}{p_txt:>9}"
            )
        if res.interaction_pooled:
            lines.append(
                f" ※ 부품×측정자 교호작용 p = {res.interaction_p:.3f} 이 커서"
                " 오차에 합쳤다."
            )
        lines.append("")

    head = f" {'성분':<16}{'σ':>11}{'%기여도':>9}{'%연구변동':>10}"
    if res.tolerance:
        head += f"{'%공차':>8}"
    lines.append(head)
    for name, var in res.components():
        row = (f" {name:<16}{_fmt(math.sqrt(var)):>11}"
               f"{res.pct_contribution(var):>9.2f}{res.pct_study(var):>10.2f}")
        if res.tolerance:
            row += f"{res.pct_tolerance(var):>8.2f}"
        lines.append(row)
    lines.append("")

    verdict, reasons = overall_verdict(res)
    lines.append(f" 판정: {verdict}")
    for r in reasons:
        lines.append(f"   - {r}")

    cc = chart_check(s)
    if cc.out_r:
        lines.append(
            "   - R 관리도 UCL 을 넘은 반복 측정 "
            + ", ".join(f"{p}/{o}" for p, o, _ in cc.out_r)
            + " → 그 조합은 다시 재 볼 것"
        )
    lines.append(
        f"   - X̄ 관리도 한계 밖 점 {cc.pct_x_outside:.0f}% "
        + ("(50% 이상: 부품 차이를 잘 가른다)" if cc.pct_x_outside >= 50
           else "(50% 미만: 부품 차이에 비해 측정 흩어짐이 크다)")
    )

    if xr is not None:
        lines += [
            "",
            " 참고 — 평균·범위 법",
            f"   EV {_fmt(xr.ev)}   AV {_fmt(xr.av)}   GRR {_fmt(xr.grr)}"
            f"   PV {_fmt(xr.pv)}   TV {_fmt(xr.tv)}",
            f"   %GRR {xr.pct_grr:.1f}%   ndc {xr.ndc}",
        ]
    lines.append("=" * 64)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG 그래프 (내장 기능만)
# ---------------------------------------------------------------------------

#: 측정자별 색. 화면 쪽 CSS 가 --s1.. 을 밝은/어두운 화면에 맞게 정한다.
#: 3개까지는 색약에서도 서로 구별되는 조합이다. 그 이상은 점 모양으로도 구별한다.
_SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)",
           "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"]
_MARKERS = ["circle", "square", "diamond", "triangle"]


def _xml_esc(t: object) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + (abs(lo) * 0.01 or 1.0)
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    i0, i1 = math.floor(lo / step + 1e-9), math.ceil(hi / step - 1e-9)
    return [round(i * step, 12) for i in range(i0, i1 + 1)]


def _tick_text(v: float, ticks: list[float]) -> str:
    step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
    dec = 0
    while dec < 6 and abs(round(step, dec) - step) > step * 1e-6:
        dec += 1
    return f"{v:.{dec}f}"


def _marker(kind: str, x: float, y: float, color: str, tip: str) -> str:
    title = f"<title>{_xml_esc(tip)}</title>"
    ring = 'stroke="var(--panel)" stroke-width="2"'
    if kind == "square":
        return (f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" '
                f'fill="{color}" {ring}>{title}</rect>')
    if kind == "diamond":
        return (f'<path d="M{x:.1f},{y - 5.5:.1f} L{x + 5.5:.1f},{y:.1f} '
                f'L{x:.1f},{y + 5.5:.1f} L{x - 5.5:.1f},{y:.1f}Z" fill="{color}" '
                f'{ring}>{title}</path>')
    if kind == "triangle":
        return (f'<path d="M{x:.1f},{y - 5.5:.1f} L{x + 5:.1f},{y + 4:.1f} '
                f'L{x - 5:.1f},{y + 4:.1f}Z" fill="{color}" {ring}>{title}</path>')
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" '
            f'{ring}>{title}</circle>')


class _Frame:
    """축 하나짜리 그래프 틀."""

    W, H = 560, 300
    L, R, T, B = 74, 16, 14, 46

    def __init__(self, y_lo: float, y_hi: float, n_x: int, y_label: str = "",
                 floor: Optional[float] = None):
        pad = (y_hi - y_lo) * 0.08 or (abs(y_hi) * 0.01 or 1.0)
        lo = y_lo - pad if floor is None else max(y_lo - pad, floor)
        self.ticks = _nice_ticks(lo, y_hi + pad)
        self.y0, self.y1 = self.ticks[0], self.ticks[-1]
        self.n_x = n_x
        self.y_label = y_label
        self.parts: list[str] = []
        self._label_ys: list[float] = []
        self.labels: list[str] = []

    def x(self, i: float) -> float:
        span = self.W - self.L - self.R
        return self.L + span * (i + 0.5) / self.n_x

    def y(self, v: float) -> float:
        span = self.H - self.T - self.B
        return self.T + span * (1 - (v - self.y0) / (self.y1 - self.y0))

    def grid(self) -> None:
        for t in self.ticks:
            yy = self.y(t)
            self.parts.append(
                f'<line x1="{self.L}" x2="{self.W - self.R}" y1="{yy:.1f}" y2="{yy:.1f}" '
                f'stroke="var(--line)" stroke-width="1"/>'
                f'<text x="{self.L - 6}" y="{yy + 4:.1f}" text-anchor="end" '
                f'font-size="11" fill="var(--ink3)">{_tick_text(t, self.ticks)}</text>'
            )
        if self.y_label:
            self.parts.append(
                f'<text x="12" y="{(self.T + self.H - self.B) / 2:.0f}" font-size="11" '
                f'fill="var(--ink2)" text-anchor="middle" '
                f'transform="rotate(-90 12 {(self.T + self.H - self.B) / 2:.0f})">'
                f'{_xml_esc(self.y_label)}</text>'
            )

    def hline(self, v: float, label: str, dash: str = "5 4", strong: bool = False) -> None:
        yy = self.y(v)
        color = "var(--ink2)" if strong else "var(--ink3)"
        # 기준선끼리 가까우면 글자가 겹친다. 이미 쓴 글자와 12px 이상 떨어뜨린다.
        ty = yy - 4
        for _ in range(len(self._label_ys) + 1):
            hit = [u for u in self._label_ys if abs(u - ty) < 12]
            if not hit:
                break
            ty = max(hit) + 12 if ty >= yy - 4 else min(hit) - 12
        self._label_ys.append(ty)
        self.parts.append(
            f'<line x1="{self.L}" x2="{self.W - self.R}" y1="{yy:.1f}" y2="{yy:.1f}" '
            f'stroke="{color}" stroke-width="1.2" stroke-dasharray="{dash}"/>'
        )
        # 글자는 맨 위에 그리도록 따로 모아 둔다 (막대·점에 가리지 않게)
        self.labels.append(
            f'<text x="{self.W - self.R - 3}" y="{ty:.1f}" text-anchor="end" '
            f'font-size="10.5" fill="var(--ink2)" stroke="var(--panel)" '
            f'stroke-width="3" paint-order="stroke">{_xml_esc(label)}</text>'
        )

    def svg(self, extra_bottom: str = "") -> str:
        return (
            f'<svg viewBox="0 0 {self.W} {self.H}" width="100%" role="img" '
            f'style="display:block;font-family:inherit">'
            + "".join(self.parts) + "".join(self.labels) + extra_bottom + "</svg>"
        )


def legend_html(study: Study) -> str:
    items = []
    for i, op in enumerate(study.operators):
        color = _SERIES[i % len(_SERIES)]
        kind = _MARKERS[i % len(_MARKERS)]
        mk = _marker(kind, 8, 8, color, op)
        items.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px">'
            f'<svg width="16" height="16" viewBox="0 0 16 16">{mk}</svg>{_xml_esc(op)}</span>'
        )
    return f'<div style="font-size:12px;color:var(--ink2);margin:2px 0 6px">{"".join(items)}</div>'


def components_svg(res: GageResult) -> str:
    """성분별 %기여도·%연구변동·%공차 막대 그래프 (10%·30% 기준선 포함)."""
    groups = [
        ("게이지 R&R", res.var_grr),
        ("반복성", res.var_ev),
        ("재현성", res.var_av),
        ("부품간", res.pv ** 2),
    ]
    series = [("%기여도", res.pct_contribution, "var(--s1)"),
              ("%연구변동", res.pct_study, "var(--s2)")]
    if res.tolerance:
        series.append(("%공차", res.pct_tolerance, "var(--s3)"))

    top = max([110.0] + [fn(v) or 0 for _, v in groups for _, fn, _ in series])
    fr = _Frame(0, top, len(groups), "%")
    fr.ticks = [t for t in _nice_ticks(0, top)]
    fr.y0, fr.y1 = 0.0, fr.ticks[-1]
    fr.grid()
    fr.hline(LIMIT_OK, "10%")
    fr.hline(LIMIT_NG, "30%")

    slot = (fr.W - fr.L - fr.R) / len(groups)
    bw = min(34.0, (slot - 18) / len(series) - 2)
    for gi, (name, var) in enumerate(groups):
        cx = fr.x(gi)
        x0 = cx - (bw + 2) * len(series) / 2
        for si, (sname, fn, color) in enumerate(series):
            val = fn(var) or 0.0
            yy = fr.y(val)
            base = fr.y(0)
            h = max(base - yy, 0.0)
            bx = x0 + si * (bw + 2) + 1
            r = min(4.0, h)
            # 위쪽만 둥근 막대
            path = (f"M{bx:.1f},{base:.1f} L{bx:.1f},{yy + r:.1f} "
                    f"Q{bx:.1f},{yy:.1f} {bx + r:.1f},{yy:.1f} "
                    f"L{bx + bw - r:.1f},{yy:.1f} Q{bx + bw:.1f},{yy:.1f} "
                    f"{bx + bw:.1f},{yy + r:.1f} L{bx + bw:.1f},{base:.1f}Z")
            fr.parts.append(
                f'<path d="{path}" fill="{color}"><title>{_xml_esc(name)} {sname} '
                f'{val:.1f}%</title></path>'
            )
        fr.parts.append(
            f'<text x="{cx:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--ink2)">{_xml_esc(name)}</text>'
        )
    fr.parts.append(
        f'<line x1="{fr.L}" x2="{fr.W - fr.R}" y1="{fr.y(0):.1f}" y2="{fr.y(0):.1f}" '
        f'stroke="var(--ink3)" stroke-width="1"/>'
    )
    legend = "".join(
        f'<rect x="{fr.L + i * 96}" y="{fr.H - 16}" width="10" height="10" rx="2" '
        f'fill="{c}"/><text x="{fr.L + i * 96 + 14}" y="{fr.H - 7}" font-size="11" '
        f'fill="var(--ink2)">{_xml_esc(n)}</text>'
        for i, (n, _, c) in enumerate(series)
    )
    return fr.svg(legend)


def _by_operator_svg(study: Study, values: dict, center: float, ucl: float,
                     lcl: float, y_label: str, what: str,
                     floor: Optional[float] = None) -> str:
    """측정자별로 칸을 나눠 부품 순서대로 점을 찍는 관리도."""
    p, o = study.n_parts, study.n_operators
    gap = 1
    n_x = o * p + gap * (o - 1)
    vals = list(values.values())
    fr = _Frame(min(vals + [lcl, center]), max(vals + [ucl, center]), n_x, y_label,
                floor)
    fr.grid()
    fr.hline(ucl, f"UCL {_fmt(ucl, 6)}")
    fr.hline(center, f"중심 {_fmt(center, 6)}", dash="0", strong=True)
    if lcl >= fr.y0:
        fr.hline(lcl, f"LCL {_fmt(lcl, 6)}")

    for oi, op in enumerate(study.operators):
        color = _SERIES[oi % len(_SERIES)]
        kind = _MARKERS[oi % len(_MARKERS)]
        xs = [oi * (p + gap) + pi for pi in range(p)]
        pts = [(fr.x(x), fr.y(values[(pt, op)])) for x, pt in zip(xs, study.parts)]
        fr.parts.append(
            '<polyline fill="none" stroke="' + color + '" stroke-width="2" points="'
            + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>'
        )
        for (a, b), pt in zip(pts, study.parts):
            fr.parts.append(_marker(kind, a, b, color,
                                    f"{op} · 부품 {pt} · {what} {_fmt(values[(pt, op)])}"))
        mid = (fr.x(xs[0]) + fr.x(xs[-1])) / 2
        fr.parts.append(
            f'<text x="{mid:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--ink2)">측정자 {_xml_esc(op)}</text>'
        )
    return fr.svg()


def r_chart_svg(study: Study) -> str:
    cc = chart_check(study)
    ranges = {k: max(v) - min(v) for k, v in study.data.items()}
    return _by_operator_svg(study, ranges, cc.r_bar, cc.ucl_r, cc.lcl_r, "범위 R", "범위",
                            floor=0.0)


def xbar_chart_svg(study: Study) -> str:
    cc = chart_check(study)
    means = {k: sum(v) / len(v) for k, v in study.data.items()}
    return _by_operator_svg(study, means, cc.x_bar, cc.ucl_x, cc.lcl_x, "평균 X̄", "평균")


def interaction_svg(study: Study) -> str:
    """부품별 측정자 평균. 선이 나란하면 교호작용이 없다."""
    means = {k: sum(v) / len(v) for k, v in study.data.items()}
    vals = list(means.values())
    fr = _Frame(min(vals), max(vals), study.n_parts, "평균")
    fr.grid()
    for oi, op in enumerate(study.operators):
        color = _SERIES[oi % len(_SERIES)]
        kind = _MARKERS[oi % len(_MARKERS)]
        pts = [(fr.x(i), fr.y(means[(pt, op)])) for i, pt in enumerate(study.parts)]
        fr.parts.append(
            '<polyline fill="none" stroke="' + color + '" stroke-width="2" points="'
            + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>'
        )
        for (a, b), pt in zip(pts, study.parts):
            fr.parts.append(_marker(kind, a, b, color,
                                    f"{op} · 부품 {pt} · 평균 {_fmt(means[(pt, op)])}"))
    for i, pt in enumerate(study.parts):
        fr.parts.append(
            f'<text x="{fr.x(i):.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="11.5" fill="var(--ink2)">{_xml_esc(pt)}</text>'
        )
    fr.parts.append(
        f'<text x="{(fr.L + fr.W - fr.R) / 2:.0f}" y="{fr.H - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--ink3)">부품</text>'
    )
    return fr.svg()


def by_part_svg(study: Study) -> str:
    """부품별 측정값 전체 (점) 과 부품 평균 (가로선)."""
    vals = study.values()
    fr = _Frame(min(vals), max(vals), study.n_parts, "측정값")
    fr.grid()
    o = study.n_operators
    for i, pt in enumerate(study.parts):
        cx = fr.x(i)
        slot = (fr.W - fr.L - fr.R) / study.n_parts
        for oi, op in enumerate(study.operators):
            color = _SERIES[oi % len(_SERIES)]
            kind = _MARKERS[oi % len(_MARKERS)]
            dx = (oi - (o - 1) / 2) * min(9.0, slot / (o + 1))
            for t, v in enumerate(study.data[(pt, op)], start=1):
                fr.parts.append(_marker(kind, cx + dx, fr.y(v), color,
                                        f"부품 {pt} · {op} · {t}회 · {_fmt(v)}"))
        m = study.part_mean(pt)
        fr.parts.append(
            f'<line x1="{cx - slot * 0.38:.1f}" x2="{cx + slot * 0.38:.1f}" '
            f'y1="{fr.y(m):.1f}" y2="{fr.y(m):.1f}" stroke="var(--ink)" stroke-width="2">'
            f'<title>부품 {_xml_esc(pt)} 평균 {_fmt(m)}</title></line>'
        )
        fr.parts.append(
            f'<text x="{cx:.1f}" y="{fr.H - fr.B + 18}" text-anchor="middle" '
            f'font-size="11.5" fill="var(--ink2)">{_xml_esc(pt)}</text>'
        )
    fr.parts.append(
        f'<text x="{(fr.L + fr.W - fr.R) / 2:.0f}" y="{fr.H - 8}" text-anchor="middle" '
        f'font-size="11" fill="var(--ink3)">부품</text>'
    )
    return fr.svg()


# ---------------------------------------------------------------------------
# 예제 데이터
# ---------------------------------------------------------------------------

#: 임펠러 외경 [mm] — 임펠러 10개, 측정자 3명(A·B·C), 3회씩.
#: 도면 치수 Ø250.00 ±0.05 (공차 0.10 mm). 웹 화면이 처음 열릴 때 쓴다.
EXAMPLE_CSV = """부품,A-1,A-2,A-3,B-1,B-2,B-3,C-1,C-2,C-3
1,250.012,250.016,250.013,250.019,250.015,250.021,250.010,250.008,250.013
2,249.981,249.985,249.979,249.988,249.990,249.984,249.979,249.976,249.982
3,250.031,250.027,250.030,250.036,250.034,250.038,250.028,250.031,250.026
4,250.004,250.001,250.007,250.010,250.006,250.009,250.000,250.003,249.999
5,249.968,249.972,249.970,249.977,249.973,249.979,249.966,249.969,249.965
6,250.022,250.019,250.024,250.027,250.030,250.025,250.017,250.021,250.020
7,249.994,249.990,249.993,250.000,249.997,250.002,249.989,249.992,249.987
8,250.040,250.044,250.041,250.048,250.045,250.043,250.037,250.039,250.042
9,249.959,249.955,249.960,249.964,249.968,249.963,249.953,249.956,249.958
10,250.009,250.006,250.011,250.015,250.012,250.017,250.003,250.007,250.005
"""
EXAMPLE_LSL = 249.95
EXAMPLE_USL = 250.05


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------

def _tolerance(lsl: Optional[float], usl: Optional[float],
               tol: Optional[float]) -> Optional[float]:
    if tol is not None:
        if tol <= 0:
            raise ValueError("공차는 0 보다 커야 합니다.")
        return tol
    if lsl is not None and usl is not None:
        if usl <= lsl:
            raise ValueError("상한(USL)이 하한(LSL)보다 커야 합니다.")
        return usl - lsl
    return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m turbochiller.gagerr",
        description="게이지 R&R (AIAG MSA) — ANOVA 법과 평균·범위 법",
    )
    ap.add_argument("csv", nargs="?", help="측정 데이터 CSV (없으면 예제 데이터)")
    ap.add_argument("--lsl", type=float, help="규격 하한")
    ap.add_argument("--usl", type=float, help="규격 상한")
    ap.add_argument("--tol", type=float, help="공차 폭 (USL−LSL). --lsl/--usl 대신")
    ap.add_argument("--process-sd", type=float,
                    help="공정 표준편차를 따로 알 때 (총변동 대신 씀)")
    ap.add_argument("--alpha", type=float, default=0.05,
                    help="교호작용을 오차에 합치는 기준 p 값 (기본 0.05)")
    args = ap.parse_args(argv)

    try:
        if args.csv:
            study = read_csv(args.csv)
            tol = _tolerance(args.lsl, args.usl, args.tol)
        else:
            print("(데이터 파일을 안 줘서 예제 — 임펠러 외경 — 로 계산합니다)\n")
            study = parse_table(EXAMPLE_CSV)
            tol = _tolerance(args.lsl, args.usl, args.tol) or (EXAMPLE_USL - EXAMPLE_LSL)
        res = anova_method(study, tol, args.alpha, args.process_sd)
        try:
            xr = xbar_r_method(study, tol, args.process_sd)
        except ValueError:
            xr = None
    except (OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(format_gagerr_report(res, xr))
    return 0


# ==========================================================================
# webui.py
# ==========================================================================

import html as html_mod
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


#: 이미 떠 있는 프로그램을 찾을 때 뒤져볼 포트 범위
PORT_RANGE = range(8765, 8785)

#: /ping 이 돌려주는 표시. 우리 프로그램인지 확인하는 용도.
PING_TOKEN = "turbochiller-ok"

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

    Field("show_retrofit", "냉매 교체 검토 (같은 압축기)", False, "check",
          group="기타",
          hint="지금 냉매로 만든 기계에 다른 냉매를 넣으면 어떻게 되는지"),
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
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px}
.cell{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--bg)}
.cap{font-size:12.5px;font-weight:600;color:var(--ink2);margin-bottom:6px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}
.quit{flex:0 0 auto;padding:7px 15px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink2);text-decoration:none;font-size:13px;
  font-weight:600;white-space:nowrap}
.quit:hover{border-color:var(--warn);color:var(--warn)}
.bye{max-width:520px;margin:12vh auto;text-align:center;padding:26px;
  background:var(--panel);border:1px solid var(--line);border-radius:12px}
.bye h1{font-size:19px;margin-bottom:8px}
/* --- 위쪽 메뉴 (사이클 해석 / 게이지 R&R) --- */
.nav{display:flex;gap:6px;margin:0 0 12px}
.nav a{padding:6px 13px;border:1px solid var(--line);border-radius:999px;
  color:var(--ink2);text-decoration:none;font-size:13px;font-weight:600;
  background:var(--panel)}
.nav a.on{background:var(--accent);border-color:var(--accent);color:#fff}
/* --- 게이지 R&R --- */
:root{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;
      --s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948}
@media (prefers-color-scheme: dark){
  :root{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;
        --s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767}
}
textarea{width:100%;min-height:230px;padding:8px 9px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--ink);font-size:12px;
  font-family:Consolas,'D2Coding',ui-monospace,monospace;line-height:1.45;
  white-space:pre;overflow:auto}
input[type=text]{width:100%;padding:7px 9px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--ink);font-size:14px;
  font-family:inherit}
.badge{display:inline-block;padding:3px 12px;border-radius:999px;font-weight:700;
  font-size:15px;border:1px solid}
.badge.ok{color:#0d6e4b;background:#e3f6ee;border-color:#a9e2cb}
.badge.mid{color:#7a4a00;background:#fdf2dc;border-color:#f0d39a}
.badge.ng{color:#8a1d18;background:#fdecea;border-color:#f5c2bd}
@media (prefers-color-scheme: dark){
  .badge.ok{color:#7fe0b8;background:#0f2f23;border-color:#1e5a43}
  .badge.mid{color:#ffcf7a;background:#33250c;border-color:#5b4416}
  .badge.ng{color:#ffb3ab;background:#3a1512;border-color:#5e241e}
}
.reasons{margin:10px 0 0;padding-left:18px;color:var(--ink2);font-size:13px}
.guide{color:var(--ink2);font-size:12.5px}
.guide b{color:var(--ink)}
/* --- 폰 화면 --- */
@media (max-width:900px){
  /* 결과를 먼저 보여준다. 입력칸이 20개라 그게 먼저 나오면
     결과까지 한참 스크롤해야 한다. */
  .wrap{flex-direction:column;padding:12px 12px 72px}
  aside{position:static;flex:1 1 auto;width:100%;order:2}
  main{order:1;width:100%}
  h1{font-size:19px}
  .metric .v{font-size:22px}
  .card{padding:13px}
  /* 표가 화면보다 넓으면 카드 안에서만 옆으로 넘긴다.
     페이지 전체가 가로로 밀리지 않게 한다. */
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .scroll table{min-width:520px}
  .grid2{grid-template-columns:1fr}
  /* 입력칸으로 바로 내려가는 단추 */
  .jump{position:fixed;right:14px;bottom:14px;z-index:9;
        padding:12px 18px;border-radius:999px;background:var(--accent);
        color:#fff;text-decoration:none;font-size:14px;font-weight:700;
        box-shadow:0 3px 12px rgba(0,0,0,.28)}
}
@media (min-width:901px){ .jump{display:none} }
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
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


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

    # 냉매 교체 검토 (같은 압축기)
    if values.get("show_retrofit"):
        out.append(_retrofit_section(res, inp, values))

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


#: 냉매 교체 검토에서 비교할 냉매들
RETROFIT_CANDIDATES = [
    "R134a", "R1234ze(E)", "R1234yf", "R513A.mix", "R1233zd(E)", "R245fa",
]


def _retrofit_section(res: CycleResult, inp: CycleInput, values: dict) -> str:
    """같은 압축기에 냉매만 바꿨을 때의 비교."""
    out = ['<div class="card"><h2>냉매 교체 검토 — 같은 압축기</h2>']

    # 지금 냉매를 맨 앞에 두고, 나머지를 뒤에 붙인다
    order = [inp.refrigerant] + [
        r for r in RETROFIT_CANDIDATES if r != inp.refrigerant
    ]
    try:
        machine, points = retrofit(inp, order, stages=res.stages)
    except (ValueError, RuntimeError) as exc:
        return f'<div class="card"><div class="msg err">비교 실패: {esc(exc)}</div></div>'

    out.append(
        '<p class="note" style="margin:0 0 10px">'
        f'기준 <b>{esc(machine.source_refrigerant)}</b> 로 만든 기계에 '
        "다른 냉매를 넣었을 때입니다. 운전조건(증발 "
        f"{inp.te:.1f}°C / 응축 {inp.tc:.1f}°C)은 그대로 두고, "
        "압축기에서 <b>흡입 체적유량 "
        f"{machine.suction_volume_flow_m3h:,.0f} m³/h</b> 와 "
        f"<b>단위질량당 일 {machine.total_work:.2f} kJ/kg</b> 를 고정했습니다."
        "</p>"
    )

    rows = []
    for p in points:
        if not p.ok:
            rows.append([p.refrigerant, "—", "—", "—", "—", "—", "—", "—", "—",
                         p.message])
            continue
        rows.append([
            p.refrigerant,
            f"{p.suction_density:.2f}",
            f"{p.volumetric_capacity:,.0f}",
            f"{p.capacity_rt:.1f}",
            f"{p.capacity_ratio * 100:.0f}%",
            f"{p.pressure_ratio:.2f}",
            f"{p.shaft_power:.1f}",
            f"{p.cop:.3f}",
            f"{p.cop_ratio * 100:.0f}%",
            f"{p.head_margin * 100:+.0f}%",
        ])
    out.append(_table(
        ["냉매", "흡입밀도 [kg/m³]", "체적능력 [kJ/m³]", "능력 [RT]", "능력비",
         "압축비", "축동력 [kW]", "COP", "COP비", "헤드여유"],
        rows,
    ))

    for p in points:
        if p.ok and p.message:
            out.append(f'<div class="msg warn">{esc(p.refrigerant)}: {esc(p.message)}</div>')

    out.append(
        '<p class="note"><b>체적능력</b>은 흡입 1 m³ 당 낼 수 있는 냉동능력입니다. '
        "같은 기계라면 능력이 이 값에 비례합니다. "
        "<b>헤드여유</b>가 음수면 그 응축온도를 만들지 못합니다.<br>"
        "설계점 근처에서만 맞는 근사입니다. 냉매가 바뀌면 마하수가 달라져 "
        "실제로는 효율도 조금 변합니다.</p>"
    )

    # 냉매별 P-h 선도
    out.append('<h2 style="margin-top:20px">냉매별 P-h 선도</h2>')
    out.append('<div class="grid2">')
    for p in points:
        if not p.ok or p.result is None:
            continue
        out.append('<div class="cell">')
        out.append(
            f'<div class="cap">{esc(p.refrigerant)} &nbsp;·&nbsp; '
            f"{p.capacity_rt:.1f} RT ({p.capacity_ratio * 100:.0f}%) "
            f"&nbsp;·&nbsp; 압축비 {p.pressure_ratio:.2f} "
            f"&nbsp;·&nbsp; {p.shaft_power:.1f} kW</div>"
        )
        out.append(ph_diagram_svg(
            p.result,
            options=ChartOptions(
                width=560, height=400, isochores=False, legend=False,
            ),
        ))
        out.append("</div>")
    out.append("</div></div>")
    return "".join(out)


def render_page(query: dict[str, list[str]], hosted: bool = False) -> str:
    values = parse_query(query)
    try:
        inp, stages = build_input(values)
        res = solve(inp, stages=stages)
        body = render_results(res, values)
    except (ValueError, RuntimeError) as exc:
        body = (
            f'<div class="msg err"><b>계산할 수 없는 조건입니다.</b><br>{esc(exc)}</div>'
        )

    # 인터넷에 올린 경우에는 '종료' 를 빼둔다.
    # 누구든 눌러 서버를 내릴 수 있으면 안 된다.
    quit_button = (
        "" if hosted
        else '<a class="quit" href="/quit" title="프로그램을 완전히 끝냅니다">종료</a>'
    )
    # 폰에서는 입력칸이 결과 아래로 내려가므로 '왼쪽' 이라고 하면 안 맞는다
    hint = "값을 고치고 '다시 계산'을 누르세요. (폰에서는 아래쪽에 입력칸이 있습니다)"

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>터보 냉동기 사이클 해석</title>
<style>{STYLE}</style>
</head><body>
<div class="wrap">
  <aside id="inputs"><div class="card">{render_form(values)}</div></aside>
  <main>
    {nav_html("cycle")}
    <div class="head">
      <div>
        <h1>터보 냉동기 사이클 해석</h1>
        <p class="sub">{hint}</p>
      </div>
      {quit_button}
    </div>
    {body}
  </main>
</div>
<a class="jump" href="#inputs">입력값 고치기 ↓</a>
</body></html>"""


def nav_html(current: str) -> str:
    """위쪽 메뉴. 두 화면을 오간다."""
    items = [("cycle", "/", "사이클 해석"), ("gagerr", "/gagerr", "게이지 R&R")]
    links = []
    for key, href, label in items:
        on = ' class="on"' if key == current else ""
        links.append(f'<a href="{href}"{on}>{esc(label)}</a>')
    return '<nav class="nav">' + "".join(links) + "</nav>"


# ---------------------------------------------------------------------------
# 게이지 R&R 화면
# ---------------------------------------------------------------------------

GAGERR_GUIDE = """
<p class="guide"><b>데이터 붙여넣기</b> — 엑셀에서 표를 그대로 복사해 붙이면 됩니다.
두 가지 모양을 받습니다.</p>
<p class="guide">· 넓은 표: 첫 칸 <b>부품</b>, 나머지 머리글 <b>A-1, A-2, B-1 …</b>
(측정자-회차)<br>
· 긴 표: 머리글에 <b>부품, 측정자, 측정값</b> (반복 칸은 있어도 됨)</p>
<p class="guide">보통 <b>부품 10개 × 측정자 3명 × 3회</b>.
부품은 실제 공정 산포를 대표하도록 고르고, 순서는 섞어서 잰다.</p>
"""


def _opt_float(query: dict[str, list[str]], key: str) -> Optional[float]:
    raw = (query.get(key, [""])[0] or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"'{raw}' 를 숫자로 읽을 수 없습니다.") from None


def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.2f}"


def _num(x: float) -> str:
    return f"{x:.5g}"


def render_gagerr_results(res: "gagerr.GageResult",
                          xr: Optional["gagerr.GageResult"]) -> str:
    s = res.study
    verdict, reasons = gagerr.overall_verdict(res)
    cls = {"적합": "ok", "조건부": "mid", "부적합": "ng"}[verdict]
    cc = gagerr.chart_check(s)
    if cc.out_r:
        reasons.append(
            "R 관리도 UCL 을 넘은 반복 측정: "
            + ", ".join(f"부품 {p}/측정자 {o}" for p, o, _ in cc.out_r)
            + " — 그 조합은 다시 재 보세요"
        )
    reasons.append(
        f"X̄ 관리도 한계 밖 점 {cc.pct_x_outside:.0f}% — "
        + ("부품 차이를 잘 가릅니다 (50% 이상)" if cc.pct_x_outside >= 50
           else "부품 차이에 비해 측정 흩어짐이 큽니다 (50% 미만)")
    )

    out = ['<div class="card">']
    out.append(
        f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
        f'<span class="badge {cls}">{esc(verdict)}</span>'
        f'<span class="sub" style="margin:0">ANOVA 법 · 부품 {s.n_parts}개 × '
        f'측정자 {s.n_operators}명 × {s.trials}회 = '
        f'{s.n_parts * s.n_operators * s.trials}개</span></div>'
    )
    out.append('<div class="metrics" style="margin-top:12px">')
    out.append(_metric("%GRR (총변동 대비)", f"{res.pct_grr:.1f}", "%"))
    if res.pct_grr_tol is not None:
        out.append(_metric("%GRR (공차 대비)", f"{res.pct_grr_tol:.1f}", "%"))
    out.append(_metric("구별 범주 수 ndc", f"{res.ndc}"))
    out.append(_metric("반복성 EV (σ)", _num(res.ev)))
    out.append(_metric("재현성 AV (σ)", _num(res.av)))
    out.append("</div>")
    out.append('<ul class="reasons">' + "".join(f"<li>{esc(r)}</li>" for r in reasons)
               + "</ul>")
    out.append(
        '<p class="note">판정 기준 (AIAG MSA): %GRR 10% 미만 적합 · 10~30% 조건부 · '
        '30% 초과 부적합, ndc 5 이상. 연구변동 = 6σ.</p></div>'
    )

    # 분산 성분 표
    headers = ["", "성분", "σ", "6σ", "%기여도", "%연구변동"]
    if res.tolerance:
        headers.append("%공차")
    rows = []
    for name, var in res.components():
        sd = math.sqrt(var)
        r = ["", name.strip(), _num(sd), _num(6 * sd),
             _pct(res.pct_contribution(var)), _pct(res.pct_study(var))]
        if res.tolerance:
            r.append(_pct(res.pct_tolerance(var)))
        rows.append(r)
    out.append('<div class="card"><h2>분산 성분</h2>')
    out.append(_table(headers, rows))
    out.append("</div>")

    # 그래프
    out.append('<div class="card"><h2>그래프</h2>')
    out.append(gagerr.legend_html(s))
    out.append('<div class="grid2">')
    charts = [
        ("변동 성분 — 게이지 R&R 막대가 낮을수록 좋다", gagerr.components_svg(res)),
        ("측정값 — 부품별 (가로선 = 부품 평균)", gagerr.by_part_svg(s)),
        ("R 관리도 — 점이 UCL 안에 있어야 한다", gagerr.r_chart_svg(s)),
        ("X̄ 관리도 — 점이 한계 밖에 많을수록 좋다", gagerr.xbar_chart_svg(s)),
        ("측정자×부품 — 선이 나란하면 교호작용이 없다", gagerr.interaction_svg(s)),
    ]
    for cap, svg in charts:
        out.append(f'<div class="cell"><div class="cap">{esc(cap)}</div>{svg}</div>')
    out.append("</div></div>")

    # ANOVA 표
    out.append('<div class="card"><h2>ANOVA 표</h2>')
    out.append(_table(
        ["", "요인", "자유도", "SS", "MS", "F", "p"],
        [["", r.source, str(r.df), _num(r.ss),
          "" if math.isnan(r.ms) else _num(r.ms),
          "" if r.f is None else ("∞" if math.isinf(r.f) else f"{r.f:.4g}"),
          "" if r.p is None or math.isnan(r.p) else f"{r.p:.3f}"]
         for r in res.anova],
    ))
    if res.interaction_pooled:
        out.append(
            f'<p class="note">부품×측정자 교호작용 p = {res.interaction_p:.3f} '
            f'(> α) 이라 오차에 합쳐서 계산했습니다.</p>'
        )
    else:
        out.append(
            f'<p class="note">부품×측정자 교호작용 p = {res.interaction_p:.3f} — '
            '측정자에 따라 부품을 다르게 재고 있습니다. 측정 방법(위치·방향·힘)을 '
            '통일했는지 확인하세요.</p>'
        )
    out.append("</div>")

    # 평균·범위 법
    if xr is not None:
        rows = [["", "반복성 EV", _num(xr.ev), _pct(xr.pct_study(xr.var_ev))],
                ["", "재현성 AV", _num(xr.av), _pct(xr.pct_study(xr.var_av))],
                ["", "게이지 R&R", _num(xr.grr), _pct(xr.pct_grr)],
                ["", "부품간 PV", _num(xr.pv), _pct(xr.pct_study(xr.pv ** 2))],
                ["", "총변동 TV", _num(xr.tv), "100.00"]]
        out.append('<div class="card"><h2>참고 — 평균·범위 법 (AIAG 양식)</h2>')
        out.append(_table(["", "성분", "σ", "%연구변동"], rows))
        out.append(
            f'<p class="note">ndc = {xr.ndc}. 손계산·엑셀 양식과 맞춰볼 때 쓰세요. '
            '교호작용을 분리하지 못하므로 판정은 ANOVA 법을 따릅니다.</p></div>'
        )
    return "".join(out)


def render_gagerr_page(query: dict[str, list[str]], hosted: bool = False) -> str:
    first_visit = "data" not in query
    data = gagerr.EXAMPLE_CSV if first_visit else query.get("data", [""])[0]
    lsl_txt = (str(gagerr.EXAMPLE_LSL) if first_visit
               else (query.get("lsl", [""])[0] or "").strip())
    usl_txt = (str(gagerr.EXAMPLE_USL) if first_visit
               else (query.get("usl", [""])[0] or "").strip())
    alpha_txt = (query.get("alpha", ["0.05"])[0] or "0.05").strip()
    psd_txt = (query.get("process_sd", [""])[0] or "").strip()

    try:
        lsl = _opt_float(query, "lsl") if not first_visit else gagerr.EXAMPLE_LSL
        usl = _opt_float(query, "usl") if not first_visit else gagerr.EXAMPLE_USL
        alpha = _opt_float(query, "alpha") or 0.05
        if not 0 < alpha < 1:
            raise ValueError("교호작용 기준 α 는 0 과 1 사이여야 합니다.")
        psd = _opt_float(query, "process_sd")
        if psd is not None and psd <= 0:
            raise ValueError("공정 표준편차는 0 보다 커야 합니다.")
        if (lsl is None) != (usl is None):
            raise ValueError("공차를 쓰려면 하한(LSL)과 상한(USL)을 둘 다 넣으세요.")
        tol = gagerr._tolerance(lsl, usl, None)
        study = gagerr.parse_table(data)
        res = gagerr.anova_method(study, tol, alpha, psd)
        try:
            xr: Optional[gagerr.GageResult] = gagerr.xbar_r_method(study, tol, psd)
        except ValueError:
            xr = None
        body = render_gagerr_results(res, xr)
    except ValueError as exc:
        body = f'<div class="msg err"><b>계산할 수 없습니다.</b><br>{esc(exc)}</div>'

    if first_visit:
        body = (
            '<div class="msg warn">예제 데이터(임펠러 외경 Ø250 ±0.05 mm)로 계산한 '
            '결과입니다. 내 데이터를 붙여넣고 \'계산\' 을 누르세요.</div>' + body
        )

    form = f"""<form method="get" action="/gagerr">
<fieldset><legend>측정 데이터</legend>
<label><textarea name="data" spellcheck="false">{esc(data)}</textarea></label>
</fieldset>
<fieldset><legend>규격 (선택)</legend>
<label><span class="t">규격 하한 LSL</span>
<input type="text" inputmode="decimal" name="lsl" value="{esc(lsl_txt)}"></label>
<label><span class="t">규격 상한 USL</span>
<input type="text" inputmode="decimal" name="usl" value="{esc(usl_txt)}">
<span class="hint">비워두면 %공차 없이 총변동 대비로만 판정</span></label>
</fieldset>
<fieldset><legend>고급</legend>
<label><span class="t">공정 표준편차 σ (선택)</span>
<input type="text" inputmode="decimal" name="process_sd" value="{esc(psd_txt)}">
<span class="hint">시료가 공정 산포를 대표하지 못할 때. 넣으면 총변동 대신 씀</span></label>
<label><span class="t">교호작용 합침 기준 α</span>
<input type="text" inputmode="decimal" name="alpha" value="{esc(alpha_txt)}">
<span class="hint">p 값이 이보다 크면 교호작용을 오차에 합침 (Minitab 기본 0.05)</span></label>
</fieldset>
<button type="submit">계산</button>
</form>{GAGERR_GUIDE}"""

    quit_button = (
        "" if hosted
        else '<a class="quit" href="/quit" title="프로그램을 완전히 끝냅니다">종료</a>'
    )
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>게이지 R&amp;R</title>
<style>{STYLE}</style>
</head><body>
<div class="wrap">
  <aside id="inputs" style="flex-basis:340px"><div class="card">{form}</div></aside>
  <main>
    {nav_html("gagerr")}
    <div class="head">
      <div>
        <h1>게이지 R&amp;R — 측정시스템 분석</h1>
        <p class="sub">측정기가 제품 차이를 가를 만큼 믿을 만한지 봅니다.
        (AIAG MSA 4판, ANOVA 법)</p>
      </div>
      {quit_button}
    </div>
    {body}
  </main>
</div>
<a class="jump" href="#inputs">데이터 고치기 ↓</a>
</body></html>"""


# ---------------------------------------------------------------------------
# 서버
# ---------------------------------------------------------------------------

BYE_PAGE = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>종료했습니다</title><style>{STYLE}</style></head>
<body><div class="bye">
  <h1>프로그램을 종료했습니다</h1>
  <p class="sub">이 탭은 닫으셔도 됩니다.<br>
     다시 쓰시려면 실행 파일을 두 번 누르세요.</p>
</div></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "turbochiller"

    def do_GET(self) -> None:  # noqa: N802  (내장 클래스가 정한 이름)
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # 이미 떠 있는 우리 프로그램인지 확인하는 용도
        if parsed.path == "/ping":
            self._send(PING_TOKEN.encode(), "text/plain; charset=utf-8")
            return

        if parsed.path == "/quit":
            self._send(BYE_PAGE.encode("utf-8"))
            # 응답을 보낸 뒤에 서버를 내린다
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        try:
            if parsed.path.rstrip("/") == "/gagerr":
                page = render_gagerr_page(query)
            else:
                page = render_page(query)
        except Exception as exc:  # 어떤 오류든 화면에 보여준다
            page = (
                "<!doctype html><meta charset='utf-8'>"
                "<body style='font-family:sans-serif;padding:24px'>"
                f"<h2>오류가 났습니다</h2><pre>{html_mod.escape(repr(exc))}</pre>"
                "</body>"
            )
        self._send(page.encode("utf-8"))

    def _send(self, data: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass   # 브라우저가 먼저 닫은 경우

    def log_message(self, *args) -> None:
        """요청 로그는 찍지 않는다 (창을 깨끗하게)."""


# ---------------------------------------------------------------------------
# 포트 찾기 / 이미 떠 있는지 확인
# ---------------------------------------------------------------------------

def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port(preferred: int = 8765) -> int:
    """쓸 수 있는 포트를 고른다."""
    for port in range(preferred, preferred + 20):
        if _port_free(port):
            return port
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_running(timeout: float = 0.3) -> Optional[int]:
    """이미 떠 있는 이 프로그램을 찾는다. 있으면 그 포트를 돌려준다.

    실행 파일을 여러 번 눌러도 프로그램이 쌓이지 않게 하려는 것이다.
    """
    for port in PORT_RANGE:
        if _port_free(port):
            continue          # 아무도 안 쓰는 포트
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=timeout
            ) as resp:
                if resp.read().decode().strip() == PING_TOKEN:
                    return port
        except (urllib.error.URLError, OSError, ValueError):
            continue          # 다른 프로그램이 쓰는 포트
    return None


def _wait_until_up(port: int, timeout: float = 25.0) -> bool:
    """서버가 응답할 때까지 기다린다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=0.5
            ) as resp:
                if resp.read().decode().strip() == PING_TOKEN:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    return False


# ---------------------------------------------------------------------------
# 서버 실행
# ---------------------------------------------------------------------------

def serve(
    port: Optional[int] = None,
    open_browser: bool = True,
    host: str = "127.0.0.1",
    quiet: bool = False,
) -> None:
    """이 프로세스에서 웹 화면을 돌린다. Ctrl+C 로 끝낸다."""
    port = port or free_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer((host, port), _Handler)

    if not quiet:
        print("=" * 46)
        print("  터보 냉동기 사이클 해석")
        print("=" * 46)
        print()
        print(f"  브라우저에서 열렸습니다: {url}")
        print()
        print("  끝내려면 이 창에서 Ctrl+C 를 누르거나,")
        print("  브라우저 오른쪽 위의 '종료' 를 누르세요.")
        print()

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n종료합니다.")
    finally:
        server.server_close()


def _spawn_detached(port: int) -> bool:
    """창 없이 백그라운드로 서버를 띄운다. 성공하면 True.

    윈도우에서는 pythonw.exe 를 써서 검은 창이 아예 뜨지 않게 한다.
    """
    base = _relaunch_command()
    if base is None:
        return False
    args = base + ["--serve", "--port", str(port), "--no-browser"]
    log_path = os.path.join(_app_dir(), "실행오류.log")

    kwargs: dict = {}
    if os.name == "nt":
        # CREATE_NO_WINDOW(0x08000000) + DETACHED_PROCESS(0x00000008)
        kwargs["creationflags"] = 0x08000000 | 0x00000008
    else:
        kwargs["start_new_session"] = True

    try:
        log = open(log_path, "w", encoding="utf-8")
        subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         **kwargs)
    except Exception:
        return False
    return _wait_until_up(port)


def _app_dir() -> str:
    """오류 기록을 남길 폴더."""
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script and os.path.isfile(script):
        return os.path.dirname(script) or "."
    return os.getcwd()


def _relaunch_command() -> Optional[list[str]]:
    """자기 자신을 다시 띄우는 명령을 만든다.

    한 파일로 합친 배포판이면 그 파일을 직접 실행하고,
    패키지로 설치돼 있으면 `-m turbochiller.webui` 로 실행한다.
    """
    python = _background_python()
    package = globals().get("__package__") or ""
    if package:
        return [python, "-m", "turbochiller.webui"]

    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script and os.path.isfile(script):
        return [python, script]
    return None


def _background_python() -> str:
    """창 없이 돌릴 파이썬 실행 파일 경로."""
    exe = sys.executable
    if os.name == "nt":
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return exe


def run(port: Optional[int] = None, background: bool = True) -> None:
    """실행 파일에서 부르는 진입점.

    background=True 면 창을 남기지 않고 백그라운드로 띄운 뒤 바로 빠져나온다.
    (검은 창을 계속 켜두지 않아도 되게 하려는 것이다)
    """
    existing = find_running()
    if existing is not None:
        url = f"http://127.0.0.1:{existing}/"
        print(f"이미 실행 중입니다. 브라우저를 엽니다: {url}")
        webbrowser.open(url)
        return

    port = port or free_port()

    if background and _spawn_detached(port):
        url = f"http://127.0.0.1:{port}/"
        webbrowser.open(url)
        print("=" * 52)
        print("  터보 냉동기 사이클 해석 — 실행했습니다")
        print("=" * 52)
        print()
        print(f"  주소 : {url}")
        print()
        print("  이 창은 닫으셔도 됩니다. 프로그램은 계속 돌아갑니다.")
        print("  끝내실 때는 브라우저 오른쪽 위의 '종료' 를 누르세요.")
        print()
        return

    # 백그라운드 실행이 안 되면 이 창에서 그대로 돌린다
    if background:
        print("(백그라운드 실행에 실패해 이 창에서 직접 실행합니다)")
        print()
    serve(port=port, open_browser=True)


def _cli(argv: Optional[list[str]] = None) -> None:
    """명령줄에서 부를 때."""
    import argparse as _argparse

    parser = _argparse.ArgumentParser(description="터보 냉동기 사이클 해석 — 웹 화면")
    parser.add_argument(
        "--serve", action="store_true",
        help="이 창에서 서버를 직접 돌린다 (백그라운드로 띄운 쪽이 쓰는 옵션)",
    )
    parser.add_argument("--port", type=int, help="포트 (기본: 8765부터 빈 곳)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument(
        "--console", action="store_true",
        help="백그라운드로 보내지 않고 이 창에서 실행한다",
    )
    args = parser.parse_args(argv)

    if args.serve:
        serve(port=args.port, open_browser=not args.no_browser, quiet=True)
    else:
        run(port=args.port, background=not args.console)


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
    parser.add_argument(
        "--gagerr", metavar="CSV", nargs="?", const="",
        help="게이지 R&R 을 글자로 계산 (CSV 를 안 주면 예제). "
             "공차는 --lsl/--usl 로",
    )
    parser.add_argument("--lsl", type=float, help="게이지 R&R 규격 하한")
    parser.add_argument("--usl", type=float, help="게이지 R&R 규격 상한")
    args = parser.parse_args()

    if args.gagerr is not None:
        gargs = [args.gagerr] if args.gagerr else []
        if args.lsl is not None:
            gargs += ["--lsl", str(args.lsl)]
        if args.usl is not None:
            gargs += ["--usl", str(args.usl)]
        sys.exit(main(gargs))

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

