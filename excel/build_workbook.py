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
from openpyxl.chart.marker import Marker
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .tables import PropertyTables

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
                           "과열 열수"], start=1):
        cell = conf.cell(row=3, column=c, value=h)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        conf.column_dimensions[get_column_letter(c)].width = 15
    for i, t in enumerate(tabs):
        info = layout[t.refrigerant]
        for c, v in enumerate([t.refrigerant, info["sat_start"], info["sat_end"],
                               info["col_offset"], info["n_cols"]], start=1):
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
        col = f"INDEX({blk},0,{col_expr})"
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
        for col, head in zip("ABCDEFGHIJK",
                             ["이름", "입력1", "입력2", "포화온도", "과열도",
                              "행", "열", "결과1", "결과2", "결과3", "비고"]):
            c = ws[f"{col}3"]
            c.value = head
            c.font = HEAD
            c.fill = HEAD_FILL
        ws.column_dimensions["A"].width = 26
        ws.column_dimensions["K"].width = 34
        for col in "BCDEFGHIJ":
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
        # 그 압력에서의 포화 물성 (2상인지 가르고, 2상이면 건도 계산에 쓴다)
        sf = sat_lookup(1, 5, f"D{r}")[1:]
        sg = sat_lookup(1, 6, f"D{r}")[1:]
        hf = sat_lookup(1, 3, f"D{r}")[1:]
        hg = sat_lookup(1, 4, f"D{r}")[1:]
        # 건도 = (s - sf) / (sg - sf). 조각 수식을 이어 붙이므로 괄호를 꼭 친다.
        quality = f"(B{r}-({sf}))/(({sg})-({sf}))"
        w[f"K{r}"] = (f"=IF(B{r}>={sg},\"과열\",\"습압축 (건도 \"&"
                      f"TEXT({quality},\"0.000\")&\")\")")
        w[f"K{r}"].font = NOTE
        # 과열 쪽 계산 (표 역보간)
        dt = inverse_dt(S_S, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.total_cols)[1:]
        w[f"E{r}"] = f"=IF(B{r}>={sg},{dt},0)"
        w[f"F{r}"] = (f"=MIN(MATCH(MAX(E{r},0),{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        hot = bilinear(S_H, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                       self.n_row, self.total_cols)[1:]
        wet = f"({hf})+({quality})*(({hg})-({hf}))"
        w[f"H{r}"] = f"=IF(B{r}>={sg},{hot},{wet})"
        for col in "BCDEH":
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
        hg = sat_lookup(1, 4, f"D{r}")[1:]
        dt = inverse_dt(S_H, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.total_cols)[1:]
        w[f"E{r}"] = f"=IF(B{r}>={hg},{dt},0)"
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
             ("과열 열수", 5)]):
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

def chart_points(tabs: list[PropertyTables]) -> int:
    """포화선에 쓸 점 개수.

    냉매마다 포화표 길이가 다르다(임계온도가 다르므로). 제일 짧은 것에
    맞추면 빈칸을 NA() 로 채울 일이 없어진다. 빈칸을 두면 엑셀이 오류로
    보고하고, 그 안에 진짜 오류가 섞여도 묻혀 버린다.
    """
    return min(len(t.saturation) for t in tabs)


def write_chart_data(wb: Workbook, tabs: list[PropertyTables], layout: dict):
    """고른 냉매의 포화선과 사이클 경로를 차트가 읽을 자리에 뽑아 둔다.

    차트는 범위를 고정해 두어야 하므로, 자리는 늘 같게 잡고 쓰지 않는 칸은
    NA() 로 채운다. 엑셀은 NA() 를 '점 없음' 으로 보고 건너뛴다.
    """
    ws = wb.create_sheet(S_CHART)
    ws["A1"] = "P-h 선도용 데이터"
    ws["A1"].font = TITLE
    ws["A2"] = ("계산 시트에서 고른 냉매의 포화선을 뽑아 온다 — 고치지 말 것. "
                "쓰지 않는 칸은 NA() 로 비워 둔다.")
    ws["A2"].font = NOTE
    for c, h in enumerate(["번호", "포화액 h", "압력", "포화증기 h", "압력",
                           "", "사이클 h", "사이클 압력", "상태점"], start=1):
        cell = ws.cell(row=3, column=c, value=h)
        cell.font = Font(name=FONT, size=9, bold=True)
        ws.column_dimensions[get_column_letter(c)].width = 12

    start = SAT_START
    n_points = chart_points(tabs)
    for i in range(n_points):
        r = 4 + i
        ws.cell(row=r, column=1, value=i + 1).font = Font(name=FONT, size=9)
        src_row = f"({start}+{i})"
        for col, sat_col_idx in ((2, 3), (4, 4)):       # hf, hg
            letter = get_column_letter(sat_col_idx)
            ws.cell(row=r, column=col,
                    value=f"=INDEX('{S_SAT}'!${letter}:${letter},{src_row})")
        for col in (3, 5):                               # 압력 (양쪽 같은 값)
            ws.cell(row=r, column=col,
                    value=f"=INDEX('{S_SAT}'!$B:$B,{src_row})")
        for col in (2, 3, 4, 5):
            ws.cell(row=r, column=col).font = Font(name=FONT, size=9)
            ws.cell(row=r, column=col).number_format = "0.000"

    # 사이클 경로 : 1→2→3→4→5→6→7→8→9→1
    order = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]
    for i, n in enumerate(order):
        r = 4 + i
        ws.cell(row=r, column=7, value=f"='{S_CALC}'!E{SR[n]}")
        ws.cell(row=r, column=8, value=f"='{S_CALC}'!D{SR[n]}")
        ws.cell(row=r, column=9, value=n)
        for col in (7, 8, 9):
            ws.cell(row=r, column=col).font = Font(name=FONT, size=9)
            ws.cell(row=r, column=col).number_format = "0.000"
    return len(order), n_points


def add_ph_chart(calc_ws, n_cycle: int, n_points: int) -> None:
    """계산 시트에 P-h 선도를 붙인다."""
    chart = ScatterChart()
    chart.title = "P-h 선도"
    chart.style = 2
    chart.x_axis.title = "엔탈피 h [kJ/kg]"
    chart.y_axis.title = "압력 P [kPa]"
    chart.y_axis.scaling.logBase = 10          # 압력축은 로그로 본다
    chart.height = 10
    chart.width = 15
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    # openpyxl 은 두 축 모두 'l'(왼쪽) 로 내놓는다. 가로축은 아래가 맞다.
    chart.x_axis.axPos = "b"
    # 눈금 숫자는 정수로. 안 그러면 '100.000' 처럼 길어져 비스듬히 눕는다.
    chart.x_axis.numFmt = "0"
    chart.y_axis.numFmt = "0"
    # 포화선 데이터는 숨긴 시트에 있다. 이 값이 참이면 엑셀이 숨은 칸을
    # 빼고 그려서 선이 통째로 사라진다.
    chart.visible_cells_only = False


    def line(x_col: int, y_col: int, rows: int, title: str, color: str,
             width: int, marker: bool):
        xs = Reference(calc_ws.parent[S_CHART], min_col=x_col, min_row=4,
                       max_row=3 + rows)
        ys = Reference(calc_ws.parent[S_CHART], min_col=y_col, min_row=4,
                       max_row=3 + rows)
        ser = Series(ys, xs, title=title)
        ser.graphicalProperties.line = LineProperties(solidFill=color, w=width)
        ser.marker = Marker(symbol="circle" if marker else "none", size=6)
        ser.smooth = False
        return ser

    chart.series.append(line(2, 3, n_points, "포화액선", "6F6E68", 14000, False))
    chart.series.append(line(4, 5, n_points, "포화증기선", "6F6E68", 14000, False))
    chart.series.append(line(7, 8, n_cycle, "사이클", "2A78D6", 22000, True))

    # 결과 바로 옆에 붙인다. 입력칸(B~D)을 가리지 않으면서 한 화면에 들어온다.
    calc_ws.add_chart(chart, "F6")


def build_workbook(tabs: list[PropertyTables], path: str) -> str:
    """냉매 여러 개를 담은 계산서 하나를 만든다."""
    wb = Workbook()
    wb.remove(wb.active)
    calc = wb.create_sheet(S_CALC)
    look = wb.create_sheet(S_LOOK)
    layout = write_tables(wb, tabs)
    lk = Lookup(look, tabs)
    write_calc(calc, lk, tabs, layout)
    n_cycle, n_points = write_chart_data(wb, tabs, layout)
    add_ph_chart(calc, n_cycle, n_points)
    calc.sheet_view.showGridLines = False
    # 인쇄 범위를 안 잡으면 빈 칸까지 끌고 가 수십 장이 나온다.
    calc.print_area = "A1:N80"
    calc.sheet_properties.pageSetUpPr.fitToPage = True
    calc.page_setup.fitToWidth = 1
    calc.page_setup.fitToHeight = 0
    calc.page_setup.orientation = "portrait"

    # 보조 시트는 숨긴다. 화면이 깔끔해지고 실수로 고칠 일도 줄어든다.
    # (엑셀에서 시트 탭 오른쪽 클릭 > 숨기기 취소 로 다시 볼 수 있다)
    for name in (S_LOOK, S_CONF, S_SAT, S_H, S_S, S_D, S_CHART):
        wb[name].sheet_state = "hidden"
    wb.active = 0
    wb.save(path)
    return path
