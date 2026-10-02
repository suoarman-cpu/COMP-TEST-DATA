"""P-h 선도에 그릴 보조선을 미리 계산한다.

등온선·건도선·포화 돔은 **냉매만 정해지면 결정된다**. 운전조건과는
상관이 없다. 그래서 엑셀 수식으로 매번 풀 이유가 없고, 여기서 CoolProp
으로 미리 계산해 시트에 심어 둔다. 엑셀은 고른 냉매의 블록을 INDEX 로
집어 오기만 하면 된다.

모든 곡선의 점 개수를 똑같이(N_POINTS) 맞춘다. 엑셀 차트는 참조 범위를
고정해 두어야 하므로, 냉매를 바꿔도 길이가 변하면 안 되기 때문이다.
점이 모자라면 마지막 점을 되풀이해 채운다 (길이 0 인 선분이라 보이지
않는다).
"""

from __future__ import annotations

from dataclasses import dataclass

import CoolProp
from CoolProp import AbstractState

T0 = 273.15

#: 곡선 하나당 점 개수
N_POINTS = 60

#: 등온선을 그릴 온도 [°C]. 네 냉매 모두 임계온도(약 95°C) 아래다.
ISOTHERMS = [-20.0, 0.0, 20.0, 40.0, 60.0, 80.0]

#: 건도선을 그릴 건도
QUALITIES = [0.2, 0.4, 0.6, 0.8]


@dataclass
class Curve:
    """선 하나. kind 는 '돔' / '등온' / '건도'."""

    kind: str
    label: str
    h: list[float]      # [kJ/kg]
    p: list[float]      # [kPa]


@dataclass
class ChartLines:
    """한 냉매의 선도 보조선 묶음."""

    refrigerant: str
    curves: list[Curve]

    @property
    def n_cols(self) -> int:
        """이 냉매가 차지하는 열 수 (곡선마다 h, P 두 열)."""
        return len(self.curves) * 2


def _pad(h: list[float], p: list[float]) -> tuple[list[float], list[float]]:
    """점 개수를 N_POINTS 로 맞춘다."""
    if not h:                       # 한 점도 못 구한 경우
        return [float("nan")] * N_POINTS, [float("nan")] * N_POINTS
    while len(h) < N_POINTS:
        h.append(h[-1])
        p.append(p[-1])
    return h[:N_POINTS], p[:N_POINTS]


def _dome(state, t_min: float, t_top: float) -> Curve:
    """포화 돔. 포화액선을 올라갔다가 임계점을 돌아 포화증기선을 내려온다."""
    half = N_POINTS // 2
    # 임계점 근처에서 점이 촘촘해지도록 간격을 좁혀 간다.
    span = t_top - t_min
    temps = [t_min + span * (i / (half - 1)) ** 0.7 for i in range(half)]

    liq_h, liq_p, vap_h, vap_p = [], [], [], []
    for t in temps:
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, t + T0)
            hf, pf = state.hmass() / 1000.0, state.p() / 1000.0
            state.update(CoolProp.QT_INPUTS, 1.0, t + T0)
            hg, pg = state.hmass() / 1000.0, state.p() / 1000.0
        except Exception:
            break
        liq_h.append(hf)
        liq_p.append(pf)
        vap_h.append(hg)
        vap_p.append(pg)
    h = liq_h + vap_h[::-1]
    p = liq_p + vap_p[::-1]
    h, p = _pad(h, p)
    return Curve("돔", "포화선", h, p)


def _isotherm(state, t: float, p_min: float, p_max: float) -> Curve:
    """등온선 하나. 과냉액 → 2상(수평) → 과열증기 순으로 잇는다."""
    n_liq, n_vap = 12, N_POINTS - 14      # 2상 2점을 뺀 나머지

    try:
        state.update(CoolProp.QT_INPUTS, 0.0, t + T0)
        p_sat, hf = state.p() / 1000.0, state.hmass() / 1000.0
        state.update(CoolProp.QT_INPUTS, 1.0, t + T0)
        hg = state.hmass() / 1000.0
    except Exception:
        return Curve("등온", f"{t:g}°C", *_pad([], []))

    h: list[float] = []
    p: list[float] = []

    # 과냉액 : 높은 압력에서 포화압력까지. 압력을 올려도 h 는 거의 안 변해
    # 거의 수직선이 된다.
    top = max(p_max, p_sat * 1.05)
    for i in range(n_liq):
        pp = top * (p_sat / top) ** (i / (n_liq - 1))
        try:
            state.update(CoolProp.PT_INPUTS, pp * 1000.0, t + T0)
            h.append(state.hmass() / 1000.0)
            p.append(pp)
        except Exception:
            pass

    # 2상 : 포화압력에서 수평
    h += [hf, hg]
    p += [p_sat, p_sat]

    # 과열증기 : 포화압력에서 낮은 압력까지
    bottom = min(p_min, p_sat * 0.95)
    for i in range(1, n_vap + 1):
        pp = p_sat * (bottom / p_sat) ** (i / n_vap)
        try:
            state.update(CoolProp.PT_INPUTS, pp * 1000.0, t + T0)
            h.append(state.hmass() / 1000.0)
            p.append(pp)
        except Exception:
            pass

    h, p = _pad(h, p)
    return Curve("등온", f"{t:g}°C", h, p)


def _quality(state, x: float, t_min: float, t_top: float) -> Curve:
    """건도선 하나. 돔 안에서 포화온도를 따라 올라간다."""
    span = t_top - t_min
    h: list[float] = []
    p: list[float] = []
    for i in range(N_POINTS):
        t = t_min + span * (i / (N_POINTS - 1)) ** 0.7
        try:
            state.update(CoolProp.QT_INPUTS, x, t + T0)
            h.append(state.hmass() / 1000.0)
            p.append(state.p() / 1000.0)
        except Exception:
            break
    h, p = _pad(h, p)
    return Curve("건도", f"x={x:g}", h, p)


def _p_sat(state, t: float) -> float:
    """포화압력. 임계점 바로 밑에서는 혼합냉매 풀이가 자주 실패하므로,
    될 때까지 온도를 조금씩 내린다."""
    for back_off in (0.0, 2.0, 5.0, 10.0, 15.0, 20.0):
        try:
            state.update(CoolProp.QT_INPUTS, 1.0, t - back_off + T0)
            return state.p() / 1000.0
        except Exception:
            continue
    raise ValueError(f"{t:.1f}°C 부근에서 포화압력을 못 구했다")


def _top_temp(state, t_crit: float) -> float:
    """돔을 어디까지 그릴지. 풀이가 되는 가장 높은 온도를 찾는다."""
    lo, hi = t_crit - 25.0, t_crit
    for _ in range(30):                      # 이분법으로 20 번이면 충분하다
        mid = (lo + hi) / 2
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, mid + T0)
            state.update(CoolProp.QT_INPUTS, 1.0, mid + T0)
            lo = mid
        except Exception:
            hi = mid
    return lo


def build(refrigerant: str, t_min: float = -30.0) -> ChartLines:
    """한 냉매의 보조선을 모두 만든다."""
    from turbochiller.props import t_crit as _t_crit

    state = AbstractState("HEOS", refrigerant)
    t_crit = _t_crit(refrigerant)
    # 순수냉매는 임계점까지 깔끔하게 풀리지만, 혼합냉매(R513A)는 그 바로
    # 밑에서 밀도 풀이가 깨진다. 실제로 풀리는 꼭대기를 찾아 거기까지만
    # 그린다. 돔이 임계점에서 조금 열리지만, 억지로 외삽하는 것보다 낫다.
    t_top = _top_temp(state, t_crit)

    p_min = _p_sat(state, t_min)
    p_max = _p_sat(state, t_top)

    curves = [_dome(state, t_min, t_top)]
    curves += [_isotherm(state, t, p_min, p_max) for t in ISOTHERMS]
    curves += [_quality(state, x, t_min, t_top) for x in QUALITIES]
    return ChartLines(refrigerant, curves)


def build_many(refrigerants: list[str], t_min: float = -30.0) -> list[ChartLines]:
    """여러 냉매의 보조선을 만든다. 곡선 구성이 같은지 확인한다."""
    out = [build(r, t_min) for r in refrigerants]
    labels = [[c.label for c in cl.curves] for cl in out]
    assert all(lb == labels[0] for lb in labels), "냉매마다 곡선 구성이 다르다"
    return out
