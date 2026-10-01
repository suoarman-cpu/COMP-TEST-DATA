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
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
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
S_CALC, S_LOOK = "계산", "조회"
S_SAT, S_H, S_S, S_D = "물성_포화", "물성_h", "물성_s", "물성_밀도"

#: 과열표가 시작하는 행/열 (1행 = 압력 머리글, A열 = 과열도)
GRID_R0, GRID_C0 = 2, 2


def _grid_sheet(wb: Workbook, name: str, t: PropertyTables,
                values: list[list[float]], unit: str) -> None:
    """과열증기 표 한 장을 쓴다. 행 = 과열도, 열 = 압력."""
    ws = wb.create_sheet(name)
    ws["A1"] = "과열도 \\ 압력[kPa]"
    ws["A1"].font = Font(name=FONT, size=9, bold=True)
    for c, p in enumerate(t.pressures):
        cell = ws.cell(row=1, column=GRID_C0 + c, value=round(p, 4))
        cell.font = Font(name=FONT, size=9, bold=True)
        cell.number_format = "0.0"
    for r, dt in enumerate(t.superheats):
        cell = ws.cell(row=GRID_R0 + r, column=1, value=dt)
        cell.font = Font(name=FONT, size=9, bold=True)
        cell.number_format = "0.0"
        for c in range(len(t.pressures)):
            v = values[r][c]
            cc = ws.cell(row=GRID_R0 + r, column=GRID_C0 + c,
                         value=None if v != v else round(v, 6))
            cc.font = Font(name=FONT, size=9)
            cc.number_format = "0.0000"
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 11
    note = ws.cell(row=GRID_R0 + len(t.superheats) + 2, column=1,
                   value=f"{t.refrigerant} 과열증기 {unit}. "
                         "행=포화온도로부터의 과열도[K], 열=압력[kPa]. "
                         "CoolProp 으로 미리 계산한 값이다 — 고치지 말 것.")
    note.font = NOTE


def write_tables(wb: Workbook, t: PropertyTables) -> None:
    """물성표 네 장을 쓴다."""
    ws = wb.create_sheet(S_SAT)
    headers = ["온도 [°C]", "포화압력 [kPa]", "포화액 h [kJ/kg]",
               "포화증기 h [kJ/kg]", "포화액 s [kJ/kg·K]",
               "포화증기 s [kJ/kg·K]", "포화증기 밀도 [kg/m³]"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = 16
    for r, row in enumerate(t.saturation, start=2):
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=round(v, 6))
            cell.font = Font(name=FONT, size=9)
            cell.number_format = "0.0000"
    ws.freeze_panes = "A2"
    n = len(t.saturation) + 3
    ws.cell(row=n, column=1,
            value=f"{t.refrigerant} 포화 물성표. CoolProp 으로 미리 계산한 값이다 "
                  "— 고치지 말 것.").font = NOTE

    _grid_sheet(wb, S_H, t, t.h, "엔탈피 [kJ/kg]")
    _grid_sheet(wb, S_S, t, t.s, "엔트로피 [kJ/kg·K]")
    _grid_sheet(wb, S_D, t, t.rho, "밀도 [kg/m³]")


# ---------------------------------------------------------------------------
# 보간 수식 조각
# ---------------------------------------------------------------------------
# 엑셀에 없는 함수는 쓰지 않는다. INDEX / MATCH / 사칙연산만 쓴다.

def sat_range(column: int, rows: int) -> str:
    """포화표의 한 열 범위. column 은 1=온도, 2=압력, 3=hf, 4=hg, 5=sg, 6=밀도."""
    letter = get_column_letter(column)
    return f"'{S_SAT}'!${letter}$2:${letter}${rows + 1}"


def sat_lookup(key_col: int, value_col: int, key_ref: str, rows: int) -> str:
    """포화표에서 한 값으로 다른 값을 찾는다 (1차원 선형보간).

    예: 온도로 포화압력 찾기 → sat_lookup(1, 2, "C5", n)
    MATCH(...,1) 로 아래 구간을 잡고, 그 구간 안에서 비례배분한다.
    """
    keys = sat_range(key_col, rows)
    vals = sat_range(value_col, rows)
    i = f"MATCH({key_ref},{keys},1)"
    # 마지막 행을 잡으면 그 위 구간을 쓴다 (범위 밖으로 나가지 않게)
    i_safe = f"MIN({i},{rows - 1})"
    k0 = f"INDEX({keys},{i_safe})"
    k1 = f"INDEX({keys},{i_safe}+1)"
    v0 = f"INDEX({vals},{i_safe})"
    v1 = f"INDEX({vals},{i_safe}+1)"
    return f"={v0}+({key_ref}-{k0})/({k1}-{k0})*({v1}-{v0})"


def grid_block(sheet: str, n_rows: int, n_cols: int) -> str:
    """과열표의 값 부분 전체 범위."""
    c1 = get_column_letter(GRID_C0)
    c2 = get_column_letter(GRID_C0 + n_cols - 1)
    return f"'{sheet}'!${c1}${GRID_R0}:${c2}${GRID_R0 + n_rows - 1}"


def grid_pressures(n_cols: int) -> str:
    """과열표 머리글(압력) 범위. 어느 시트든 같으니 h 시트를 쓴다."""
    c1 = get_column_letter(GRID_C0)
    c2 = get_column_letter(GRID_C0 + n_cols - 1)
    return f"'{S_H}'!${c1}$1:${c2}$1"


def grid_superheats(n_rows: int) -> str:
    """과열표 첫 열(과열도) 범위."""
    return f"'{S_H}'!$A${GRID_R0}:$A${GRID_R0 + n_rows - 1}"


def bilinear(sheet: str, dt_ref: str, p_ref: str,
             ri_ref: str, ci_ref: str, n_rows: int, n_cols: int) -> str:
    """과열표에서 2방향 보간.

    ri_ref / ci_ref 는 미리 구해 둔 행·열 번호가 있는 칸이다.
    네 모서리를 꺼내 과열도 방향으로 두 번, 압력 방향으로 한 번 보간한다.
    """
    blk = grid_block(sheet, n_rows, n_cols)
    ps = grid_pressures(n_cols)
    ds = grid_superheats(n_rows)
    p0, p1 = f"INDEX({ps},{ci_ref})", f"INDEX({ps},{ci_ref}+1)"
    d0, d1 = f"INDEX({ds},{ri_ref})", f"INDEX({ds},{ri_ref}+1)"
    v00 = f"INDEX({blk},{ri_ref},{ci_ref})"
    v10 = f"INDEX({blk},{ri_ref}+1,{ci_ref})"
    v01 = f"INDEX({blk},{ri_ref},{ci_ref}+1)"
    v11 = f"INDEX({blk},{ri_ref}+1,{ci_ref}+1)"
    # 과열도 방향 보간 (압력 왼쪽 열 / 오른쪽 열)
    a = f"({v00}+({dt_ref}-{d0})/({d1}-{d0})*({v10}-{v00}))"
    b = f"({v01}+({dt_ref}-{d0})/({d1}-{d0})*({v11}-{v01}))"
    return f"={a}+({p_ref}-{p0})/({p1}-{p0})*({b}-{a})"


def inverse_dt(sheet: str, target_ref: str, p_ref: str, ci_ref: str,
               n_rows: int, n_cols: int) -> str:
    """그 압력에서 어떤 물성이 목표값이 되는 '과열도' 를 거꾸로 찾는다.

    등엔트로피 압축 후 엔탈피(s 로 찾기)와 실제 토출온도(h 로 찾기)에 쓴다.
    압력 양쪽 열에서 각각 찾아 과열도를 구한 뒤, 둘을 압력으로 보간한다.
    """
    blk = grid_block(sheet, n_rows, n_cols)
    ps = grid_pressures(n_cols)
    ds = grid_superheats(n_rows)
    p0, p1 = f"INDEX({ps},{ci_ref})", f"INDEX({ps},{ci_ref}+1)"

    def in_column(col_expr: str) -> str:
        col = f"INDEX({blk},0,{col_expr})"
        i = f"MIN(MATCH({target_ref},{col},1),{n_rows - 1})"
        v0, v1 = f"INDEX({col},{i})", f"INDEX({col},{i}+1)"
        s0, s1 = f"INDEX({ds},{i})", f"INDEX({ds},{i}+1)"
        return f"({s0}+({target_ref}-{v0})/({v1}-{v0})*({s1}-{s0}))"

    left, right = in_column(ci_ref), in_column(f"{ci_ref}+1")
    return f"={left}+({p_ref}-{p0})/({p1}-{p0})*({right}-{left})"


# ---------------------------------------------------------------------------
# 조회 시트 — 물성 조회를 한 줄씩 펼쳐 놓는다
# ---------------------------------------------------------------------------
# 한 칸에 긴 수식을 몰아넣지 않고 중간값(포화온도·과열도·행·열 번호)을
# 옆 칸에 드러낸다. 값이 이상할 때 어디서 틀어졌는지 바로 보인다.

class Lookup:
    """조회 시트를 채우면서, 각 결과가 있는 칸 주소를 돌려준다."""

    def __init__(self, ws, t: PropertyTables):
        self.ws = ws
        self.n_sat = len(t.saturation)
        self.n_row = len(t.superheats)
        self.n_col = len(t.pressures)
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
        self.ws[f"H{r}"] = sat_lookup(key_col, val_col, f"B{r}", self.n_sat)
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
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}", self.n_sat)
        w[f"E{r}"] = f"=B{r}-D{r}"
        w[f"F{r}"] = (f"=MIN(MATCH(E{r},{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{grid_pressures(self.n_col)},1),"
                      f"{self.n_col - 1})")
        w[f"H{r}"] = bilinear(S_H, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.n_col)
        w[f"I{r}"] = bilinear(S_S, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.n_col)
        w[f"J{r}"] = bilinear(S_D, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.n_col)
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
        n = self.n_sat
        w[f"B{r}"] = f"={s_ref}"
        w[f"C{r}"] = f"={p_ref}"
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}", n)          # 포화온도
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{grid_pressures(self.n_col)},1),"
                      f"{self.n_col - 1})")
        # 그 압력에서의 포화 물성 (2상인지 가르고, 2상이면 건도 계산에 쓴다)
        sf = sat_lookup(1, 5, f"D{r}", n)[1:]
        sg = sat_lookup(1, 6, f"D{r}", n)[1:]
        hf = sat_lookup(1, 3, f"D{r}", n)[1:]
        hg = sat_lookup(1, 4, f"D{r}", n)[1:]
        # 건도 = (s - sf) / (sg - sf). 조각 수식을 이어 붙이므로 괄호를 꼭 친다.
        quality = f"(B{r}-({sf}))/(({sg})-({sf}))"
        w[f"K{r}"] = (f"=IF(B{r}>={sg},\"과열\",\"습압축 (건도 \"&"
                      f"TEXT({quality},\"0.000\")&\")\")")
        w[f"K{r}"].font = NOTE
        # 과열 쪽 계산 (표 역보간)
        dt = inverse_dt(S_S, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.n_col)[1:]
        w[f"E{r}"] = f"=IF(B{r}>={sg},{dt},0)"
        w[f"F{r}"] = (f"=MIN(MATCH(MAX(E{r},0),{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        hot = bilinear(S_H, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                       self.n_row, self.n_col)[1:]
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
        w[f"D{r}"] = sat_lookup(2, 1, f"C{r}", self.n_sat)
        w[f"G{r}"] = (f"=MIN(MATCH(C{r},{grid_pressures(self.n_col)},1),"
                      f"{self.n_col - 1})")
        # 2상 영역이면 온도는 포화온도 그대로다 (과열도 0)
        hg = sat_lookup(1, 4, f"D{r}", self.n_sat)[1:]
        dt = inverse_dt(S_H, f"B{r}", f"C{r}", f"G{r}",
                        self.n_row, self.n_col)[1:]
        w[f"E{r}"] = f"=IF(B{r}>={hg},{dt},0)"
        w[f"F{r}"] = (f"=MIN(MATCH(MAX(E{r},0),{grid_superheats(self.n_row)},1),"
                      f"{self.n_row - 1})")
        w[f"H{r}"] = f"=D{r}+E{r}"
        w[f"I{r}"] = bilinear(S_S, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.n_col)
        w[f"J{r}"] = bilinear(S_D, f"E{r}", f"C{r}", f"F{r}", f"G{r}",
                              self.n_row, self.n_col)
        for col in "BCDEHIJ":
            w[f"{col}{r}"].font = BLACK
            w[f"{col}{r}"].number_format = "0.0000"
        return (f"'{S_LOOK}'!H{r}", f"'{S_LOOK}'!I{r}")


# ---------------------------------------------------------------------------
# 계산 시트
# ---------------------------------------------------------------------------

#: 입력칸 정의 — (칸, 이름, 기본값, 단위, 설명)
INPUTS = [
    ("B5",  "냉동능력",            150.0, "RT",   "정격 냉동능력"),
    ("B6",  "냉수 입구온도",        12.0, "°C",   ""),
    ("B7",  "냉수 출구온도",         7.0, "°C",   ""),
    ("B8",  "증발기 approach",      1.0, "K",    "증발온도 = 냉수출구 - 이 값"),
    ("B9",  "과열도",               1.0, "K",    ""),
    ("B10", "냉각 공기/물 입구온도", 35.0, "°C",  "공랭이면 외기온도"),
    ("B11", "응축기 approach",     15.0, "K",    "응축온도 = 냉각입구 + 이 값"),
    ("B12", "과냉도",               3.0, "K",    ""),
    ("B13", "흡입관 압력손실",       3.0, "kPa",  ""),
    ("B14", "1단 단열효율",         0.80, "-",    ""),
    ("B15", "2단 단열효율",         0.80, "-",    ""),
    ("B16", "wire-to-shaft 효율",  0.89, "-",    "모터·인버터 효율"),
]


def _put(ws, cell: str, value, font=BLACK, fmt: str | None = None):
    ws[cell] = value
    ws[cell].font = font
    if fmt:
        ws[cell].number_format = fmt


def _section(ws, row: int, title: str) -> None:
    ws[f"A{row}"] = title
    ws[f"A{row}"].font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
    ws[f"A{row}"].fill = HEAD_FILL
    for col in "BCDEF":
        ws[f"{col}{row}"].fill = HEAD_FILL


def write_calc(ws, lk: "Lookup", t: PropertyTables) -> None:
    """입력칸과 사이클 계산을 쓴다."""
    ws["A1"] = f"터보 냉동기 사이클 계산 — {t.refrigerant}"
    ws["A1"].font = Font(name=FONT, size=14, bold=True)
    ws["A2"] = "2단 압축 + 이코노마이저 사이클"
    ws["A2"].font = NOTE

    # 범례 — 어느 칸을 고쳐도 되는지 분명히 해 둔다
    _put(ws, "F4", "■ 보는 법", Font(name=FONT, size=10, bold=True))
    legend = [
        ("F5", "파란 글씨 + 노란 칸", BLUE, "여기만 고치면 된다"),
        ("F6", "검은 글씨", BLACK, "수식이다. 건드리면 결과가 틀어진다"),
        ("F7", "[조회] 시트", BLACK, "물성표를 뒤지는 곳. 손대지 말 것"),
        ("F8", "[물성_*] 시트", BLACK, "미리 계산해 둔 물성표. 손대지 말 것"),
    ]
    for cell, label, font, desc in legend:
        _put(ws, cell, label, font)
        r = int(cell[1:])
        _put(ws, f"G{r}", desc, NOTE)
    _put(ws, "F10", "맨 아래 '에너지 수지 오차' 가 0 에서 멀어지면", NOTE)
    _put(ws, "F11", "입력값이 말이 안 되는 조합이라는 뜻이다.", NOTE)
    ws.column_dimensions["A"].width = 24
    for col, w in zip("BCDEFG", (13, 7, 30, 13, 13, 13)):
        ws.column_dimensions[col].width = w

    # --- 입력 ---
    _section(ws, 4, "입력  (파란 글씨만 고칠 것)")
    for cell, name, default, unit, desc in INPUTS:
        r = int(cell[1:])
        _put(ws, f"A{r}", name)
        _put(ws, cell, default, BLUE, "0.00")
        ws[cell].fill = INPUT_FILL
        _put(ws, f"C{r}", unit, NOTE)
        if desc:
            _put(ws, f"D{r}", desc, NOTE)

    # --- 운전조건 ---
    _section(ws, 18, "운전조건  (입력에서 계산됨)")
    rows = [
        ("증발온도 Te", "=B7-B8", "°C", "냉수 출구온도 - 증발기 approach"),
        ("응축온도 Tc", "=B10+B11", "°C", "냉각 입구온도 + 응축기 approach"),
        ("냉동능력", "=B5*3.516", "kW", "1 RT = 3.516 kW"),
    ]
    for i, (name, f, unit, desc) in enumerate(rows):
        r = 19 + i
        _put(ws, f"A{r}", name)
        _put(ws, f"B{r}", f, BLACK, "0.000")
        _put(ws, f"C{r}", unit, NOTE)
        _put(ws, f"D{r}", desc, NOTE)

    te, tc = "B19", "B20"

    # 포화압력 (조회 시트에서 가져온다)
    p_evap = lk.sat("증발압력 Psat(Te)", 1, 2, f"'{S_CALC}'!{te}")
    p_cond = lk.sat("응축압력 Psat(Tc)", 1, 2, f"'{S_CALC}'!{tc}")
    _put(ws, "A22", "증발압력 Pe")
    _put(ws, "B22", f"={p_evap}", BLACK, "0.00")
    _put(ws, "C22", "kPa", NOTE)
    _put(ws, "A23", "응축압력 Pc")
    _put(ws, "B23", f"={p_cond}", BLACK, "0.00")
    _put(ws, "C23", "kPa", NOTE)

    _put(ws, "A24", "중간압 Pm")
    _put(ws, "B24", "=SQRT(B22*B23)", BLACK, "0.00")
    _put(ws, "C24", "kPa", NOTE)
    _put(ws, "D24", "흡입·토출 압력의 기하평균. 두 단의 압축비가 고르게 나뉜다.",
         NOTE)

    t_mid = lk.sat("서브콘덴서 온도 Tsat(Pm)", 2, 1, f"'{S_CALC}'!B24")
    _put(ws, "A25", "서브콘덴서 온도 Tm")
    _put(ws, "B25", f"={t_mid}", BLACK, "0.000")
    _put(ws, "C25", "°C", NOTE)

    # --- 상태점 ---
    _section(ws, 27, "상태점")
    heads = ["No", "위치", "온도 [°C]", "압력 [kPa]", "엔탈피 [kJ/kg]",
             "밀도 [kg/m³]"]
    for c, h in enumerate(heads, start=1):
        cell = ws.cell(row=28, column=c, value=h)
        cell.font = Font(name=FONT, size=10, bold=True)
        cell.border = BOX
        cell.alignment = Alignment(horizontal="center")

    names = {
        1: "1단 흡입", 2: "1단 토출", 3: "2단 흡입(혼합후)", 4: "2단 토출",
        5: "응축기 출구(과냉액)", 6: "서브콘덴서 입구", 7: "서브콘덴서 액출구",
        8: "증발기 입구(팽창후)", 9: "증발기 출구",
    }
    R = {n: 28 + n for n in names}      # 상태점 n 의 행
    for n, label in names.items():
        _put(ws, f"A{R[n]}", n)
        _put(ws, f"B{R[n]}", label)

    # 1 : 1단 흡입
    _put(ws, f"C{R[1]}", "=B19+B9", BLACK, "0.00")
    _put(ws, f"D{R[1]}", "=B22-B13", BLACK, "0.00")
    h1, s1, d1 = lk.superheated("상태1 1단 흡입",
                                f"'{S_CALC}'!C{R[1]}", f"'{S_CALC}'!D{R[1]}")
    _put(ws, f"E{R[1]}", f"={h1}", BLACK, "0.000")
    _put(ws, f"F{R[1]}", f"={d1}", BLACK, "0.00")

    # 9 : 증발기 출구
    _put(ws, f"C{R[9]}", "=B19+B9", BLACK, "0.00")
    _put(ws, f"D{R[9]}", "=B22", BLACK, "0.00")
    h9, _, _ = lk.superheated("상태9 증발기 출구",
                              f"'{S_CALC}'!C{R[9]}", f"'{S_CALC}'!D{R[9]}")
    _put(ws, f"E{R[9]}", f"={h9}", BLACK, "0.000")

    # --- 1단 압축 ---
    _section(ws, 39, "1단 압축")
    _put(ws, "A40", "흡입 엔트로피 s1")
    _put(ws, "B40", f"={s1}", BLACK, "0.0000")
    _put(ws, "C40", "kJ/kg·K", NOTE)
    h2s = lk.from_entropy("1단 등엔트로피 h2s", "'계산'!B40", f"'{S_CALC}'!B24",
                          "s1 과 중간압으로 찾은 엔탈피")
    _put(ws, "A41", "등엔트로피 엔탈피 h2s")
    _put(ws, "B41", f"={h2s}", BLACK, "0.000")
    _put(ws, "A42", "단열 헤드")
    _put(ws, "B42", f"=B41-E{R[1]}", BLACK, "0.000")
    _put(ws, "C42", "kJ/kg", NOTE)
    _put(ws, "A43", "실제 헤드")
    _put(ws, "B43", "=B42/B14", BLACK, "0.000")
    _put(ws, "C43", "kJ/kg", NOTE)
    _put(ws, "D43", "단열 헤드 ÷ 1단 단열효율", NOTE)
    _put(ws, f"E{R[2]}", f"=E{R[1]}+B43", BLACK, "0.000")
    _put(ws, f"D{R[2]}", "=B24", BLACK, "0.00")
    t2, _ = lk.temp_from_enthalpy("상태2 1단 토출온도",
                                  f"'{S_CALC}'!E{R[2]}", f"'{S_CALC}'!D{R[2]}")
    _put(ws, f"C{R[2]}", f"={t2}", BLACK, "0.00")

    # --- 응축기 출구 / 서브콘덴서 ---
    _put(ws, f"C{R[5]}", "=B20-B12", BLACK, "0.00")
    _put(ws, f"D{R[5]}", "=B23", BLACK, "0.00")
    h5 = lk.sat("상태5 과냉액 hf(T5)", 1, 3, f"'{S_CALC}'!C{R[5]}",
                "과냉액은 압력 영향이 작아 포화액 엔탈피로 본다")
    _put(ws, f"E{R[5]}", f"={h5}", BLACK, "0.000")

    _put(ws, f"C{R[6]}", "=B25", BLACK, "0.00")
    _put(ws, f"D{R[6]}", "=B24", BLACK, "0.00")
    _put(ws, f"E{R[6]}", f"=E{R[5]}", BLACK, "0.000")

    _put(ws, f"C{R[7]}", "=B25-B12", BLACK, "0.00")
    _put(ws, f"D{R[7]}", "=B24", BLACK, "0.00")
    h7 = lk.sat("상태7 서브콘덴서 액 hf(T7)", 1, 3, f"'{S_CALC}'!C{R[7]}")
    _put(ws, f"E{R[7]}", f"={h7}", BLACK, "0.000")

    _put(ws, f"C{R[8]}", "=B19", BLACK, "0.00")
    _put(ws, f"D{R[8]}", "=B22", BLACK, "0.00")
    _put(ws, f"E{R[8]}", f"=E{R[7]}", BLACK, "0.000")

    # --- 이코노마이저 유량비 ---
    _section(ws, 45, "이코노마이저")
    hg_mid = lk.sat("중간압 포화증기 hg(Tm)", 1, 4, f"'{S_CALC}'!B25")
    _put(ws, "A46", "포화증기 엔탈피 hg(Tm)")
    _put(ws, "B46", f"={hg_mid}", BLACK, "0.000")
    _put(ws, "A47", "중간단 유량비 x")
    _put(ws, "B47", f"=(E{R[5]}-E{R[7]})/(B46-E{R[5]})", BLACK, "0.0000")
    _put(ws, "D47", "에너지 수지: (1+x)·h5 = x·hg + h7", NOTE)

    # --- 2단 압축 ---
    _section(ws, 49, "2단 압축")
    _put(ws, f"D{R[3]}", "=B24", BLACK, "0.00")
    _put(ws, f"E{R[3]}", f"=(E{R[2]}+B47*B46)/(1+B47)", BLACK, "0.000")
    t3, s3 = lk.temp_from_enthalpy("상태3 2단 흡입",
                                   f"'{S_CALC}'!E{R[3]}", f"'{S_CALC}'!D{R[3]}")
    _put(ws, f"C{R[3]}", f"={t3}", BLACK, "0.00")
    _put(ws, "A50", "2단 흡입 엔트로피 s3")
    _put(ws, "B50", f"={s3}", BLACK, "0.0000")
    h4s = lk.from_entropy("2단 등엔트로피 h4s", "'계산'!B50", f"'{S_CALC}'!B23")
    _put(ws, "A51", "등엔트로피 엔탈피 h4s")
    _put(ws, "B51", f"={h4s}", BLACK, "0.000")
    _put(ws, "A52", "단열 헤드")
    _put(ws, "B52", f"=B51-E{R[3]}", BLACK, "0.000")
    _put(ws, "A53", "실제 헤드")
    _put(ws, "B53", "=B52/B15", BLACK, "0.000")
    _put(ws, f"D{R[4]}", "=B23", BLACK, "0.00")
    _put(ws, f"E{R[4]}", f"=E{R[3]}+B53", BLACK, "0.000")
    t4, _ = lk.temp_from_enthalpy("상태4 2단 토출온도",
                                  f"'{S_CALC}'!E{R[4]}", f"'{S_CALC}'!D{R[4]}")
    _put(ws, f"C{R[4]}", f"={t4}", BLACK, "0.00")

    # --- 결과 ---
    _section(ws, 55, "결과")
    out = [
        ("냉동효과", f"=E{R[9]}-E{R[8]}", "kJ/kg", "증발기에서 받는 열"),
        ("증발기 유량", "=B21/B56", "kg/s", "냉동능력 ÷ 냉동효과"),
        ("전체 유량", "=B57*(1+B47)", "kg/s", "1단 유량 × (1+x)"),
        ("흡입 체적유량", f"=B57/F{R[1]}*3600", "m³/h", "압축기 크기를 정하는 값"),
        ("체적 냉동능력", f"=F{R[1]}*B56", "kJ/m³", "흡입 1 m³ 당 냉동능력"),
        ("1단 축동력", "=B57*B43", "kW", ""),
        ("2단 축동력", "=B58*B53", "kW", ""),
        ("총 축동력", "=B61+B62", "kW", ""),
        ("총 입력전력", "=B63/B16", "kW", "축동력 ÷ wire-to-shaft 효율"),
        ("총 압축비", f"=B23/D{R[1]}", "-", ""),
        ("COP (축동력)", "=B21/B63", "-", ""),
        ("COP (입력전력)", "=B21/B64", "-", ""),
        ("냉동톤당 전력", "=B64/B5", "kW/RT", "작을수록 좋다"),
        ("응축 열량 Qc", f"=B58*(E{R[4]}-E{R[5]})", "kW", "응축기가 버리는 열"),
        ("에너지 수지 오차", "=(B69-B21-B63)/B21*100", "%",
         "Qc - Qe - W. 0 에 가까워야 정상이다"),
    ]
    for i, (name, f, unit, desc) in enumerate(out):
        r = 56 + i
        _put(ws, f"A{r}", name)
        _put(ws, f"B{r}", f, BLACK, "0.0000" if "COP" in name or "오차" in name
             else "0.000")
        _put(ws, f"C{r}", unit, NOTE)
        if desc:
            _put(ws, f"D{r}", desc, NOTE)
    ws["A56"].font = Font(name=FONT, size=10, bold=True)

    # 상태점 표 테두리
    for n in names:
        for col in "ABCDEF":
            ws[f"{col}{R[n]}"].border = BOX


def build_workbook(t: PropertyTables, path: str) -> str:
    """냉매 하나짜리 계산서를 만든다."""
    wb = Workbook()
    wb.remove(wb.active)
    calc = wb.create_sheet(S_CALC)
    look = wb.create_sheet(S_LOOK)
    write_tables(wb, t)
    lk = Lookup(look, t)
    write_calc(calc, lk, t)
    wb.save(path)
    return path
