"""입력 파일(YAML/JSON) 읽고 쓰기.

코드를 고치지 않고 조건만 바꿔가며 돌릴 수 있게 한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from .cycle import CycleInput, ExcelCompat


def _load_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - 안내용
            raise SystemExit(
                "YAML 파일을 읽으려면 PyYAML 이 필요하다: pip install pyyaml\n"
                "(또는 입력 파일을 .json 으로 저장해서 쓰면 된다)"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 최상위가 사전(dict) 형태여야 한다")
    return data


def load_input(path: str | Path) -> tuple[CycleInput, dict[str, Any]]:
    """입력 파일을 읽어 CycleInput 과 나머지 설정을 돌려준다.

    사이클 입력에 해당하지 않는 키(stages, impeller, iplv 등)는
    두 번째 반환값에 그대로 담아 준다.
    """
    path = Path(path)
    data = _load_raw(path)

    known = {f.name for f in fields(CycleInput)}
    cycle_kwargs = {k: v for k, v in data.items() if k in known and k != "compat"}
    extra = {k: v for k, v in data.items() if k not in known}

    compat_data = data.get("compat") or {}
    compat_known = {f.name for f in fields(ExcelCompat)}
    unknown_compat = set(compat_data) - compat_known
    if unknown_compat:
        raise ValueError(f"{path}: compat 에 모르는 항목 {sorted(unknown_compat)}")
    cycle_kwargs["compat"] = ExcelCompat(**compat_data)

    return CycleInput(**cycle_kwargs), extra


def dump_input(inp: CycleInput, path: str | Path) -> None:
    """현재 입력을 파일로 저장한다."""
    path = Path(path)
    data = asdict(inp)
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml

        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    else:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
