"""냉매별 계산서를 한꺼번에 만든다.

    python -m excel.make_all [출력폴더]
"""

from __future__ import annotations

import sys
from pathlib import Path

from .build_workbook import build_workbook
from .tables import build

#: 만들 냉매들
REFRIGERANTS = ["R1234ze(E)", "R134a", "R1234yf", "R513A.mix"]


def safe_name(refrigerant: str) -> str:
    """파일 이름에 쓸 수 있게 다듬는다."""
    return (
        refrigerant.replace("(", "").replace(")", "").replace(".mix", "")
    )


def main(out_dir: str = "excel/출력") -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    for ref in REFRIGERANTS:
        tables = build(ref)
        path = out / f"터보냉동기_사이클계산_{safe_name(ref)}.xlsx"
        build_workbook(tables, str(path))
        made.append(str(path))
        print(f"  만들었다: {path.name}")
    return made


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "excel/출력")
