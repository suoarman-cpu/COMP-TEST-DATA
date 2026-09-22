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
