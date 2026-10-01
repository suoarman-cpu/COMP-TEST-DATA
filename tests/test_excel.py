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


def _recalc_script() -> Path | None:
    hits = list(Path("/root/.claude/skills").rglob("xlsx/scripts/recalc.py"))
    return hits[0] if hits else None


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """냉매별 계산서를 만들고 LibreOffice 로 계산까지 시킨다."""
    from excel.make_all import main as make_all

    out = tmp_path_factory.mktemp("xlsx")
    paths = make_all(str(out))

    script = _recalc_script()
    if script is None:
        pytest.skip("recalc.py 를 찾지 못했다")

    for path in paths:
        result = subprocess.run(
            [sys.executable, str(script), path, "240"],
            capture_output=True, text=True, timeout=400,
        )
        report = json.loads(result.stdout)
        assert report.get("status") == "success", (
            f"{Path(path).name}: {report}"
        )
        assert report["total_errors"] == 0
    return {Path(p).stem.split("_")[-1]: p for p in paths}


def _compression_notes(ws) -> list[str]:
    """등엔트로피 압축 줄의 판정 문구('과열' / '습압축 ...')를 모은다."""
    out = []
    for r in range(4, 30):
        label = ws[f"A{r}"].value
        note = ws[f"K{r}"].value
        if label and "등엔트로피" in str(label) and note:
            out.append(str(note))
    return out


CASES = [
    ("R1234zeE", "R1234ze(E)"),
    ("R134a", "R134a"),
    ("R1234yf", "R1234yf"),
    ("R513A", "R513A.mix"),
]


@pytest.mark.parametrize("key,refrigerant", CASES)
def test_excel_matches_python(built, key: str, refrigerant: str) -> None:
    """엑셀이 낸 숫자가 파이썬 엔진과 맞아야 한다."""
    from turbochiller import CycleInput, solve

    ws = openpyxl.load_workbook(built[key], data_only=True)["계산"]
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
        ("증발온도", ws["B19"].value, res.inp.te),
        ("응축온도", ws["B20"].value, res.inp.tc),
        ("중간압", ws["B24"].value, res.state(2).p),
        ("2단 토출온도", ws["C32"].value, res.stage_results[1].t_out),
        ("중간단 유량비", ws["B47"].value, res.subcond_mass_ratio),
        ("증발기 유량", ws["B57"].value, res.mass_flow_evap),
        ("흡입 체적유량", ws["B59"].value, res.volume_flow_m3h),
        ("총 축동력", ws["B63"].value, res.shaft_power),
        ("COP", ws["B67"].value, res.cop_input),
        ("응축 열량", ws["B69"].value, res.qc),
    ]
    for name, got, expected in checks:
        assert got is not None, f"{name}: 엑셀 값이 비어 있다"
        assert got == pytest.approx(expected, rel=TOLERANCE / 100), name


@pytest.mark.parametrize("key,_ref", CASES)
def test_excel_energy_balance_closes(built, key: str, _ref: str) -> None:
    """엑셀 스스로 하는 에너지 수지 점검이 0 에 가까워야 한다."""
    ws = openpyxl.load_workbook(built[key], data_only=True)["계산"]
    assert abs(ws["B70"].value) < 0.3


def test_wet_compression_is_detected(built) -> None:
    """R1234yf 는 1단 등엔트로피 압축이 포화영역 안으로 들어간다.

    과열표만으로는 값을 찾을 수 없는 경우다. 건도로 갈라 계산하고,
    그 사실을 사용자에게 알려 줘야 한다.
    """
    ws = openpyxl.load_workbook(built["R1234yf"], data_only=True)["조회"]
    notes = _compression_notes(ws)
    wet = [n for n in notes if "습압축" in n]
    assert wet, "습압축을 알려주는 문구가 없다"
    assert "0.99" in wet[0], f"건도가 이상하다: {wet[0]}"


def test_dry_compression_is_labelled(built) -> None:
    """R1234ze(E) 는 두 단 모두 과열 압축이어야 한다."""
    ws = openpyxl.load_workbook(built["R1234zeE"], data_only=True)["조회"]
    notes = _compression_notes(ws)
    assert notes, "판정 문구가 없다"
    assert all("습압축" not in n for n in notes)


def test_inputs_are_marked_editable(built) -> None:
    """고쳐도 되는 칸은 파란 글씨여야 한다 (쓰는 사람이 구분할 수 있게)."""
    wb = openpyxl.load_workbook(built["R134a"])
    ws = wb["계산"]
    from excel.build_workbook import INPUTS

    for cell, name, *_ in INPUTS:
        assert ws[cell].font.color is not None, f"{name}: 색이 없다"
        assert ws[cell].font.color.rgb.endswith("0000FF"), f"{name}: 파란색이 아니다"
