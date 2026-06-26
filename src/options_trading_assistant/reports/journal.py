from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.models import ScanResult


def json_default(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def append_scan_result(result: ScanResult, journal_dir: Path | None = None) -> Path:
    output_dir = journal_dir or PROJECT_ROOT / "data" / "journal"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "scan_results.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result.to_dict(), default=json_default, sort_keys=True))
        file.write("\n")
    return path
