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

#: 선도가 그려지는 창. 이름표가 이 밖으로 나가면 안 보인다.
H_MIN, H_MAX = 100.0, 500.0
P_MIN, P_MAX = 10.0, 10000.0

#: 글자가 차지하는 세로 높이 (창 크기를 1 로 본 상대 크기).
LABEL_H = 0.052

#: 글자 한 자의 가로 폭. 한글·°C 는 영문 숫자보다 넓다.
CHAR_W_ASCII = 0.0155
CHAR_W_WIDE = 0.0280


def label_width(text: str) -> float:
    """글자가 가로로 차지하는 폭. '0.4' 와 '등엔트로피선' 은 많이 다르다."""
    wide = sum(1 for ch in text if ord(ch) > 0x2000)
    return (len(text) - wide) * CHAR_W_ASCII + wide * CHAR_W_WIDE

#: 등엔트로피선·등비체적선은 '포화증기선 위의 어느 점에서 출발하는가'
#: 로 고른다. 그래야 냉매가 달라도 선이 고르게 퍼진다.
ISENTROPE_STARTS = [-20.0, 0.0, 20.0, 40.0, 60.0]
ISOCHORE_STARTS = [-20.0, 0.0, 20.0, 40.0]


@dataclass
class Curve:
    """선 하나. kind 는 '돔' / '등온' / '건도' / '등엔트로피' / '등비체적'."""

    kind: str
    label: str
    h: list[float]      # [kJ/kg]
    p: list[float]      # [kPa]
    #: 선 위에 이름표를 붙일 점의 번호. None 이면 이름표 없음.
    label_idx: int | None = None
    #: 이름표에 쓸 글자 (비면 label 을 쓴다)
    label_text: str = ""
    #: 이름표를 놓아도 되는 점 번호들. 여기서 서로 안 겹치는 자리를 고른다.
    candidates: tuple[int, ...] = ()

    @property
    def label_point(self) -> tuple[str, float, float] | None:
        """(글자, h, P). 이름표를 안 붙이는 선이면 None."""
        if self.label_idx is None:
            return None
        i = min(self.label_idx, len(self.h) - 1)
        return (self.label_text or self.label, self.h[i], self.p[i])


@dataclass
class ChartLines:
    """한 냉매의 선도 보조선 묶음."""

    refrigerant: str
    curves: list[Curve]

    @property
    def n_cols(self) -> int:
        """이 냉매가 차지하는 열 수 (곡선마다 h, P 두 열)."""
        return len(self.curves) * 2

    @property
    def labels(self) -> list[tuple[str, float, float]]:
        """선 위에 찍을 이름표들. (글자, h, P)

        범례로 빼면 어느 선이 몇 도인지 알 수가 없다. 실제 P-h 선도가
        그렇듯 선 옆에 숫자를 직접 붙인다.
        """
        out = []
        for c in self.curves:
            pt = c.label_point
            if pt is not None:
                out.append(pt)
        return out


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
    n_two_phase = len(h) - 1          # 포화증기점의 번호

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

    n_real = len(h)
    vapor0 = n_two_phase + 1          # 2상 구간 바로 다음 = 과열 가지 시작
    h, p = _pad(h, p)
    # 이름표는 과열 가지 위 어딘가에 붙인다. 정확히 어디인지는 나중에
    # 다른 이름표와 겹치지 않는 자리로 고른다.
    return Curve("등온", f"{t:g}°C", h, p,
                 candidates=tuple(range(vapor0, n_real)))


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
    n_real = len(h)
    h, p = _pad(h, p)
    # 돔 아래쪽에 건도를 적는다. 위로 갈수록 선이 모여 숫자가 겹친다.
    return Curve("건도", f"x={x:g}", h, p, label_text=f"{x:g}",
                 candidates=tuple(range(0, max(1, n_real // 3))))


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


def _isentrope(state, t_start: float, p_max: float,
               label: bool = False) -> Curve:
    """등엔트로피선. 포화증기선 위의 한 점에서 출발해 위로 올라간다.

    압축기가 지나가는 길이다. 실제 압축선이 이 선과 얼마나 벌어지는지가
    곧 단열효율이므로, 선도에서 제일 쓸모 있는 보조선이다.
    """
    try:
        state.update(CoolProp.QT_INPUTS, 1.0, t_start + T0)
        p_sat = state.p() / 1000.0
        s_val = state.smass()
    except Exception:
        return Curve("등엔트로피", f"s@{t_start:g}°C", *_pad([], []))

    h: list[float] = []
    p: list[float] = []
    for i in range(N_POINTS):
        pp = p_sat * (p_max / p_sat) ** (i / (N_POINTS - 1))
        try:
            state.update(CoolProp.PSmass_INPUTS, pp * 1000.0, s_val)
            h.append(state.hmass() / 1000.0)
            p.append(pp)
        except Exception:
            break
    n_real = len(h)
    h, p = _pad(h, p)
    cand = tuple(range(n_real // 3, n_real)) if (label and n_real) else ()
    return Curve("등엔트로피", f"s@{t_start:g}°C", h, p,
                 label_text="등엔트로피선", candidates=cand)


def _isochore(state, t_start: float, p_max: float, label: bool = False) -> Curve:
    """등비체적선. 흡입 비체적이 곧 압축기 크기라서 같이 본다.

    밀도와 압력(DmassP)으로 풀면 혼합냉매에서 'DP_flash not ready for
    mixtures' 로 깨진다. 밀도와 온도(DmassT)로 풀면 둘 다 된다.
    """
    name = f"v@{t_start:g}°C"
    try:
        state.update(CoolProp.QT_INPUTS, 1.0, t_start + T0)
        rho = state.rhomass()
    except Exception:
        return Curve("등비체적", name, *_pad([], []))

    h: list[float] = []
    p: list[float] = []
    for i in range(N_POINTS):
        t = t_start + 130.0 * i / (N_POINTS - 1)
        try:
            state.update(CoolProp.DmassT_INPUTS, rho, t + T0)
            pp = state.p() / 1000.0
        except Exception:
            break
        if pp > p_max:
            break
        h.append(state.hmass() / 1000.0)
        p.append(pp)
    n_real = len(h)
    h, p = _pad(h, p)
    # 등비체적선은 가로축 오른쪽 밖까지 뻗는다. 이름표는 화면 안에
    # 남아 있는 마지막 점에 붙여야 보인다.
    cand = tuple(range(n_real)) if (label and n_real) else ()
    return Curve("등비체적", name, h, p, label_text="등비체적선",
                 candidates=cand)


def _norm(h: float, pp: float) -> tuple[float, float]:
    """선도 창 안에서의 상대 위치 (0~1). 글자가 겹치는지 재는 자다."""
    import math
    x = (h - H_MIN) / (H_MAX - H_MIN)
    y = (math.log10(pp) - math.log10(P_MIN)) / (
        math.log10(P_MAX) - math.log10(P_MIN))
    return x, y


def _clearance(x: float, y: float, w: float,
               taken: list[tuple[float, float, float]]) -> float:
    """이미 놓인 이름표에서 얼마나 떨어졌나. 1 이상이면 안 겹친다.

    글자 폭이 서로 다르므로, 두 글자 폭의 평균만큼 떨어져야 한다.
    """
    if not taken:
        return 9.9
    return min(max(abs(x - tx) / ((w + tw) / 2), abs(y - ty) / LABEL_H)
               for tx, ty, tw in taken)


def _place_labels(curves: list[Curve]) -> None:
    """이름표를 서로 겹치지 않는 자리에 놓는다.

    자리를 미리 못 박아 두면 냉매에 따라 숫자가 서로 포개진다. 선마다
    '여기면 된다' 하는 후보 구간을 받아 두고, 이미 놓은 이름표와 겹치지
    않는 자리를 고른다. 겹치지 않는 자리가 여럿이면 후보 구간에서 앞쪽
    (등온선은 압력이 낮은 쪽) 을 쓴다 — 선이 벌어져 있어 읽기 쉽다.
    """
    taken: list[tuple[float, float, float]] = []
    for c in curves:
        if not c.candidates:
            continue
        w = label_width(c.label_text or c.label)
        best, best_score = None, -1.0
        for i in c.candidates:
            if i >= len(c.h):
                continue
            x, y = _norm(c.h[i], c.p[i])
            if not (0.02 < x < 0.90 and 0.04 < y < 0.96):
                continue            # 창 밖이거나 테두리에 붙는다
            # 넉넉히 떨어졌으면 더 멀 것 없다. 그 안에서는 앞쪽을 쓴다.
            score = min(_clearance(x, y, w, taken), 1.15)
            if score > best_score + 1e-9:
                best, best_score = i, score
        if best is not None:
            c.label_idx = best
            x, y = _norm(c.h[best], c.p[best])
            taken.append((x, y, w))


def build(refrigerant: str, t_min: float = -50.0) -> ChartLines:
    """한 냉매의 보조선을 모두 만든다.

    선도는 물성표(-30°C 부터)보다 아래까지 그린다. 운전 범위는 아니지만,
    세로축을 10 kPa 부터 잡아야 눈금이 100/1000/10000 으로 읽기 좋은데,
    돔이 60 kPa 에서 끊기면 아래가 횅하게 빈다.
    """
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
    # 등엔트로피선·등비체적선에는 선 위 이름표를 붙이지 않는다. 글자가
    # 길어 온도 숫자와 겹치기 때문이다. 이 둘만 범례로 밝힌다.
    curves += [_isentrope(state, t, p_max) for t in ISENTROPE_STARTS]
    curves += [_isochore(state, t, p_max) for t in ISOCHORE_STARTS]
    _place_labels(curves)
    return ChartLines(refrigerant, curves)


def build_many(refrigerants: list[str], t_min: float = -50.0) -> list[ChartLines]:
    """여러 냉매의 보조선을 만든다. 곡선 구성이 같은지 확인한다."""
    out = [build(r, t_min) for r in refrigerants]
    labels = [[c.label for c in cl.curves] for cl in out]
    assert all(lb == labels[0] for lb in labels), "냉매마다 곡선 구성이 다르다"
    return out
