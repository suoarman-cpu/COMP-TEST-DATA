"""계산 결과를 사람이 읽는 표로 찍어준다."""

from __future__ import annotations

from .cycle import CycleResult
from .hx import HXResult
from .impeller import ImpellerSizing
from .standards import IplvResult

LINE = "=" * 78
THIN = "-" * 78


def format_report(res: CycleResult) -> str:
    """사이클 결과 전체를 문자열로 만든다."""
    inp = res.inp
    out: list[str] = []
    add = out.append

    add(LINE)
    add(f" 터보 냉동기 사이클 해석 — {res.refrigerant} / {res.stages}단 압축")
    add(LINE)

    add("")
    add("[ 운전 조건 ]")
    add(f"  냉동능력        : {inp.capacity_rt:8.1f} RT   ({res.qe:.1f} kW)")
    add(f"  증발온도 Te     : {inp.te:8.2f} °C   (냉수 {inp.chilled_water_in:.1f} -> "
        f"{inp.chilled_water_out:.1f}°C, approach {inp.evap_approach:.1f}K)")
    add(f"  응축온도 Tc     : {inp.tc:8.2f} °C   (냉각 입구 {inp.cooling_medium_in:.1f}°C, "
        f"approach {inp.cond_approach:.1f}K)")
    add(f"  과열도 / 과냉도 : {inp.superheat:8.2f} / {inp.subcool:.2f} K")
    if res.stages == 2:
        tm = res.state(6).t
        auto = " (중간압 자동)" if inp.t_subcond is None else ""
        add(f"  서브콘덴서 온도 : {tm:8.2f} °C{auto}   "
            f"(중간단 유량비 x = {res.subcond_mass_ratio:.4f})")

    add("")
    add("[ 상태점 ]")
    add(f"  {'No':>2}  {'위치':<20} {'T[°C]':>9} {'P[kPa]':>10} "
        f"{'h[kJ/kg]':>10} {'d[kg/m3]':>10}")
    add(f"  {THIN[:72]}")
    for s in res.states:
        d = f"{s.d:10.2f}" if s.d is not None else " " * 10
        add(f"  {s.no:>2}  {s.name:<20} {s.t:9.2f} {s.p:10.2f} {s.h:10.2f} {d}")

    add("")
    add("[ 압축기 ]")
    for stage in res.stage_results:
        add(f"  - {stage.name}")
        add(f"      흡입/토출 압력   : {stage.p_in:9.2f} -> {stage.p_out:.2f} kPa "
            f"(압축비 {stage.pressure_ratio:.3f})")
        add(f"      흡입/토출 온도   : {stage.t_in:9.2f} -> {stage.t_out:.2f} °C "
            f"(등엔트로피 {stage.t_out_isentropic:.2f}°C)")
        add(f"      단열 헤드        : {stage.dh_isentropic:9.3f} kJ/kg "
            f"(실제 {stage.dh_actual:.3f}, η_is {stage.eta_isentropic:.3f})")
        add(f"      질량/체적 유량   : {stage.mass_flow:9.4f} kg/s, "
            f"{stage.volume_flow_m3h:.1f} m3/h")
        add(f"      축동력           : {stage.power:9.2f} kW")

    add("")
    add("[ 종합 성능 ]")
    add(f"  총 압축비       : {res.total_pressure_ratio:8.3f}")
    add(f"  냉매 유량       : 증발기 {res.mass_flow_evap:.4f} kg/s, "
        f"응축기 {res.mass_flow_total:.4f} kg/s")
    add(f"  1단 흡입 체적유량: {res.volume_flow_m3h:7.1f} m3/h")
    add(f"  응축 열량 Qc    : {res.qc:8.2f} kW")
    add(f"  총 축동력       : {res.shaft_power:8.2f} kW")
    add(f"  총 입력전력     : {res.input_power:8.2f} kW "
        f"(wire-to-shaft {inp.eta_wire_to_shaft:.3f})")
    add(f"  COP (축동력)    : {res.cop:8.3f}")
    add(f"  COP (입력전력)  : {res.cop_input:8.3f}   ({res.kw_per_rt:.4f} kW/RT)")
    err = res.energy_balance_error
    mark = "" if abs(err) < 0.5 else "   <- 확인 필요"
    add(f"  에너지 수지 오차: {err:8.3f} %   (Qc - Qe - W){mark}")

    if res.max_condition is not None:
        mc = res.max_condition
        add("")
        add(f"[ 최대 조건 (응축 {mc.t_cond:.1f}°C) ]")
        add(f"  최대 응축압력   : {mc.p_cond:8.2f} kPa (압축비 {mc.pressure_ratio:.3f})")
        add(f"  최대 토출온도   : {mc.t_discharge:8.2f} °C")
        add(f"  최대 축동력     : {mc.shaft_power:8.2f} kW")
        add(f"  최대 입력전력   : {mc.input_power:8.2f} kW")

    add(LINE)
    return "\n".join(out)


def format_hx(results: list[HXResult]) -> str:
    """열교환기 2차측 결과."""
    out = ["", "[ 열교환기 2차측 ]"]
    for r in results:
        out.append(f"  - {r.name}")
        out.append(f"      열량             : {r.duty:9.2f} kW")
        out.append(f"      2차측 온도       : {r.t_in:9.2f} -> {r.t_out:.2f} °C "
                   f"(Δ{r.delta_t:.2f}K)")
        out.append(f"      유량             : {r.volume_flow_m3h:9.2f} m3/h "
                   f"({r.mass_flow:.2f} kg/s)")
        out.append(f"      온도차 입구/출구 : {r.td_in:9.2f} / {r.td_out:.2f} K")
        out.append(f"      LMTD / UA        : {r.lmtd:9.3f} K / {r.ua:.2f} kW/K")
    return "\n".join(out)


def format_impeller(sizings: list[ImpellerSizing]) -> str:
    """임펠러 개략 설계 결과."""
    out = ["", "[ 임펠러 개략 설계 (1차 근사) ]"]
    for s in sizings:
        out.append(f"  - {s.stage_name}")
        out.append(f"      회전수 N         : {s.rpm:10.0f} rpm")
        out.append(f"      임펠러 외경 D2   : {s.diameter_mm:10.1f} mm")
        out.append(f"      선단 주속 u2     : {s.tip_speed:10.1f} m/s "
                   f"(마하수 {s.tip_mach:.3f})")
        out.append(f"      흡입구 외경 D_eye: {s.eye_diameter_mm:10.1f} mm")
        out.append(f"      헤드/일 계수     : psi {s.head_coefficient:.3f} / "
                   f"lambda {s.work_coefficient:.3f}")
        out.append(f"      비속도 / 비직경  : Ns {s.specific_speed:.3f} / "
                   f"Ds {s.specific_diameter:.3f}")
        out.append(f"      유량계수 phi     : {s.flow_coefficient:10.4f}")
        for w in s.warnings:
            out.append(f"      ! {w}")
    return "\n".join(out)


def format_iplv(res: IplvResult) -> str:
    """IPLV 결과 표."""
    out = ["", f"[ IPLV — {'공랭' if res.medium == 'air' else '수냉'} 기준 ]"]
    out.append(f"  {'부하':>6} {'냉각입구':>9} {'응축온도':>9} {'능력[kW]':>10} "
               f"{'입력[kW]':>10} {'COP':>7} {'kW/RT':>8}")
    out.append("  " + THIN[:64])
    for p in res.points:
        out.append(
            f"  {p.load * 100:5.0f}% {p.condition.medium_in:9.1f} "
            f"{p.condition.t_cond:9.1f} {p.result.qe:10.1f} "
            f"{p.result.input_power:10.2f} {p.cop:7.3f} {p.kw_per_rt:8.4f}"
        )
    out.append("  " + THIN[:64])
    out.append(f"  IPLV : COP {res.iplv_cop:.3f} / {res.iplv_kw_per_rt:.4f} kW/RT")
    return "\n".join(out)
