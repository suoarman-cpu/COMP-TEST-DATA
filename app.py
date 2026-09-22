"""터보 냉동기 사이클 해석 — 웹 화면.

코드를 몰라도 왼쪽에서 값만 바꾸면 결과가 바로 나온다.

실행 방법 (터미널에서 한 줄):
    streamlit run app.py
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from turbochiller import (
    CycleInput,
    ExcelCompat,
    condenser_side,
    evaporator_side,
    iplv,
    size_impeller,
    solve,
)
from turbochiller.plot import ph_diagram

REFRIGERANTS = [
    "R1234ze(E)",
    "R134a",
    "R1234yf",
    "R513A.mix",
    "R1233zd(E)",
    "R245fa",
    "R1336mzz(Z)",
]


# ---------------------------------------------------------------------------
# 입력 (왼쪽 사이드바)
# ---------------------------------------------------------------------------

def read_inputs() -> tuple[CycleInput, int, dict]:
    sb = st.sidebar
    sb.title("입력 조건")

    sb.subheader("기본 사양")
    stages = sb.radio("압축 단수", (2, 1), format_func=lambda n: f"{n}단 압축")
    refrigerant = sb.selectbox("냉매", REFRIGERANTS)
    capacity = sb.number_input("냉동능력 [RT]", 10.0, 2000.0, 150.0, step=10.0)

    sb.subheader("증발기 (냉수)")
    cw_in = sb.number_input("냉수 입구온도 [°C]", 0.0, 30.0, 12.0, step=0.1)
    cw_out = sb.number_input("냉수 출구온도 [°C]", -5.0, 25.0, 7.0, step=0.1)
    evap_app = sb.number_input("증발기 approach [K]", 0.1, 10.0, 1.0, step=0.1)
    superheat = sb.number_input("과열도 [K]", 0.0, 15.0, 1.0, step=0.1)

    sb.subheader("응축기")
    medium_in = sb.number_input("냉각 공기/물 입구온도 [°C]", 0.0, 55.0, 35.0, step=0.5)
    cond_app = sb.number_input("응축기 approach [K]", 0.5, 25.0, 15.0, step=0.5)
    subcool = sb.number_input("과냉도 [K]", 0.0, 15.0, 3.0, step=0.1)

    sb.subheader("압축기")
    eta1 = sb.slider("1단 단열효율", 0.40, 0.95, 0.80, step=0.01)
    eta2 = sb.slider("2단 단열효율", 0.40, 0.95, 0.80, step=0.01) if stages == 2 else eta1
    eta_wts = sb.slider("wire-to-shaft 효율", 0.70, 1.00, 0.89, step=0.01)

    dp_s = sb.number_input("흡입관 압력손실 [kPa]", 0.0, 50.0, 3.0, step=0.5)
    dp_d = sb.number_input("토출관 압력손실 [kPa]", 0.0, 50.0, 5.0, step=0.5)

    t_sub = None
    x = None
    if stages == 2:
        sb.subheader("서브콘덴서 (이코노마이저)")
        auto_p = sb.checkbox(
            "중간압 자동 (√(P1·P2))", value=True,
            help="끄면 서브콘덴서 온도를 직접 지정한다",
        )
        if not auto_p:
            t_sub = sb.number_input("서브콘덴서 온도 [°C]", -10.0, 60.0, 32.0, step=0.5)
        auto_x = sb.checkbox(
            "중간단 유량비 자동 (에너지 밸런스)", value=True,
            help="끄면 유량비를 직접 지정한다 (원본 엑셀 방식)",
        )
        if not auto_x:
            x = sb.number_input("중간단 유량비 x", 0.0, 1.0, 0.20, step=0.01)

    sb.subheader("최대 운전조건")
    t_cond_max = sb.number_input("최대 응축온도 [°C]", 40.0, 100.0, 70.0, step=1.0)

    sb.subheader("추가 계산")
    opts = {
        "hx": sb.checkbox("열교환기 2차측 (LMTD / UA)", value=True),
        "impeller": sb.checkbox("임펠러 개략 치수", value=True),
        "iplv": sb.checkbox("IPLV (부분부하 효율)", value=False),
        "psi": sb.slider("임펠러 압력계수 ψ", 0.40, 0.75, 0.60, step=0.01),
        "ns": sb.slider("임펠러 비속도 Ns", 0.40, 1.00, 0.70, step=0.01),
        "medium": sb.selectbox("IPLV 기준", ("air", "water"),
                               format_func=lambda m: "공랭" if m == "air" else "수냉"),
    }

    excel_compat = sb.checkbox(
        "엑셀 호환 모드", value=False,
        help="원본 엑셀과 똑같이 계산한다 (온도 혼합 + 응축열량을 1단 유량으로)",
    )

    inp = CycleInput(
        refrigerant=refrigerant,
        capacity_rt=capacity,
        chilled_water_in=cw_in,
        chilled_water_out=cw_out,
        evap_approach=evap_app,
        superheat=superheat,
        cooling_medium_in=medium_in,
        cond_approach=cond_app,
        subcool=subcool,
        dp_suction=dp_s,
        dp_discharge=dp_d,
        eta_is_stage1=eta1,
        eta_is_stage2=eta2,
        eta_wire_to_shaft=eta_wts,
        t_subcond=t_sub,
        subcond_mass_ratio=x,
        t_cond_max=t_cond_max,
        eta_is_max=eta1,
        compat=ExcelCompat(
            temperature_mixing=excel_compat,
            condenser_duty_first_stage_flow=excel_compat,
        ),
    )
    return inp, stages, opts


# ---------------------------------------------------------------------------
# 결과 표시
# ---------------------------------------------------------------------------

def show_summary(res) -> None:
    c = st.columns(4)
    c[0].metric("COP (입력전력 기준)", f"{res.cop_input:.3f}")
    c[1].metric("소비전력", f"{res.input_power:.1f} kW")
    c[2].metric("냉동톤당 전력", f"{res.kw_per_rt:.4f} kW/RT")
    c[3].metric("총 압축비", f"{res.total_pressure_ratio:.3f}")

    c = st.columns(4)
    c[0].metric("증발온도", f"{res.inp.te:.2f} °C")
    c[1].metric("응축온도", f"{res.inp.tc:.2f} °C")
    c[2].metric("냉매 유량 (증발기)", f"{res.mass_flow_evap:.3f} kg/s")
    c[3].metric("1단 흡입 체적유량", f"{res.volume_flow_m3h:.0f} m³/h")

    err = res.energy_balance_error
    if abs(err) >= 0.5:
        st.warning(
            f"에너지 수지 오차 {err:+.2f} % — 이코노마이저 유량비를 손으로 지정했거나 "
            "배관 손실이 큰 경우다. '중간단 유량비 자동'을 켜면 수지가 맞는다."
        )


def states_table(res) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "No": s.no,
                "위치": s.name,
                "온도 [°C]": round(s.t, 2),
                "압력 [kPa]": round(s.p, 2),
                "엔탈피 [kJ/kg]": round(s.h, 2),
                "밀도 [kg/m³]": round(s.d, 2) if s.d is not None else None,
                "엔트로피 [kJ/kg·K]": round(s.s, 4) if s.s is not None else None,
            }
            for s in res.states
        ]
    )


def stages_table(res) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "단": stage.name,
                "흡입압력 [kPa]": round(stage.p_in, 2),
                "토출압력 [kPa]": round(stage.p_out, 2),
                "압축비": round(stage.pressure_ratio, 3),
                "흡입온도 [°C]": round(stage.t_in, 2),
                "토출온도 [°C]": round(stage.t_out, 2),
                "단열헤드 [kJ/kg]": round(stage.dh_isentropic, 3),
                "실제헤드 [kJ/kg]": round(stage.dh_actual, 3),
                "유량 [kg/s]": round(stage.mass_flow, 4),
                "흡입체적 [m³/h]": round(stage.volume_flow_m3h, 1),
                "축동력 [kW]": round(stage.power, 2),
            }
            for stage in res.stage_results
        ]
    )


def main() -> None:
    st.set_page_config(
        page_title="터보 냉동기 사이클 해석", page_icon="❄", layout="wide"
    )
    st.title("❄ 터보 냉동기 사이클 해석")
    st.caption(
        "원본 엑셀(150RT_Cycle_Analysis)의 계산을 그대로 옮기고, "
        "이코노마이저 에너지 밸런스와 임펠러 개략 설계를 더했다."
    )

    inp, stages, opts = read_inputs()

    try:
        res = solve(inp, stages=stages)
    except (ValueError, RuntimeError) as exc:
        st.error(f"계산할 수 없는 조건이다.\n\n{exc}")
        st.stop()

    show_summary(res)

    tabs = st.tabs(["P-h 선도", "상태점", "압축기", "열교환기", "임펠러", "IPLV"])

    with tabs[0]:
        st.pyplot(ph_diagram(res, figsize=(9, 6.5)))
        st.caption(
            "가로축 엔탈피, 세로축 압력(로그). 회색은 포화선, 주황색이 압축 구간이다."
        )

    with tabs[1]:
        st.dataframe(states_table(res), width="stretch", hide_index=True)
        buf = io.StringIO()
        states_table(res).to_csv(buf, index=False)
        st.download_button(
            "상태점 CSV 내려받기", buf.getvalue(),
            file_name="상태점.csv", mime="text/csv",
        )

    with tabs[2]:
        st.dataframe(stages_table(res), width="stretch", hide_index=True)
        mc = res.max_condition
        if mc is not None:
            st.subheader(f"최대 조건 (응축 {mc.t_cond:.0f}°C)")
            c = st.columns(4)
            c[0].metric("최대 응축압력", f"{mc.p_cond:.0f} kPa")
            c[1].metric("최대 토출온도", f"{mc.t_discharge:.1f} °C")
            c[2].metric("최대 압축비", f"{mc.pressure_ratio:.2f}")
            c[3].metric("최대 입력전력", f"{mc.input_power:.1f} kW")

    with tabs[3]:
        if not opts["hx"]:
            st.info("왼쪽에서 '열교환기 2차측'을 켜면 계산한다.")
        else:
            rows = []
            for hx in (
                evaporator_side(res.qe, inp.te, inp.chilled_water_in),
                condenser_side(res.qc, inp.tc, inp.cooling_medium_in),
            ):
                rows.append(
                    {
                        "열교환기": hx.name,
                        "열량 [kW]": round(hx.duty, 1),
                        "2차측 입구 [°C]": round(hx.t_in, 2),
                        "2차측 출구 [°C]": round(hx.t_out, 2),
                        "유량 [m³/h]": round(hx.volume_flow_m3h, 1),
                        "온도차 입구 [K]": round(hx.td_in, 2),
                        "온도차 출구 [K]": round(hx.td_out, 2),
                        "LMTD [K]": round(hx.lmtd, 3),
                        "UA [kW/K]": round(hx.ua, 2),
                    }
                )
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with tabs[4]:
        if not opts["impeller"]:
            st.info("왼쪽에서 '임펠러 개략 치수'를 켜면 계산한다.")
        else:
            st.caption(
                "무차원수로 잡은 1차 근사다. 깃 형상·확산기·CFD 로 다시 확인해야 한다."
            )
            rows = []
            warns: list[str] = []
            for stage in res.stage_results:
                sz = size_impeller(
                    stage, inp.refrigerant,
                    head_coefficient=opts["psi"], specific_speed=opts["ns"],
                )
                rows.append(
                    {
                        "단": sz.stage_name,
                        "회전수 [rpm]": round(sz.rpm),
                        "임펠러 외경 [mm]": round(sz.diameter_mm, 1),
                        "선단 주속 [m/s]": round(sz.tip_speed, 1),
                        "선단 마하수": round(sz.tip_mach, 3),
                        "흡입구 외경 [mm]": round(sz.eye_diameter_mm, 1),
                        "일계수 λ": round(sz.work_coefficient, 3),
                        "유량계수 φ": round(sz.flow_coefficient, 4),
                        "비직경 Ds": round(sz.specific_diameter, 3),
                    }
                )
                warns += [f"{sz.stage_name}: {w}" for w in sz.warnings]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            for w in warns:
                st.warning(w)

    with tabs[5]:
        if not opts["iplv"]:
            st.info("왼쪽에서 'IPLV'를 켜면 계산한다. (부하점 4개를 다시 풀어서 조금 걸린다)")
        else:
            try:
                r = iplv(inp, stages=stages, medium=opts["medium"])
            except (ValueError, RuntimeError) as exc:
                st.error(f"IPLV 계산 실패: {exc}")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "부하 [%]": round(p.load * 100),
                                "냉각 입구 [°C]": p.condition.medium_in,
                                "응축온도 [°C]": p.condition.t_cond,
                                "능력 [kW]": round(p.result.qe, 1),
                                "입력전력 [kW]": round(p.result.input_power, 2),
                                "COP": round(p.cop, 3),
                                "kW/RT": round(p.kw_per_rt, 4),
                            }
                            for p in r.points
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
                c = st.columns(2)
                c[0].metric("IPLV (COP 기준)", f"{r.iplv_cop:.3f}")
                c[1].metric("IPLV (kW/RT 기준)", f"{r.iplv_kw_per_rt:.4f}")
                st.caption(
                    "부분부하 단열효율은 가정값이다 (standards.default_part_load_efficiency). "
                    "실측 성능곡선이 있으면 그 함수를 바꿔 쓰면 된다."
                )


if __name__ == "__main__":
    main()
