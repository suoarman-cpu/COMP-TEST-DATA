"""냉매를 골라 쓰는 계산서 한 개를 만든다.

    python -m excel.make_all [출력폴더]
"""

from __future__ import annotations

import sys
from pathlib import Path

from .build_workbook import build_workbook
from .chartlines import build_many as build_lines
from .tables import build_many

#: 계산서에 담을 냉매들
REFRIGERANTS = ["R1234ze(E)", "R134a", "R1234yf", "R513A.mix"]

from .version import REVISION

FILENAME = f"터보냉동기_사이클계산_Rev{REVISION}.xlsx"


def main(out_dir: str = "excel/출력") -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tabs = build_many(REFRIGERANTS)
    lines = build_lines(REFRIGERANTS)
    path = out / FILENAME
    build_workbook(tabs, lines, str(path))
    print(f"  만들었다: {path}  (냉매 {len(tabs)}종)")
    return str(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "excel/출력")
