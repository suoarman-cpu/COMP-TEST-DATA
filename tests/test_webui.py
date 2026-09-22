"""내장 웹 화면과 SVG 선도 검증.

이 두 모듈은 파이썬 내장 기능과 CoolProp 만으로 동작해야 한다.
(streamlit / pandas / matplotlib / pyarrow 가 깔리지 않는 PC 를 위한 것이다)
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

import pytest

from turbochiller import CycleInput, single_stage, two_stage
from turbochiller.svg import ph_diagram_svg
from turbochiller.webui import FIELDS, build_input, parse_query, render_page

ROOT = Path(__file__).resolve().parent.parent

#: 이 프로그램의 배포판이 절대 쓰면 안 되는 라이브러리
HEAVY = ("streamlit", "pandas", "matplotlib", "pyarrow", "numpy", "yaml")


# --- SVG -------------------------------------------------------------------

def test_svg_is_wellformed() -> None:
    """XML 로 파싱되는 온전한 SVG 여야 한다."""
    import xml.etree.ElementTree as ET

    svg = ph_diagram_svg(two_stage(CycleInput()))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "viewBox" in root.attrib


@pytest.mark.parametrize("stages", [1, 2])
def test_svg_marks_every_state_point(stages: int) -> None:
    """상태점 개수만큼 점이 찍혀야 한다."""
    res = (single_stage if stages == 1 else two_stage)(CycleInput())
    svg = ph_diagram_svg(res)
    assert svg.count("<circle") == len(res.states)
    for s in res.states:
        assert f">{s.no}</text>" in svg


def test_svg_dark_mode_differs() -> None:
    res = two_stage(CycleInput())
    assert ph_diagram_svg(res, dark=True) != ph_diagram_svg(res, dark=False)


def test_svg_escapes_refrigerant_name() -> None:
    """냉매 이름의 괄호 등이 SVG 를 깨뜨리지 않아야 한다."""
    svg = ph_diagram_svg(two_stage(CycleInput(refrigerant="R1234ze(E)")))
    assert "R1234ze(E)" in svg


# --- 입력 해석 -------------------------------------------------------------

def test_first_visit_uses_defaults() -> None:
    """주소에 아무것도 없으면 기본값으로 계산한다."""
    values = parse_query({})
    inp, stages = build_input(values)
    assert stages == 2
    assert inp.refrigerant == "R1234ze(E)"
    assert inp.capacity_rt == 150.0
    assert inp.t_subcond is None          # 중간압 자동
    assert inp.subcond_mass_ratio is None  # 유량비 자동


def test_query_values_are_applied() -> None:
    q = urllib.parse.parse_qs(
        "stages=1&refrigerant=R134a&capacity_rt=250&cond_approach=8", keep_blank_values=True
    )
    inp, stages = build_input(parse_query(q))
    assert stages == 1
    assert inp.refrigerant == "R134a"
    assert inp.capacity_rt == 250.0
    assert inp.cond_approach == 8.0


def test_blank_optional_stays_none() -> None:
    """빈 칸으로 둔 서브콘덴서 값은 '자동' 으로 남아야 한다."""
    q = urllib.parse.parse_qs("t_subcond=&subcond_mass_ratio=", keep_blank_values=True)
    inp, _ = build_input(parse_query(q))
    assert inp.t_subcond is None
    assert inp.subcond_mass_ratio is None


def test_checkbox_off_when_submitted_without_it() -> None:
    """체크박스는 꺼져 있으면 전송되지 않는다 — 그걸 '꺼짐' 으로 읽어야 한다."""
    q = urllib.parse.parse_qs("stages=2&capacity_rt=150", keep_blank_values=True)
    assert parse_query(q)["excel_compat"] is False


def test_bad_number_falls_back_to_default() -> None:
    q = urllib.parse.parse_qs("capacity_rt=abc", keep_blank_values=True)
    inp, _ = build_input(parse_query(q))
    assert inp.capacity_rt == 150.0


# --- 페이지 --------------------------------------------------------------

def test_page_renders_all_sections() -> None:
    html = render_page({})
    for section in ("P-h 선도", "상태점", "압축기", "열교환기"):
        assert section in html, f"'{section}' 구역이 없다"
    assert "<svg" in html
    assert "계산할 수 없는 조건" not in html


def test_page_has_every_input_field() -> None:
    html = render_page({})
    for f in FIELDS:
        assert f'name="{f.key}"' in html, f"{f.key} 입력칸이 없다"


def test_page_shows_message_for_impossible_condition() -> None:
    """말이 안 되는 조건이면 예외가 아니라 안내 문구가 나와야 한다."""
    q = urllib.parse.parse_qs(
        "cooling_medium_in=-40&cond_approach=0.5&chilled_water_out=25",
        keep_blank_values=True,
    )
    html = render_page(q)
    assert "계산할 수 없는 조건" in html


def test_page_escapes_user_input() -> None:
    """이상한 값을 넣어도 HTML 이 깨지지 않아야 한다."""
    q = urllib.parse.parse_qs(
        'refrigerant=<script>alert("x")</script>', keep_blank_values=True
    )
    html = render_page(q)
    assert "<script>alert" not in html


def test_iplv_section_only_when_requested() -> None:
    assert "IPLV (부분부하 효율)" not in render_page({})
    q = urllib.parse.parse_qs("show_iplv=1", keep_blank_values=True)
    assert "IPLV (부분부하 효율)" in render_page(q)


# --- 배포판이 가벼운지 -----------------------------------------------------

def test_webui_and_svg_import_no_heavy_libraries() -> None:
    """webui / svg 가 무거운 라이브러리를 import 하지 않아야 한다."""
    for name in ("turbochiller/webui.py", "turbochiller/svg.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        for lib in HEAVY:
            assert not re.search(rf"^\s*(import|from)\s+{lib}\b", source, re.M), (
                f"{name} 이 {lib} 을(를) 쓰고 있다"
            )


@pytest.mark.skipif(
    not (ROOT / "dist" / "터보냉동기_사이클해석.py").exists(),
    reason="배포판이 아직 만들어지지 않았다",
)
def test_single_file_build_is_light_and_runs() -> None:
    """배포용 단일 파일이 CoolProp 외에 아무것도 필요로 하지 않아야 한다."""
    path = ROOT / "dist" / "터보냉동기_사이클해석.py"
    source = path.read_text(encoding="utf-8")
    for lib in HEAVY:
        assert not re.search(rf"^\s*(import|from)\s+{lib}\b", source, re.M), (
            f"배포판이 {lib} 을(를) 쓰고 있다"
        )
    # __main__ 블록은 맨 끝 하나뿐이어야 한다 (중간에 있으면 먼저 실행돼 버린다)
    assert source.count('if __name__ == "__main__":') == 1

    import importlib.util

    spec = importlib.util.spec_from_file_location("_dist_build", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_dist_build"] = module
    try:
        spec.loader.exec_module(module)
        res = module.solve(module.CycleInput(), stages=2)
        assert res.cop > 1.0
        assert "<svg" in module.render_page({})
    finally:
        sys.modules.pop("_dist_build", None)
