from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
import sys

from options_trading_assistant.backtesting.diagnostics import (
    build_stock_diagnostics_report,
    format_stock_diagnostics_report,
)
from options_trading_assistant.backtesting.engine import run_backtest
from options_trading_assistant.backtesting.scenarios import get_scenario, scenario_names
from options_trading_assistant.config import load_config
from options_trading_assistant.engines.cooling_off import CoolingOffTracker
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.engines.scoring import (
    passes_mean_reversion,
    score_confirmation,
    score_options,
    score_sector,
    score_trend,
)
from options_trading_assistant.models import (
    OptionSpread,
    RecommendationAction,
    RejectedCandidate,
    ScanResult,
    SectorSnapshot,
    StockSnapshot,
    TradeCandidate,
)
from options_trading_assistant.providers.factory import build_provider
from options_trading_assistant.providers.historical import HistoricalDataProvider, hydrate_massive_ohlcv
from options_trading_assistant.reports.decision_packets import write_decision_packets
from options_trading_assistant.reports.daily_report import (
    format_daily_report_html,
    format_report_footer,
    write_daily_report,
    write_daily_report_html,
)
from options_trading_assistant.reports.dashboard import build_dashboard, serve_dashboard
from options_trading_assistant.reports.journal import append_scan_result
from options_trading_assistant.reports.journal_review import (
    filter_scan_records,
    format_journal_review,
    load_scan_records,
    summarize_scan_records,
)
from options_trading_assistant.reports.packet_review import (
    find_packet_files,
    format_packet_list,
    format_packet_review,
    packet_summary,
    summarize_packets,
    update_packet_outcome,
)
from options_trading_assistant.reports.signal_rankings import write_signal_ranking_snapshot
from options_trading_assistant.validation.engine import (
    evaluate_edge,
    format_validation_report,
    load_backtest_evidence,
    load_packet_evidence,
    load_validation_protocol,
    result_to_dict,
)
from options_trading_assistant.validation.ranking import (
    evaluate_ranking_criteria,
    run_ranking_experiment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the options trading assistant scanner.")
    subparsers = parser.add_subparsers(dest="command")

    diagnose = subparsers.add_parser("diagnose", help="Inspect provider response shapes for one ticker.")
    diagnose.add_argument("--provider", default="moomoo", help="Data provider to diagnose.")
    diagnose.add_argument("--ticker", default="MSFT", help="Ticker to inspect.")
    diagnose.add_argument("--date", dest="as_of", default=None, help="Diagnostic date in YYYY-MM-DD format.")

    scan_options = subparsers.add_parser("scan-options", help="Inspect bull call spread candidates for one ticker.")
    scan_options.add_argument("--provider", default="moomoo", help="Data provider to use.")
    scan_options.add_argument("--ticker", default="MSFT", help="Ticker to scan.")
    scan_options.add_argument("--date", dest="as_of", default=None, help="Scan date in YYYY-MM-DD format.")
    scan_options.add_argument("--limit", type=int, default=10, help="Maximum number of spreads to show.")

    rank_sectors = subparsers.add_parser("rank-sectors", help="Rank configured sectors with live provider data.")
    rank_sectors.add_argument("--provider", default="moomoo", help="Data provider to use.")
    rank_sectors.add_argument("--date", dest="as_of", default=None, help="Ranking date in YYYY-MM-DD format.")
    rank_sectors.add_argument("--limit", type=int, default=13, help="Maximum number of sectors to show.")

    scan_stocks = subparsers.add_parser("scan-stocks", help="Inspect stock candidates within one configured sector.")
    scan_stocks.add_argument("--provider", default="moomoo", help="Data provider to use.")
    scan_stocks.add_argument("--sector", required=True, help="Configured sector name to scan.")
    scan_stocks.add_argument("--mode", default=None, help="Scanner mode for confirmation thresholds.")
    scan_stocks.add_argument("--date", dest="as_of", default=None, help="Scan date in YYYY-MM-DD format.")
    scan_stocks.add_argument("--limit", type=int, default=20, help="Maximum number of stocks to show.")

    review_journal = subparsers.add_parser("review-journal", help="Summarize logged scan recommendations and rejections.")
    review_journal.add_argument("--days", type=int, default=None, help="Only include scans from the last N days.")
    review_journal.add_argument("--ticker", default=None, help="Only include scans mentioning this ticker.")
    review_journal.add_argument("--stage", default=None, help="Only include scans with this rejection stage.")
    review_journal.add_argument("--limit", type=int, default=10, help="Maximum rows per summary section.")

    list_packets = subparsers.add_parser("list-packets", help="List decision packet files and outcome status.")
    list_packets.add_argument("--date", dest="scan_date", default=None, help="Only include packets for YYYY-MM-DD.")
    list_packets.add_argument("--limit", type=int, default=None, help="Maximum packets to show.")

    update_outcome = subparsers.add_parser("update-outcome", help="Update a decision packet outcome block.")
    update_outcome.add_argument("--packet", required=True, help="Path to a decision packet JSON file.")
    update_outcome.add_argument("--status", default=None, help="Outcome status, such as reviewed or closed.")
    update_outcome.add_argument("--notes", default=None, help="Outcome notes.")
    update_outcome.add_argument("--closed-at", default=None, help="Closed timestamp/date.")
    update_outcome.add_argument("--final-pl", type=float, default=None, help="Final realized or simulated P/L.")

    review_packets = subparsers.add_parser("review-packets", help="Summarize decision packet outcomes.")
    review_packets.add_argument("--date", dest="scan_date", default=None, help="Only include packets for YYYY-MM-DD.")
    review_packets.add_argument("--limit", type=int, default=10, help="Maximum rows per summary section.")

    daily_report = subparsers.add_parser("daily-report", help="Run the daily scanner and save a Markdown report.")
    daily_report.add_argument("--provider", default=None, help="Data provider: mock or moomoo.")
    daily_report.add_argument("--mode", default=None, help="Scanner mode: conservative, balanced, or aggressive.")
    daily_report.add_argument("--date", dest="as_of", default=None, help="Report date in YYYY-MM-DD format.")
    daily_report.add_argument("--no-log", action="store_true", help="Do not append JSONL or decision packets.")

    dashboard = subparsers.add_parser("dashboard", help="Build a local HTML dashboard for reports and decision packets.")
    dashboard.add_argument("--serve", action="store_true", help="Serve the dashboard at a local URL after building it.")
    dashboard.add_argument("--host", default="127.0.0.1", help="Host for --serve.")
    dashboard.add_argument("--port", type=int, default=8765, help="Port for --serve.")

    backtest = subparsers.add_parser("backtest", help="Run the scanner across historical OHLCV data.")
    backtest.add_argument("--start", required=True, help="Backtest start date in YYYY-MM-DD format.")
    backtest.add_argument("--end", required=True, help="Backtest end date in YYYY-MM-DD format.")
    backtest.add_argument("--mode", default=None, help="Scanner mode: conservative, balanced, or aggressive.")
    backtest.add_argument("--data-source", choices=("cache", "massive"), default="cache", help="Historical data source.")
    backtest.add_argument("--cache-dir", default=None, help="Historical data cache directory.")
    backtest.add_argument("--vix-proxy", default="VIXY", help="Ticker to use as the VIX/risk proxy.")
    backtest.add_argument("--calls-per-minute", type=int, default=5, help="Massive API call limit.")
    backtest.add_argument("--run-id", default=None, help="Optional stable output folder name.")
    backtest.add_argument("--scenario", default="balanced", help="Backtest scenario: balanced, high_probability, aggressive.")
    backtest.add_argument(
        "--summary-only",
        action="store_true",
        help="Write summary and trades without per-scan journals or decision packets.",
    )

    scenarios = subparsers.add_parser("backtest-scenarios", help="Run multiple entry/exit scenarios over the same period.")
    scenarios.add_argument("--start", required=True, help="Backtest start date in YYYY-MM-DD format.")
    scenarios.add_argument("--end", required=True, help="Backtest end date in YYYY-MM-DD format.")
    scenarios.add_argument("--mode", default=None, help="Scanner mode, usually balanced for scenario comparison.")
    scenarios.add_argument("--data-source", choices=("cache", "massive"), default="cache", help="Historical data source.")
    scenarios.add_argument("--cache-dir", default=None, help="Historical data cache directory.")
    scenarios.add_argument("--vix-proxy", default="VIXY", help="Ticker to use as the VIX/risk proxy.")
    scenarios.add_argument("--calls-per-minute", type=int, default=5, help="Massive API call limit.")
    scenarios.add_argument("--scenarios", default="all", help="Comma-separated scenarios or 'all'.")
    scenarios.add_argument(
        "--summary-only",
        action="store_true",
        help="Write summary and trades without per-scan journals or decision packets.",
    )

    hydrate = subparsers.add_parser("hydrate-history", help="Download historical OHLCV bars into the local cache.")
    hydrate.add_argument("--start", required=True, help="Hydration start date in YYYY-MM-DD format.")
    hydrate.add_argument("--end", required=True, help="Hydration end date in YYYY-MM-DD format.")
    hydrate.add_argument("--cache-dir", default=None, help="Historical data cache directory.")
    hydrate.add_argument("--vix-proxy", default="VIXY", help="Ticker to use as the VIX/risk proxy.")
    hydrate.add_argument("--calls-per-minute", type=int, default=5, help="Massive API call limit.")
    hydrate.add_argument("--limit", type=int, default=None, help="Only process the first N uncached/cached symbols.")
    hydrate.add_argument("--tickers", default=None, help="Comma-separated ticker override for testing or partial hydrates.")

    stock_diagnostics = subparsers.add_parser(
        "backtest-stock-diagnostics",
        help="Rank and explain historical stock-layer rejections for one date.",
    )
    stock_diagnostics.add_argument("--date", dest="as_of", required=True, help="Historical date in YYYY-MM-DD format.")
    stock_diagnostics.add_argument("--mode", default=None, help="Scanner mode: conservative, balanced, or aggressive.")
    stock_diagnostics.add_argument("--cache-dir", default=None, help="Historical data cache directory.")
    stock_diagnostics.add_argument("--vix-proxy", default="VIXY", help="Ticker to use as the VIX/risk proxy.")
    stock_diagnostics.add_argument("--limit", type=int, default=25, help="Number of ranked stocks to show.")

    lifecycle = subparsers.add_parser("review-trades", help="Print trade lifecycle diagnostics for a backtest run.")
    lifecycle.add_argument("--run-dir", required=True, help="Backtest result directory containing trades.jsonl.")
    lifecycle.add_argument("--limit", type=int, default=None, help="Maximum trades to show.")

    validate_edge = subparsers.add_parser(
        "validate-edge",
        help="Evaluate frozen-baseline evidence against the predeclared edge protocol.",
    )
    validate_edge.add_argument("--source", choices=("backtest", "packets"), default="backtest")
    validate_edge.add_argument("--runs-root", default=None, help="Backtest result root containing trades.jsonl files.")
    validate_edge.add_argument("--packet-root", default=None, help="Decision packet root for forward evidence.")
    validate_edge.add_argument("--scenario", default="current_otm", help="Scenario name to evaluate.")
    validate_edge.add_argument(
        "--benchmark-scenario",
        default=None,
        help="Optional predeclared control scenario from the same backtest root.",
    )
    validate_edge.add_argument(
        "--evidence-kind",
        choices=("retrospective", "holdout", "forward"),
        default="retrospective",
    )
    validate_edge.add_argument("--protocol", default=None, help="Validation protocol YAML path.")
    validate_edge.add_argument("--output-dir", default=None, help="Validation report output directory.")

    ranking = subparsers.add_parser(
        "ranking-experiment",
        help="Save each market-pass day's top-ranked stocks and evaluate forward performance.",
    )
    ranking.add_argument("--start", required=True, help="Experiment start date in YYYY-MM-DD format.")
    ranking.add_argument("--end", required=True, help="Experiment end date in YYYY-MM-DD format.")
    ranking.add_argument("--cache-dir", required=True, help="Historical OHLCV cache directory.")
    ranking.add_argument("--mode", default=None, help="Scanner mode, normally balanced.")
    ranking.add_argument("--protocol", default=None, help="Validation protocol YAML path.")
    ranking.add_argument("--output-dir", default=None, help="Ranking artifact output directory.")

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

    rejection_summary = format_rejection_summary(result.rejections)

    if result.action == RecommendationAction.SIT_TODAY_OUT:
        return "\n".join(header + rejection_summary)

    sections = ["\n---\n" + format_candidate(candidate) for candidate in result.recommendations]
    return "\n".join(header + sections + rejection_summary)


def rejection_label(rejection: RejectedCandidate) -> str:
    if rejection.ticker and rejection.long_call is not None and rejection.short_call is not None:
        return f"{rejection.ticker} {rejection.long_call:g}/{rejection.short_call:g}"
    if rejection.ticker:
        return rejection.ticker
    if rejection.sector:
        return rejection.sector
    return rejection.stage.value


def format_rejection_summary(rejections: tuple[RejectedCandidate, ...], limit: int = 8) -> list[str]:
    if not rejections:
        return []

    lines = [
        "",
        "Rejected Candidates:",
    ]
    for rejection in rejections[:limit]:
        reasons = "; ".join(rejection.reasons[:3])
        if len(rejection.reasons) > 3:
            reasons += f"; +{len(rejection.reasons) - 3} more"
        score_text = f" score={rejection.score:.2f}" if rejection.score is not None else ""
        lines.append(f"- [{rejection.stage.value}] {rejection_label(rejection)}{score_text}: {reasons}")

    if len(rejections) > limit:
        lines.append(f"- ... {len(rejections) - limit} more rejection(s)")
    return lines


def format_option_spread(spread: OptionSpread, options_score: float) -> str:
    lines = [
        f"Expiration: {spread.expiration.isoformat()}",
        f"Spread: {spread.long_call:g}/{spread.short_call:g} bull call spread",
        f"Options Score: {options_score:.2f}/15",
        f"Debit: ${spread.debit:.2f}",
        f"Max Profit: ${spread.max_profit:.0f}",
        f"Max Loss: ${spread.max_loss:.0f}",
        f"Reward/Risk: {spread.reward_to_risk:.2f}",
        f"Breakeven: ${spread.breakeven:.2f}",
        f"Long Delta: {spread.long_delta:.3f}",
        f"Short Delta: {spread.short_delta:.3f}",
        f"Open Interest: {spread.long_open_interest}/{spread.short_open_interest}",
        f"Bid/Ask Width: {spread.bid_ask_width_pct:.2%}",
        f"Volume Score: {spread.volume_score:.2f}",
        f"IV: {spread.iv_rank:.2%}",
    ]
    if spread.estimated_debit is not None:
        lines.extend(
            [
                f"Estimated Debit: ${spread.estimated_debit:.2f}",
                f"Debit % Width: {spread.debit_pct_of_width:.2%}",
                f"Expected Move: ${spread.expected_move:.2f}",
                f"Distance to Long Strike: {spread.distance_to_long_strike:.2f}%",
                f"Distance to Short Strike: {spread.distance_to_short_strike:.2f}%",
                f"Estimated Reward/Risk: {spread.estimated_reward_risk:.2f}",
                f"Pricing Reason: {spread.pricing_reason}",
            ]
        )
    return "\n".join(lines)


def format_option_scan(ticker: str, as_of: date, scored_spreads: list[tuple[OptionSpread, float]]) -> str:
    lines = [
        f"Ticker: {ticker}",
        f"Date: {as_of.isoformat()}",
        f"Spread Candidates: {len(scored_spreads)}",
    ]
    if not scored_spreads:
        lines.append("No spread candidates matched the configured expiration/width filters.")
        return "\n".join(lines)

    for index, (spread, options_score_value) in enumerate(scored_spreads, start=1):
        lines.append("")
        lines.append(f"[{index}]")
        lines.append(format_option_spread(spread, options_score_value))
    return "\n".join(lines)


def format_sector_ranking(as_of: date, ranked_sectors: list[tuple[SectorSnapshot, float]]) -> str:
    lines = [
        f"Date: {as_of.isoformat()}",
        f"Sectors Ranked: {len(ranked_sectors)}",
        "",
        "Rank | Sector | ETF | Score | RS 1D | RS 5D | RS 20D | >20DMA | >50DMA | Volume | Momentum | Recovery",
        "---: | --- | --- | ---: | ---: | ---: | ---: | :---: | :---: | ---: | ---: | ---:",
    ]
    for index, (sector, sector_score_value) in enumerate(ranked_sectors, start=1):
        lines.append(
            " | ".join(
                [
                    str(index),
                    sector.name,
                    sector.primary_etf,
                    f"{sector_score_value:.2f}/15",
                    f"{sector.relative_strength_1d:.2f}",
                    f"{sector.relative_strength_5d:.2f}",
                    f"{sector.relative_strength_20d:.2f}",
                    "Y" if sector.above_20dma else "N",
                    "Y" if sector.above_50dma else "N",
                    f"{sector.volume_trend_score:.2f}",
                    f"{sector.momentum_score:.2f}",
                    f"{sector.recovery_score:.2f}",
                ]
            )
        )
    return "\n".join(lines)


def stock_rejection_reasons(
    stock: StockSnapshot,
    trend_score_value: float,
    confirmation_score_value: float,
    required_signals: int,
    strategy_config: dict,
) -> list[str]:
    reasons = []
    trend_config = strategy_config["trend"]
    mean_reversion_config = strategy_config["mean_reversion"]
    confirmation_config = strategy_config["confirmation"]

    if trend_score_value < trend_config["minimum_score"]:
        reasons.append("trend score below threshold")
    if not stock.above_100dma:
        reasons.append("below 100 DMA")
    if not stock.above_200dma:
        reasons.append("below 200 DMA")
    if stock.trend_90d < 0:
        reasons.append("negative 90-day trend")
    if stock.making_lower_lows:
        reasons.append("making lower lows")
    if not (
        mean_reversion_config["min_pullback_pct"]
        <= stock.drawdown_from_swing_high_pct
        <= mean_reversion_config["max_pullback_pct"]
    ):
        reasons.append(
            "pullback not in "
            f"{mean_reversion_config['min_pullback_pct']:g}-{mean_reversion_config['max_pullback_pct']:g}% "
            "controlled range"
        )
    if stock.rsi > mean_reversion_config["max_rsi"]:
        reasons.append("RSI not low enough for mean-reversion setup")
    if not stock.near_support:
        reasons.append("not near support")
    if not stock.selling_volume_stabilizing:
        reasons.append("selling volume not stabilizing")
    if stock.company_specific_warning:
        reasons.append("company-specific warning")
    if len(stock.confirmation_signals) < required_signals or confirmation_score_value < confirmation_config["minimum_score"]:
        reasons.append(f"insufficient confirmation signals ({len(stock.confirmation_signals)}/{required_signals})")
    return reasons


def format_stock_scan(
    sector_name: str,
    as_of: date,
    rows: list[tuple[StockSnapshot, float, float, bool, list[str]]],
) -> str:
    lines = [
        f"Sector: {sector_name}",
        f"Date: {as_of.isoformat()}",
        f"Stocks Scanned: {len(rows)}",
        "",
        "Ticker | Price | Trend | Confirmation | Pullback | RSI | >100DMA | >200DMA | Support | Volume Stable | Pass | Reasons",
        "--- | ---: | ---: | ---: | ---: | ---: | :---: | :---: | :---: | :---: | :---: | ---",
    ]
    for stock, trend_score_value, confirmation_score_value, mean_reversion_pass, reasons in rows:
        passes = mean_reversion_pass and trend_score_value >= 14 and confirmation_score_value >= 12 and not reasons
        reason_text = "; ".join(reasons) if reasons else "eligible for options scan"
        lines.append(
            " | ".join(
                [
                    stock.ticker,
                    f"${stock.price:.2f}",
                    f"{trend_score_value:.2f}/20",
                    f"{confirmation_score_value:.2f}/20",
                    f"{stock.drawdown_from_swing_high_pct:.1f}%",
                    f"{stock.rsi:.1f}",
                    "Y" if stock.above_100dma else "N",
                    "Y" if stock.above_200dma else "N",
                    "Y" if stock.near_support else "N",
                    "Y" if stock.selling_volume_stabilizing else "N",
                    "Y" if passes else "N",
                    reason_text,
                ]
            )
        )
        if stock.confirmation_signals:
            lines.append(f"  confirmations: {', '.join(stock.confirmation_signals)}")
    return "\n".join(lines)


def format_diagnostics(report: dict) -> str:
    lines = [
        f"Provider: {report['provider']}",
        f"OpenD: {report['host']}:{report['port']}",
        f"Ticker: {report['ticker']}",
        f"Code: {report['code']}",
        f"Date: {report['as_of']}",
    ]

    for section_name, section in report["sections"].items():
        lines.append("")
        lines.append(f"[{section_name}]")
        if not section.get("ok"):
            lines.append(f"Status: ERROR")
            lines.append(f"Error: {section.get('error', 'Unknown error')}")
            continue

        lines.append("Status: OK")
        if "rows" in section:
            lines.append(f"Rows: {section['rows']}")
        if "call_rows" in section:
            lines.append(f"Call Rows: {section['call_rows']}")
        if "expiration" in section:
            lines.append(f"Expiration: {section['expiration']}")
        if "selected_expiration" in section:
            lines.append(f"Selected Expiration: {section['selected_expiration'] or 'None'}")
        if "eligible_expirations" in section:
            eligible = ", ".join(section["eligible_expirations"]) or "None"
            lines.append(f"Eligible Expirations: {eligible}")

        columns = section.get("columns", [])
        lines.append(f"Columns ({len(columns)}): {', '.join(columns) if columns else 'None'}")

        required_fields = section.get("required_fields", {})
        if required_fields:
            lines.append("Required Field Coverage:")
            for field, coverage in required_fields.items():
                status = "OK" if coverage["ok"] else "MISSING"
                matched = ", ".join(coverage["matched"]) if coverage["matched"] else "none"
                lines.append(f"- {field}: {status} ({matched})")

        sample = section.get("sample", {})
        if sample:
            preview_items = list(sample.items())[:8]
            preview = "; ".join(f"{key}={value}" for key, value in preview_items)
            lines.append(f"Sample: {preview}")

    return "\n".join(lines)


def run_diagnostics(args: argparse.Namespace) -> None:
    config = load_config()
    provider = build_provider(args.provider, config)
    try:
        diagnose = getattr(provider, "diagnose_ticker", None)
        if diagnose is None:
            raise RuntimeError(f"Provider '{args.provider}' does not support diagnostics.")
        report = diagnose(args.ticker, parse_scan_date(args.as_of))
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    print(format_diagnostics(report))


def run_option_scan(args: argparse.Namespace) -> None:
    config = load_config()
    as_of = parse_scan_date(args.as_of)
    provider = build_provider(args.provider, config)
    try:
        spreads = provider.get_option_spreads(args.ticker, as_of)
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    scored = [
        (spread, score_options(spread, config.strategy["trade"], as_of))
        for spread in spreads
    ]
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)[: args.limit]
    print(format_option_scan(args.ticker, as_of, ranked))


def run_sector_ranking(args: argparse.Namespace) -> None:
    config = load_config()
    as_of = parse_scan_date(args.as_of)
    provider = build_provider(args.provider, config)
    try:
        sectors = provider.get_sector_snapshots(as_of)
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    ranked = sorted(
        [(sector, score_sector(sector)) for sector in sectors],
        key=lambda item: item[1],
        reverse=True,
    )[: args.limit]
    print(format_sector_ranking(as_of, ranked))


def run_stock_scan(args: argparse.Namespace) -> None:
    config = load_config()
    as_of = parse_scan_date(args.as_of)
    selected_mode = args.mode or config.strategy["default_mode"]
    mode_config = config.strategy["modes"][selected_mode]
    cooling_off_tracker = CoolingOffTracker.from_decision_packets(config)
    provider = build_provider(args.provider, config)
    try:
        stocks = provider.get_stocks_for_sector(args.sector, as_of)
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    required_signals = mode_config["confirmation_signals_required"]
    rows = []
    for stock in stocks:
        trend_score_value = score_trend(stock)
        confirmation_score_value = score_confirmation(stock, required_signals)
        mean_reversion_pass = passes_mean_reversion(stock, config.strategy["mean_reversion"])
        reasons = stock_rejection_reasons(
            stock,
            trend_score_value,
            confirmation_score_value,
            required_signals,
            config.strategy,
        )
        cooling_reason = cooling_off_tracker.rejection_reason(stock)
        if cooling_reason:
            mean_reversion_pass = False
            reasons.insert(0, cooling_reason)
        rows.append((stock, trend_score_value, confirmation_score_value, mean_reversion_pass, reasons))

    ranked = sorted(
        rows,
        key=lambda item: (item[3] and not item[4], item[1] + item[2]),
        reverse=True,
    )[: args.limit]
    print(format_stock_scan(args.sector, as_of, ranked))


def run_journal_review(args: argparse.Namespace) -> None:
    records = load_scan_records()
    filtered = filter_scan_records(
        records,
        days=args.days,
        ticker=args.ticker,
        stage=args.stage,
    )
    summary = summarize_scan_records(filtered)
    print(format_journal_review(summary, limit=args.limit))


def run_list_packets(args: argparse.Namespace) -> None:
    paths = find_packet_files(scan_date=args.scan_date)
    summaries = [packet_summary(path) for path in paths]
    print(format_packet_list(summaries, limit=args.limit))


def run_update_outcome(args: argparse.Namespace) -> None:
    packet_path = Path(args.packet)
    packet = update_packet_outcome(
        packet_path,
        status=args.status,
        notes=args.notes,
        closed_at=args.closed_at,
        final_pl=args.final_pl,
    )
    outcome = packet.get("outcome", {})
    print(f"Updated outcome for: {packet_path}")
    print(f"Status: {outcome.get('status')}")
    print(f"Closed At: {outcome.get('closed_at')}")
    print(f"Final P/L: {outcome.get('final_pl')}")
    print(f"Notes: {outcome.get('notes')}")


def run_packet_review(args: argparse.Namespace) -> None:
    paths = find_packet_files(scan_date=args.scan_date)
    summary = summarize_packets(paths)
    print(format_packet_review(summary, limit=args.limit))


def run_daily_report(args: argparse.Namespace) -> None:
    config = load_config()
    selected_mode = args.mode or config.strategy["default_mode"]
    selected_provider = args.provider or config.broker["active_provider"]
    as_of = parse_scan_date(args.as_of)

    provider = build_provider(selected_provider, config)
    try:
        scanner = DailyScanner(
            config=config,
            provider=provider,
            cooling_off_tracker=CoolingOffTracker.from_decision_packets(config),
        )
        result = scanner.run(
            mode=selected_mode,
            as_of=as_of,
            include_all_signal_rankings=True,
        )
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    packet_paths = []
    if not args.no_log:
        append_scan_result(result)
        packet_paths = write_decision_packets(result)
        if scanner.last_signal_result is not None:
            write_signal_ranking_snapshot(scanner.last_signal_result)

    report_content = "\n".join(
        [
            "# Daily Trading Report",
            "",
            format_result(result),
            format_report_footer(result, len(packet_paths)),
        ]
    )
    report_path = write_daily_report(as_of, report_content)
    html_path = write_daily_report_html(as_of, format_daily_report_html(result, len(packet_paths)))
    print(report_content)
    print(f"\nSaved daily report to: {report_path}")
    print(f"Saved HTML email report to: {html_path}")


def run_dashboard(args: argparse.Namespace) -> None:
    path = build_dashboard()
    print(f"Built dashboard: {path}")
    if args.serve:
        serve_dashboard(path, host=args.host, port=args.port)


def run_historical_backtest(args: argparse.Namespace) -> None:
    config = load_config()
    mode = args.mode or config.strategy["default_mode"]
    start = parse_scan_date(args.start)
    end = parse_scan_date(args.end)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    scenario = get_scenario(args.scenario)
    if args.data_source == "massive":
        provider = HistoricalDataProvider.from_massive(
            config=config,
            start=start,
            end=end,
            cache_dir=cache_dir,
            calls_per_minute=args.calls_per_minute,
            vix_proxy=args.vix_proxy,
            scenario=scenario,
        )
    else:
        provider = HistoricalDataProvider.from_cache(
            config=config,
            cache_dir=cache_dir,
            vix_proxy=args.vix_proxy,
            scenario=scenario,
        )

    result = run_backtest(
        config=config,
        provider=provider,
        mode=mode,
        start=start,
        end=end,
        run_id=args.run_id,
        scenario=scenario,
        detailed_artifacts=not args.summary_only,
    )
    print(format_backtest_summary(result.summary))
    print(f"Backtest artifacts: {result.output_dir}")


def run_backtest_scenarios(args: argparse.Namespace) -> None:
    config = load_config()
    mode = args.mode or config.strategy["default_mode"]
    start = parse_scan_date(args.start)
    end = parse_scan_date(args.end)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    results = []
    for name in scenario_names(args.scenarios):
        scenario = get_scenario(name)
        if args.data_source == "massive":
            provider = HistoricalDataProvider.from_massive(
                config=config,
                start=start,
                end=end,
                cache_dir=cache_dir,
                calls_per_minute=args.calls_per_minute,
                vix_proxy=args.vix_proxy,
                scenario=scenario,
            )
        else:
            provider = HistoricalDataProvider.from_cache(
                config=config,
                cache_dir=cache_dir,
                vix_proxy=args.vix_proxy,
                scenario=scenario,
            )
        result = run_backtest(
            config=config,
            provider=provider,
            mode=mode,
            start=start,
            end=end,
            scenario=scenario,
            detailed_artifacts=not args.summary_only,
        )
        results.append(result)
    print(format_scenario_comparison(results))


def format_scenario_comparison(results) -> str:
    lines = [
        "Scenario Comparison",
        "Scenario | Scans | Trades | Sit-outs | Win Rate | Avg Win | Avg Loss | Expectancy | Max DD | Artifacts",
        "--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---",
    ]
    for result in results:
        summary = result.summary
        lines.append(
            " | ".join(
                [
                    str(summary["scenario"]),
                    str(summary["scan_count"]),
                    str(summary["trade_count"]),
                    str(summary["sit_out_count"]),
                    f"{summary['win_rate']:.1%}",
                    f"${summary['average_win']:.2f}",
                    f"${summary['average_loss']:.2f}",
                    f"${summary['expectancy']:.2f}",
                    f"${summary['max_drawdown']:.2f}",
                    result.output_dir,
                ]
            )
        )
    return "\n".join(lines)


def run_hydrate_history(args: argparse.Namespace) -> None:
    config = load_config()
    start = parse_scan_date(args.start)
    end = parse_scan_date(args.end)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()] if args.tickers else None
    summary = hydrate_massive_ohlcv(
        config=config,
        start=start,
        end=end,
        cache_dir=cache_dir,
        calls_per_minute=args.calls_per_minute,
        vix_proxy=args.vix_proxy,
        tickers=tickers,
        limit=args.limit,
    )
    print(format_hydrate_summary(summary))


def run_backtest_stock_diagnostics(args: argparse.Namespace) -> None:
    config = load_config()
    mode = args.mode or config.strategy["default_mode"]
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    provider = HistoricalDataProvider.from_cache(config=config, cache_dir=cache_dir, vix_proxy=args.vix_proxy)
    report = build_stock_diagnostics_report(
        config=config,
        provider=provider,
        mode=mode,
        as_of=parse_scan_date(args.as_of),
        limit=args.limit,
    )
    print(format_stock_diagnostics_report(report))


def run_review_trades(args: argparse.Namespace) -> None:
    trades_path = Path(args.run_dir) / "trades.jsonl"
    if not trades_path.exists():
        raise RuntimeError(f"No trades.jsonl found at {trades_path}")
    trades = [
        json.loads(line)
        for line in trades_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(format_trade_lifecycle_report(trades[: args.limit] if args.limit else trades))


def run_edge_validation(args: argparse.Namespace) -> None:
    protocol = load_validation_protocol(Path(args.protocol) if args.protocol else None)
    if args.source == "packets":
        packet_root = (
            Path(args.packet_root)
            if args.packet_root
            else Path("data") / "journal" / "decision_packets"
        )
        evidence = load_packet_evidence(packet_root)
        benchmark = None
    else:
        if not args.runs_root:
            raise RuntimeError("--runs-root is required for backtest edge validation.")
        runs_root = Path(args.runs_root)
        evidence = load_backtest_evidence(runs_root, args.scenario)
        benchmark = (
            load_backtest_evidence(runs_root, args.benchmark_scenario)
            if args.benchmark_scenario
            else None
        )
    result = evaluate_edge(
        evidence=evidence,
        scenario=args.scenario,
        evidence_kind=args.evidence_kind,
        protocol=protocol,
        benchmark_evidence=benchmark,
    )
    report = format_validation_report(result)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("backtesting") / "results" / "edge-validation" / args.scenario
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "validation.md").write_text(report, encoding="utf-8")
    (output_dir / "validation.json").write_text(
        json.dumps(result_to_dict(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(report)
    print(f"Validation artifacts: {output_dir}")


def run_ranking_validation(args: argparse.Namespace) -> None:
    config = load_config()
    protocol = load_validation_protocol(Path(args.protocol) if args.protocol else None)
    ranking_config = protocol["ranking_experiment"]
    provider = HistoricalDataProvider.from_cache(
        config=config,
        cache_dir=Path(args.cache_dir),
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("backtesting") / "results" / "ranking-experiment"
    )
    summary = run_ranking_experiment(
        config=config,
        provider=provider,
        mode=args.mode or config.strategy["default_mode"],
        start=parse_scan_date(args.start),
        end=parse_scan_date(args.end),
        top_n=int(ranking_config["top_n"]),
        horizons=[int(value) for value in ranking_config["horizons"]],
        output_dir=output_dir,
    )
    criteria = evaluate_ranking_criteria(summary, protocol)
    summary["criteria"] = criteria
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report = (output_dir / "summary.md").read_text(encoding="utf-8")
    report += (
        "\n## Predeclared Verdict\n\n"
        f"**{criteria['verdict']}** at the {criteria['primary_horizon']}-day primary horizon.\n"
    )
    (output_dir / "summary.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Verdict at {criteria['primary_horizon']} days: {criteria['verdict']}")
    print(f"Ranking artifacts: {output_dir}")


def format_trade_lifecycle_report(trades: list[dict]) -> str:
    if not trades:
        return "Trade Lifecycle Report\n- No trades recorded."
    lines = [
        "Trade Lifecycle Report",
        f"Trades: {len(trades)}",
        "",
    ]
    for trade in trades:
        lines.extend(
            [
                f"{trade['ticker']} {trade['entry_date']} -> {trade['exit_date']} ({trade.get('scenario', 'unknown')})",
                f"- Sector: {trade['sector']}",
                f"- Entry stock price: ${trade['entry_underlying_price']:.2f}",
                f"- Spread: {trade['long_call']:g}/{trade['short_call']:g}",
                f"- Debit: ${trade['debit']:.2f}",
                f"- Exit stock price: ${trade['exit_underlying_price']:.2f}",
                f"- Exit spread value: ${trade['exit_spread_value']:.2f}",
                f"- P/L: ${trade['final_pl']:.2f}",
                f"- Max favorable excursion: ${trade['max_favorable_excursion']:.2f}",
                f"- Max adverse excursion: ${trade['max_adverse_excursion']:.2f}",
                f"- Highest stock price during hold: ${trade['highest_underlying_price']:.2f}",
                f"- Lowest stock price during hold: ${trade['lowest_underlying_price']:.2f}",
                f"- Profit target touched: {'YES' if trade['profit_target_touched'] else 'NO'}",
                f"- Stop/invalidation before 14-day exit: {'YES' if trade['stop_triggered_before_exit'] else 'NO'}",
                f"- Market score entry/exit: {trade['market_score_entry']:.2f} -> {trade['market_score_exit']:.2f}",
                f"- Sector score entry/exit: {trade['sector_score_entry']:.2f} -> {trade['sector_score_exit']:.2f}",
                f"- Confirmation signals at entry: {', '.join(trade['confirmation_signals_entry']) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_hydrate_summary(summary: dict) -> str:
    lines = [
        "Historical Hydration Summary",
        f"- Requested symbols: {summary['requested']}",
        f"- Processed this run: {summary['processed']}",
        f"- Remaining after limit: {summary['remaining']}",
        f"- Already cached: {len(summary['cached'])}",
        f"- Fetched: {len(summary['fetched'])}",
        f"- Failed: {len(summary['failed'])}",
        f"- Cache: {summary['cache_dir']}",
    ]
    if summary["fetched"]:
        lines.append(f"- Fetched symbols: {', '.join(summary['fetched'])}")
    if summary["failed"]:
        lines.append("- Failures:")
        for ticker, reason in summary["failed"].items():
            lines.append(f"  - {ticker}: {reason}")
    return "\n".join(lines)


def format_backtest_summary(summary: dict) -> str:
    lines = [
        "Backtest Summary",
        f"- Scans: {summary['scan_count']}",
        f"- Trades: {summary['trade_count']}",
        f"- Sit-outs: {summary['sit_out_count']}",
        f"- Win rate: {summary['win_rate']:.1%}",
        f"- Average win: ${summary['average_win']:.2f}",
        f"- Average loss: ${summary['average_loss']:.2f}",
        f"- Expectancy: ${summary['expectancy']:.2f}",
        f"- Max drawdown: ${summary['max_drawdown']:.2f}",
        "",
        "Performance by sector:",
    ]
    lines.extend(_format_backtest_group(summary["performance_by_sector"]))
    lines.append("")
    lines.append("Performance by market regime:")
    lines.extend(_format_backtest_group(summary["performance_by_market_regime"]))
    lines.append("")
    lines.append("Performance by score bucket:")
    lines.extend(_format_backtest_group(summary["performance_by_score_bucket"]))
    return "\n".join(lines)


def _format_backtest_group(group: dict) -> list[str]:
    if not group:
        return ["- none"]
    return [
        (
            f"- {name}: trades={metrics['trades']} win_rate={metrics['win_rate']:.1%} "
            f"total_pl=${metrics['total_pl']:.2f} avg_pl=${metrics['average_pl']:.2f}"
        )
        for name, metrics in group.items()
    ]


def run_scan(args: argparse.Namespace) -> None:
    config = load_config()
    selected_mode = args.mode or config.strategy["default_mode"]
    selected_provider = args.provider or config.broker["active_provider"]
    as_of = parse_scan_date(args.as_of)

    provider = build_provider(selected_provider, config)
    try:
        scanner = DailyScanner(
            config=config,
            provider=provider,
            cooling_off_tracker=CoolingOffTracker.from_decision_packets(config),
        )
        result = scanner.run(
            mode=selected_mode,
            as_of=as_of,
            include_all_signal_rankings=True,
        )
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    print(format_result(result))
    if not args.no_log:
        path = append_scan_result(result)
        print(f"\nLogged scan result to: {path}")
        packet_paths = write_decision_packets(result)
        print(f"Logged decision packets: {len(packet_paths)}")
        if scanner.last_signal_result is not None:
            ranking_path = write_signal_ranking_snapshot(scanner.last_signal_result)
            print(f"Logged signal ranking snapshot: {ranking_path}")


def main() -> None:
    args = parse_args()
    try:
        if args.command == "diagnose":
            run_diagnostics(args)
        elif args.command == "scan-options":
            run_option_scan(args)
        elif args.command == "rank-sectors":
            run_sector_ranking(args)
        elif args.command == "scan-stocks":
            run_stock_scan(args)
        elif args.command == "review-journal":
            run_journal_review(args)
        elif args.command == "list-packets":
            run_list_packets(args)
        elif args.command == "update-outcome":
            run_update_outcome(args)
        elif args.command == "review-packets":
            run_packet_review(args)
        elif args.command == "daily-report":
            run_daily_report(args)
        elif args.command == "dashboard":
            run_dashboard(args)
        elif args.command == "backtest":
            run_historical_backtest(args)
        elif args.command == "backtest-scenarios":
            run_backtest_scenarios(args)
        elif args.command == "hydrate-history":
            run_hydrate_history(args)
        elif args.command == "backtest-stock-diagnostics":
            run_backtest_stock_diagnostics(args)
        elif args.command == "review-trades":
            run_review_trades(args)
        elif args.command == "validate-edge":
            run_edge_validation(args)
        elif args.command == "ranking-experiment":
            run_ranking_validation(args)
        else:
            run_scan(args)
    except RuntimeError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
