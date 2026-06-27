from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT


PACKET_ROOT = PROJECT_ROOT / "data" / "journal" / "decision_packets"


def find_packet_files(base_dir: Path | None = None, scan_date: str | None = None) -> list[Path]:
    root = base_dir or PACKET_ROOT
    if scan_date:
        root = root / scan_date
    if not root.exists():
        return []
    return sorted(root.rglob("*.json"))


def load_packet(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_summary(path: Path) -> dict[str, Any]:
    packet = load_packet(path)
    outcome = packet.get("outcome", {})
    scan = packet.get("scan", {})
    return {
        "path": str(path),
        "date": scan.get("as_of"),
        "decision_type": packet.get("decision_type"),
        "ticker": packet.get("ticker"),
        "sector": packet.get("sector"),
        "stage": packet.get("stage"),
        "status": outcome.get("status", "unknown"),
        "final_pl": outcome.get("final_pl"),
    }


def update_packet_outcome(
    path: Path,
    status: str | None = None,
    notes: str | None = None,
    closed_at: str | None = None,
    final_pl: float | None = None,
) -> dict[str, Any]:
    packet = load_packet(path)
    outcome = dict(packet.get("outcome") or {})

    if status is not None:
        outcome["status"] = status
    if notes is not None:
        outcome["notes"] = notes
    if closed_at is not None:
        outcome["closed_at"] = closed_at
    if final_pl is not None:
        outcome["final_pl"] = final_pl

    outcome["updated_at"] = datetime.now().isoformat(timespec="seconds")
    packet["outcome"] = outcome
    path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return packet


def summarize_packets(paths: list[Path]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    total_final_pl = 0.0
    packets_with_pl = 0

    for path in paths:
        packet = load_packet(path)
        outcome = packet.get("outcome", {})
        status_counts[outcome.get("status", "unknown")] += 1
        decision_counts[packet.get("decision_type", "unknown")] += 1
        if packet.get("stage"):
            stage_counts[packet["stage"]] += 1
        if packet.get("ticker"):
            ticker_counts[packet["ticker"]] += 1
        if outcome.get("final_pl") is not None:
            total_final_pl += float(outcome["final_pl"])
            packets_with_pl += 1

    return {
        "packet_count": len(paths),
        "status_counts": status_counts,
        "decision_counts": decision_counts,
        "stage_counts": stage_counts,
        "ticker_counts": ticker_counts,
        "total_final_pl": total_final_pl,
        "packets_with_pl": packets_with_pl,
    }


def format_packet_list(summaries: list[dict[str, Any]], limit: int | None = None) -> str:
    selected = summaries[:limit] if limit else summaries
    lines = [
        f"Decision Packets: {len(summaries)}",
        "",
        "Type | Ticker | Stage | Status | Final P/L | Path",
        "--- | --- | --- | --- | ---: | ---",
    ]
    for item in selected:
        lines.append(
            " | ".join(
                [
                    str(item.get("decision_type") or ""),
                    str(item.get("ticker") or item.get("sector") or ""),
                    str(item.get("stage") or ""),
                    str(item.get("status") or ""),
                    "" if item.get("final_pl") is None else f"{float(item['final_pl']):.2f}",
                    item["path"],
                ]
            )
        )
    if limit and len(summaries) > limit:
        lines.append(f"... {len(summaries) - limit} more packet(s)")
    return "\n".join(lines)


def format_packet_review(summary: dict[str, Any], limit: int = 10) -> str:
    lines = [
        "Packet Review",
        f"Packets: {summary['packet_count']}",
        f"Packets With P/L: {summary['packets_with_pl']}",
        f"Total Final P/L: {summary['total_final_pl']:.2f}",
        "",
        "Outcome Status:",
    ]
    lines.extend(_format_counter(summary["status_counts"], limit))
    lines.append("")
    lines.append("Decision Types:")
    lines.extend(_format_counter(summary["decision_counts"], limit))
    lines.append("")
    lines.append("Rejection Stages:")
    lines.extend(_format_counter(summary["stage_counts"], limit))
    lines.append("")
    lines.append("Tickers:")
    lines.extend(_format_counter(summary["ticker_counts"], limit))
    return "\n".join(lines)


def _format_counter(counter: Counter[str], limit: int) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- {name}: {count}" for name, count in counter.most_common(limit)]
