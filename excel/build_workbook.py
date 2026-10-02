"""애드인 없이 혼자 도는 엑셀 사이클 계산서를 만든다.

구조
    [계산]      입력칸과 사이클 결과. 여기를 고쳐 쓰면 된다.
    [조회]      물성표를 뒤지는 보간 계산. 중간값이 다 보이게 펼쳐 두었다.
    [물성_포화] 포화 물성표
    [물성_h/s/d] 과열증기 표 (행 = 과열도, 열 = 압력)

물성표를 '과열도 x 압력' 으로 잡은 이유
    압력마다 포화온도가 달라서 온도를 그대로 행으로 쓰면 표가 들쭉날쭉해진다.
    행을 과열도(포화온도로부터 몇 도 위인가)로 잡으면 모든 압력에서 행이
    가지런해져 보간 수식이 단순해진다.
"""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.chart.axis import ChartLines as Gridlines
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.legend import Legend, LegendEntry
from openpyxl.chart.marker import Marker
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .chartlines import (ISOCHORE_STARTS, ISENTROPE_STARTS, ISOTHERMS,
                         N_POINTS, QUALITIES, ChartLines)
from .tables import PropertyTables
from .version import CHANGELOG, REVISION, revision_label

#: 선도에 그릴 곡선의 이름 — chartlines.build 가 내놓는 순서 그대로다.
CHART_CURVES = (["포화선"]
                + [f"{t:g}°C" for t in ISOTHERMS]
                + [f"x={x:g}" for x in QUALITIES]
                + [f"s@{t:g}°C" for t in ISENTROPE_STARTS]
                + [f"v@{t:g}°C" for t in ISOCHORE_STARTS])

#: 같은 순서로 선 종류 (색·굵기를 정하는 데 쓴다)
CHART_KINDS = (["돔"]
               + ["등온"] * len(ISOTHERMS)
               + ["건도"] * len(QUALITIES)
               + ["등엔트로피"] * len(ISENTROPE_STARTS)
               + ["등비체적"] * len(ISOCHORE_STARTS))

#: 선 위에 붙는 이름표 — chartlines 의 labels 순서와 같아야 한다.
#: 등엔트로피선·등비체적선은 글자가 길어 온도 숫자와 겹친다. 이 둘만
#: 범례로 밝히고, 숫자를 읽어야 하는 온도·건도는 선 위에 직접 적는다.
LABEL_TEXTS = ([f"{t:g}°C" for t in ISOTHERMS]
               + [f"{x:g}" for x in QUALITIES])
N_LABELS = len(LABEL_TEXTS)

#: 범례에 남길 선 — (곡선 번호, 범례에 쓸 이름)
LEGEND_KEEP = {
    0: "포화선",
    1 + len(ISOTHERMS) + len(QUALITIES): "등엔트로피선",
    1 + len(ISOTHERMS) + len(QUALITIES) + len(ISENTROPE_STARTS): "등비체적선",
}

FONT = "맑은 고딕"          # 전부 한글이라 한글 전용 서체를 쓴다

# 색 규칙 (엑셀 모델 관례)
BLUE = Font(name=FONT, size=10, color="0000FF")        # 사람이 넣는 값
BLACK = Font(name=FONT, size=10)                       # 수식
TITLE = Font(name=FONT, size=12, bold=True)
HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
NOTE = Font(name=FONT, size=9, color="808080")
HEAD_FILL = PatternFill("solid", fgColor="44546A")
INPUT_FILL = PatternFill("solid", fgColor="FFF7E0")
BOX = Border(*[Side(style="thin", color="D0D0D0")] * 4)

# 시트 이름
S_CALC, S_LOOK, S_CONF = "계산", "조회", "설정"
S_LINES = "선도데이터"
S_SAT, S_H, S_S, S_D = "물성_포화", "물성_h", "물성_s", "물성_밀도"

#: 과열표가 시작하는 행/열 (1행 = 압력 머리글, A열 = 과열도)
GRID_R0, GRID_C0 = 2, 2


def _grid_sheet(wb: Workbook, name: str, tabs: list[PropertyTables],
                pick, unit: str) -> None:
    """과열증기 표. 행 = 과열도(냉매 공통), 열 = 냉매별 압력 블록을 나란히.

    냉매를 바꾸면 '열 오프셋' 만 달라진다. 시트를 갈아끼우는 방식(INDIRECT)
    보다 빠르고 덜 깨진다.
    """
    ws = wb.create_sheet(name)
    ws["A1"] = "과열도 \\ 압력[kPa]"
    ws["A1"].font = Font(name=FONT, size=9, bold=True)
    superheats = tabs[0].superheats
    for r, dt in enumerate(superheats):
        cell = ws.cell(row=GRID_R0 + r, column=1, value=dt)
        cell.font = Font(name=FONT, size=9, bold=True)
        cell.number_format = "0.0"

    col = GRID_C0
    for t in tabs:
        values = pick(t)
        for c, p in enumerate(t.pressures):
            head = ws.cell(row=1, column=col + c, value=round(p, 4))
            head.font = Font(name=FONT, size=9, bold=True)
            head.number_format = "0.0"
        for r in range(len(superheats)):
            for c in range(len(t.pressures)):
                v = values[r][c]
                cc = ws.cell(row=GRID_R0 + r, column=col + c,
                             value=None if v != v else round(v, 6))
                cc.font = Font(name=FONT, size=9)
                cc.number_format = "0.0000"
        col += len(t.pressures)

    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 11
    note = ws.cell(row=GRID_R0 + len(superheats) + 2, column=1,
                   value=f"과열증기 {unit}. 행=포화온도로부터의 과열도[K], "
                         "열=압력[kPa]. 냉매별 블록이 가로로 이어 붙어 있다. "
                         "CoolProp 으로 미리 계산한 값이다 — 고치지 말 것.")
    note.font = NOTE


def write_tables(wb: Workbook, tabs: list[PropertyTables]) -> dict:
    """물성표와 설정 시트를 쓴다. 냉매별 위치 정보를 돌려준다."""
    # --- 포화표 : 냉매별로 세로로 이어 붙인다 ---
    ws = wb.create_sheet(S_SAT)
    headers = ["온도 [°C]", "포화압력 [kPa]", "포화액 h [kJ/kg]",
               "포화증기 h [kJ/kg]", "포화액 s [kJ/kg·K]",
               "포화증기 s [kJ/kg·K]", "포화증기 밀도 [kg/m³]", "냉매"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = 15
    layout = {}
    row = 2
    for ti, t in enumerate(tabs):
        start = row
        for values in t.saturation:
            for c, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=c, value=round(v, 6))
                cell.font = Font(name=FONT, size=9)
                cell.number_format = "0.0000"
            ws.cell(row=row, column=8, value=t.refrigerant).font = Font(
                name=FONT, size=9)
            row += 1
        layout[t.refrigerant] = {
            "sat_start": start,
            "sat_end": row - 1,
            "col_offset": ti * len(t.pressures),
            "n_cols": len(t.pressures),
        }
    ws.freeze_panes = "A2"
    ws.cell(row=row + 2, column=1,
            value="포화 물성표. 냉매별로 세로로 이어 붙어 있다. "
                  "CoolProp 으로 미리 계산한 값이다 — 고치지 말 것.").font = NOTE

    _grid_sheet(wb, S_H, tabs, lambda t: t.h, "엔탈피 [kJ/kg]")
    _grid_sheet(wb, S_S, tabs, lambda t: t.s, "엔트로피 [kJ/kg·K]")
    _grid_sheet(wb, S_D, tabs, lambda t: t.rho, "밀도 [kg/m³]")

    # --- 설정 시트 : 냉매별 표 위치 ---
    conf = wb.create_sheet(S_CONF)
    conf["A1"] = "냉매별 표 위치"
    conf["A1"].font = TITLE
    conf["A2"] = "계산 시트에서 냉매를 고르면 여기서 위치를 찾아 쓴다 — 고치지 말 것."
    conf["A2"].font = NOTE
    for c, h in enumerate(["냉매", "포화 시작행", "포화 끝행", "과열 열오프셋",
                           "과열 열수", "선도 열오프셋"], start=1):
        cell = conf.cell(row=3, column=c, value=h)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        conf.column_dimensions[get_column_letter(c)].width = 15
    for i, t in enumerate(tabs):
        info = layout[t.refrigerant]
        for c, v in enumerate([t.refrigerant, info["sat_start"], info["sat_end"],
                               info["col_offset"], info["n_cols"],
                               i * LINE_COLS], start=1):
            conf.cell(row=4 + i, column=c, value=v).font = BLACK
    layout["_conf_rows"] = len(tabs)
    layout["_n_sh"] = len(tabs[0].superheats)
    return layout



# ---------------------------------------------------------------------------
# 보간 수식 조각
# ---------------------------------------------------------------------------
# 엑셀에 없는 함수는 쓰지 않는다. INDEX / MATCH / 사칙연산만 쓴다.
#
# 냉매를 바꾸면 '표에서 볼 자리' 가 달라진다. 그 자리를 가리키는 칸을
# 계산 시트에 두고(SAT_START/SAT_END/COL_OFF/N_COLS), 아래 수식들이 그걸
# 참조한다. 시트 이름을 바꿔 끼우는 INDIRECT 보다 빠르고 덜 깨진다.

#: 선택된 냉매의 표 위치가 들어 있는 칸 (계산 시트).
#: P-h 선도가 F 열부터 앉으므로, 겹치지 않게 멀리 R 열로 빼 두었다.
SAT_START = f"'{S_CALC}'!$R$5"
SAT_END = f"'{S_CALC}'!$R$6"
COL_OFF = f"'{S_CALC}'!$R$7"
N_COLS = f"'{S_CALC}'!$R$8"
LINE_OFF = f"'{S_CALC}'!$R$9"


def sat_col(column: int) -> str:
    """포화표의 한 열에서, 지금 고른 냉매에 해당하는 구간만 잘라낸다.

    INDEX(열,시작):INDEX(열,끝) 은 범위를 동적으로 만드는 방법이다.
    OFFSET 과 달리 '휘발성' 이 아니라 다시 계산할 일이 적다.
    """
    letter = get_column_letter(column)
    whole = f"'{S_SAT}'!${letter}:${letter}"
    return f"INDEX({whole},{SAT_START}):INDEX({whole},{SAT_END})"


def sat_lookup(key_col: int, value_col: int, key_ref: str) -> str:
    """포화표에서 한 값으로 다른 값을 찾는다 (1차원 선형보간)."""
    keys = sat_col(key_col)
    vals = sat_col(value_col)
    n = f"({SAT_END}-{SAT_START})"          # 구간 길이 - 1
    i = f"MIN(MATCH({key_ref},{keys},1),{n})"
    k0, k1 = f"INDEX({keys},{i})", f"INDEX({keys},{i}+1)"
    v0, v1 = f"INDEX({vals},{i})", f"INDEX({vals},{i}+1)"
    return f"={v0}+({key_ref}-{k0})/({k1}-{k0})*({v1}-{v0})"


def grid_block(sheet: str, n_rows: int, total_cols: int) -> str:
    """과열표의 값 부분 전체 (모든 냉매 블록을 포함한다)."""
    c1 = get_column_letter(GRID_C0)
    c2 = get_column_letter(GRID_C0 + total_cols - 1)
    return f"'{sheet}'!${c1}${GRID_R0}:${c2}${GRID_R0 + n_rows - 1}"


def grid_pressures(total_cols: int) -> str:
    """과열표 머리글(압력) 전체 범위."""
    c1 = get_column_letter(GRID_C0)
    c2 = get_column_letter(GRID_C0 + total_cols - 1)
    return f"'{S_H}'!${c1}$1:${c2}$1"


def my_pressures(total_cols: int) -> str:
    """지금 고른 냉매의 압력 머리글 구간만 잘라낸다."""
    whole = grid_pressures(total_cols)
    return f"INDEX({whole},{COL_OFF}+1):INDEX({whole},{COL_OFF}+{N_COLS})"


def grid_superheats(n_rows: int) -> str:
    """과열표 첫 열(과열도). 냉매 공통이다."""
    return f"'{S_H}'!$A${GRID_R0}:$A${GRID_R0 + n_rows - 1}"


def bilinear(sheet: str, dt_ref: str, p_ref: str, ri_ref: str, ci_ref: str,
             n_rows: int, total_cols: int) -> str:
    """과열표에서 2방향 보간. ci_ref 는 '냉매 블록 안에서의' 열 번호다."""
    blk = grid_block(sheet, n_rows, total_cols)
    ps = my_pressures(total_cols)
    ds = grid_superheats(n_rows)
    c = f"({ci_ref}+{COL_OFF})"             # 전체 표에서의 실제 열 번호
    p0, p1 = f"INDEX({ps},{ci_ref})", f"INDEX({ps},{ci_ref}+1)"
    d0, d1 = f"INDEX({ds},{ri_ref})", f"INDEX({ds},{ri_ref}+1)"
    v00 = f"INDEX({blk},{ri_ref},{c})"
    v10 = f"INDEX({blk},{ri_ref}+1,{c})"
    v01 = f"INDEX({blk},{ri_ref},{c}+1)"
    v11 = f"INDEX({blk},{ri_ref}+1,{c}+1)"
    a = f"({v00}+({dt_ref}-{d0})/({d1}-{d0})*({v10}-{v00}))"
    b = f"({v01}+({dt_ref}-{d0})/({d1}-{d0})*({v11}-{v01}))"
    return f"={a}+({p_ref}-{p0})/({p1}-{p0})*({b}-{a})"


def inverse_dt(sheet: str, target_ref: str, p_ref: str, ci_ref: str,
               n_rows: int, total_cols: int) -> str:
    """그 압력에서 어떤 물성이 목표값이 되는 '과열도' 를 거꾸로 찾는다."""
    blk = grid_block(sheet, n_rows, total_cols)
    ps = my_pressures(total_cols)
    ds = grid_superheats(n_rows)
    c = f"({ci_ref}+{COL_OFF})"
    p0, p1 = f"INDEX({ps},{ci_ref})", f"INDEX({ps},{ci_ref}+1)"

    def in_column(col_expr: str) -> str:
        # INDEX(범위,0,열) 로도 한 열을 통째로 집을 수 있지만, 행 번호 0 을
        # 어떻게 보느냐가 엑셀 버전마다 미묘하다. 시작·끝을 또박또박 적어
        # INDEX(..):INDEX(..) 로 잡으면 해석의 여지가 없다.
        col = (f"INDEX({blk},1,{col_expr}):"
               f"INDEX({blk},{n_rows},{col_expr})")
        i = f"MIN(MATCH({target_ref},{col},1),{n_rows - 1})"
        v0, v1 = f"INDEX({col},{i})", f"INDEX({col},{i}+1)"
        s0, s1 = f"INDEX({ds},{i})", f"INDEX({ds},{i}+1)"
        return f"({s0}+({target_ref}-{v0})/({v1}-{v0})*({s1}-{s0}))"

    left, right = in_column(c), in_column(f"{c}+1")
    return f"={left}+({p_ref}-{p0})/({p1}-{p0})*({right}-{left})"


# ---------------------------------------------------------------------------
# 조회 시트 — 물성 조회를 한 줄씩 펼쳐 놓는다
# ---------------------------------------------------------------------------
# 한 칸에 긴 수식을 몰아넣지 않고 중간값(포화온도·과열도·행·열 번호)을
# 옆 칸에 드러낸다. 값이 이상할 때 어디서 틀어졌는지 바로 보인다.

class Lookup:
    """조회 시트를 채우면서, 각 결과가 있는 칸 주소를 돌려준다."""

    def __init__(self, ws, tabs: list[PropertyTables]):
        self.ws = ws
        self.n_row = len(tabs[0].superheats)
        self.total_cols = sum(len(t.pressures) for t in tabs)
        self.row = 4
        ws["A1"] = "물성 조회"
        ws["A1"].font = TITLE
        ws["A2"] = ("물성표를 뒤져 보간하는 칸이다. 중간값을 일부러 펼쳐 두었다. "
                    "계산 시트가 여기 결과를 가져다 쓴다 — 직접 고치지 말 것.")
        ws["A2"].font = NOTE
        for col, head in zip("ABCDEFGHIJKLMNOPQ",
                             ["이름", "입력1", "입력2", "포화온도", "과열도",
                              "행", "열", "결과1", "결과2", "결과3", "비고",
                              "sf", "sg", "hf", "hg", "건도", "과열 h"]):
            c = ws[f"{col}3"]
            c.value = head
            c.font = HEAD
            c.fill = HEAD_FILL
        ws.column_dimensions["A"].width = 26
        ws.column_dimensions["K"].width = 34
        for col in "BCDEFGHIJLMNOPQ":
            ws.column_dimensions[col].width = 13

    def _label(self, name: str, note: str = "") -> int:
        r = self.row
        self.ws[f"A{r}"] = name
        self.ws[f"A{r}"].font = BLACK
        if note:
            self.ws[f"K{r}"] = note
            self.ws[f"K{r}"].font = NOTE
        self.row += 1
        return r

    def sat(self, name: str, key_col: int, val_col: int, key_ref: str,
            note: str = "") -> str:
        """포화표 1차원 조회. 결과 칸 주소를 돌려준다."""
        r = self._label(name, note)
        self.ws[f"B{r}"] = f"={key_ref}"
        self.ws[f"H{r}"] = sat_lookup(key_col, val_col, f"B{r}")
        for col in "BH":
            self.ws[f"{col}{r}"].font = BLACK
            self.ws[f"{col}{r}"].number_format = "0.0000"
        return f"'{S_LOOK}'!H{r}"

    def superheated(self, name: str, t_ref: str, p_ref: str,
                    note: str = "") -> tuple[str, str, str]:
        """과열증기 2차원 조회. (h, s, 밀도) 칸 주소를 돌려준다."""
        r = self._label(name, note)
        w = self.ws
        w[f"B{r}"] = f"={t_ref}"
        w[f"C{r}"] = f"={p_ref}"
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}")
        w[f"E{r}"] = f"=B{r}-D{r}"
        w[f"F{r}"] = (f"=MIN(MATCH(E{r},{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{my_pressures(self.total_cols)},1),"
                      f"{N_COLS}-1)")
        w[f"H{r}"] = bilinear(S_H, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        w[f"I{r}"] = bilinear(S_S, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        w[f"J{r}"] = bilinear(S_D, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        for col in "BCDEHIJ":
            w[f"{col}{r}"].font = BLACK
            w[f"{col}{r}"].number_format = "0.0000"
        for col in "FG":
            w[f"{col}{r}"].font = BLACK
        return (f"'{S_LOOK}'!H{r}", f"'{S_LOOK}'!I{r}", f"'{S_LOOK}'!J{r}")

    def from_entropy(self, name: str, s_ref: str, p_ref: str,
                     note: str = "") -> str:
        """등엔트로피 압축: s 와 압력으로 엔탈피를 찾는다.

        압축 후가 포화영역 안으로 들어가는 경우(습압축)가 있다. 그때는
        과열표에 값이 없으므로, 건도를 구해 포화액·포화증기 사이를 비례
        배분한다. R1234yf 처럼 포화증기선 기울기가 다른 냉매에서 실제로
        일어난다.
        """
        r = self._label(name, note or "과열이면 표 보간, 습압축이면 건도로 계산")
        w = self.ws
        w[f"B{r}"] = f"={s_ref}"
        w[f"C{r}"] = f"={p_ref}"
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}")          # 포화온도
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{my_pressures(self.total_cols)},1),"
                      f"{N_COLS}-1)")
        # 그 압력에서의 포화 물성. 한 칸씩 따로 둔다 — 수식 안에 통째로
        # 끼워 넣으면 엑셀의 수식 길이 한도(8192자)를 넘겨 버린다.
        w[f"L{r}"] = sat_lookup(1, 5, f"D{r}")          # sf
        w[f"M{r}"] = sat_lookup(1, 6, f"D{r}")          # sg
        w[f"N{r}"] = sat_lookup(1, 3, f"D{r}")          # hf
        w[f"O{r}"] = sat_lookup(1, 4, f"D{r}")          # hg
        w[f"P{r}"] = f"=(B{r}-L{r})/(M{r}-L{r})"        # 건도
        w[f"K{r}"] = (f"=IF(B{r}>=M{r},\"과열\",\"습압축 (건도 \"&"
                      f"TEXT(P{r},\"0.000\")&\")\")")
        w[f"K{r}"].font = NOTE
        # 과열 쪽 계산 (표 역보간)
        dt = inverse_dt(S_S, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.total_cols)[1:]
        w[f"E{r}"] = f"=IF(B{r}>=M{r},{dt},0)"
        w[f"F{r}"] = (f"=MIN(MATCH(MAX(E{r},0),{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        w[f"Q{r}"] = bilinear(S_H, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        # 과열이면 표 보간값, 습압축이면 건도로 포화액·포화증기 사이 배분
        w[f"H{r}"] = f"=IF(B{r}>=M{r},Q{r},N{r}+P{r}*(O{r}-N{r}))"
        for col in "BCDEHLMNOPQ":
            w[f"{col}{r}"].font = BLACK
            w[f"{col}{r}"].number_format = "0.0000"
        return f"'{S_LOOK}'!H{r}"

    def temp_from_enthalpy(self, name: str, h_ref: str, p_ref: str,
                           note: str = "") -> tuple[str, str]:
        """엔탈피와 압력으로 온도를 찾는다. (온도, 엔트로피) 칸 주소."""
        r = self._label(name, note)
        w = self.ws
        w[f"B{r}"] = f"={h_ref}"
        w[f"C{r}"] = f"={p_ref}"
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}")
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{my_pressures(self.total_cols)},1),"
                      f"{N_COLS}-1)")
        # 2상 영역이면 온도는 포화온도 그대로다 (과열도 0)
        w[f"O{r}"] = sat_lookup(1, 4, f"D{r}")          # hg
        w[f"O{r}"].number_format = "0.0000"
        dt = inverse_dt(S_H, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.total_cols)[1:]
        w[f"E{r}"] = f"=IF(B{r}>=O{r},{dt},0)"
        w[f"F{r}"] = (f"=MIN(MATCH(MAX(E{r},0),{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        w[f"H{r}"] = f"=D{r}+E{r}"
        w[f"I{r}"] = bilinear(S_S, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        w[f"J{r}"] = bilinear(S_D, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.total_cols)
        for col in "BCDEHIJ":
            w[f"{col}{r}"].font = BLACK
            w[f"{col}{r}"].number_format = "0.0000"
        return (f"'{S_LOOK}'!H{r}", f"'{S_LOOK}'!I{r}")


# ---------------------------------------------------------------------------
# 계산 시트
# ---------------------------------------------------------------------------
# 보는 순서를 "냉매 고르기 → 결과 한눈에 → 입력 → 상세" 로 잡았다.
# 쓰는 사람이 제일 먼저 보고 싶은 건 COP 와 소비전력이지, 중간 계산이 아니다.

#: 입력칸 — (행, 이름, 기본값, 단위, 설명)
INPUTS = [
    (16, "냉동능력",            150.0, "RT",  "정격 냉동능력"),
    (17, "냉수 입구온도",        12.0, "°C",  ""),
    (18, "냉수 출구온도",         7.0, "°C",  ""),
    (19, "증발기 approach",      1.0, "K",   "증발온도 = 냉수 출구 − 이 값"),
    (20, "과열도",               1.0, "K",   ""),
    (21, "냉각 공기/물 입구온도", 35.0, "°C", "공랭이면 외기온도"),
    (22, "응축기 approach",     15.0, "K",   "응축온도 = 냉각 입구 + 이 값"),
    (23, "과냉도",               3.0, "K",   ""),
    (24, "흡입관 압력손실",       3.0, "kPa", ""),
    (25, "1단 단열효율",         0.80, "-",   ""),
    (26, "2단 단열효율",         0.80, "-",   ""),
    (27, "wire-to-shaft 효율",  0.89, "-",   "모터·인버터 효율"),
]

#: 상태점 이름과 행
STATE_ROW0 = 40
STATE_NAMES = {
    1: "1단 흡입", 2: "1단 토출", 3: "2단 흡입(혼합후)", 4: "2단 토출",
    5: "응축기 출구(과냉액)", 6: "서브콘덴서 입구", 7: "서브콘덴서 액출구",
    8: "증발기 입구(팽창후)", 9: "증발기 출구",
}
SR = {n: STATE_ROW0 + n - 1 for n in STATE_NAMES}


def _put(ws, cell, value, font=BLACK, fmt=None, fill=None):
    ws[cell] = value
    ws[cell].font = font
    if fmt:
        ws[cell].number_format = fmt
    if fill:
        ws[cell].fill = fill


def _section(ws, row: int, title: str, span: str = "ABCD") -> None:
    ws[f"A{row}"] = title
    ws[f"A{row}"].font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
    for col in span:
        ws[f"{col}{row}"].fill = HEAD_FILL


def _row(ws, r: int, name: str, formula, unit: str = "", desc: str = "",
         fmt: str = "0.000", bold: bool = False) -> None:
    _put(ws, f"A{r}", name,
         Font(name=FONT, size=10, bold=True) if bold else BLACK)
    _put(ws, f"B{r}", formula, Font(name=FONT, size=10, bold=True) if bold
         else BLACK, fmt)
    if unit:
        _put(ws, f"C{r}", unit, NOTE)
    if desc:
        _put(ws, f"D{r}", desc, NOTE)


def write_calc(ws, lk: "Lookup", tabs: list[PropertyTables], layout: dict) -> None:
    """계산 시트를 쓴다."""
    names = [t.refrigerant for t in tabs]

    ws["A1"] = "터보 냉동기 사이클 계산"
    ws["A1"].font = Font(name=FONT, size=16, bold=True)
    ws["A2"] = "2단 압축 + 이코노마이저 ·  파란 칸만 고치면 됩니다"
    ws["A2"].font = Font(name=FONT, size=10, color="808080")
    # 리비전은 눈에 띄는 자리에 찍는다. 파일 이름이 비슷해서 옛 판을
    # 열어 놓고 새 판인 줄 아는 일이 실제로 있었다.
    _put(ws, "D1", revision_label(),
         Font(name=FONT, size=11, bold=True, color="1F3864"))
    _put(ws, "D2", next(c for n, _, c in CHANGELOG if n == REVISION), NOTE)
    ws.column_dimensions["A"].width = 22
    # D 는 설명 글과 상태점 표의 '압력' 을 겸한다. E/F 는 엔탈피·밀도라
    # 숫자가 들어갈 만큼 넓혀야 한다 (좁으면 ### 으로 깨진다).
    for col, w in zip("BCDEFGH", (15, 9, 30, 15, 14, 12, 10)):
        ws.column_dimensions[col].width = w

    # ---- 냉매 고르기 ----
    _put(ws, "A4", "냉매", Font(name=FONT, size=12, bold=True))
    _put(ws, "B4", names[0], Font(name=FONT, size=12, bold=True, color="0000FF"),
         fill=INPUT_FILL)
    ws["B4"].border = Border(*[Side(style="medium", color="0000FF")] * 4)
    _put(ws, "D4", "← 칸을 누르면 목록이 나옵니다", NOTE)
    dv = DataValidation(type="list", formula1=f'"{",".join(names)}"',
                        allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv)
    dv.add(ws["B4"])

    # 고른 냉매의 표 위치 (수식이 참조한다. 보기엔 거추장스러워 옆으로 뺐다)
    conf_n = layout["_conf_rows"]
    _put(ws, "Q4", "표 위치 (자동)", NOTE)
    for i, (label, col) in enumerate(
            [("포화 시작행", 2), ("포화 끝행", 3), ("과열 열오프셋", 4),
             ("과열 열수", 5), ("선도 열오프셋", 6)]):
        r = 5 + i
        _put(ws, f"Q{r}", label, NOTE)
        _put(ws, f"R{r}",
             f"=INDEX('{S_CONF}'!${get_column_letter(col)}$4:"
             f"${get_column_letter(col)}${3 + conf_n},"
             f"MATCH($B$4,'{S_CONF}'!$A$4:$A${3 + conf_n},0))", NOTE)

    # ---- 결과 한눈에 ----
    _section(ws, 6, "■ 결과")
    summary = [
        (7, "COP (입력전력 기준)", "=B76", "", "0.000"),
        (8, "소비전력", "=B73", "kW", "0.0"),
        (9, "냉동톤당 전력", "=B77", "kW/RT", "0.0000"),
        (10, "흡입 체적유량", "=B68", "m³/h", "0.0"),
        (11, "총 압축비", "=B74", "", "0.000"),
        (12, "2단 토출온도", f"=C{SR[4]}", "°C", "0.0"),
        (13, "에너지 수지 오차", "=B79", "%", "0.000"),
    ]
    for r, name, f, unit, fmt in summary:
        _put(ws, f"A{r}", name, Font(name=FONT, size=10, bold=True))
        _put(ws, f"B{r}", f, Font(name=FONT, size=13, bold=True,
                                  color="1F3864"), fmt)
        if unit:
            _put(ws, f"C{r}", unit, NOTE)
    _put(ws, "D13", "0 에서 멀어지면 입력 조합이 말이 안 된다는 뜻입니다", NOTE)

    # ---- 입력 ----
    _section(ws, 15, "■ 입력 — 파란 칸만 고치세요")
    for r, name, default, unit, desc in INPUTS:
        _put(ws, f"A{r}", name)
        _put(ws, f"B{r}", default, BLUE, "0.00", INPUT_FILL)
        _put(ws, f"C{r}", unit, NOTE)
        if desc:
            _put(ws, f"D{r}", desc, NOTE)

    # ---- 운전조건 ----
    _section(ws, 29, "■ 운전조건 (입력에서 자동 계산)")
    _row(ws, 30, "증발온도 Te", "=B18-B19", "°C", "냉수 출구 − 증발기 approach")
    _row(ws, 31, "응축온도 Tc", "=B21+B22", "°C", "냉각 입구 + 응축기 approach")
    _row(ws, 32, "냉동능력", "=B16*3.516", "kW", "1 RT = 3.516 kW")

    p_evap = lk.sat("증발압력 Psat(Te)", 1, 2, f"'{S_CALC}'!B30")
    p_cond = lk.sat("응축압력 Psat(Tc)", 1, 2, f"'{S_CALC}'!B31")
    _row(ws, 33, "증발압력 Pe", f"={p_evap}", "kPa", "", "0.00")
    _row(ws, 34, "응축압력 Pc", f"={p_cond}", "kPa", "", "0.00")
    _row(ws, 35, "중간압 Pm", "=SQRT(B33*B34)", "kPa",
         "흡입·토출 압력의 기하평균. 두 단의 압축비가 고르게 나뉩니다", "0.00")
    t_mid = lk.sat("서브콘덴서 온도 Tsat(Pm)", 2, 1, f"'{S_CALC}'!B35")
    _row(ws, 36, "서브콘덴서 온도 Tm", f"={t_mid}", "°C")

    # ---- 상태점 ----
    _section(ws, 38, "■ 상태점")
    for c, h in enumerate(["No", "위치", "온도 [°C]", "압력 [kPa]",
                           "엔탈피 [kJ/kg]", "밀도 [kg/m³]"], start=1):
        cell = ws.cell(row=39, column=c, value=h)
        cell.font = Font(name=FONT, size=10, bold=True)
        cell.fill = PatternFill("solid", fgColor="E7E6E6")
        cell.border = BOX
        cell.alignment = Alignment(horizontal="center")
    for n, label in STATE_NAMES.items():
        _put(ws, f"A{SR[n]}", n)
        _put(ws, f"B{SR[n]}", label)
        for col in "ABCDEF":
            ws[f"{col}{SR[n]}"].border = BOX

    # 1 : 1단 흡입
    _put(ws, f"C{SR[1]}", "=B30+B20", BLACK, "0.00")
    _put(ws, f"D{SR[1]}", "=B33-B24", BLACK, "0.00")
    h1, s1, d1 = lk.superheated("상태1 1단 흡입",
                                f"'{S_CALC}'!C{SR[1]}", f"'{S_CALC}'!D{SR[1]}")
    _put(ws, f"E{SR[1]}", f"={h1}", BLACK, "0.000")
    _put(ws, f"F{SR[1]}", f"={d1}", BLACK, "0.00")

    # 9 : 증발기 출구
    _put(ws, f"C{SR[9]}", "=B30+B20", BLACK, "0.00")
    _put(ws, f"D{SR[9]}", "=B33", BLACK, "0.00")
    h9, _, _ = lk.superheated("상태9 증발기 출구",
                              f"'{S_CALC}'!C{SR[9]}", f"'{S_CALC}'!D{SR[9]}")
    _put(ws, f"E{SR[9]}", f"={h9}", BLACK, "0.000")

    # 5 / 6 / 7 / 8
    _put(ws, f"C{SR[5]}", "=B31-B23", BLACK, "0.00")
    _put(ws, f"D{SR[5]}", "=B34", BLACK, "0.00")
    h5 = lk.sat("상태5 과냉액 hf(T5)", 1, 3, f"'{S_CALC}'!C{SR[5]}",
                "과냉액은 압력 영향이 작아 포화액 엔탈피로 봅니다")
    _put(ws, f"E{SR[5]}", f"={h5}", BLACK, "0.000")
    _put(ws, f"C{SR[6]}", "=B36", BLACK, "0.00")
    _put(ws, f"D{SR[6]}", "=B35", BLACK, "0.00")
    _put(ws, f"E{SR[6]}", f"=E{SR[5]}", BLACK, "0.000")
    _put(ws, f"C{SR[7]}", "=B36-B23", BLACK, "0.00")
    _put(ws, f"D{SR[7]}", "=B35", BLACK, "0.00")
    h7 = lk.sat("상태7 서브콘덴서 액 hf(T7)", 1, 3, f"'{S_CALC}'!C{SR[7]}")
    _put(ws, f"E{SR[7]}", f"={h7}", BLACK, "0.000")
    _put(ws, f"C{SR[8]}", "=B30", BLACK, "0.00")
    _put(ws, f"D{SR[8]}", "=B33", BLACK, "0.00")
    _put(ws, f"E{SR[8]}", f"=E{SR[7]}", BLACK, "0.000")

    # ---- 압축기 ----
    _section(ws, 50, "■ 압축 계산")
    _row(ws, 51, "1단 흡입 엔트로피 s1", f"={s1}", "kJ/kg·K", "", "0.0000")
    h2s = lk.from_entropy("1단 등엔트로피 h2s", f"'{S_CALC}'!B51",
                          f"'{S_CALC}'!B35")
    _row(ws, 52, "1단 등엔트로피 h2s", f"={h2s}", "kJ/kg")
    _row(ws, 53, "1단 단열 헤드", f"=B52-E{SR[1]}", "kJ/kg")
    _row(ws, 54, "1단 실제 헤드", "=B53/B25", "kJ/kg", "단열 헤드 ÷ 1단 효율")
    _put(ws, f"D{SR[2]}", "=B35", BLACK, "0.00")
    _put(ws, f"E{SR[2]}", f"=E{SR[1]}+B54", BLACK, "0.000")
    t2, _ = lk.temp_from_enthalpy("상태2 1단 토출", f"'{S_CALC}'!E{SR[2]}",
                                  f"'{S_CALC}'!D{SR[2]}")
    _put(ws, f"C{SR[2]}", f"={t2}", BLACK, "0.00")

    hg_mid = lk.sat("중간압 포화증기 hg(Tm)", 1, 4, f"'{S_CALC}'!B36")
    _row(ws, 55, "중간압 포화증기 hg", f"={hg_mid}", "kJ/kg")
    _row(ws, 56, "중간단 유량비 x", f"=(E{SR[5]}-E{SR[7]})/(B55-E{SR[5]})", "",
         "이코노마이저 에너지 수지: (1+x)·h5 = x·hg + h7", "0.0000")

    _put(ws, f"D{SR[3]}", "=B35", BLACK, "0.00")
    _put(ws, f"E{SR[3]}", f"=(E{SR[2]}+B56*B55)/(1+B56)", BLACK, "0.000")
    t3, s3 = lk.temp_from_enthalpy("상태3 2단 흡입", f"'{S_CALC}'!E{SR[3]}",
                                   f"'{S_CALC}'!D{SR[3]}")
    _put(ws, f"C{SR[3]}", f"={t3}", BLACK, "0.00")
    _row(ws, 57, "2단 흡입 엔트로피 s3", f"={s3}", "kJ/kg·K", "", "0.0000")
    h4s = lk.from_entropy("2단 등엔트로피 h4s", f"'{S_CALC}'!B57",
                          f"'{S_CALC}'!B34")
    _row(ws, 58, "2단 등엔트로피 h4s", f"={h4s}", "kJ/kg")
    _row(ws, 59, "2단 단열 헤드", f"=B58-E{SR[3]}", "kJ/kg")
    _row(ws, 60, "2단 실제 헤드", "=B59/B26", "kJ/kg")
    _put(ws, f"D{SR[4]}", "=B34", BLACK, "0.00")
    _put(ws, f"E{SR[4]}", f"=E{SR[3]}+B60", BLACK, "0.000")
    t4, _ = lk.temp_from_enthalpy("상태4 2단 토출", f"'{S_CALC}'!E{SR[4]}",
                                  f"'{S_CALC}'!D{SR[4]}")
    _put(ws, f"C{SR[4]}", f"={t4}", BLACK, "0.00")

    # ---- 최종 ----
    _section(ws, 63, "■ 계산 결과")
    _row(ws, 64, "냉동효과", f"=E{SR[9]}-E{SR[8]}", "kJ/kg", "증발기에서 받는 열")
    _row(ws, 65, "증발기 유량", "=B32/B64", "kg/s", "냉동능력 ÷ 냉동효과", "0.0000")
    _row(ws, 66, "전체 유량", "=B65*(1+B56)", "kg/s", "1단 유량 × (1+x)", "0.0000")
    _row(ws, 67, "흡입 밀도", f"=F{SR[1]}", "kg/m³", "", "0.00")
    _row(ws, 68, "흡입 체적유량", "=B65/B67*3600", "m³/h",
         "압축기 크기를 정하는 값", "0.0")
    _row(ws, 69, "체적 냉동능력", "=B67*B64", "kJ/m³", "흡입 1 m³ 당 냉동능력", "0.0")
    _row(ws, 70, "1단 축동력", "=B65*B54", "kW")
    _row(ws, 71, "2단 축동력", "=B66*B60", "kW")
    _row(ws, 72, "총 축동력", "=B70+B71", "kW", "", "0.000", bold=True)
    _row(ws, 73, "총 입력전력", "=B72/B27", "kW", "축동력 ÷ wire-to-shaft 효율",
         "0.000", bold=True)
    _row(ws, 74, "총 압축비", f"=B34/D{SR[1]}", "", "", "0.000")
    _row(ws, 75, "COP (축동력)", "=B32/B72", "", "", "0.0000")
    _row(ws, 76, "COP (입력전력)", "=B32/B73", "", "", "0.0000", bold=True)
    _row(ws, 77, "냉동톤당 전력", "=B73/B16", "kW/RT", "작을수록 좋습니다",
         "0.0000")
    _row(ws, 78, "응축 열량 Qc", f"=B66*(E{SR[4]}-E{SR[5]})", "kW",
         "응축기가 버리는 열")
    _row(ws, 79, "에너지 수지 오차", "=(B78-B32-B72)/B32*100", "%",
         "Qc − Qe − W. 0 에 가까워야 정상입니다", "0.000")


# ---------------------------------------------------------------------------
# P-h 선도
# ---------------------------------------------------------------------------

S_CHART = "차트데이터"

#: 곡선 하나가 쓰는 열 수 (h, P)
CURVE_COLS = 2

#: 한 냉매가 선도데이터 시트에서 차지하는 열 수
LINE_COLS = len(CHART_CURVES) * CURVE_COLS

#: 사이클 경로 (상태점 번호 순서). 1 로 돌아와 고리를 닫는다.
CYCLE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]

#: 사이클 좌표가 들어가는 열 (선도 곡선들 다음 자리)
CYCLE_C0 = 2 + LINE_COLS

#: 이름표 좌표가 들어가는 열 / 선도데이터 시트에서의 시작 행
LABEL_C0 = CYCLE_C0 + 2
LABEL_R0 = 3 + N_POINTS + 2


def write_lines_sheet(wb: Workbook, lines: list[ChartLines]) -> None:
    """등온선·건도선·포화돔을 냉매별로 나란히 심는다.

    이 선들은 냉매만 정해지면 결정된다. 운전조건과 무관하므로 엑셀이
    매번 풀 이유가 없고, CoolProp 으로 미리 계산한 값을 그대로 둔다.
    """
    ws = wb.create_sheet(S_LINES)
    ws["A1"] = "P-h 선도 보조선 (미리 계산한 값 — 고치지 말 것)"
    ws["A1"].font = TITLE
    for i, cl in enumerate(lines):
        base = 2 + i * LINE_COLS
        for j, curve in enumerate(cl.curves):
            c0 = base + j * CURVE_COLS
            head = f"{cl.refrigerant} {curve.label}"
            ws.cell(row=2, column=c0, value=f"{head} h").font = HEAD
            ws.cell(row=2, column=c0 + 1, value=f"{head} P").font = HEAD
            for k, (h, pp) in enumerate(zip(curve.h, curve.p)):
                ws.cell(row=3 + k, column=c0, value=round(h, 4))
                ws.cell(row=3 + k, column=c0 + 1, value=round(pp, 4))
        # 이름표 좌표는 곡선 블록 아래에 따로 쌓는다.
        ws.cell(row=LABEL_R0 - 1, column=base, value="이름표 h").font = HEAD
        ws.cell(row=LABEL_R0 - 1, column=base + 1, value="이름표 P").font = HEAD
        for k, (_text, h, pp) in enumerate(cl.labels):
            ws.cell(row=LABEL_R0 + k, column=base, value=round(h, 4))
            ws.cell(row=LABEL_R0 + k, column=base + 1, value=round(pp, 4))


def write_chart_data(wb: Workbook, lines: list[ChartLines]) -> int:
    """고른 냉매의 선들을 차트가 읽을 자리로 옮겨 적는다.

    차트는 참조 범위를 고정해 두어야 한다. 그래서 '고른 냉매의 블록을
    여기로 베껴 오는' 칸을 따로 두고, 차트는 늘 이 자리만 본다.
    """
    ws = wb.create_sheet(S_CHART)
    ws["A1"] = "P-h 선도용 데이터"
    ws["A1"].font = TITLE
    ws["A2"] = ("계산 시트에서 고른 냉매의 선을 선도데이터 시트에서 "
                "가져온다 — 고치지 말 것.")
    ws["A2"].font = NOTE

    n_pt = N_POINTS
    last_col = get_column_letter(1 + len(lines) * LINE_COLS)
    block = f"'{S_LINES}'!$B$3:${last_col}${2 + n_pt}"

    for j, label in enumerate(CHART_CURVES):
        c0 = 2 + j * CURVE_COLS
        ws.cell(row=2, column=c0, value=f"{label} h").font = HEAD
        ws.cell(row=2, column=c0 + 1, value=f"{label} P").font = HEAD
        for k in range(n_pt):
            for d in (0, 1):
                col_in_block = f"({j * CURVE_COLS + 1 + d}+{LINE_OFF})"
                ws.cell(row=3 + k, column=c0 + d,
                        value=f"=INDEX({block},{k + 1},{col_in_block})")

    # 사이클 경로는 운전조건에 따라 변하므로 계산 시트에서 직접 끌어온다.
    ws.cell(row=2, column=CYCLE_C0, value="사이클 h").font = HEAD
    ws.cell(row=2, column=CYCLE_C0 + 1, value="사이클 P").font = HEAD
    for k, n in enumerate(CYCLE_ORDER):
        ws.cell(row=3 + k, column=CYCLE_C0, value=f"='{S_CALC}'!E{SR[n]}")
        ws.cell(row=3 + k, column=CYCLE_C0 + 1, value=f"='{S_CALC}'!D{SR[n]}")

    # 이름표 좌표. 한 점짜리 계열을 여기에 걸어 선 위에 글자를 띄운다.
    lbl_last = get_column_letter(1 + len(lines) * LINE_COLS)
    lbl_block = (f"'{S_LINES}'!$B${LABEL_R0}:"
                 f"${lbl_last}${LABEL_R0 + N_LABELS - 1}")
    ws.cell(row=2, column=LABEL_C0, value="이름표 h").font = HEAD
    ws.cell(row=2, column=LABEL_C0 + 1, value="이름표 P").font = HEAD
    for k in range(N_LABELS):
        for d in (0, 1):
            ws.cell(row=3 + k, column=LABEL_C0 + d,
                    value=f"=INDEX({lbl_block},{k + 1},{1 + d}+{LINE_OFF})")
    return n_pt


#: 선 모양 — (종류, 색, 굵기, 점선 여부)
LINE_STYLE = {
    "돔": ("4A4A4A", 20000, None),
    "등온": ("D4765A", 7000, None),
    "건도": ("9AA6B4", 6500, "sysDash"),
    "등엔트로피": ("7FA893", 6500, None),
    "등비체적": ("A89BBF", 6500, "sysDot"),
}


def add_ph_chart(calc_ws, n_points: int) -> None:
    """계산 시트에 P-h 선도를 붙인다."""
    chart = ScatterChart()
    chart.title = "P-h 선도"
    chart.style = 2
    chart.x_axis.title = "엔탈피 h [kJ/kg]"
    chart.y_axis.title = "압력 P [kPa]"
    chart.y_axis.scaling.logBase = 10          # 압력축은 로그로 본다
    chart.height = 13
    chart.width = 20
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    # openpyxl 은 두 축 모두 'l'(왼쪽) 로 내놓는다. 가로축은 아래가 맞다.
    chart.x_axis.axPos = "b"
    # 눈금 숫자는 정수로. 안 그러면 '100.000' 처럼 길어져 비스듬히 눕는다.
    chart.x_axis.numFmt = "0"
    chart.y_axis.numFmt = "0"
    # 네 냉매를 모두 담는 범위로 고정한다. 냉매를 바꿔도 축이 출렁이지
    # 않아야 선도끼리 눈으로 비교가 된다.
    chart.x_axis.scaling.min = 100
    chart.x_axis.scaling.max = 500
    # 로그축의 눈금은 최솟값에서 한 자리씩 올라간다. 10 에서 시작해야
    # 100 / 1000 / 10000 처럼 읽기 좋은 눈금이 나온다 (30 으로 두면
    # 30 / 300 / 3000 이 된다).
    chart.y_axis.scaling.min = 10
    chart.y_axis.scaling.max = 10000
    # 로그 모눈종이처럼 눈금선을 깐다. 압력을 눈으로 읽을 때 한 자리
    # 사이를 가늠할 수 있어야 한다. 다만 선이 진하면 정작 봐야 할
    # 등온선·사이클이 묻히므로, 보조선은 아주 연하게 깐다.
    def _grid(color: str, width: int) -> Gridlines:
        return Gridlines(spPr=GraphicalProperties(
            ln=LineProperties(solidFill=color, w=width)))

    chart.y_axis.minorGridlines = _grid("ECECEC", 3000)
    chart.y_axis.majorGridlines = _grid("D9D9D9", 4500)
    chart.x_axis.majorGridlines = _grid("D9D9D9", 4500)
    # 보조선 데이터는 숨긴 시트에 있다. 이 값이 참이면 엑셀이 숨은 칸을
    # 빼고 그려서 선이 통째로 사라진다.
    chart.visible_cells_only = False

    data = calc_ws.parent[S_CHART]

    def series(x_col: int, y_col: int, rows: int, title: str,
               color: str, width: int, dash: str | None, marker: bool):
        xs = Reference(data, min_col=x_col, min_row=3, max_row=2 + rows)
        ys = Reference(data, min_col=y_col, min_row=3, max_row=2 + rows)
        ser = Series(ys, xs, title=title)
        ln = LineProperties(solidFill=color, w=width)
        if dash:
            ln.prstDash = dash
        ser.graphicalProperties.line = ln
        ser.marker = Marker(symbol="circle" if marker else "none", size=5)
        ser.smooth = False
        return ser

    for j, label in enumerate(CHART_CURVES):
        kind = CHART_KINDS[j]
        color, width, dash = LINE_STYLE[kind]
        c0 = 2 + j * CURVE_COLS
        chart.series.append(
            series(c0, c0 + 1, n_points, LEGEND_KEEP.get(j, label),
                   color, width, dash, False))

    CYCLE_SER_IDX = len(chart.series)
    chart.series.append(
        series(CYCLE_C0, CYCLE_C0 + 1, len(CYCLE_ORDER), "사이클",
               "2A78D6", 24000, None, True))

    # 선 위에 숫자를 직접 붙인다. 범례로 빼면 어느 선이 몇 도인지 알 수가
    # 없다 — 실제 P-h 선도가 그러듯 온도와 건도를 선 옆에 적는다.
    # 한 점짜리 계열에 '계열 이름 표시' 를 켜는 방식이라야 엑셀과
    # LibreOffice 둘 다에서 똑같이 나온다 (점마다 지정하는 방식은
    # LibreOffice 가 무시하고 모든 점에 값을 찍어 버린다).
    for k, text in enumerate(LABEL_TEXTS):
        xs = Reference(data, min_col=LABEL_C0, min_row=3 + k, max_row=3 + k)
        ys = Reference(data, min_col=LABEL_C0 + 1, min_row=3 + k,
                       max_row=3 + k)
        ser = Series(ys, xs, title=text)
        ser.graphicalProperties.line = LineProperties(noFill=True)
        ser.marker = Marker(symbol="none")
        # 이 줄이 없으면 <c:smooth> 가 빠지고, LibreOffice 는 그걸 차트
        # 전체에 적용해 사이클과 등온선까지 곡선으로 뭉개 버린다.
        ser.smooth = False
        lbls = DataLabelList()
        lbls.showSerName = True
        lbls.showVal = False
        lbls.showCatName = False
        lbls.showLegendKey = False
        lbls.showBubbleSize = False
        lbls.dLblPos = "r"
        ser.dLbls = lbls
        chart.series.append(ser)

    # 범례는 선 위에 이름표를 못 붙인 것만 남긴다. 온도·건도 숫자까지
    # 범례로 보내면 어느 선이 몇 도인지 알아볼 수가 없다.
    chart.legend = Legend()
    chart.legend.position = "b"
    chart.legend.overlay = False
    chart.legend.legendEntry = [
        LegendEntry(idx=i, delete=True)
        for i in range(len(chart.series))
        if i not in LEGEND_KEEP and i != CYCLE_SER_IDX
    ]

    # 결과 바로 옆에 붙인다. 입력칸(B~D)을 가리지 않으면서 한 화면에 들어온다.
    calc_ws.add_chart(chart, "F6")


#: 엑셀의 수식 한 칸 길이 한도. 넘으면 엑셀이 파일을 열면서 그 수식을
#: 조용히 버린다 — 오류 표시도 없이 값만 0 이 된다. LibreOffice 에는
#: 이 한도가 없어서, 리브레로만 검사하면 절대 못 잡는다.
EXCEL_FORMULA_LIMIT = 8192

#: 여유를 두고 살펴볼 선. 한도의 절반이다.
SAFE_FORMULA_LEN = 4096


def check_formula_lengths(wb: Workbook) -> list[tuple[str, str, int]]:
    """한도에 가까운 수식을 모두 찾아 돌려준다 (긴 것부터)."""
    found = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.startswith("=") \
                        and len(v) > SAFE_FORMULA_LEN:
                    found.append((ws.title, cell.coordinate, len(v)))
    return sorted(found, key=lambda t: -t[2])


def build_workbook(tabs: list[PropertyTables], lines: list[ChartLines],
                   path: str) -> str:
    """냉매 여러 개를 담은 계산서 하나를 만든다."""
    wb = Workbook()
    wb.remove(wb.active)
    calc = wb.create_sheet(S_CALC)
    look = wb.create_sheet(S_LOOK)
    layout = write_tables(wb, tabs)
    lk = Lookup(look, tabs)
    write_calc(calc, lk, tabs, layout)
    write_lines_sheet(wb, lines)
    n_points = write_chart_data(wb, lines)
    add_ph_chart(calc, n_points)
    calc.sheet_view.showGridLines = False
    # 인쇄 범위를 안 잡으면 빈 칸까지 끌고 가 수십 장이 나온다.
    calc.print_area = "A1:N80"
    calc.sheet_properties.pageSetUpPr.fitToPage = True
    calc.page_setup.fitToWidth = 1
    calc.page_setup.fitToHeight = 0
    calc.page_setup.orientation = "portrait"

    # 보조 시트는 숨긴다. 화면이 깔끔해지고 실수로 고칠 일도 줄어든다.
    # (엑셀에서 시트 탭 오른쪽 클릭 > 숨기기 취소 로 다시 볼 수 있다)
    for name in (S_LOOK, S_CONF, S_SAT, S_H, S_S, S_D, S_CHART, S_LINES):
        wb[name].sheet_state = "hidden"
    wb.active = 0

    # 저장하기 전에 수식 길이를 본다. 한도를 넘긴 파일은 엑셀에서 조용히
    # 망가지므로 (리브레는 멀쩡히 돈다) 아예 내보내지 않는다.
    long_ones = check_formula_lengths(wb)
    over = [t for t in long_ones if t[2] > EXCEL_FORMULA_LIMIT]
    if over:
        lines = "\n".join(f"  {sh}!{cell}  {n}자" for sh, cell, n in over)
        raise ValueError(
            f"엑셀 수식 길이 한도({EXCEL_FORMULA_LIMIT}자)를 넘는 수식이 있다.\n"
            f"{lines}\n중간값을 옆 칸으로 빼서 수식을 짧게 나눠야 한다."
        )
    if long_ones:
        sh, cell, n = long_ones[0]
        print(f"  제일 긴 수식: {sh}!{cell} {n}자 "
              f"(한도 {EXCEL_FORMULA_LIMIT}자)")

    wb.save(path)
    return path
