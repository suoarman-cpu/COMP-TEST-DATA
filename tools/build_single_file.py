"""여러 모듈로 나뉜 프로그램을 '파일 하나'로 합친다.

폴더 구조 없이 파일 하나만 받아서 쓰고 싶을 때를 위한 배포용 빌드다.
turbochiller 패키지의 모듈들을 의존 순서대로 이어 붙이고,
패키지 내부의 상대 import (`from . import props`) 만 걷어낸다.

    python tools/build_single_file.py

결과: dist/터보냉동기_사이클해석.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "turbochiller"
OUT = ROOT / "dist" / "터보냉동기_사이클해석.py"

#: 의존 순서대로. 앞에 있는 모듈이 뒤 모듈에서 쓰인다.
#:
#: plot.py(matplotlib)와 app.py(streamlit)는 일부러 뺐다.
#: streamlit 은 pyarrow 를 끌고 오는데, pyarrow 는 32비트·ARM 윈도우용
#: 설치 파일이 없어서 그런 PC 에서는 설치가 아예 안 된다.
#: 대신 파이썬 내장 기능만 쓰는 webui.py 를 넣어서, CoolProp 하나만 있으면 돌게 했다.
MODULES = [
    "props",
    "cycle",
    "hx",
    "impeller",
    "standards",
    "report",
    "svg",
    "webui",
]

#: 패키지 내부를 가리키는 import 만 지운다 (외부 라이브러리 import 는 남긴다)
RELATIVE_IMPORT = re.compile(r"^\s*from \.[\w.]* import .*$|^\s*from \. import .*$")

#: `props.h_tp(...)` 처럼 모듈 이름으로 부르던 것을 그대로 쓰게 별칭을 준다
MODULE_ALIASES = """
# --- 모듈 별칭 -------------------------------------------------------------
# 원래는 turbochiller.props 처럼 모듈로 나뉘어 있었다.
# 한 파일로 합치면서, 코드 안의 `props.xxx` 호출이 그대로 동작하도록
# 이 파일 자신을 props 라는 이름으로도 가리키게 해 둔다.


class _SelfModule:
    \"\"\"`props.h_tp(...)` 같은 호출을 이 파일 안의 같은 이름 함수로 연결한다.\"\"\"

    def __getattr__(self, name: str):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(f"{name} 을(를) 찾을 수 없다") from None


props = _SelfModule()
"""

HEADER = '''"""터보 냉동기 사이클 해석 — 파일 하나로 합친 배포판.

이 파일 하나만 있으면 돌아간다. 폴더 구조가 필요 없다.

쓰는 법
    화면으로 보기 :  python 터보냉동기_사이클해석.py
                     (브라우저가 자동으로 열린다)
    계산만 찍기   :  python 터보냉동기_사이클해석.py --text

설치할 것은 하나뿐이다
    pip install CoolProp

화면은 파이썬에 처음부터 들어 있는 기능(http.server)으로 만들었다.
streamlit / pandas / matplotlib 이 필요 없어서, 32비트나 ARM 윈도우처럼
pyarrow 가 깔리지 않는 PC 에서도 그대로 돌아간다.

원본은 turbochiller 패키지다 (github: suoarman-cpu/COMP-TEST-DATA).
이 파일은 tools/build_single_file.py 가 자동으로 만든 것이라,
고칠 일이 있으면 원본 패키지를 고치고 다시 빌드하는 편이 좋다.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Literal, Optional

from CoolProp.CoolProp import PropsSI
'''


def strip_module(path: Path) -> str:
    """모듈 하나에서 헤더(주석·import)와 __main__ 블록을 걷어내고 본문만 남긴다."""
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    in_docstring = False
    docstring_done = False
    in_main_block = False

    for line in lines:
        # `if __name__ == "__main__":` 블록은 통째로 버린다.
        # 남겨두면 합친 파일 중간에서 그 모듈의 실행이 먼저 일어나 버린다.
        if in_main_block:
            if line.strip() and not line[0].isspace():
                in_main_block = False
            else:
                continue
        if line.startswith("if __name__ =="):
            in_main_block = True
            continue

        stripped = line.strip()

        # 파일 맨 앞 docstring 은 주석으로 바꿔 남겨 둔다 (설명이 아까우니)
        if not docstring_done:
            if not in_docstring and stripped.startswith('"""'):
                in_docstring = True
                if stripped.endswith('"""') and len(stripped) > 3:
                    in_docstring = False
                    docstring_done = True
                continue
            if in_docstring:
                if stripped.endswith('"""'):
                    in_docstring = False
                    docstring_done = True
                continue
            if not stripped:
                continue
            docstring_done = True

        # 패키지 내부 import 는 버린다
        if RELATIVE_IMPORT.match(line):
            continue

        # 아래는 '모듈 최상단'(들여쓰기 없음) import 에만 적용한다.
        # 함수 안의 지연 import (예: from CoolProp.CoolProp import PropsSI as _P)
        # 까지 지우면 이름이 사라져 버린다.
        if line == stripped and stripped:
            if stripped == "from __future__ import annotations":
                continue
            if re.match(
                r"^(import|from) "
                r"(math|re|io|sys|argparse|json|dataclasses|typing|pathlib)\b",
                stripped,
            ):
                continue
            if stripped.startswith("from CoolProp"):
                continue

        out.append(line)

    return "\n".join(out).strip("\n")


def build() -> Path:
    parts = [HEADER, MODULE_ALIASES]

    for name in MODULES:
        path = PKG / f"{name}.py"
        if not path.exists():
            raise SystemExit(f"모듈을 찾을 수 없다: {path}")
        parts.append(f"\n\n# {'=' * 74}\n# {name}.py\n# {'=' * 74}\n")
        parts.append(strip_module(path))

    parts.append(ENTRYPOINT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return OUT


ENTRYPOINT = '''

# ==========================================================================
# 실행 진입점
# ==========================================================================

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="터보 냉동기 사이클 해석 (파일 하나 배포판)"
    )
    parser.add_argument(
        "--text", action="store_true",
        help="화면 대신 계산 결과를 글자로만 찍는다",
    )
    parser.add_argument("--port", type=int, help="웹 화면 포트 (기본: 8765부터 빈 곳)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않는다")
    parser.add_argument("--refrigerant", default="R1234ze(E)", help="냉매")
    parser.add_argument("--capacity", type=float, default=150.0, help="냉동능력 [RT]")
    parser.add_argument("--stages", type=int, choices=(1, 2), default=2, help="압축 단수")
    parser.add_argument("--t-evap", type=float, help="증발온도 [°C]")
    parser.add_argument("--t-cond", type=float, help="응축온도 [°C]")
    parser.add_argument("--rpm", type=float, help="축 회전수 고정 [rpm]")
    args = parser.parse_args()

    if args.text:
        inp = CycleInput(
            refrigerant=args.refrigerant,
            capacity_rt=args.capacity,
            t_evap=args.t_evap,
            t_cond=args.t_cond,
        )
        result = solve(inp, stages=args.stages)
        print(format_report(result))
        print(format_impeller(size_machine(result, Given(rpm=args.rpm))))
        return

    serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    _main()
'''


if __name__ == "__main__":
    path = build()
    size = path.stat().st_size
    print(f"만들었다: {path}  ({size / 1024:.1f} KB, {len(path.read_text(encoding='utf-8').splitlines())} 줄)")
