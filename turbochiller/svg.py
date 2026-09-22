"""P-h 선도(몰리에르 선도)를 SVG 로 그린다.

실제 냉매 선도처럼 보조선을 모두 넣는다.
    포화선, 등온선, 등건도선, 등엔트로피선, 등비체적선, 임계점

matplotlib 없이 파이썬 내장 기능만 쓴다.
설치가 까다로운 라이브러리(pyarrow 등)를 피하기 위한 것이다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import props
from .cycle import CycleResult

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


def _saturation(fluid: str, box: _Box, n: int = 140):
    """포화액선·포화증기선. (h, p) 목록 두 개를 돌려준다."""
    t_crit = props.t_crit(fluid)
    t_hi = t_crit - 0.15
    t_lo = props.t_sat(fluid, box.p_min, q=1) - 25.0
    liq: list[tuple[float, float]] = []
    vap: list[tuple[float, float]] = []
    for i in range(n):
        t = t_lo + (t_hi - t_lo) * i / (n - 1)
        try:
            p = props.p_sat(fluid, t, q=1)
            liq.append((props.h_sat(fluid, t, 0), p))
            vap.append((props.h_sat(fluid, t, 1), p))
        except Exception:
            continue
    return liq, vap


def _isotherm(fluid: str, t: float, box: _Box) -> list[tuple[float, float]]:
    """등온선 하나. 액 -> 2상(수평) -> 과열증기 순으로 이어 붙인다."""
    pts: list[tuple[float, float]] = []
    t_crit = props.t_crit(fluid)

    if t >= t_crit:
        for p in reversed(_p_grid(box, 40)):
            try:
                pts.append((props.h_tp(fluid, t, p), p))
            except Exception:
                continue
        return pts

    try:
        p_sat = props.p_sat(fluid, t, q=1)
        h_f = props.h_sat(fluid, t, 0)
        h_g = props.h_sat(fluid, t, 1)
    except Exception:
        return pts

    # 1) 과냉 액 구간 : 높은 압력에서 포화압까지 (거의 수직)
    if p_sat < box.p_max:
        for p in sorted((p for p in _p_grid(box, 16) if p > p_sat), reverse=True):
            try:
                pts.append((props.h_tp(fluid, t, p), p))
            except Exception:
                continue
    pts.append((h_f, p_sat))

    # 2) 2상 구간 : 포화압에서 수평
    pts.append((h_g, p_sat))

    # 3) 과열 증기 구간 : 포화압에서 낮은 압력으로
    for p in sorted(p for p in _p_grid(box, 30) if p < p_sat):
        try:
            pts.append((props.h_tp(fluid, t, p), p))
        except Exception:
            continue
    return pts


def _quality_line(fluid: str, x: float, box: _Box, n: int = 70):
    """등건도선 (포화 영역 안)."""
    t_crit = props.t_crit(fluid)
    t_hi = t_crit - 0.3
    t_lo = props.t_sat(fluid, box.p_min, q=1) - 20.0
    pts: list[tuple[float, float]] = []
    for i in range(n):
        t = t_lo + (t_hi - t_lo) * i / (n - 1)
        try:
            p = props.p_sat(fluid, t, q=1)
            h_f = props.h_sat(fluid, t, 0)
            h_g = props.h_sat(fluid, t, 1)
        except Exception:
            continue
        pts.append((h_f + x * (h_g - h_f), p))
    return pts


def _isentrope(fluid: str, s: float, box: _Box, n: int = 52):
    """등엔트로피선 (과열 증기 영역만).

    포화(2상) 영역 안에서는 등엔트로피선을 그리지 않는다.
    실제 선도도 과열 영역에만 그린다.
    """
    pts: list[tuple[float, float]] = []
    for p in _p_grid(box, n):
        try:
            h = props.h_sp(fluid, s, p)
            # 과열증기 쪽만 남긴다. 2상·과냉액 구간은 선을 끊는다.
            if h <= props.h_sat(fluid, props.t_sat(fluid, p, q=1), 1):
                pts.append((float("nan"), p))
                continue
            pts.append((h, p))
        except Exception:
            pts.append((float("nan"), p))
    return pts


def _isochore(fluid: str, density: float, box: _Box, n: int = 52):
    """등비체적선 (과열 증기 영역만)."""
    pts: list[tuple[float, float]] = []
    for p in _p_grid(box, n):
        try:
            if props.in_two_phase(props.q_dp(fluid, density, p)):
                pts.append((float("nan"), p))
                continue
            pts.append((props.h_dp(fluid, density, p), p))
        except Exception:
            pts.append((float("nan"), p))
    return pts


# ---------------------------------------------------------------------------
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
            pts = _quality_line(fluid, x_q, box)
            if draw(pts, c["quality"], DASH["quality"], 0.9, 0.9):
                put_label(pts, "bottom", f"{x_q:.1f}", c["quality"], 0, -5)

    # --- 등엔트로피선 ---
    # 포화증기선 근처에만 몰리지 않도록, 화면 오른쪽 끝(과열 깊은 곳)까지
    # 걸치는 범위를 잡는다.
    if opt.isentropes:
        try:
            # 화면에 보이는 '과열증기 영역' 안에서만 s 범위를 잡는다.
            # 과냉액까지 포함하면 범위가 지나치게 넓어져,
            # 정작 압축 구간 주변에는 선이 한 줄도 안 그려진다.
            candidates = []
            for pp in (box.p_min, math.sqrt(box.p_min * box.p_max), box.p_max):
                try:
                    candidates.append(
                        props.s_sat(fluid, props.t_sat(fluid, pp, q=1), 1)
                    )
                except Exception:
                    continue
            for pp in (box.p_min, box.p_max):
                try:
                    candidates.append(props.s_hp(fluid, box.h_max, pp))
                except Exception:
                    continue
            if not candidates:
                raise ValueError("등엔트로피선 범위를 잡을 수 없다")
            lo, hi = min(candidates), max(candidates)
            step = _nice_step(hi - lo, 9)
            sv = math.ceil(lo / step) * step
            while sv <= hi + 1e-9:
                pts = _isentrope(fluid, sv, box)
                if draw(pts, c["isentrope"], DASH["isentrope"], 0.9, 0.85):
                    put_label(pts, "top", f"s={sv:g}", c["isentrope"], 0, 13)
                sv += step
        except Exception:
            pass

    # --- 등비체적선 ---
    if opt.isochores:
        try:
            d_lo = props.d_tp(fluid, props.t_sat(fluid, box.p_min, q=1) + 1, box.p_min)
            d_hi = props.d_tp(fluid, props.t_sat(fluid, box.p_max, q=1) + 1, box.p_max)
            steps = 5
            for i in range(steps + 1):
                dens = d_lo * (d_hi / d_lo) ** (i / steps)
                pts = _isochore(fluid, dens, box)
                if draw(pts, c["isochore"], DASH["isochore"], 0.9, 0.8):
                    put_label(pts, "right", f"v={_sig(1 / dens)}", c["isochore"],
                              -4, -5, "end")
        except Exception:
            pass

    # --- 포화선 ---
    liq, vap = _saturation(fluid, box)
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
