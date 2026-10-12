"""게이지 R&R 검증.

AIAG MSA 4판 본문의 예제 (부품 10 × 측정자 3 × 3회) 로 두 방법 모두 대조한다.
"""

from __future__ import annotations

import math
import re
import xml.dom.minidom

import pytest

from turbochiller import gagerr, webui

# AIAG MSA 4판 예제 데이터 — [회차][부품]
_A = [[0.29, -0.56, 1.34, 0.47, -0.80, 0.02, 0.59, -0.31, 2.26, -1.36],
      [0.41, -0.68, 1.17, 0.50, -0.92, -0.11, 0.75, -0.20, 1.99, -1.25],
      [0.64, -0.58, 1.27, 0.64, -0.84, -0.21, 0.66, -0.17, 2.01, -1.31]]
_B = [[0.08, -0.47, 1.19, 0.01, -0.56, -0.20, 0.47, -0.63, 1.80, -1.68],
      [0.25, -1.22, 0.94, 1.03, -1.20, 0.22, 0.55, 0.08, 2.12, -1.62],
      [0.07, -0.68, 1.34, 0.20, -1.28, 0.06, 0.83, -0.34, 2.19, -1.50]]
_C = [[0.04, -1.38, 0.88, 0.14, -1.46, -0.29, 0.02, -0.46, 1.77, -1.49],
      [-0.11, -1.13, 1.09, 0.20, -1.07, -0.67, 0.01, -0.56, 1.45, -1.77],
      [-0.15, -0.96, 0.67, 0.11, -1.45, -0.49, 0.21, -0.49, 1.87, -2.16]]


@pytest.fixture(scope="module")
def aiag() -> gagerr.Study:
    rows = []
    for op, table in zip("ABC", (_A, _B, _C)):
        for trial in table:
            for i, v in enumerate(trial, start=1):
                rows.append((str(i), op, v))
    return gagerr.build_study(rows)


def test_xbar_r_matches_aiag(aiag) -> None:
    """MSA 4판 평균·범위 법 결과: EV .20188 AV .22963 GRR .30575 PV 1.10456 TV 1.14610"""
    r = gagerr.xbar_r_method(aiag)
    assert r.ev == pytest.approx(0.20188, abs=5e-5)
    assert r.av == pytest.approx(0.22963, abs=5e-5)
    assert r.grr == pytest.approx(0.30575, abs=5e-5)
    assert r.pv == pytest.approx(1.10456, abs=5e-5)
    assert r.tv == pytest.approx(1.14610, abs=5e-5)
    assert r.pct_grr == pytest.approx(26.68, abs=0.01)
    assert r.ndc == 5


def test_anova_matches_aiag(aiag) -> None:
    """MSA 4판 ANOVA 법 결과 (교호작용 p=0.974 → 오차에 합침)."""
    r = gagerr.anova_method(aiag)
    assert r.interaction_pooled
    assert r.interaction_p == pytest.approx(0.974, abs=0.001)
    assert r.ev == pytest.approx(0.199933, abs=1e-5)
    assert r.av == pytest.approx(0.226838, abs=1e-5)
    assert r.grr == pytest.approx(0.302372, abs=1e-5)
    assert r.pv == pytest.approx(1.042327, abs=1e-5)
    assert r.tv == pytest.approx(1.085300, abs=1e-5)
    assert r.ndc == 4
    # 제곱합이 서로 맞아떨어지는지
    ss = {row.source: row.ss for row in r.anova}
    assert ss["부품"] + ss["측정자"] + ss["반복성(오차)"] == pytest.approx(ss["합계"])


def test_r_chart_flags_aiag_outlier(aiag) -> None:
    """MSA 본문도 측정자 B 의 부품 4 를 관리 이탈로 짚는다."""
    cc = gagerr.chart_check(aiag)
    assert [(p, o) for p, o, _ in cc.out_r] == [("4", "B")]


@pytest.mark.parametrize("f, d1, d2, expected", [
    (1.0, 1, 1, 0.5),                               # 대칭
    (4.9646, 1, 10, 0.05),                          # t(10) 양측 5% 의 제곱
    (0.4, 2, 78, (1 + 2 * 0.4 / 78) ** -39),        # d1=2 닫힌 꼴
    (7.5, 2, 9, (1 + 2 * 7.5 / 9) ** -4.5),
])
def test_f_pvalue(f, d1, d2, expected) -> None:
    assert gagerr.f_pvalue(f, d1, d2) == pytest.approx(expected, rel=1e-4)


def test_interaction_kept_when_significant() -> None:
    """측정자 B 가 부품마다 다르게 재면 교호작용이 남아야 한다."""
    rows = []
    for p in range(1, 6):
        for op in "AB":
            shift = (0.5 if p % 2 else -0.5) if op == "B" else 0.0
            for t in (-0.01, 0.0, 0.01):
                rows.append((str(p), op, p + shift + t))
    r = gagerr.anova_method(gagerr.build_study(rows))
    assert not r.interaction_pooled
    assert r.var_interaction > 0
    assert any(row.source == "부품×측정자" for row in r.anova)


def test_perfect_gage_does_not_crash() -> None:
    rows = [(str(p), op, float(p)) for p in range(1, 4) for op in "AB" for _ in range(2)]
    r = gagerr.anova_method(gagerr.build_study(rows), tolerance=1.0)
    assert r.grr == 0
    assert r.pct_grr == 0
    assert gagerr.overall_verdict(r)[0] == "적합"


def test_verdict_thresholds() -> None:
    assert gagerr.verdict_of(9.9) == "적합"
    assert gagerr.verdict_of(10.0) == "조건부"
    assert gagerr.verdict_of(30.0) == "조건부"
    assert gagerr.verdict_of(30.1) == "부적합"


def test_tolerance_percent(aiag) -> None:
    r = gagerr.anova_method(aiag, tolerance=6.0)
    # 6σ / 공차 = σ 그대로
    assert r.pct_grr_tol == pytest.approx(100 * r.grr)


# ---------------------------------------------------------------------------
# 표 읽기
# ---------------------------------------------------------------------------

def test_wide_and_long_tables_agree() -> None:
    wide = gagerr.parse_table(gagerr.EXAMPLE_CSV)
    long_lines = ["부품,측정자,반복,측정값"]
    for op in wide.operators:
        for t in range(wide.trials):
            for p in wide.parts:
                long_lines.append(f"{p},{op},{t + 1},{wide.data[(p, op)][t]}")
    long = gagerr.parse_table("\n".join(long_lines))
    assert long.data == wide.data


def test_tab_separated_paste_from_excel() -> None:
    text = gagerr.EXAMPLE_CSV.replace(",", "\t")
    assert gagerr.parse_table(text).n_parts == 10


def test_english_headers_and_wide_without_separator() -> None:
    s = gagerr.parse_table("Part,A1,A2,B1,B2\n1,1.0,1.1,1.2,1.0\n2,2.0,2.1,2.2,2.1\n")
    assert s.operators == ["A", "B"] and s.trials == 2
    s = gagerr.parse_table(
        "part,operator,value\n1,x,1\n1,x,2\n2,x,3\n2,x,4\n1,y,1\n1,y,2\n2,y,3\n2,y,5\n"
    )
    assert s.operators == ["x", "y"]


@pytest.mark.parametrize("text, words", [
    ("", "비어"),
    ("부품,A-1,A-2\n1,1,2\n2,1,2\n", "측정자"),
    ("부품,A-1,A-2,B-1\n1,1,2,3\n2,1,2,3\n", "반복 횟수"),
    ("부품,A-1,A-2,B-1,B-2\n1,1,2,3,abc\n2,1,2,3,4\n", "숫자"),
    ("부품,무엇,A-2\n1,1,2\n", "머리글"),
])
def test_bad_tables_give_korean_message(text, words) -> None:
    with pytest.raises(ValueError, match=words):
        gagerr.parse_table(text)


def test_cli_runs_example(capsys) -> None:
    assert gagerr.main([]) == 0
    assert "게이지 R&R" in capsys.readouterr().out


def test_cli_reads_example_file(capsys) -> None:
    assert gagerr.main(["examples/게이지RR_임펠러외경.csv", "--tol", "0.1"]) == 0
    assert "%공차" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------

def test_page_first_visit_shows_example() -> None:
    html = webui.render_gagerr_page({})
    assert "예제 데이터" in html
    assert "분산 성분" in html and "ANOVA 표" in html
    for svg in re.findall(r"<svg viewBox.*?</svg>", html, re.S):
        xml.dom.minidom.parseString(svg)


def test_page_shows_message_for_bad_data() -> None:
    html = webui.render_gagerr_page({"data": ["부품,A-1\n1,2"]})
    assert "계산할 수 없습니다" in html


def test_page_escapes_user_input() -> None:
    html = webui.render_gagerr_page({"data": ["<script>alert(1)</script>"]})
    assert "<script>alert" not in html


def test_page_without_tolerance_has_no_tolerance_column() -> None:
    html = webui.render_gagerr_page({"data": [gagerr.EXAMPLE_CSV], "lsl": [""], "usl": [""]})
    assert "<th>%공차</th>" not in html
    assert "%GRR (총변동 대비)" in html


def test_page_rejects_one_sided_spec() -> None:
    html = webui.render_gagerr_page({"data": [gagerr.EXAMPLE_CSV], "lsl": ["1"], "usl": [""]})
    assert "둘 다" in html


def test_both_pages_link_to_each_other() -> None:
    assert 'href="/gagerr"' in webui.render_page({})
    assert 'href="/"' in webui.render_gagerr_page({})


def test_numbers_are_finite_for_example() -> None:
    r = gagerr.anova_method(gagerr.parse_table(gagerr.EXAMPLE_CSV), 0.1)
    for _, var in r.components():
        assert math.isfinite(var) and var >= 0
