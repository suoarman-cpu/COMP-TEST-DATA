"""P-h 선도(몰리에르 선도) 그리기.

matplotlib 이 있어야 동작한다.  pip install matplotlib
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from . import props
from .cycle import CycleResult

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
    for st, (a, b) in zip(res.stage_results, _compression_segments(res)):
        ax.plot(
            [res.state(a).h, res.state(b).h],
            [res.state(a).p, res.state(b).p],
            color=COLOR_COMPRESSION,
            linewidth=3,
            zorder=4,
            solid_capstyle="round",
            label=label("compression").capitalize() if st is first else None,
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
