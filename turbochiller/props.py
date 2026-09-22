"""냉매 물성 계산 (CoolProp 기반).

엑셀 시트에서 쓰던 REFPROP / CoolProp 애드인 함수를 대체한다.

엑셀 대응표
    PropsSI("H","T",T+273.15,"P",P*1000,ref)/1000   ->  h_tp(ref, T, P)
    PropsSI("P","T",T+273.15,"Q",1,ref)/1000        ->  p_sat(ref, T)
    PropsSI("T","S",s*1000,"P",P*1000,ref)-273.15   ->  t_sp(ref, s, P)

단위는 모두 엑셀 시트와 동일한 공학 단위를 쓴다.
    온도 °C, 압력 kPa(절대), 엔탈피 kJ/kg, 엔트로피 kJ/kg·K, 밀도 kg/m3
"""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI

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
