from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT


def load_scan_records(path: Path | None = None) -> list[dict[str, Any]]:
    journal_path = path or PROJECT_ROOT / "data" / "journal" / "scan_results.jsonl"
    if not journal_path.exists():
        return []

    records = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def filter_scan_records(
    records: list[dict[str, Any]],
    days: int | None = None,
    ticker: str | None = None,
    stage: str | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    cutoff = None
    if days is not None:
        reference_date = today or date.today()
        cutoff = reference_date - timedelta(days=days - 1)

    filtered = []
    ticker_upper = ticker.upper() if ticker else None
    stage_lower = stage.lower() if stage else None

    for record in records:
        record_date = date.fromisoformat(record["as_of"])
        if cutoff and record_date < cutoff:
            continue

        rejections = record.get("rejections", [])
        if ticker_upper and not _record_mentions_ticker(record, ticker_upper):
            continue
        if stage_lower and not any(rejection.get("stage") == stage_lower for rejection in rejections):
            continue

        filtered.append(record)

    return filtered


def summarize_scan_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(record.get("action", "unknown") for record in records)
    stage_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    option_reason_counts: Counter[str] = Counter()
    market_reason_counts: Counter[str] = Counter()
    total_rejections = 0
    stocks_scanned = 0
    spreads_evaluated = 0
    volatility_sources: Counter[str] = Counter()
    leading_sectors: Counter[str] = Counter()

    for record in records:
        context = record.get("context", {})
        stocks_scanned += int(context.get("stocks_scanned") or 0)
        spreads_evaluated += int(context.get("spreads_evaluated") or 0)
        volatility_source = context.get("volatility_source")
        if volatility_source:
            volatility_sources[volatility_source] += 1
        top_sectors = context.get("top_sectors", [])
        if top_sectors:
            leading_sector = top_sectors[0].get("sector")
            if leading_sector:
                leading_sectors[leading_sector] += 1

        for rejection in record.get("rejections", []):
            total_rejections += 1
            stage = rejection.get("stage", "unknown")
            stage_counts[stage] += 1
            ticker = rejection.get("ticker")
            if ticker:
                ticker_counts[ticker] += 1
            for reason in rejection.get("reasons", []):
                reason_counts[reason] += 1
                if stage == "options":
                    option_reason_counts[reason] += 1
                if stage == "market":
                    market_reason_counts[reason] += 1

    return {
        "scan_count": len(records),
        "action_counts": action_counts,
        "total_rejections": total_rejections,
        "stocks_scanned": stocks_scanned,
        "spreads_evaluated": spreads_evaluated,
        "volatility_sources": volatility_sources,
        "leading_sectors": leading_sectors,
        "stage_counts": stage_counts,
        "ticker_counts": ticker_counts,
        "reason_counts": reason_counts,
        "option_reason_counts": option_reason_counts,
        "market_reason_counts": market_reason_counts,
    }


def format_journal_review(summary: dict[str, Any], limit: int = 10) -> str:
    lines = [
        "Journal Review",
        f"Scans: {summary['scan_count']}",
        f"Rejected Candidates: {summary['total_rejections']}",
        f"Stocks Scanned: {summary['stocks_scanned']}",
        f"Spreads Evaluated: {summary['spreads_evaluated']}",
        "",
        "Actions:",
    ]
    lines.extend(_format_counter(summary["action_counts"], limit))

    lines.append("")
    lines.append("Volatility Sources:")
    lines.extend(_format_counter(summary["volatility_sources"], limit))

    lines.append("")
    lines.append("Leading Sectors:")
    lines.extend(_format_counter(summary["leading_sectors"], limit))

    lines.append("")
    lines.append("Rejection Stages:")
    lines.extend(_format_counter(summary["stage_counts"], limit))

    lines.append("")
    lines.append("Most Rejected Tickers:")
    lines.extend(_format_counter(summary["ticker_counts"], limit))

    lines.append("")
    lines.append("Most Common Rejection Reasons:")
    lines.extend(_format_counter(summary["reason_counts"], limit))

    lines.append("")
    lines.append("Options Rejection Reasons:")
    lines.extend(_format_counter(summary["option_reason_counts"], limit))

    lines.append("")
    lines.append("Market Rejection Reasons:")
    lines.extend(_format_counter(summary["market_reason_counts"], limit))

    return "\n".join(lines)


def _record_mentions_ticker(record: dict[str, Any], ticker: str) -> bool:
    for recommendation in record.get("recommendations", []):
        stock = recommendation.get("stock", {})
        if str(stock.get("ticker", "")).upper() == ticker:
            return True
    for rejection in record.get("rejections", []):
        if str(rejection.get("ticker", "")).upper() == ticker:
            return True
    return False


def _format_counter(counter: Counter[str], limit: int) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- {name}: {count}" for name, count in counter.most_common(limit)]
