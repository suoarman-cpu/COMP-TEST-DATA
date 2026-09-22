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
MODULES = [
    "props",
    "cycle",
    "hx",
    "impeller",
    "standards",
    "report",
    "plot",
]

#: 패키지 내부를 가리키는 import 만 지운다 (외부 라이브러리 import 는 남긴다)
RELATIVE_IMPORT = re.compile(r"^\s*from \.[\w.]* import .*$|^\s*from \. import .*$")

#: `props.h_tp(...)` 처럼 모듈 이름으로 부르던 것을 그대로 쓰게 별칭을 준다
MODULE_ALIASES = """
# --- 모듈 별칭 -------------------------------------------------------------
# 원래는 turbochiller.props 처럼 모듈로 나뉘어 있었다.
# 한 파일로 합치면서, 코드 안의 `props.xxx` 호출이 그대로 동작하도록
# 이 파일 자신을 props 라는 이름으로도 가리키게 해 둔다.
import sys as _sys

props = _sys.modules[__name__]
"""

HEADER = '''"""터보 냉동기 사이클 해석 — 파일 하나로 합친 배포판.

이 파일 하나만 있으면 돌아간다. 폴더 구조가 필요 없다.

쓰는 법
    화면으로 보기 :  streamlit run 터보냉동기_사이클해석.py
    바로 계산만   :  python 터보냉동기_사이클해석.py

필요한 라이브러리
    pip install CoolProp streamlit pandas matplotlib

원본은 turbochiller 패키지다 (github: suoarman-cpu/COMP-TEST-DATA).
이 파일은 tools/build_single_file.py 가 자동으로 만든 것이라,
고칠 일이 있으면 원본 패키지를 고치고 다시 빌드하는 편이 좋다.
"""

from __future__ import annotations

import argparse
import io
import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable, Literal, Optional, Sequence

from CoolProp.CoolProp import PropsSI
'''


def strip_module(path: Path) -> str:
    """모듈 하나에서 헤더(주석·import)를 걷어내고 본문만 남긴다."""
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    in_docstring = False
    docstring_done = False

    for line in lines:
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

    # streamlit 화면 (app.py)
    app = ROOT / "app.py"
    parts.append(f"\n\n# {'=' * 74}\n# app.py — streamlit 화면\n# {'=' * 74}\n")
    app_body = strip_module(app)
    # app.py 는 turbochiller 에서 import 하던 것을 전부 지운다
    app_body = re.sub(
        r"^from turbochiller[\w.]* import \([^)]*\)$|^from turbochiller[\w.]* import .*$",
        "",
        app_body,
        flags=re.MULTILINE,
    )
    app_body = app_body.replace("if __name__ == \"__main__\":\n    main()", "")
    parts.append(app_body.strip("\n"))

    parts.append(ENTRYPOINT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return OUT


ENTRYPOINT = '''

# ==========================================================================
# 실행 진입점
# ==========================================================================

def _streamlit_is_running() -> bool:
    """`streamlit run` 으로 실행됐는지 확인한다."""
    try:
        from streamlit.runtime import exists

        return exists()
    except Exception:
        return False


def _print_default_report() -> None:
    """화면 없이 그냥 실행했을 때 기본 조건으로 한 번 계산해 보여준다."""
    parser = argparse.ArgumentParser(
        description="터보 냉동기 사이클 해석 (파일 하나 배포판)"
    )
    parser.add_argument("--refrigerant", default="R1234ze(E)", help="냉매")
    parser.add_argument("--capacity", type=float, default=150.0, help="냉동능력 [RT]")
    parser.add_argument("--stages", type=int, choices=(1, 2), default=2, help="압축 단수")
    parser.add_argument("--t-evap", type=float, help="증발온도 [°C]")
    parser.add_argument("--t-cond", type=float, help="응축온도 [°C]")
    args = parser.parse_args()

    inp = CycleInput(
        refrigerant=args.refrigerant,
        capacity_rt=args.capacity,
        t_evap=args.t_evap,
        t_cond=args.t_cond,
    )
    print(format_report(solve(inp, stages=args.stages)))
    print()
    print("화면으로 보시려면:  streamlit run 터보냉동기_사이클해석.py")


if __name__ == "__main__":
    if _streamlit_is_running():
        main()
    else:
        _print_default_report()
'''


if __name__ == "__main__":
    path = build()
    size = path.stat().st_size
    print(f"만들었다: {path}  ({size / 1024:.1f} KB, {len(path.read_text(encoding='utf-8').splitlines())} 줄)")
