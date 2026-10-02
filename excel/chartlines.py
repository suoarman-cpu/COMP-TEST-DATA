"""P-h 선도에 그릴 보조선을 미리 계산한다.

등온선·건도선·등엔트로피선·등비체적선·포화 돔은 **냉매만 정해지면
결정된다**. 운전조건과는 상관이 없다. 그래서 엑셀 수식으로 매번 풀 이유가
없고, 여기서 CoolProp 으로 미리 계산해 시트에 심어 둔다. 엑셀은 고른
냉매의 블록을 INDEX 로 집어 오기만 하면 된다.

두 가지를 지킨다.

**값은 절대값으로 고른다.** 등엔트로피선을 '포화증기선 위 어느 점' 으로
잡으면 선들이 한데 뭉친다(포화증기 엔트로피는 온도가 변해도 거의 같다).
실제 선도가 그러듯 s = 1.6, 1.7, … 처럼 값을 못 박는다. 그래야 선이
화면 전체에 고르게 퍼지고, 이름표 글자도 냉매와 무관하게 맞는다
(엑셀 차트의 계열 이름은 냉매에 따라 바꿀 수 없다).

**선은 화면 끝까지 그린다.** 포화선 근처에서 끊으면 선도가 아니라
그림이 된다.

모든 곡선의 점 개수를 똑같이(N_POINTS) 맞춘다. 엑셀 차트는 참조 범위를
고정해 두어야 하므로, 냉매를 바꿔도 길이가 변하면 안 되기 때문이다.
점이 모자라면 마지막 점을 되풀이해 채운다 (길이 0 인 선분이라 안 보인다).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import CoolProp
from CoolProp import AbstractState

T0 = 273.15

#: 곡선 하나당 점 개수
N_POINTS = 60

#: 선도가 그려지는 창
H_MIN, H_MAX = 100.0, 600.0        # [kJ/kg]
P_MIN, P_MAX = 10.0, 10000.0       # [kPa]

#: 등온선 [°C]. 네 냉매 모두 임계온도(약 95°C) 아래다.
ISOTHERMS = [-40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0,
             40.0, 50.0, 60.0, 70.0, 80.0]

#: 건도선
QUALITIES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

#: 등엔트로피선 [kJ/kg·K]
ENTROPIES = [1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3]

#: 등비체적선 [m³/kg]
VOLUMES = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]

#: 글자가 차지하는 세로 높이 (창 크기를 1 로 본 상대 크기).
LABEL_H = 0.042

#: 글자 한 자의 가로 폭. 한글·°C 는 영문 숫자보다 넓다.
CHAR_W_ASCII = 0.0130
CHAR_W_WIDE = 0.0240


def label_width(text: str) -> float:
    """글자가 가로로 차지하는 폭. '0.4' 와 '-40' 은 다르다."""
    wide = sum(1 for ch in text if ord(ch) > 0x2000)
    return max(0.022, (len(text) - wide) * CHAR_W_ASCII + wide * CHAR_W_WIDE)


@dataclass
class Curve:
    """선 하나."""

    kind: str                       # 돔 / 등온 / 건도 / 등엔트로피 / 등비체적
    label: str                      # 이름표 글자
    h: list[float] = field(default_factory=list)      # [kJ/kg]
    p: list[float] = field(default_factory=list)      # [kPa]
    #: 선 위에 이름표를 붙일 점의 번호. None 이면 이름표 없음.
    label_idx: int | None = None
    #: 이름표를 놓아도 되는 점 번호들
    candidates: tuple[int, ...] = ()

    @property
    def label_point(self) -> tuple[str, float, float] | None:
        if self.label_idx is None:
            return None
        i = min(self.label_idx, len(self.h) - 1)
        return (self.label, self.h[i], self.p[i])


@dataclass
class ChartLines:
    """한 냉매의 선도 보조선 묶음."""

    refrigerant: str
    curves: list[Curve]

    @property
    def labels(self) -> list[tuple[str, float, float]]:
        """선 위에 찍을 이름표들. (글자, h, P)

        범례로 빼면 어느 선이 몇 도인지 알 수가 없다. 실제 P-h 선도가
        그렇듯 선 옆에 숫자를 직접 붙인다.
        """
        return [pt for c in self.curves if (pt := c.label_point) is not None]


def _inside(h: float, pp: float) -> bool:
    return H_MIN <= h <= H_MAX and P_MIN <= pp <= P_MAX


def _pad(h: list[float], p: list[float]) -> tuple[list[float], list[float]]:
    """점 개수를 N_POINTS 로 맞춘다."""
    if not h:
        return [float("nan")] * N_POINTS, [float("nan")] * N_POINTS
    h, p = list(h), list(p)
    while len(h) < N_POINTS:
        h.append(h[-1])
        p.append(p[-1])
    return h[:N_POINTS], p[:N_POINTS]


def _log_steps(a: float, b: float, n: int) -> list[float]:
    """a 에서 b 까지 로그 간격으로 n 개."""
    return [a * (b / a) ** (i / (n - 1)) for i in range(n)]


def _top_temp(state, t_crit: float) -> float:
    """돔을 어디까지 그릴지. 풀이가 되는 가장 높은 온도를 이분법으로 찾는다.

    혼합냉매(R513A)는 임계점 바로 밑에서 밀도 풀이가 깨진다.
    """
    lo, hi = t_crit - 25.0, t_crit
    for _ in range(30):
        mid = (lo + hi) / 2
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, mid + T0)
            state.update(CoolProp.QT_INPUTS, 1.0, mid + T0)
            lo = mid
        except Exception:
            hi = mid
    return lo


def _p_sat(state, t: float) -> float | None:
    try:
        state.update(CoolProp.QT_INPUTS, 1.0, t + T0)
        return state.p() / 1000.0
    except Exception:
        return None


def _dome(state, t_min: float, t_top: float) -> Curve:
    """포화 돔. 포화액선을 올라갔다가 임계점을 돌아 포화증기선을 내려온다."""
    half = N_POINTS // 2
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
    h, p = _pad(liq_h + vap_h[::-1], liq_p + vap_p[::-1])
    return Curve("돔", "포화선", h, p)


def _isotherm(state, t: float) -> Curve:
    """등온선. 과냉액(거의 수직) → 2상(수평) → 과열증기(완만히 하강).

    화면 위끝에서 아래끝까지 그린다.
    """
    name = f"{t:g}"
    p_sat = _p_sat(state, t)
    if p_sat is None:
        return Curve("등온", name, *_pad([], []))
    try:
        state.update(CoolProp.QT_INPUTS, 0.0, t + T0)
        hf = state.hmass() / 1000.0
        state.update(CoolProp.QT_INPUTS, 1.0, t + T0)
        hg = state.hmass() / 1000.0
    except Exception:
        return Curve("등온", name, *_pad([], []))

    n_liq, n_vap = 14, N_POINTS - 16
    h: list[float] = []
    p: list[float] = []

    # 과냉액 : 화면 위끝에서 포화압력까지
    for pp in _log_steps(P_MAX * 0.97, p_sat, n_liq):
        try:
            state.update(CoolProp.PT_INPUTS, pp * 1000.0, t + T0)
        except Exception:
            continue
        hh = state.hmass() / 1000.0
        if _inside(hh, pp):
            h.append(hh)
            p.append(pp)

    # 2상 : 포화압력에서 수평
    h += [hf, hg]
    p += [p_sat, p_sat]
    vapor0 = len(h) - 1

    # 과열증기 : 포화압력에서 화면 아래끝까지
    for pp in _log_steps(p_sat, P_MIN * 1.03, n_vap + 1)[1:]:
        try:
            state.update(CoolProp.PT_INPUTS, pp * 1000.0, t + T0)
        except Exception:
            continue
        hh = state.hmass() / 1000.0
        if _inside(hh, pp):
            h.append(hh)
            p.append(pp)

    n_real = len(h)
    h, p = _pad(h, p)
    return Curve("등온", name, h, p,
                 candidates=tuple(range(vapor0 + 1, n_real)))


def _quality(state, x: float, t_min: float, t_top: float) -> Curve:
    """건도선. 돔 안에서 포화온도를 따라 올라간다."""
    span = t_top - t_min
    h: list[float] = []
    p: list[float] = []
    for i in range(N_POINTS):
        t = t_min + span * (i / (N_POINTS - 1)) ** 0.7
        try:
            state.update(CoolProp.QT_INPUTS, x, t + T0)
        except Exception:
            break
        hh, pp = state.hmass() / 1000.0, state.p() / 1000.0
        if _inside(hh, pp):
            h.append(hh)
            p.append(pp)
    n_real = len(h)
    h, p = _pad(h, p)
    # 돔 아래쪽에 적는다. 위로 갈수록 선이 모여 숫자가 겹친다.
    return Curve("건도", f"{x:g}", h, p,
                 candidates=tuple(range(0, max(1, n_real // 3))))


def _isentrope(state, s_val: float) -> Curve:
    """등엔트로피선. 압축기가 지나는 길이다.

    실제 압축선이 이 선과 얼마나 벌어지는지가 곧 단열효율이므로,
    선도에서 제일 쓸모 있는 보조선이다.
    """
    h: list[float] = []
    p: list[float] = []
    for pp in _log_steps(P_MIN * 1.03, P_MAX * 0.97, N_POINTS):
        try:
            state.update(CoolProp.PSmass_INPUTS, pp * 1000.0, s_val * 1000.0)
        except Exception:
            continue
        hh = state.hmass() / 1000.0
        if _inside(hh, pp):
            h.append(hh)
            p.append(pp)
    n_real = len(h)
    h, p = _pad(h, p)
    return Curve("등엔트로피", f"{s_val:g}", h, p,
                 candidates=tuple(range(n_real)))


def _isochore(state, v_val: float) -> Curve:
    """등비체적선. 흡입 비체적이 곧 압축기 크기라서 같이 본다.

    밀도와 압력(DmassP)으로 풀면 혼합냉매에서 'DP_flash not ready for
    mixtures' 로 깨진다. 밀도와 온도(DmassT)로 풀면 둘 다 된다.
    """
    rho = 1.0 / v_val
    h: list[float] = []
    p: list[float] = []
    for i in range(N_POINTS * 3):
        t = -60.0 + 320.0 * i / (N_POINTS * 3 - 1)
        try:
            state.update(CoolProp.DmassT_INPUTS, rho, t + T0)
        except Exception:
            continue
        hh, pp = state.hmass() / 1000.0, state.p() / 1000.0
        if _inside(hh, pp):
            h.append(hh)
            p.append(pp)
    # 점이 많으면 고르게 솎아 N_POINTS 로 맞춘다.
    if len(h) > N_POINTS:
        step = (len(h) - 1) / (N_POINTS - 1)
        idx = [round(i * step) for i in range(N_POINTS)]
        h = [h[i] for i in idx]
        p = [p[i] for i in idx]
    n_real = len(h)
    h, p = _pad(h, p)
    return Curve("등비체적", f"{v_val:g}", h, p,
                 candidates=tuple(range(n_real)))


def _norm(h: float, pp: float) -> tuple[float, float]:
    """선도 창 안에서의 상대 위치 (0~1). 글자가 겹치는지 재는 자다."""
    x = (h - H_MIN) / (H_MAX - H_MIN)
    y = (math.log10(pp) - math.log10(P_MIN)) / (
        math.log10(P_MAX) - math.log10(P_MIN))
    return x, y


def _clearance(x: float, y: float, w: float,
               taken: list[tuple[float, float, float]]) -> float:
    """이미 놓인 이름표에서 얼마나 떨어졌나. 1 이상이면 안 겹친다."""
    if not taken:
        return 9.9
    return min(max(abs(x - tx) / ((w + tw) / 2), abs(y - ty) / LABEL_H)
               for tx, ty, tw in taken)


def _place_labels(curves: list[Curve]) -> None:
    """이름표를 서로 겹치지 않는 자리에 놓는다.

    자리를 미리 못 박아 두면 냉매에 따라 숫자가 서로 포개진다. 선마다
    '여기면 된다' 하는 후보 구간을 받아 두고, 이미 놓은 이름표와 겹치지
    않는 자리를 고른다. 어디에도 자리가 없으면 그 선은 이름표를 **포기
    한다** — 겹쳐 적느니 안 적는 게 낫다.
    """
    taken: list[tuple[float, float, float]] = []
    for c in curves:
        if not c.candidates:
            continue
        w = label_width(c.label)
        best, best_score = None, 0.0
        for i in c.candidates:
            if i >= len(c.h) or math.isnan(c.h[i]):
                continue
            x, y = _norm(c.h[i], c.p[i])
            if not (0.015 < x < 0.95 and 0.03 < y < 0.97):
                continue
            score = min(_clearance(x, y, w, taken), 1.1)
            if score > best_score + 1e-9:
                best, best_score = i, score
        if best is not None and best_score >= 1.0:
            c.label_idx = best
            x, y = _norm(c.h[best], c.p[best])
            taken.append((x, y, w))


def build(refrigerant: str, t_min: float = -60.0) -> ChartLines:
    """한 냉매의 보조선을 모두 만든다."""
    from turbochiller.props import t_crit as _t_crit

    state = AbstractState("HEOS", refrigerant)
    t_top = _top_temp(state, _t_crit(refrigerant))

    curves = [_dome(state, t_min, t_top)]
    curves += [_isotherm(state, t) for t in ISOTHERMS]
    curves += [_quality(state, x, t_min, t_top) for x in QUALITIES]
    curves += [_isentrope(state, s) for s in ENTROPIES]
    curves += [_isochore(state, v) for v in VOLUMES]
    _place_labels(curves)
    return ChartLines(refrigerant, curves)


def build_many(refrigerants: list[str],
               t_min: float = -60.0) -> list[ChartLines]:
    """여러 냉매의 보조선을 만든다. 곡선 구성이 같은지 확인한다."""
    out = [build(r, t_min) for r in refrigerants]
    labels = [[c.label for c in cl.curves] for cl in out]
    assert all(lb == labels[0] for lb in labels), "냉매마다 곡선 구성이 다르다"
    return out
