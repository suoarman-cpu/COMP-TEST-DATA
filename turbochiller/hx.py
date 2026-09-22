"""열교환기 2차측(물/공기) 계산 — 유량, LMTD, UA.

엑셀 시트의 'Condenser / Evaporator - Secondary side' 블록과 같은 계산이다.
설계 단계에서 열교환기 크기(UA)를 가늠하는 용도다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class HXResult:
    """열교환기 2차측 계산 결과."""

    name: str
    duty: float             # 교환 열량 [kW]
    t_refrigerant: float    # 냉매측 포화온도 [°C]
    t_in: float             # 2차측 입구 [°C]
    t_out: float            # 2차측 출구 [°C]
    delta_t: float          # 2차측 온도변화 [°C]
    volume_flow_m3h: float  # 2차측 체적유량 [m3/h]
    mass_flow: float        # 2차측 질량유량 [kg/s]
    td_in: float            # 입구측 온도차 [°C]
    td_out: float           # 출구측 온도차 [°C]
    lmtd: float             # 대수평균온도차 [°C]
    ua: float               # UA [kW/K]

    def __str__(self) -> str:
        return (
            f"{self.name}: Q={self.duty:.1f} kW, "
            f"{self.t_in:.2f} -> {self.t_out:.2f}°C, "
            f"{self.volume_flow_m3h:.1f} m3/h, LMTD={self.lmtd:.2f}K, "
            f"UA={self.ua:.1f} kW/K"
        )


def _lmtd(td_in: float, td_out: float) -> float:
    """대수평균온도차. 두 온도차가 같으면 그 값을 그대로 쓴다."""
    if td_in <= 0 or td_out <= 0:
        raise ValueError(
            f"온도차가 0 이하다 (입구 {td_in:.2f}K, 출구 {td_out:.2f}K). "
            "approach 나 유량 설정을 확인할 것"
        )
    if math.isclose(td_in, td_out, rel_tol=1e-9):
        return td_in
    return (td_in - td_out) / math.log(td_in / td_out)


def _side(
    name: str,
    duty: float,
    t_ref: float,
    t_in: float,
    spec_volume: float,
    density: float,
    cp: float,
    heating: bool,
) -> HXResult:
    """2차측 공통 계산.

    spec_volume : 단위 열량당 유량 [liter/s per kW] (AHRI 550/590 기준값)
    heating     : True 면 2차측이 데워진다(응축기), False 면 식는다(증발기)
    """
    volume_flow_m3h = spec_volume * duty / 1000.0 * 3600.0
    mass_flow = density * volume_flow_m3h / 3600.0
    delta_t = duty / (mass_flow * cp)

    if heating:
        t_out = t_in + delta_t
        td_in, td_out = t_ref - t_in, t_ref - t_out
    else:
        t_out = t_in - delta_t
        td_in, td_out = t_in - t_ref, t_out - t_ref

    lmtd = _lmtd(td_in, td_out)
    return HXResult(
        name=name,
        duty=duty,
        t_refrigerant=t_ref,
        t_in=t_in,
        t_out=t_out,
        delta_t=delta_t,
        volume_flow_m3h=volume_flow_m3h,
        mass_flow=mass_flow,
        td_in=td_in,
        td_out=td_out,
        lmtd=lmtd,
        ua=duty / lmtd,
    )


def condenser_side(
    duty: float,
    t_cond: float,
    t_in: float,
    spec_volume: float = 0.054,
    density: float = 995.67,
    cp: float = 4.18,
) -> HXResult:
    """응축기 2차측(냉각수). spec_volume 기본값은 AHRI 550 의 0.054 L/s·kW."""
    return _side("응축기", duty, t_cond, t_in, spec_volume, density, cp, heating=True)


def evaporator_side(
    duty: float,
    t_evap: float,
    t_in: float,
    spec_volume: float = 0.043,
    density: float = 999.45,
    cp: float = 4.19,
) -> HXResult:
    """증발기 2차측(냉수). spec_volume 기본값은 AHRI 550 의 0.043 L/s·kW."""
    return _side("증발기", duty, t_evap, t_in, spec_volume, density, cp, heating=False)
