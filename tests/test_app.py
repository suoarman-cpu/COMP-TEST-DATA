"""웹 화면(app.py) 이 예외 없이 그려지는지 확인한다.

streamlit 이 없으면 통째로 건너뛴다 (CLI 만 쓰는 환경을 위해).
"""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("matplotlib")

from pathlib import Path  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

#: 사이드바 계산이 많아 기본 3초로는 모자란다
TIMEOUT = 180

#: app.py 는 저장소 최상위에 있다
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def run_app(**widget_changes) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, at.exception
    for key, value in widget_changes.items():
        _set_widget(at, key, value)
    if widget_changes:
        at.run()
    return at


def _set_widget(at: AppTest, label_fragment: str, value) -> None:
    """라벨 일부로 위젯을 찾아 값을 바꾼다."""
    for group in (at.checkbox, at.radio, at.selectbox, at.slider, at.number_input):
        for widget in group:
            if label_fragment in (widget.label or ""):
                widget.set_value(value)
                return
    raise AssertionError(f"'{label_fragment}' 위젯을 찾지 못했다")


def test_app_renders_without_error() -> None:
    at = run_app()
    assert not at.exception
    assert any("터보 냉동기" in t.value for t in at.title)
    # 요약 지표 8개 (COP, 소비전력, ... )
    assert len(at.metric) >= 8
    assert not at.error


def test_app_single_stage() -> None:
    at = run_app(**{"압축 단수": 1})
    assert not at.exception
    assert not at.error


def test_app_iplv_tab() -> None:
    """IPLV 를 켜면 부하점 4개가 계산된다."""
    at = run_app(**{"IPLV (부분부하 효율)": True})
    assert not at.exception
    assert not at.error
    labels = [m.label for m in at.metric]
    assert any("IPLV" in (label or "") for label in labels)


def test_app_reports_impossible_condition() -> None:
    """말이 안 되는 조건을 넣으면 예외가 아니라 안내 메시지가 떠야 한다."""
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    # 응축기 approach 를 음수 가까이 낮춰 응축온도를 증발온도 아래로 내린다
    _set_widget(at, "냉각 공기/물 입구온도", 0.0)
    _set_widget(at, "응축기 approach", 0.5)
    _set_widget(at, "냉수 출구온도", 25.0)
    at.run()
    assert not at.exception
    assert at.error, "에러 메시지가 떠야 한다"
