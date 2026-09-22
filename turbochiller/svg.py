"""P-h 선도를 SVG 그림으로 그린다.

matplotlib 없이 파이썬 내장 기능만 쓴다.
설치가 까다로운 라이브러리(pyarrow 등)를 피하기 위한 것이다.

색은 접근성 검증을 통과한 조합을 쓴다 (색각 이상에서도 구분된다).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import props
from .cycle import CycleResult

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
