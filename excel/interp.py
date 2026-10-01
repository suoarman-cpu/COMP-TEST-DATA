"""엑셀 보간 수식이 하는 계산을 파이썬으로 똑같이 흉내낸다.

엑셀에 넣기 전에 '표만으로 사이클이 맞게 풀리는지' 확인하는 용도다.
여기서 쓰는 연산은 전부 엑셀의 INDEX/MATCH + 선형보간으로 옮길 수 있는 것만 쓴다.
"""

from __future__ import annotations

from .tables import PropertyTables


def _lerp(x, x0, x1, y0, y1):
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def _bracket(values: list[float], x: float) -> tuple[int, int]:
    """x 가 끼는 구간의 앞뒤 번호. (엑셀의 MATCH 1 과 같은 일)"""
    if x <= values[0]:
        return 0, min(1, len(values) - 1)
    if x >= values[-1]:
        return len(values) - 2, len(values) - 1
    lo = 0
    for i, v in enumerate(values):
        if v <= x:
            lo = i
        else:
            break
    return lo, lo + 1


class TableProps:
    """표 + 보간으로 물성을 내주는 계산기."""

    def __init__(self, tables: PropertyTables):
        self.t = tables
        self.sat_t = [r[0] for r in tables.saturation]
        self.sat_p = [r[1] for r in tables.saturation]
        self.sat_hf = [r[2] for r in tables.saturation]
        self.sat_hg = [r[3] for r in tables.saturation]
        self.sat_sg = [r[4] for r in tables.saturation]
        self.sat_rg = [r[5] for r in tables.saturation]

    # --- 포화 물성 (1차원 보간) ---
    def _sat(self, column: list[float], t_c: float) -> float:
        i, j = _bracket(self.sat_t, t_c)
        return _lerp(t_c, self.sat_t[i], self.sat_t[j], column[i], column[j])

    def p_sat(self, t_c: float) -> float:
        return self._sat(self.sat_p, t_c)

    def hf(self, t_c: float) -> float:
        return self._sat(self.sat_hf, t_c)

    def hg(self, t_c: float) -> float:
        return self._sat(self.sat_hg, t_c)

    def t_sat(self, p_kpa: float) -> float:
        i, j = _bracket(self.sat_p, p_kpa)
        return _lerp(p_kpa, self.sat_p[i], self.sat_p[j], self.sat_t[i], self.sat_t[j])

    # --- 과열증기 (2차원 보간: 과열도 x 압력) ---
    def _grid(self, name: str) -> list[list[float]]:
        return {"h": self.t.h, "s": self.t.s, "rho": self.t.rho}[name]

    def _at(self, name: str, dt: float, p_kpa: float) -> float:
        g = self._grid(name)
        pi, pj = _bracket(self.t.pressures, p_kpa)
        di, dj = _bracket(self.t.superheats, dt)
        # 압력 두 열에서 각각 과열도 방향으로 보간한 뒤, 둘을 압력으로 보간
        a = _lerp(dt, self.t.superheats[di], self.t.superheats[dj], g[di][pi], g[dj][pi])
        b = _lerp(dt, self.t.superheats[di], self.t.superheats[dj], g[di][pj], g[dj][pj])
        return _lerp(p_kpa, self.t.pressures[pi], self.t.pressures[pj], a, b)

    def h_tp(self, t_c: float, p_kpa: float) -> float:
        return self._at("h", t_c - self.t_sat(p_kpa), p_kpa)

    def s_tp(self, t_c: float, p_kpa: float) -> float:
        return self._at("s", t_c - self.t_sat(p_kpa), p_kpa)

    def d_tp(self, t_c: float, p_kpa: float) -> float:
        return self._at("rho", t_c - self.t_sat(p_kpa), p_kpa)

    # --- 역보간 (압력 한 열 안에서 값을 찾아 과열도를 역산) ---
    def _inverse(self, name: str, value: float, p_kpa: float) -> float:
        """그 압력에서 name 물성이 value 가 되는 과열도를 찾는다."""
        g = self._grid(name)
        pi, pj = _bracket(self.t.pressures, p_kpa)
        p_lo, p_hi = self.t.pressures[pi], self.t.pressures[pj]

        def dt_in_column(col: int) -> float:
            column = [g[r][col] for r in range(len(self.t.superheats))]
            i, j = _bracket(column, value)
            return _lerp(value, column[i], column[j],
                         self.t.superheats[i], self.t.superheats[j])

        return _lerp(p_kpa, p_lo, p_hi, dt_in_column(pi), dt_in_column(pj))

    def h_sp(self, s: float, p_kpa: float) -> float:
        """등엔트로피 압축 후 엔탈피."""
        return self._at("h", self._inverse("s", s, p_kpa), p_kpa)

    def t_hp(self, h: float, p_kpa: float) -> float:
        """엔탈피와 압력에서 온도."""
        return self.t_sat(p_kpa) + self._inverse("h", h, p_kpa)
