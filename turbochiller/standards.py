"""규격 조건과 부분부하 효율(IPLV) 계산.

엑셀 '규격' 시트의 AHRI 550/590(구 ARI 550) · KS B 6275 조건표를 코드로 옮겼다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from .cycle import CycleInput, CycleResult, solve

#: AHRI 550/590 IPLV 가중치 (100 / 75 / 50 / 25 % 부하)
IPLV_WEIGHTS = (0.01, 0.42, 0.45, 0.12)


@dataclass(frozen=True)
class LoadCondition:
    """부분부하 한 점의 조건."""

    load: float              # 부하율 [0~1]
    medium_in: float         # 냉각 공기/물 입구온도 [°C]
    approach: float          # 응축기 approach [°C]

    @property
    def t_cond(self) -> float:
        """해당 부하에서의 응축온도 [°C]."""
        return self.medium_in + self.approach


#: 공랭식 (엑셀 '규격' C71:G75) — 95/80/65/55°F 를 °C 로 환산한 값
AIR_COOLED = (
    LoadCondition(1.00, 35.0, 15.0),
    LoadCondition(0.75, 27.0, 10.0),
    LoadCondition(0.50, 19.0, 7.0),
    LoadCondition(0.25, 13.0, 7.0),
)

#: 수냉식 (엑셀 '규격' C78:G82) — 85/75/65/65°F, approach 6°C 가정
WATER_COOLED = (
    LoadCondition(1.00, 30.0, 6.0),
    LoadCondition(0.75, 24.5, 6.0),
    LoadCondition(0.50, 19.0, 6.0),
    LoadCondition(0.25, 19.0, 6.0),
)

IPLV_CONDITIONS = {"air": AIR_COOLED, "water": WATER_COOLED}


def default_part_load_efficiency(load: float, rated_eta: float) -> float:
    """부하에 따른 단열효율 보정(기본 가정).

    터보 압축기는 IGV/인버터로 용량을 줄이면 효율이 떨어진다.
    실측 데이터가 있으면 이 함수 대신 직접 만든 함수를 넘겨 쓰면 된다.
    여기서는 50% 부하까지는 거의 유지되고 그 아래에서 떨어지는 형태로 잡았다.
    """
    factor = 1.0 - 0.45 * (1.0 - load) ** 2
    return max(0.25, rated_eta * factor)


@dataclass
class LoadPoint:
    """부분부하 한 점의 계산 결과."""

    load: float
    condition: LoadCondition
    result: CycleResult

    @property
    def cop(self) -> float:
        return self.result.cop_input

    @property
    def kw_per_rt(self) -> float:
        return self.result.kw_per_rt


@dataclass
class IplvResult:
    """IPLV 계산 결과."""

    points: list[LoadPoint]
    iplv_cop: float
    iplv_kw_per_rt: float
    medium: str

    def __str__(self) -> str:
        return f"IPLV (COP 기준) = {self.iplv_cop:.3f}, {self.iplv_kw_per_rt:.4f} kW/RT"


def iplv(
    inp: CycleInput,
    stages: int = 2,
    medium: Literal["air", "water"] = "air",
    conditions: Optional[tuple[LoadCondition, ...]] = None,
    eta_curve: Callable[[float, float], float] = default_part_load_efficiency,
    float_intermediate: bool = True,
) -> IplvResult:
    """AHRI 550/590 방식의 IPLV 를 계산한다.

    각 부하점마다 냉동능력과 응축온도를 바꿔 사이클을 다시 푼다.
    eta_curve(load, rated_eta) 로 부분부하 단열효율을 준다.

    float_intermediate=True 면 부분부하에서 서브콘덴서 온도를 고정하지 않고
    중간압(sqrt(P1·P2))을 따라가게 한다. 응축온도가 내려가면 정격 중간온도가
    응축온도보다 높아져 계산이 불가능해지므로 기본값을 True 로 두었다.
    """
    table = conditions if conditions is not None else IPLV_CONDITIONS[medium]
    rated_rt = inp.capacity_rt

    points: list[LoadPoint] = []
    for cond in table:
        case = inp.at(
            capacity_rt=rated_rt * cond.load,
            cooling_medium_in=cond.medium_in,
            cond_approach=cond.approach,
            t_cond=None,
            eta_is_stage1=eta_curve(cond.load, inp.eta_is_stage1),
            eta_is_stage2=eta_curve(cond.load, inp.eta_is_stage2),
            **({"t_subcond": None} if float_intermediate else {}),
        )
        points.append(LoadPoint(cond.load, cond, solve(case, stages=stages)))

    if len(points) != len(IPLV_WEIGHTS):
        raise ValueError(
            f"IPLV 는 부하점 {len(IPLV_WEIGHTS)}개가 필요하다 (입력 {len(points)}개)"
        )

    # kW/RT 기준은 가중 조화평균, COP 기준은 가중 산술평균으로 합산한다.
    kw_per_rt = sum(w * p.kw_per_rt for w, p in zip(IPLV_WEIGHTS, points))
    cop = sum(w * p.cop for w, p in zip(IPLV_WEIGHTS, points))

    return IplvResult(points=points, iplv_cop=cop, iplv_kw_per_rt=kw_per_rt, medium=medium)
