"""파이썬 내장 기능만으로 만든 웹 화면.

streamlit / pandas / pyarrow 가 필요 없다.
(pyarrow 는 32비트·ARM 윈도우용 설치 파일이 없어서 깔리지 않는 PC 가 있다)

필요한 것은 CoolProp 하나뿐이고, 나머지는 파이썬에 처음부터 들어 있다.

    python -m turbochiller.webui
"""

from __future__ import annotations

import html as html_mod
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .cycle import CycleInput, CycleResult, ExcelCompat, solve
from .hx import condenser_side, evaporator_side
from .standards import iplv
from .svg import ph_diagram_svg

#: 이미 떠 있는 프로그램을 찾을 때 뒤져볼 포트 범위
PORT_RANGE = range(8765, 8785)

#: /ping 이 돌려주는 표시. 우리 프로그램인지 확인하는 용도.
PING_TOKEN = "turbochiller-ok"

REFRIGERANTS = [
    "R1234ze(E)",
    "R134a",
    "R1234yf",
    "R513A.mix",
    "R1233zd(E)",
    "R245fa",
    "R1336mzz(Z)",
]


@dataclass
class Field:
    """입력 칸 하나의 정의."""

    key: str
    label: str
    default: Any
    kind: str = "number"          # number | select | check
    step: str = "0.1"
    choices: tuple = ()
    group: str = ""
    hint: str = ""


FIELDS: tuple[Field, ...] = (
    Field("stages", "압축 단수", 2, "select", choices=((2, "2단 압축"), (1, "1단 압축")),
          group="기본 사양"),
    Field("refrigerant", "냉매", "R1234ze(E)", "select",
          choices=tuple((r, r) for r in REFRIGERANTS), group="기본 사양"),
    Field("capacity_rt", "냉동능력 [RT]", 150.0, step="1", group="기본 사양"),

    Field("chilled_water_in", "냉수 입구온도 [°C]", 12.0, group="증발기 (냉수)"),
    Field("chilled_water_out", "냉수 출구온도 [°C]", 7.0, group="증발기 (냉수)"),
    Field("evap_approach", "증발기 approach [K]", 1.0, group="증발기 (냉수)"),
    Field("superheat", "과열도 [K]", 1.0, group="증발기 (냉수)"),

    Field("cooling_medium_in", "냉각 공기/물 입구온도 [°C]", 35.0, step="0.5",
          group="응축기"),
    Field("cond_approach", "응축기 approach [K]", 15.0, step="0.5", group="응축기"),
    Field("subcool", "과냉도 [K]", 3.0, group="응축기"),

    Field("eta_is_stage1", "1단 단열효율", 0.80, step="0.01", group="압축기"),
    Field("eta_is_stage2", "2단 단열효율", 0.80, step="0.01", group="압축기"),
    Field("eta_wire_to_shaft", "wire-to-shaft 효율", 0.89, step="0.01", group="압축기"),
    Field("dp_suction", "흡입관 압력손실 [kPa]", 3.0, step="0.5", group="압축기"),
    Field("dp_discharge", "토출관 압력손실 [kPa]", 5.0, step="0.5", group="압축기"),

    Field("t_subcond", "서브콘덴서 온도 [°C]", "", step="0.5", group="서브콘덴서",
          hint="비워두면 중간압을 √(P1·P2) 로 자동"),
    Field("subcond_mass_ratio", "중간단 유량비 x", "", step="0.01", group="서브콘덴서",
          hint="비워두면 에너지 밸런스로 계산"),

    Field("t_cond_max", "최대 응축온도 [°C]", 70.0, step="1", group="기타"),

    Field("excel_compat", "엑셀 호환 모드", False, "check", group="기타",
          hint="원본 엑셀과 똑같이 계산"),
    Field("show_iplv", "IPLV 계산 (조금 느림)", False, "check", group="기타"),
)

FIELD_BY_KEY = {f.key: f for f in FIELDS}


# ---------------------------------------------------------------------------
# 입력 해석
# ---------------------------------------------------------------------------

def parse_query(query: dict[str, list[str]]) -> dict[str, Any]:
    """주소창의 값들을 읽어 필드 값 사전으로 만든다."""
    values: dict[str, Any] = {}
    first_visit = not query

    for f in FIELDS:
        raw = query.get(f.key, [None])[0]

        if f.kind == "check":
            # 체크박스는 꺼져 있으면 아예 전송되지 않는다
            values[f.key] = f.default if first_visit else (raw is not None)
            continue

        if raw is None or raw == "":
            values[f.key] = f.default if first_visit else ("" if f.default == "" else f.default)
            if raw == "":
                values[f.key] = ""
            continue

        if f.kind == "select":
            values[f.key] = int(raw) if f.key == "stages" else raw
        else:
            try:
                values[f.key] = float(raw)
            except ValueError:
                values[f.key] = f.default
    return values


def build_input(values: dict[str, Any]) -> tuple[CycleInput, int]:
    """필드 값으로 CycleInput 을 만든다."""

    def num(key: str) -> float:
        v = values.get(key, FIELD_BY_KEY[key].default)
        return float(v) if v != "" else float(FIELD_BY_KEY[key].default)

    def opt(key: str) -> Optional[float]:
        v = values.get(key, "")
        return None if v == "" or v is None else float(v)

    compat = bool(values.get("excel_compat"))
    inp = CycleInput(
        refrigerant=str(values.get("refrigerant", "R1234ze(E)")),
        capacity_rt=num("capacity_rt"),
        chilled_water_in=num("chilled_water_in"),
        chilled_water_out=num("chilled_water_out"),
        evap_approach=num("evap_approach"),
        superheat=num("superheat"),
        cooling_medium_in=num("cooling_medium_in"),
        cond_approach=num("cond_approach"),
        subcool=num("subcool"),
        dp_suction=num("dp_suction"),
        dp_discharge=num("dp_discharge"),
        eta_is_stage1=num("eta_is_stage1"),
        eta_is_stage2=num("eta_is_stage2"),
        eta_wire_to_shaft=num("eta_wire_to_shaft"),
        t_subcond=opt("t_subcond"),
        subcond_mass_ratio=opt("subcond_mass_ratio"),
        t_cond_max=num("t_cond_max"),
        eta_is_max=num("eta_is_stage1"),
        compat=ExcelCompat(
            temperature_mixing=compat, condenser_duty_first_stage_flow=compat
        ),
    )
    return inp, int(values.get("stages", 2))


# ---------------------------------------------------------------------------
# HTML 만들기
# ---------------------------------------------------------------------------

def esc(text: Any) -> str:
    return html_mod.escape(str(text), quote=True)


STYLE = """
:root{
  color-scheme: light dark;
  --bg:#f6f6f4; --panel:#fcfcfb; --line:#e0dfd9;
  --ink:#0b0b0b; --ink2:#52514e; --ink3:#86857e;
  --accent:#2a78d6; --warn:#eb6834; --ok:#1baf7a;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#121211; --panel:#1a1a19; --line:#2f2f2c;
         --ink:#ffffff; --ink2:#c3c2b7; --ink3:#8b8a82; --accent:#3987e5; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;
     font-size:14px;line-height:1.55}
.wrap{display:flex;gap:18px;align-items:flex-start;padding:18px;max-width:1500px;margin:0 auto}
aside{flex:0 0 288px;position:sticky;top:18px}
main{flex:1;min-width:0}
h1{font-size:21px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 16px;font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
      padding:16px;margin-bottom:16px}
fieldset{border:0;padding:0;margin:0 0 14px}
legend{font-weight:700;font-size:12px;color:var(--ink2);padding:0 0 6px;
       text-transform:none;letter-spacing:.02em}
label{display:block;margin-bottom:9px}
label .t{display:block;font-size:12px;color:var(--ink2);margin-bottom:3px}
label .hint{display:block;font-size:11px;color:var(--ink3);margin-top:2px}
input[type=number],select{width:100%;padding:7px 9px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--ink);font-size:14px;
  font-family:inherit}
input[type=checkbox]{margin-right:6px;vertical-align:-1px}
button{width:100%;padding:11px;border:0;border-radius:9px;background:var(--accent);
  color:#fff;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}
button:hover{filter:brightness(1.07)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.metric .k{font-size:12px;color:var(--ink2)}
.metric .v{font-size:25px;font-weight:700;letter-spacing:-.02em}
.metric .u{font-size:14px;font-weight:600;color:var(--ink2);margin-left:3px}
h2{font-size:15px;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 9px;text-align:right;border-bottom:1px solid var(--line);
      font-variant-numeric:tabular-nums}
th{color:var(--ink2);font-weight:600;font-size:12px;white-space:nowrap}
td:nth-child(2),th:nth-child(2){text-align:left}
tbody tr:last-child td{border-bottom:0}
.msg{padding:12px 14px;border-radius:9px;margin-bottom:14px;font-size:13px}
.msg.err{background:#fdecea;color:#8a1d18;border:1px solid #f5c2bd}
.msg.warn{background:#fdf2e6;color:#7a3c12;border:1px solid #f3d3b0}
@media (prefers-color-scheme: dark){
  .msg.err{background:#3a1512;color:#ffb3ab;border-color:#5e241e}
  .msg.warn{background:#38230f;color:#ffca92;border-color:#5b3a1a}
}
.note{color:var(--ink3);font-size:12px;margin-top:8px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}
.quit{flex:0 0 auto;padding:7px 15px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:var(--ink2);text-decoration:none;font-size:13px;
  font-weight:600;white-space:nowrap}
.quit:hover{border-color:var(--warn);color:var(--warn)}
.bye{max-width:520px;margin:12vh auto;text-align:center;padding:26px;
  background:var(--panel);border:1px solid var(--line);border-radius:12px}
.bye h1{font-size:19px;margin-bottom:8px}
@media (max-width:900px){
  .wrap{flex-direction:column}
  aside{position:static;flex:1 1 auto;width:100%}
}
"""


def render_form(values: dict[str, Any]) -> str:
    out = ['<form method="get" action="/">']
    groups: list[str] = []
    for f in FIELDS:
        if f.group not in groups:
            groups.append(f.group)

    for group in groups:
        out.append(f"<fieldset><legend>{esc(group)}</legend>")
        for f in (x for x in FIELDS if x.group == group):
            v = values.get(f.key, f.default)
            hint = f'<span class="hint">{esc(f.hint)}</span>' if f.hint else ""
            if f.kind == "check":
                checked = " checked" if v else ""
                out.append(
                    f'<label><input type="checkbox" name="{f.key}" value="1"{checked}>'
                    f'{esc(f.label)}{hint}</label>'
                )
            elif f.kind == "select":
                opts = "".join(
                    f'<option value="{esc(cv)}"'
                    f'{" selected" if str(cv) == str(v) else ""}>{esc(cl)}</option>'
                    for cv, cl in f.choices
                )
                out.append(
                    f'<label><span class="t">{esc(f.label)}</span>'
                    f'<select name="{f.key}">{opts}</select>{hint}</label>'
                )
            else:
                out.append(
                    f'<label><span class="t">{esc(f.label)}</span>'
                    f'<input type="number" step="{f.step}" name="{f.key}" '
                    f'value="{esc(v)}">{hint}</label>'
                )
        out.append("</fieldset>")

    out.append("<button type=\"submit\">다시 계산</button></form>")
    return "".join(out)


def _metric(key: str, value: str, unit: str = "") -> str:
    u = f'<span class="u">{esc(unit)}</span>' if unit else ""
    return (
        f'<div class="metric"><div class="k">{esc(key)}</div>'
        f'<div class="v">{esc(value)}{u}</div></div>'
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_results(res: CycleResult, values: dict[str, Any]) -> str:
    inp = res.inp
    out: list[str] = []

    out.append('<div class="card"><div class="metrics">')
    out.append(_metric("COP (입력전력 기준)", f"{res.cop_input:.3f}"))
    out.append(_metric("소비전력", f"{res.input_power:.1f}", " kW"))
    out.append(_metric("냉동톤당 전력", f"{res.kw_per_rt:.4f}", " kW/RT"))
    out.append(_metric("총 압축비", f"{res.total_pressure_ratio:.3f}"))
    out.append(_metric("증발온도", f"{inp.te:.2f}", " °C"))
    out.append(_metric("응축온도", f"{inp.tc:.2f}", " °C"))
    out.append(_metric("냉매 유량", f"{res.mass_flow_evap:.3f}", " kg/s"))
    out.append(_metric("1단 흡입 체적유량", f"{res.volume_flow_m3h:.0f}", " m³/h"))
    out.append("</div>")

    err = res.energy_balance_error
    if abs(err) >= 0.5:
        out.append(
            f'<div class="msg warn" style="margin-top:14px">'
            f"에너지 수지 오차 {err:+.2f} % — 이코노마이저 유량비를 직접 넣었거나 "
            f"배관 손실이 큽니다. '중간단 유량비 x' 를 비워두면 수지가 맞습니다.</div>"
        )
    out.append("</div>")

    # P-h 선도
    out.append('<div class="card"><h2>P-h 선도</h2>')
    out.append(ph_diagram_svg(res, width=760, height=520))
    out.append(
        '<p class="note">점 위에 마우스를 올리면 상태점 값이 보입니다. '
        "주황색이 압축 구간입니다.</p></div>"
    )

    # 상태점
    out.append('<div class="card"><h2>상태점</h2>')
    out.append(_table(
        ["No", "위치", "온도 [°C]", "압력 [kPa]", "엔탈피 [kJ/kg]", "밀도 [kg/m³]"],
        [
            [
                s.no, s.name, f"{s.t:.2f}", f"{s.p:.2f}", f"{s.h:.2f}",
                f"{s.d:.2f}" if s.d is not None else "-",
            ]
            for s in res.states
        ],
    ))
    out.append("</div>")

    # 압축기
    out.append('<div class="card"><h2>압축기</h2>')
    out.append(_table(
        ["단", "압축비", "흡입 [°C]", "토출 [°C]", "단열헤드 [kJ/kg]",
         "유량 [kg/s]", "흡입체적 [m³/h]", "축동력 [kW]"],
        [
            [
                st.name, f"{st.pressure_ratio:.3f}", f"{st.t_in:.2f}",
                f"{st.t_out:.2f}", f"{st.dh_isentropic:.3f}",
                f"{st.mass_flow:.4f}", f"{st.volume_flow_m3h:.1f}",
                f"{st.power:.2f}",
            ]
            for st in res.stage_results
        ],
    ))
    mc = res.max_condition
    if mc is not None:
        out.append(
            f'<p class="note">최대 조건 (응축 {mc.t_cond:.0f}°C): '
            f"토출온도 {mc.t_discharge:.1f}°C, 압축비 {mc.pressure_ratio:.2f}, "
            f"입력전력 {mc.input_power:.1f} kW</p>"
        )
    out.append("</div>")

    # 열교환기
    hx = [
        evaporator_side(res.qe, inp.te, inp.chilled_water_in),
        condenser_side(res.qc, inp.tc, inp.cooling_medium_in),
    ]
    out.append('<div class="card"><h2>열교환기 2차측</h2>')
    out.append(_table(
        ["열교환기", "열량 [kW]", "입구 [°C]", "출구 [°C]", "유량 [m³/h]",
         "LMTD [K]", "UA [kW/K]"],
        [
            [
                x.name, f"{x.duty:.1f}", f"{x.t_in:.2f}", f"{x.t_out:.2f}",
                f"{x.volume_flow_m3h:.1f}", f"{x.lmtd:.3f}", f"{x.ua:.2f}",
            ]
            for x in hx
        ],
    ))
    out.append("</div>")

    # IPLV
    if values.get("show_iplv"):
        out.append('<div class="card"><h2>IPLV (부분부하 효율)</h2>')
        try:
            r = iplv(inp, stages=res.stages, medium="air")
        except (ValueError, RuntimeError) as exc:
            out.append(f'<div class="msg err">IPLV 계산 실패: {esc(exc)}</div>')
        else:
            out.append(_table(
                ["부하 [%]", "냉각 입구 [°C]", "응축온도 [°C]", "능력 [kW]",
                 "입력전력 [kW]", "COP", "kW/RT"],
                [
                    [
                        f"{p.load * 100:.0f}", f"{p.condition.medium_in:.1f}",
                        f"{p.condition.t_cond:.1f}", f"{p.result.qe:.1f}",
                        f"{p.result.input_power:.2f}", f"{p.cop:.3f}",
                        f"{p.kw_per_rt:.4f}",
                    ]
                    for p in r.points
                ],
            ))
            out.append(
                f'<p class="note">IPLV: COP {r.iplv_cop:.3f} / '
                f"{r.iplv_kw_per_rt:.4f} kW/RT — 부분부하 단열효율은 가정값입니다.</p>"
            )
        out.append("</div>")

    return "".join(out)


def render_page(query: dict[str, list[str]]) -> str:
    values = parse_query(query)
    try:
        inp, stages = build_input(values)
        res = solve(inp, stages=stages)
        body = render_results(res, values)
    except (ValueError, RuntimeError) as exc:
        body = (
            f'<div class="msg err"><b>계산할 수 없는 조건입니다.</b><br>{esc(exc)}</div>'
        )

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>터보 냉동기 사이클 해석</title>
<style>{STYLE}</style>
</head><body>
<div class="wrap">
  <aside><div class="card">{render_form(values)}</div></aside>
  <main>
    <div class="head">
      <div>
        <h1>터보 냉동기 사이클 해석</h1>
        <p class="sub">왼쪽 값을 고치고 '다시 계산'을 누르세요.</p>
      </div>
      <a class="quit" href="/quit" title="프로그램을 완전히 끝냅니다">종료</a>
    </div>
    {body}
  </main>
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# 서버
# ---------------------------------------------------------------------------

BYE_PAGE = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>종료했습니다</title><style>{STYLE}</style></head>
<body><div class="bye">
  <h1>프로그램을 종료했습니다</h1>
  <p class="sub">이 탭은 닫으셔도 됩니다.<br>
     다시 쓰시려면 실행 파일을 두 번 누르세요.</p>
</div></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "turbochiller"

    def do_GET(self) -> None:  # noqa: N802  (내장 클래스가 정한 이름)
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # 이미 떠 있는 우리 프로그램인지 확인하는 용도
        if parsed.path == "/ping":
            self._send(PING_TOKEN.encode(), "text/plain; charset=utf-8")
            return

        if parsed.path == "/quit":
            self._send(BYE_PAGE.encode("utf-8"))
            # 응답을 보낸 뒤에 서버를 내린다
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        try:
            page = render_page(query)
        except Exception as exc:  # 어떤 오류든 화면에 보여준다
            page = (
                "<!doctype html><meta charset='utf-8'>"
                "<body style='font-family:sans-serif;padding:24px'>"
                f"<h2>오류가 났습니다</h2><pre>{html_mod.escape(repr(exc))}</pre>"
                "</body>"
            )
        self._send(page.encode("utf-8"))

    def _send(self, data: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass   # 브라우저가 먼저 닫은 경우

    def log_message(self, *args) -> None:
        """요청 로그는 찍지 않는다 (창을 깨끗하게)."""


# ---------------------------------------------------------------------------
# 포트 찾기 / 이미 떠 있는지 확인
# ---------------------------------------------------------------------------

def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port(preferred: int = 8765) -> int:
    """쓸 수 있는 포트를 고른다."""
    for port in range(preferred, preferred + 20):
        if _port_free(port):
            return port
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_running(timeout: float = 0.3) -> Optional[int]:
    """이미 떠 있는 이 프로그램을 찾는다. 있으면 그 포트를 돌려준다.

    실행 파일을 여러 번 눌러도 프로그램이 쌓이지 않게 하려는 것이다.
    """
    for port in PORT_RANGE:
        if _port_free(port):
            continue          # 아무도 안 쓰는 포트
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=timeout
            ) as resp:
                if resp.read().decode().strip() == PING_TOKEN:
                    return port
        except (urllib.error.URLError, OSError, ValueError):
            continue          # 다른 프로그램이 쓰는 포트
    return None


def _wait_until_up(port: int, timeout: float = 25.0) -> bool:
    """서버가 응답할 때까지 기다린다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=0.5
            ) as resp:
                if resp.read().decode().strip() == PING_TOKEN:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    return False


# ---------------------------------------------------------------------------
# 서버 실행
# ---------------------------------------------------------------------------

def serve(
    port: Optional[int] = None,
    open_browser: bool = True,
    host: str = "127.0.0.1",
    quiet: bool = False,
) -> None:
    """이 프로세스에서 웹 화면을 돌린다. Ctrl+C 로 끝낸다."""
    port = port or free_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer((host, port), _Handler)

    if not quiet:
        print("=" * 46)
        print("  터보 냉동기 사이클 해석")
        print("=" * 46)
        print()
        print(f"  브라우저에서 열렸습니다: {url}")
        print()
        print("  끝내려면 이 창에서 Ctrl+C 를 누르거나,")
        print("  브라우저 오른쪽 위의 '종료' 를 누르세요.")
        print()

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n종료합니다.")
    finally:
        server.server_close()


def _spawn_detached(port: int) -> bool:
    """창 없이 백그라운드로 서버를 띄운다. 성공하면 True.

    윈도우에서는 pythonw.exe 를 써서 검은 창이 아예 뜨지 않게 한다.
    """
    base = _relaunch_command()
    if base is None:
        return False
    args = base + ["--serve", "--port", str(port), "--no-browser"]
    log_path = os.path.join(_app_dir(), "실행오류.log")

    kwargs: dict = {}
    if os.name == "nt":
        # CREATE_NO_WINDOW(0x08000000) + DETACHED_PROCESS(0x00000008)
        kwargs["creationflags"] = 0x08000000 | 0x00000008
    else:
        kwargs["start_new_session"] = True

    try:
        log = open(log_path, "w", encoding="utf-8")
        subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         **kwargs)
    except Exception:
        return False
    return _wait_until_up(port)


def _app_dir() -> str:
    """오류 기록을 남길 폴더."""
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script and os.path.isfile(script):
        return os.path.dirname(script) or "."
    return os.getcwd()


def _relaunch_command() -> Optional[list[str]]:
    """자기 자신을 다시 띄우는 명령을 만든다.

    한 파일로 합친 배포판이면 그 파일을 직접 실행하고,
    패키지로 설치돼 있으면 `-m turbochiller.webui` 로 실행한다.
    """
    python = _background_python()
    package = globals().get("__package__") or ""
    if package:
        return [python, "-m", "turbochiller.webui"]

    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script and os.path.isfile(script):
        return [python, script]
    return None


def _background_python() -> str:
    """창 없이 돌릴 파이썬 실행 파일 경로."""
    exe = sys.executable
    if os.name == "nt":
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return exe


def run(port: Optional[int] = None, background: bool = True) -> None:
    """실행 파일에서 부르는 진입점.

    background=True 면 창을 남기지 않고 백그라운드로 띄운 뒤 바로 빠져나온다.
    (검은 창을 계속 켜두지 않아도 되게 하려는 것이다)
    """
    existing = find_running()
    if existing is not None:
        url = f"http://127.0.0.1:{existing}/"
        print(f"이미 실행 중입니다. 브라우저를 엽니다: {url}")
        webbrowser.open(url)
        return

    port = port or free_port()

    if background and _spawn_detached(port):
        url = f"http://127.0.0.1:{port}/"
        webbrowser.open(url)
        print("=" * 52)
        print("  터보 냉동기 사이클 해석 — 실행했습니다")
        print("=" * 52)
        print()
        print(f"  주소 : {url}")
        print()
        print("  이 창은 닫으셔도 됩니다. 프로그램은 계속 돌아갑니다.")
        print("  끝내실 때는 브라우저 오른쪽 위의 '종료' 를 누르세요.")
        print()
        return

    # 백그라운드 실행이 안 되면 이 창에서 그대로 돌린다
    if background:
        print("(백그라운드 실행에 실패해 이 창에서 직접 실행합니다)")
        print()
    serve(port=port, open_browser=True)


def _cli(argv: Optional[list[str]] = None) -> None:
    """명령줄에서 부를 때."""
    import argparse as _argparse

    parser = _argparse.ArgumentParser(description="터보 냉동기 사이클 해석 — 웹 화면")
    parser.add_argument(
        "--serve", action="store_true",
        help="이 창에서 서버를 직접 돌린다 (백그라운드로 띄운 쪽이 쓰는 옵션)",
    )
    parser.add_argument("--port", type=int, help="포트 (기본: 8765부터 빈 곳)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument(
        "--console", action="store_true",
        help="백그라운드로 보내지 않고 이 창에서 실행한다",
    )
    args = parser.parse_args(argv)

    if args.serve:
        serve(port=args.port, open_browser=not args.no_browser, quiet=True)
    else:
        run(port=args.port, background=not args.console)


if __name__ == "__main__":
    _cli()
