from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.models import ScanResult
from options_trading_assistant.reports.journal import json_default


def write_decision_packets(result: ScanResult, output_dir: Path | None = None) -> list[Path]:
    base_dir = output_dir or PROJECT_ROOT / "data" / "journal" / "decision_packets"
    scan_dir = base_dir / result.as_of.isoformat() / _scan_slug(result)
    scan_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for index, recommendation in enumerate(result.recommendations, start=1):
        packet = {
            **_base_packet(result),
            "decision_type": "recommendation",
            "decision_id": f"recommendation-{index:03d}",
            "ticker": recommendation.stock.ticker,
            "sector": recommendation.sector.name,
            "grade": recommendation.grade,
            "score": asdict(recommendation.score),
            "stock": asdict(recommendation.stock),
            "sector_snapshot": asdict(recommendation.sector),
            "spread": asdict(recommendation.spread),
            "rationale": recommendation.rationale,
            "risks": recommendation.risks,
        }
        paths.append(_write_packet(scan_dir / f"recommendation-{index:03d}-{recommendation.stock.ticker}.json", packet))

    for index, rejection in enumerate(result.rejections, start=1):
        label = rejection.ticker or rejection.sector or rejection.stage.value
        packet = {
            **_base_packet(result),
            "decision_type": "rejection",
            "decision_id": f"rejection-{index:03d}",
            "ticker": rejection.ticker,
            "sector": rejection.sector,
            "stage": rejection.stage,
            "score": rejection.score,
            "expiration": rejection.expiration,
            "long_call": rejection.long_call,
            "short_call": rejection.short_call,
            "reasons": rejection.reasons,
        }
        paths.append(_write_packet(scan_dir / f"rejection-{index:03d}-{_safe_filename(label)}.json", packet))

    return paths


def _base_packet(result: ScanResult) -> dict[str, Any]:
    return {
        "schema_version": "decision_packet_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scan": {
            "as_of": result.as_of,
            "mode": result.mode,
            "strategy_version": result.strategy_version,
            "action": result.action,
            "reason": result.reason,
            "market_score": result.market_score,
            "context": asdict(result.context),
        },
        "outcome": {
            "status": "pending",
            "notes": None,
            "closed_at": None,
            "final_pl": None,
        },
    }


def _scan_slug(result: ScanResult) -> str:
    timestamp = datetime.now().strftime("%H%M%S-%f")
    return f"{result.strategy_version}-{result.mode}-{result.action.value.lower().replace(' ', '-')}-{timestamp}"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value)
    return safe.strip("-") or "unknown"


def _write_packet(path: Path, packet: dict[str, Any]) -> Path:
    path.write_text(json.dumps(packet, default=json_default, indent=2, sort_keys=True), encoding="utf-8")
    return path
