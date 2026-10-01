"""엑셀에 심을 냉매 물성표를 만든다.

표 구조를 이렇게 잡은 이유
  과열증기 영역은 압력마다 포화온도가 달라서, 온도를 그대로 행으로 쓰면
  표가 들쭉날쭉해진다. 그래서 행을 '과열도(포화온도로부터 몇 도 위인가)'
  로 잡았다. 그러면 모든 압력에서 행이 가지런해져 엑셀 보간 수식이
  단순해진다.

      행 : 과열도 dT = 0, 5, 10, ... K
      열 : 압력 P
      칸 : 그 자리에서의 엔탈피 h / 엔트로피 s / 밀도 rho
"""

from __future__ import annotations

from dataclasses import dataclass

import CoolProp
from CoolProp import AbstractState

T0 = 273.15


@dataclass
class PropertyTables:
    """한 냉매의 물성표 묶음."""

    refrigerant: str
    # 포화표 : 각 행이
    #   (온도, 포화압력, 포화액 h, 포화증기 h, 포화액 s, 포화증기 s, 포화증기 rho)
    saturation: list[tuple[float, float, float, float, float, float, float]]
    # 과열표
    superheats: list[float]          # 행 (과열도 [K])
    pressures: list[float]           # 열 (압력 [kPa])
    h: list[list[float]]             # [행][열]
    s: list[list[float]]
    rho: list[list[float]]

    @property
    def t_min(self) -> float:
        return self.saturation[0][0]

    @property
    def t_max(self) -> float:
        return self.saturation[-1][0]


def build(
    refrigerant: str,
    t_min: float = -30.0,
    t_max: float | None = None,
    t_step: float = 1.0,
    p_count: int = 40,
    superheat_max: float = 100.0,
    superheat_step: float = 2.5,
) -> PropertyTables:
    """한 냉매의 표를 만든다."""
    state = AbstractState("HEOS", refrigerant)
    # 혼합냉매는 CoolProp 이 임계점을 내주지 못한다.
    # 프로젝트에 이미 대체 경로를 둔 함수를 쓴다.
    from turbochiller.props import t_crit as _t_crit

    t_crit = _t_crit(refrigerant)
    if t_max is None:
        t_max = t_crit - 2.0

    # --- 포화표 ---
    saturation: list[tuple[float, float, float, float, float, float, float]] = []
    t = t_min
    while t <= t_max + 1e-9:
        try:
            state.update(CoolProp.QT_INPUTS, 0.0, t + T0)
            p = state.p() / 1000.0
            hf = state.hmass() / 1000.0
            sf = state.smass() / 1000.0
            state.update(CoolProp.QT_INPUTS, 1.0, t + T0)
            hg = state.hmass() / 1000.0
            sg = state.smass() / 1000.0
            rg = state.rhomass()
            saturation.append((t, p, hf, hg, sf, sg, rg))
        except Exception:
            pass
        t += t_step

    # --- 과열표 ---
    p_lo = saturation[0][1]
    p_hi = saturation[-1][1]
    pressures = [p_lo * (p_hi / p_lo) ** (i / (p_count - 1)) for i in range(p_count)]
    superheats = [
        i * superheat_step
        for i in range(int(superheat_max / superheat_step) + 1)
    ]

    h_grid: list[list[float]] = []
    s_grid: list[list[float]] = []
    r_grid: list[list[float]] = []
    for dt in superheats:
        h_row, s_row, r_row = [], [], []
        for p in pressures:
            try:
                state.update(CoolProp.PQ_INPUTS, p * 1000.0, 1.0)
                if dt > 0:
                    # 과열도가 0 이면 포화선 바로 위라, (압력,온도) 로 물으면
                    # 액인지 증기인지 모호해서 계산이 실패한다.
                    # 그 행만은 포화증기 상태를 그대로 쓴다.
                    t_sat = state.T()
                    state.update(CoolProp.PT_INPUTS, p * 1000.0, t_sat + dt)
                h_row.append(state.hmass() / 1000.0)
                s_row.append(state.smass() / 1000.0)
                r_row.append(state.rhomass())
            except Exception:
                h_row.append(float("nan"))
                s_row.append(float("nan"))
                r_row.append(float("nan"))
        h_grid.append(h_row)
        s_grid.append(s_row)
        r_grid.append(r_row)

    return PropertyTables(
        refrigerant=refrigerant,
        saturation=saturation,
        superheats=superheats,
        pressures=pressures,
        h=h_grid,
        s=s_grid,
        rho=r_grid,
    )
