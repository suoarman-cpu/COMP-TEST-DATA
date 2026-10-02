"""엑셀 계산서가 파이썬 엔진과 같은 답을 내는지 검증한다.

원본 엑셀의 진짜 문제는 '엑셀이라서' 가 아니라 '검증이 없어서' 였다.
응축 열량이 20% 과소평가되던 오류가 오래 숨어 있었던 것도 그래서다.
여기서는 엑셀을 LibreOffice 로 실제 계산시킨 뒤, 그 숫자를 파이썬
엔진(CoolProp) 과 맞춰 본다. 수식을 고치다 깨뜨리면 여기서 걸린다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

openpyxl = pytest.importorskip("openpyxl")

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None,
    reason="LibreOffice 가 없으면 엑셀 수식을 계산할 수 없다",
)

#: 표 보간에서 오는 오차. 측정 불확도보다 훨씬 작다.
TOLERANCE = 0.3     # [%]

#: 사용자가 보는 유일한 시트
CALC = "계산"

#: 확인할 값이 들어 있는 칸. build_workbook 의 줄 번호와 짝이 맞아야 한다.
CELLS = {
    "증발온도": "B30",
    "응축온도": "B31",
    "중간압": "B35",
    "2단 토출온도": "C43",      # 상태점 4 (STATE_ROW0=40)
    "중간단 유량비": "B56",
    "냉동효과": "B64",
    "증발기 유량": "B65",
    "흡입 체적유량": "B68",
    "총 축동력": "B72",
    "COP": "B76",
    "응축 열량": "B78",
    "수지 오차": "B79",
}

#: 계산서에 담긴 냉매 (키, CoolProp 이름)
CASES = [
    ("R1234zeE", "R1234ze(E)"),
    ("R134a", "R134a"),
    ("R1234yf", "R1234yf"),
    ("R513A", "R513A.mix"),
]


def _recalc_script() -> Path | None:
    hits = list(Path("/root/.claude/skills").rglob("xlsx/scripts/recalc.py"))
    return hits[0] if hits else None


def _recalc(path: str) -> None:
    """LibreOffice 로 실제 계산시키고, 오류 칸이 하나도 없는지 본다."""
    script = _recalc_script()
    if script is None:
        pytest.skip("recalc.py 를 찾지 못했다")
    result = subprocess.run(
        [sys.executable, str(script), path, "240"],
        capture_output=True, text=True, timeout=400,
    )
    report = json.loads(result.stdout)
    assert report.get("status") == "success", f"{Path(path).name}: {report}"
    assert report["total_errors"] == 0, report


@pytest.fixture(scope="module")
def master(tmp_path_factory) -> str:
    """계산서를 한 번 만들어 둔다 (냉매는 기본값 그대로).

    서식·드롭다운·차트를 보는 시험은 이 원본을 쓴다. openpyxl 로
    다시 저장하면 차트가 떨어져 나가므로 건드리지 않는다.
    """
    from excel.make_all import main as make_all

    out = tmp_path_factory.mktemp("xlsx")
    return make_all(str(out))


@pytest.fixture(scope="module")
def switched(master, tmp_path_factory) -> dict:
    """냉매 칸(B4)만 바꿔 가며 냉매별로 계산시킨 사본들.

    계산서가 한 개이므로, '냉매를 고른다' 는 것이 곧 B4 를 쓰는 것이다.
    사람이 드롭다운에서 고르는 동작을 그대로 흉내 낸다.
    """
    out = tmp_path_factory.mktemp("switched")
    paths = {}
    for key, refrigerant in CASES:
        path = out / f"{key}.xlsx"
        shutil.copyfile(master, path)
        wb = openpyxl.load_workbook(path)
        wb[CALC]["B4"] = refrigerant
        wb.save(path)
        _recalc(str(path))
        paths[refrigerant] = str(path)
    return paths


def _compression_notes(ws) -> list[str]:
    """등엔트로피 압축 줄의 판정 문구('과열' / '습압축 ...')를 모은다."""
    out = []
    for r in range(4, 30):
        label = ws[f"A{r}"].value
        note = ws[f"K{r}"].value
        if label and "등엔트로피" in str(label) and note:
            out.append(str(note))
    return out


@pytest.mark.parametrize("_key,refrigerant", CASES)
def test_excel_matches_python(switched, _key: str, refrigerant: str) -> None:
    """고른 냉매마다 엑셀이 낸 숫자가 파이썬 엔진과 맞아야 한다."""
    from turbochiller import CycleInput, solve

    ws = openpyxl.load_workbook(switched[refrigerant], data_only=True)[CALC]
    res = solve(
        CycleInput(
            refrigerant=refrigerant, capacity_rt=150, chilled_water_out=7,
            evap_approach=1, cooling_medium_in=35, cond_approach=15,
            superheat=1, subcool=3, dp_suction=3,
            eta_is_stage1=0.8, eta_is_stage2=0.8, eta_wire_to_shaft=0.89,
        ),
        stages=2,
    )

    checks = [
        ("증발온도", ws[CELLS["증발온도"]].value, res.inp.te),
        ("응축온도", ws[CELLS["응축온도"]].value, res.inp.tc),
        ("중간압", ws[CELLS["중간압"]].value, res.state(2).p),
        ("2단 토출온도", ws[CELLS["2단 토출온도"]].value,
         res.stage_results[1].t_out),
        ("중간단 유량비", ws[CELLS["중간단 유량비"]].value,
         res.subcond_mass_ratio),
        ("증발기 유량", ws[CELLS["증발기 유량"]].value, res.mass_flow_evap),
        ("흡입 체적유량", ws[CELLS["흡입 체적유량"]].value, res.volume_flow_m3h),
        ("총 축동력", ws[CELLS["총 축동력"]].value, res.shaft_power),
        ("COP", ws[CELLS["COP"]].value, res.cop_input),
        ("응축 열량", ws[CELLS["응축 열량"]].value, res.qc),
    ]
    for name, got, expected in checks:
        assert got is not None, f"{name}: 엑셀 값이 비어 있다"
        assert got == pytest.approx(expected, rel=TOLERANCE / 100), name


@pytest.mark.parametrize("_key,refrigerant", CASES)
def test_excel_energy_balance_closes(switched, _key: str,
                                     refrigerant: str) -> None:
    """엑셀 스스로 하는 에너지 수지 점검이 0 에 가까워야 한다."""
    ws = openpyxl.load_workbook(switched[refrigerant], data_only=True)[CALC]
    assert abs(ws[CELLS["수지 오차"]].value) < 0.3


def test_wet_compression_is_detected(switched) -> None:
    """R1234yf 는 1단 등엔트로피 압축이 포화영역 안으로 들어간다.

    과열표만으로는 값을 찾을 수 없는 경우다. 건도로 갈라 계산하고,
    그 사실을 사용자에게 알려 줘야 한다.
    """
    ws = openpyxl.load_workbook(switched["R1234yf"], data_only=True)["조회"]
    notes = _compression_notes(ws)
    wet = [n for n in notes if "습압축" in n]
    assert wet, "습압축을 알려주는 문구가 없다"
    assert "0.99" in wet[0], f"건도가 이상하다: {wet[0]}"


def test_dry_compression_is_labelled(switched) -> None:
    """R1234ze(E) 는 두 단 모두 과열 압축이어야 한다."""
    ws = openpyxl.load_workbook(switched["R1234ze(E)"], data_only=True)["조회"]
    notes = _compression_notes(ws)
    assert notes, "판정 문구가 없다"
    assert all("습압축" not in n for n in notes)


def test_inputs_are_marked_editable(master) -> None:
    """고쳐도 되는 칸은 파란 글씨여야 한다 (쓰는 사람이 구분할 수 있게)."""
    from excel.build_workbook import INPUTS

    ws = openpyxl.load_workbook(master)[CALC]
    for row, name, *_ in INPUTS:
        cell = ws[f"B{row}"]
        assert cell.font.color is not None, f"{name}: 색이 없다"
        assert cell.font.color.rgb.endswith("0000FF"), f"{name}: 파란색이 아니다"
    assert ws["B4"].font.color.rgb.endswith("0000FF"), "냉매 칸이 파란색이 아니다"


def test_only_calc_sheet_is_visible(master) -> None:
    """쓰는 사람에게는 계산 시트만 보여야 한다."""
    wb = openpyxl.load_workbook(master)
    visible = [n for n in wb.sheetnames if wb[n].sheet_state == "visible"]
    assert visible == [CALC], visible


def test_refrigerant_dropdown_lists_all(master) -> None:
    """냉매 칸에 목록(드롭다운)이 달려 있어야 한다."""
    from excel.make_all import REFRIGERANTS

    ws = openpyxl.load_workbook(master)[CALC]
    lists = [dv for dv in ws.data_validations.dataValidation if dv.type == "list"]
    assert lists, "드롭다운이 없다"
    formula = lists[0].formula1
    for refrigerant in REFRIGERANTS:
        assert refrigerant in formula, refrigerant


def test_ph_chart_exists(master) -> None:
    """P-h 선도에 포화선·등온선·건도선·사이클이 모두 있어야 한다."""
    from excel.build_workbook import CHART_CURVES

    from excel.build_workbook import N_LABELS

    ws = openpyxl.load_workbook(master)[CALC]
    assert len(ws._charts) == 1, "차트가 없다"
    chart = ws._charts[0]
    assert len(chart.series) == len(CHART_CURVES) + 1 + N_LABELS
    assert chart.y_axis.scaling.logBase == 10, "압력축이 로그가 아니다"


def test_chart_has_isotherms(master) -> None:
    """온도선이 있어야 한다. 온도를 못 읽는 선도는 쓸모가 적다."""
    from excel.chartlines import ISOTHERMS

    ws = openpyxl.load_workbook(master)[CALC]
    titles = [s.tx.v for s in ws._charts[0].series if s.tx is not None]
    for t in ISOTHERMS:
        assert f"{t:g}" in titles, f"{t}°C 등온선이 없다"


def test_chart_has_all_four_line_families(master) -> None:
    """실제 P-h 선도처럼 네 가지 보조선이 다 있어야 한다."""
    from excel.build_workbook import CHART_KINDS

    for kind in ("등온", "건도", "등엔트로피", "등비체적"):
        assert kind in CHART_KINDS, f"{kind}선이 없다"


def test_numbers_are_on_the_lines_not_in_the_legend(master) -> None:
    """온도·건도 숫자는 선 위에 적혀 있어야 한다.

    범례로 빼면 어느 선이 몇 도인지 알아볼 수가 없다. 한 점짜리 계열에
    '계열 이름 표시' 를 켜는 방식만 엑셀과 LibreOffice 둘 다에서 똑같이
    나온다.
    """
    from excel.build_workbook import LABEL_TEXTS

    ws = openpyxl.load_workbook(master)[CALC]
    labelled = {
        s.tx.v for s in ws._charts[0].series
        if s.tx is not None and s.dLbls is not None and s.dLbls.showSerName
    }
    for text in LABEL_TEXTS:
        assert text in labelled, f"'{text}' 가 선 위에 안 적혀 있다"


def test_chart_has_no_legend(master) -> None:
    """범례는 없어야 한다.

    계열이 78 개라 범례를 켜면 그림의 절반을 잡아먹는다. 엑셀은
    legendEntry 로 항목을 지우는 것도 무시한다 — 켜면 전부 나온다.
    숫자는 선 위에 적혀 있으니 범례가 할 일이 없다.
    """
    chart = openpyxl.load_workbook(master)[CALC]._charts[0]
    assert chart.legend is None, "범례가 켜져 있다"


def test_helper_cells_are_off_the_calc_sheet(master) -> None:
    """표 위치를 찾는 칸은 계산 시트에 있으면 안 된다.

    선도 옆으로 숫자가 비어져 나온다. 숨긴 설정 시트에 둬야 한다.
    """
    ws = openpyxl.load_workbook(master)[CALC]
    for row in ws.iter_rows(min_col=9, max_col=30):
        for cell in row:
            assert cell.value is None, f"{cell.coordinate} 에 {cell.value!r}"


def test_every_series_is_straight(master) -> None:
    """모든 계열에 smooth=0 이 적혀 있어야 한다.

    <c:smooth> 를 빠뜨린 계열이 하나라도 있으면 LibreOffice 는 그걸
    차트 전체에 적용해, 사이클을 둥근 덩어리로 뭉개 버린다.
    """
    chart = openpyxl.load_workbook(master)[CALC]._charts[0]
    for i, ser in enumerate(chart.series):
        assert ser.smooth is not None and not ser.smooth, f"{i}번 계열"


def test_chart_labels_do_not_overlap(master) -> None:
    """선 위 숫자끼리 겹치면 안 된다 — 냉매 4종 모두."""
    from excel.chartlines import LABEL_H, _norm, build_many, label_width
    from excel.make_all import REFRIGERANTS

    for cl in build_many(REFRIGERANTS):
        items = [(t, *_norm(h, p), label_width(t)) for t, h, p in cl.labels]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                t1, x1, y1, w1 = items[i]
                t2, x2, y2, w2 = items[j]
                gap = max(abs(x1 - x2) / ((w1 + w2) / 2),
                          abs(y1 - y2) / LABEL_H)
                assert gap >= 1.0, (
                    f"{cl.refrigerant}: '{t1}' 과 '{t2}' 가 겹친다 ({gap:.2f})")


def test_chart_lines_follow_refrigerant(master) -> None:
    """냉매마다 보조선 값이 달라야 한다 (한 냉매 것을 돌려쓰면 안 된다)."""
    from excel.chartlines import build_many
    from excel.make_all import REFRIGERANTS

    lines = build_many(REFRIGERANTS)
    domes = [tuple(round(v, 3) for v in cl.curves[0].h) for cl in lines]
    assert len(set(domes)) == len(REFRIGERANTS), "포화 돔이 겹친다"


def test_pure_fluid_dome_closes_at_critical_point(master) -> None:
    """순수냉매의 포화 돔은 임계점에서 닫혀야 한다 (액선 끝 ≈ 증기선 끝).

    혼합냉매는 제외한다. R513A 는 임계점 근처에서 CoolProp 의 밀도 풀이가
    깨진다 ("critical point finding routine found 2 critical points").
    임계온도 4.4 K 아래까지가 한계라, 돔 꼭대기가 벌어진 채로 남는다.
    없는 값을 지어내 메우느니 계산되는 데까지만 그린다 — 운전 범위는
    임계점보다 45 K 아래라 쓰는 데 지장이 없다.
    """
    from excel.chartlines import build_many
    from excel.make_all import REFRIGERANTS

    pure = [r for r in REFRIGERANTS if not r.endswith(".mix")]
    assert pure, "순수냉매가 하나도 없다"
    for cl in build_many(pure):
        dome = cl.curves[0]
        half = len(dome.h) // 2
        gap = abs(dome.h[half - 1] - dome.h[half])
        span = max(dome.h) - min(dome.h)
        assert gap < span * 0.02, f"{cl.refrigerant}: 돔이 {gap:.1f} 벌어졌다"


def test_mixture_dome_is_drawn_as_far_as_coolprop_allows(master) -> None:
    """혼합냉매 돔도 임계점 가까이까지는 올라가야 한다.

    닫히지는 않지만, 중간에서 끊기면 그건 다른 문제다.
    """
    from excel.chartlines import build_many
    from excel.make_all import REFRIGERANTS
    from turbochiller.props import t_crit

    mixes = [r for r in REFRIGERANTS if r.endswith(".mix")]
    for cl in build_many(mixes):
        dome = cl.curves[0]
        tc = t_crit(cl.refrigerant)
        import CoolProp
        from CoolProp import AbstractState
        st = AbstractState("HEOS", cl.refrigerant)
        st.update(CoolProp.QT_INPUTS, 1.0, tc - 10.0 + 273.15)
        assert max(dome.p) >= st.p() / 1000.0 * 0.98, (
            f"{cl.refrigerant}: 돔이 임계점에서 10 K 넘게 모자란다")


def test_no_formula_exceeds_excel_limit(master) -> None:
    """엑셀은 수식 한 칸이 8192자를 넘으면 그 수식을 조용히 버린다.

    오류 표시도 없이 값만 0 이 된다. LibreOffice 에는 이 한도가 없어서
    리브레로 계산해 보는 것만으로는 절대 잡히지 않는다. 실제로 h2s/h4s
    수식이 8333자였고, 엑셀에서 열면 압축 동력이 음수로 나왔다.
    """
    from excel.build_workbook import EXCEL_FORMULA_LIMIT

    wb = openpyxl.load_workbook(master)
    longest = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.startswith("="):
                    longest.append((len(v), ws.title, cell.coordinate))
    longest.sort(reverse=True)
    assert longest, "수식이 하나도 없다"
    n, sheet, coord = longest[0]
    assert n <= EXCEL_FORMULA_LIMIT, f"{sheet}!{coord} 가 {n}자다"


def test_formula_nesting_is_within_excel_limit(master) -> None:
    """엑셀의 함수 중첩 한도는 64단이다."""
    wb = openpyxl.load_workbook(master)
    worst = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                depth = 0
                for ch in v:
                    if ch == "(":
                        depth += 1
                        worst = max(worst, depth)
                    elif ch == ")":
                        depth -= 1
    assert worst <= 64, f"중첩이 {worst}단이다"
