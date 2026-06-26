from __future__ import annotations

import argparse
from datetime import date, datetime
import sys

from options_trading_assistant.config import load_config
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
    ScanResult,
    SectorSnapshot,
    StockSnapshot,
    TradeCandidate,
)
from options_trading_assistant.providers.factory import build_provider
from options_trading_assistant.reports.journal import append_scan_result


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


def format_option_spread(spread: OptionSpread, options_score: float) -> str:
    return "\n".join(
        [
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
    )


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


def stock_rejection_reasons(stock: StockSnapshot, trend_score_value: float, confirmation_score_value: float, required_signals: int) -> list[str]:
    reasons = []
    if trend_score_value < 14:
        reasons.append("trend score below threshold")
    if not stock.above_100dma:
        reasons.append("below 100 DMA")
    if not stock.above_200dma:
        reasons.append("below 200 DMA")
    if stock.trend_90d < 0:
        reasons.append("negative 90-day trend")
    if stock.making_lower_lows:
        reasons.append("making lower lows")
    if not (5.0 <= stock.drawdown_from_swing_high_pct <= 12.0):
        reasons.append("pullback not in 5-12% controlled range")
    if stock.rsi > 42.0:
        reasons.append("RSI not low enough for mean-reversion setup")
    if not stock.near_support:
        reasons.append("not near support")
    if not stock.selling_volume_stabilizing:
        reasons.append("selling volume not stabilizing")
    if stock.company_specific_warning:
        reasons.append("company-specific warning")
    if len(stock.confirmation_signals) < required_signals or confirmation_score_value < 12:
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
        mean_reversion_pass = passes_mean_reversion(stock)
        reasons = stock_rejection_reasons(stock, trend_score_value, confirmation_score_value, required_signals)
        rows.append((stock, trend_score_value, confirmation_score_value, mean_reversion_pass, reasons))

    ranked = sorted(rows, key=lambda item: (not item[4], item[1] + item[2]), reverse=True)[: args.limit]
    print(format_stock_scan(args.sector, as_of, ranked))


def run_scan(args: argparse.Namespace) -> None:
    config = load_config()
    selected_mode = args.mode or config.strategy["default_mode"]
    selected_provider = args.provider or config.broker["active_provider"]
    as_of = parse_scan_date(args.as_of)

    provider = build_provider(selected_provider, config)
    try:
        scanner = DailyScanner(config=config, provider=provider)
        result = scanner.run(mode=selected_mode, as_of=as_of)
    finally:
        close = getattr(provider, "close", None)
        if close:
            close()

    print(format_result(result))
    if not args.no_log:
        path = append_scan_result(result)
        print(f"\nLogged scan result to: {path}")


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
        else:
            run_scan(args)
    except RuntimeError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
