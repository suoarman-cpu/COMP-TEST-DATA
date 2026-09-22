"""터보 냉동기 사이클 해석 / 터보 압축기 개략 설계 패키지.

사용 예::

    from turbochiller import CycleInput, two_stage, format_report

    inp = CycleInput(refrigerant="R1234ze(E)", capacity_rt=150)
    res = two_stage(inp)
    print(format_report(res))
"""

from .cycle import (
    KW_PER_RT,
    CycleInput,
    CycleResult,
    ExcelCompat,
    MaxCondition,
    StatePoint,
    StageResult,
    compress,
    single_stage,
    solve,
    two_stage,
)
from .hx import HXResult, condenser_side, evaporator_side
from .retrofit import MachineSpec, RetrofitPoint, retrofit, retrofit_one
from .standards import IPLV_CONDITIONS, IplvResult, iplv
from .report import format_hx, format_iplv, format_report, format_retrofit

__all__ = [
    "KW_PER_RT",
    "CycleInput",
    "CycleResult",
    "ExcelCompat",
    "MaxCondition",
    "StatePoint",
    "StageResult",
    "compress",
    "single_stage",
    "solve",
    "two_stage",
    "HXResult",
    "condenser_side",
    "evaporator_side",
    "IPLV_CONDITIONS",
    "IplvResult",
    "iplv",
    "format_report",
    "format_hx",
    "format_retrofit",
    "MachineSpec",
    "RetrofitPoint",
    "retrofit",
    "retrofit_one",
    "format_iplv",
]

__version__ = "0.1.0"
