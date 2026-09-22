"""명령줄 실행기.

    python -m turbochiller examples/150RT_2stage_R1234ze.yaml
    python -m turbochiller examples/150RT_2stage_R1234ze.yaml --iplv --impeller
    python -m turbochiller --refrigerant R134a --capacity 200 --stages 2
"""

from __future__ import annotations

import argparse
import sys

from .config import load_input
from .cycle import CycleInput, ExcelCompat, solve
from .hx import condenser_side, evaporator_side
from .impeller import size_impeller
from .report import format_hx, format_impeller, format_iplv, format_report
from .standards import iplv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="turbochiller",
        description="터보 냉동기 사이클 해석 / 터보 압축기 개략 설계",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("config", nargs="?", help="입력 파일 (.yaml 또는 .json)")
    p.add_argument("--stages", type=int, choices=(1, 2), help="압축 단수")
    p.add_argument("--refrigerant", help="냉매 (예: R1234ze(E), R134a, R515B)")
    p.add_argument("--capacity", type=float, help="냉동능력 [RT]")
    p.add_argument("--t-evap", type=float, help="증발온도 [°C] (직접 지정)")
    p.add_argument("--t-cond", type=float, help="응축온도 [°C] (직접 지정)")
    p.add_argument("--t-subcond", type=float, help="서브콘덴서 온도 [°C]")
    p.add_argument(
        "--auto-economizer",
        action="store_true",
        help="중간단 유량비를 에너지 밸런스로 직접 계산",
    )
    p.add_argument("--eta", type=float, help="단열효율(두 단 모두)")
    p.add_argument("--hx", action="store_true", help="열교환기 2차측 LMTD/UA 계산")
    p.add_argument("--impeller", action="store_true", help="임펠러 개략 치수 산정")
    p.add_argument("--rpm", type=float, help="임펠러 회전수 고정 [rpm]")
    p.add_argument("--psi", type=float, default=0.60, help="임펠러 압력계수 (기본 0.60)")
    p.add_argument("--iplv", action="store_true", help="IPLV(부분부하 효율) 계산")
    p.add_argument(
        "--iplv-medium", choices=("air", "water"), default="air", help="IPLV 기준"
    )
    p.add_argument(
        "--excel-compat",
        action="store_true",
        help="원본 엑셀과 똑같은 방식으로 계산 (온도 혼합 + 응축열량 1단유량)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.config:
        try:
            inp, extra = load_input(args.config)
        except (OSError, ValueError) as exc:
            print(f"입력 파일 오류: {exc}", file=sys.stderr)
            return 2
    else:
        inp, extra = CycleInput(), {}

    stages = args.stages or int(extra.get("stages", 2))

    # 명령줄 인자가 파일 값을 덮어쓴다.
    overrides: dict = {}
    if args.refrigerant:
        overrides["refrigerant"] = args.refrigerant
    if args.capacity is not None:
        overrides["capacity_rt"] = args.capacity
    if args.t_evap is not None:
        overrides["t_evap"] = args.t_evap
    if args.t_cond is not None:
        overrides["t_cond"] = args.t_cond
    if args.t_subcond is not None:
        overrides["t_subcond"] = args.t_subcond
    if args.auto_economizer:
        overrides["subcond_mass_ratio"] = None
    if args.eta is not None:
        overrides["eta_is_stage1"] = args.eta
        overrides["eta_is_stage2"] = args.eta
    if args.excel_compat:
        overrides["compat"] = ExcelCompat(
            temperature_mixing=True, condenser_duty_first_stage_flow=True
        )
    if overrides:
        inp = inp.at(**overrides)

    try:
        res = solve(inp, stages=stages)
    except (ValueError, RuntimeError) as exc:
        print(f"계산 실패: {exc}", file=sys.stderr)
        return 1

    print(format_report(res))

    if args.hx or extra.get("hx"):
        hx = [
            evaporator_side(
                res.qe, inp.te, inp.chilled_water_in, spec_volume=0.043,
                density=999.45, cp=4.19,
            ),
            condenser_side(
                res.qc, inp.tc, inp.cooling_medium_in, spec_volume=0.054,
                density=995.67, cp=4.18,
            ),
        ]
        print(format_hx(hx))

    if args.impeller or extra.get("impeller"):
        opts = extra.get("impeller") if isinstance(extra.get("impeller"), dict) else {}
        sizings = [
            size_impeller(
                st,
                inp.refrigerant,
                head_coefficient=opts.get("head_coefficient", args.psi),
                specific_speed=opts.get("specific_speed", 0.70),
                rpm=opts.get("rpm", args.rpm),
            )
            for st in res.stage_results
        ]
        print(format_impeller(sizings))

    if args.iplv or extra.get("iplv"):
        medium = args.iplv_medium
        if isinstance(extra.get("iplv"), dict):
            medium = extra["iplv"].get("medium", medium)
        print(format_iplv(iplv(inp, stages=stages, medium=medium)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
