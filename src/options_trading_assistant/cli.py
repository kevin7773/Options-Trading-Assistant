from __future__ import annotations

import argparse
from datetime import date, datetime
import sys

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import RecommendationAction, ScanResult, TradeCandidate
from options_trading_assistant.providers.factory import build_provider
from options_trading_assistant.reports.journal import append_scan_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the options trading assistant scanner.")
    parser.add_argument("--mode", default=None, help="Scanner mode: conservative, balanced, or aggressive.")
    parser.add_argument("--provider", default=None, help="Data provider: mock or moomoo.")
    parser.add_argument("--date", dest="as_of", default=None, help="Scan date in YYYY-MM-DD format.")
    parser.add_argument("--no-log", action="store_true", help="Do not append the scan result to the JSONL journal.")
    return parser.parse_args()


def parse_scan_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_candidate(candidate: TradeCandidate) -> str:
    spread = candidate.spread
    stock = candidate.stock
    lines = [
        f"Ticker: {stock.ticker}",
        f"Sector: {candidate.sector.name}",
        f"Setup Grade: {candidate.grade}",
        f"Confidence Score: {candidate.score.total:.2f}/100",
        f"Expiration: {spread.expiration.isoformat()}",
        f"Long Call: {spread.long_call:g}",
        f"Short Call: {spread.short_call:g}",
        f"Spread Width: ${spread.width:g}",
        f"Target Debit: ${spread.debit:.2f}",
        f"Max Profit: ${spread.max_profit:.0f}",
        f"Max Loss: ${spread.max_loss:.0f}",
        f"Breakeven: ${spread.breakeven:.2f}",
        "Why This Trade:",
    ]
    lines.extend(f"- {item}" for item in candidate.rationale)
    lines.append("Key Risks:")
    lines.extend(f"- {item}" for item in candidate.risks)
    lines.extend(
        [
            f"Entry Trigger: Only enter if {stock.ticker} holds above support after the first 30-60 minutes.",
            "Profit Target: Consider profits at 60-75% of max gain.",
            "Stop / Invalidating Condition: Exit or reassess if market, sector, or support thesis fails.",
            "Management Plan: Review daily and avoid holding into the final week unless risk/reward remains favorable.",
        ]
    )
    return "\n".join(lines)


def format_result(result: ScanResult) -> str:
    header = [
        f"Date: {result.as_of.isoformat()}",
        f"Mode: {result.mode}",
        f"Strategy Version: {result.strategy_version}",
        f"Market Score: {result.market_score:.2f}/30",
        f"Today's Recommendation: {result.action.value}",
        f"Reason: {result.reason}",
    ]

    if result.action == RecommendationAction.SIT_TODAY_OUT:
        return "\n".join(header)

    sections = ["\n---\n" + format_candidate(candidate) for candidate in result.recommendations]
    return "\n".join(header + sections)


def main() -> None:
    args = parse_args()
    config = load_config()
    selected_mode = args.mode or config.strategy["default_mode"]
    selected_provider = args.provider or config.broker["active_provider"]
    as_of = parse_scan_date(args.as_of)

    provider = build_provider(selected_provider, config)
    try:
        try:
            scanner = DailyScanner(config=config, provider=provider)
            result = scanner.run(mode=selected_mode, as_of=as_of)
        finally:
            close = getattr(provider, "close", None)
            if close:
                close()
    except RuntimeError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(format_result(result))
    if not args.no_log:
        path = append_scan_result(result)
        print(f"\nLogged scan result to: {path}")


if __name__ == "__main__":
    main()
