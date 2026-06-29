from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.engines.scoring import (
    market_block_reason,
    score_confirmation,
    score_market,
    score_options,
    score_sector,
    score_trend,
)
from options_trading_assistant.models import OptionSpread, RejectionStage, SectorSnapshot, StockSnapshot
from options_trading_assistant.providers.base import DataProvider


@dataclass(frozen=True)
class DiagnosticCheck:
    passed: bool
    label: str


@dataclass(frozen=True)
class StockDiagnostic:
    ticker: str
    sector: str
    score: float
    status: str
    stage: str
    checks: tuple[DiagnosticCheck, ...]
    reasons: tuple[str, ...]
    option_spreads: tuple[OptionSpread, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StockDiagnosticsReport:
    as_of: date
    mode: str
    market_passed: bool
    market_score: float
    market_reason: str | None
    diagnostics: tuple[StockDiagnostic, ...]


def build_stock_diagnostics_report(
    config: AppConfig,
    provider: DataProvider,
    mode: str,
    as_of: date,
    limit: int = 25,
) -> StockDiagnosticsReport:
    mode_config = config.strategy["modes"][mode]
    scanner = DailyScanner(config=config, provider=provider)
    market = provider.get_market_snapshot(as_of)
    market_score = score_market(market, config.strategy["market"])
    block_reason = market_block_reason(market, config.strategy["market"])
    market_passed = block_reason is None and market_score >= mode_config["minimum_market_score"]

    sector_scores = [(sector, score_sector(sector)) for sector in provider.get_sector_snapshots(as_of)]
    ranked_sectors = sorted(sector_scores, key=lambda item: item[1], reverse=True)
    eligible_sector_names = {
        sector.name
        for sector, _score in ranked_sectors[: mode_config["max_sectors"]]
    }

    diagnostics: list[StockDiagnostic] = []
    required_confirmations = mode_config["confirmation_signals_required"]
    for sector, sector_score_value in ranked_sectors:
        for stock in provider.get_stocks_for_sector(sector.name, as_of):
            trend_score = score_trend(stock)
            confirmation_score = score_confirmation(stock, required_confirmations)
            setup_score = round(market_score + sector_score_value + trend_score + confirmation_score, 2)
            stock_rejection = scanner._stock_rejection(  # noqa: SLF001 - this diagnostic mirrors scanner gates.
                stock=stock,
                trend_score=trend_score,
                confirmation_score=confirmation_score,
                required_confirmations=required_confirmations,
                strategy_config=config.strategy,
            )
            checks = list(_stock_checks(stock, trend_score, confirmation_score, required_confirmations, config))
            reasons: list[str] = []
            stage = "stock"
            status = "Rejected"
            option_spreads: tuple[OptionSpread, ...] = ()

            if sector.name not in eligible_sector_names:
                reasons.append(f"Sector ranked outside top {mode_config['max_sectors']}.")
                checks.insert(0, DiagnosticCheck(False, f"Sector eligible: {sector.name}"))
                stage = RejectionStage.SECTOR.value
            else:
                checks.insert(0, DiagnosticCheck(True, f"Sector eligible: {sector.name}"))

            if stock_rejection:
                reasons.extend(stock_rejection.reasons)
                stage = stock_rejection.stage.value
            elif sector.name in eligible_sector_names:
                option_spreads = provider.get_option_spreads(stock.ticker, as_of)
                option_failures = _option_failures(scanner, option_spreads, as_of)
                if option_failures:
                    reasons.extend(option_failures)
                    stage = RejectionStage.OPTIONS.value
                elif option_spreads:
                    status = "Eligible"
                    stage = "passed"
                    checks.append(DiagnosticCheck(True, "Options structure passed configured filters"))
                else:
                    reasons.append("No option spreads matched the configured expiration and width filters.")
                    stage = RejectionStage.OPTIONS.value

            diagnostics.append(
                StockDiagnostic(
                    ticker=stock.ticker,
                    sector=stock.sector,
                    score=setup_score,
                    status=status,
                    stage=stage,
                    checks=tuple(checks),
                    reasons=tuple(dict.fromkeys(reasons)),
                    option_spreads=option_spreads,
                )
            )

    ranked = sorted(diagnostics, key=lambda item: item.score, reverse=True)[:limit]
    return StockDiagnosticsReport(
        as_of=as_of,
        mode=mode,
        market_passed=market_passed,
        market_score=market_score,
        market_reason=block_reason,
        diagnostics=tuple(ranked),
    )


def format_stock_diagnostics_report(report: StockDiagnosticsReport) -> str:
    lines = [
        f"Date: {report.as_of.isoformat()}",
        f"Mode: {report.mode}",
        f"Market passed: {'YES' if report.market_passed else 'NO'}",
        f"Market score: {report.market_score:.2f}/30",
    ]
    if report.market_reason:
        lines.append(f"Market reason: {report.market_reason}")

    lines.extend(["", f"Top {len(report.diagnostics)} stocks ranked:"])
    for item in report.diagnostics:
        lines.append(f"{item.ticker.ljust(8, '.')} {item.score:.2f}  {item.status} ({item.stage})")

    lines.append("")
    for item in report.diagnostics:
        lines.append(item.ticker)
        for check in item.checks:
            prefix = "[pass]" if check.passed else "[fail]"
            lines.append(f"{prefix} {check.label}")
        if item.reasons:
            lines.append("Reasons:")
            for reason in item.reasons:
                lines.append(f"- {reason}")
        lines.append(item.status)
        lines.append("")
    return "\n".join(lines).rstrip()


def _stock_checks(
    stock: StockSnapshot,
    trend_score: float,
    confirmation_score: float,
    required_confirmations: int,
    config: AppConfig,
) -> tuple[DiagnosticCheck, ...]:
    trend_config = config.strategy["trend"]
    mean_reversion = config.strategy["mean_reversion"]
    confirmation = config.strategy["confirmation"]
    pullback_ok = (
        mean_reversion["min_pullback_pct"]
        <= stock.drawdown_from_swing_high_pct
        <= mean_reversion["max_pullback_pct"]
    )
    return (
        DiagnosticCheck(trend_score >= trend_config["minimum_score"], f"Trend score {trend_score:.2f}/20"),
        DiagnosticCheck(stock.above_100dma, "Above 100 DMA"),
        DiagnosticCheck(stock.above_200dma, "Above 200 DMA"),
        DiagnosticCheck(stock.trend_90d >= 0, f"90-day trend {stock.trend_90d:.2f}%"),
        DiagnosticCheck(stock.sector_relative_strength >= 0, f"Sector relative strength {stock.sector_relative_strength:.2f}"),
        DiagnosticCheck(pullback_ok, f"Pullback {stock.drawdown_from_swing_high_pct:.1f}%"),
        DiagnosticCheck(stock.rsi <= mean_reversion["max_rsi"], f"RSI {stock.rsi:.1f}"),
        DiagnosticCheck(stock.near_support, "Near support"),
        DiagnosticCheck(stock.selling_volume_stabilizing, "Selling volume stabilizing"),
        DiagnosticCheck(not stock.making_lower_lows, "Not making lower lows"),
        DiagnosticCheck(
            len(stock.confirmation_signals) >= required_confirmations
            and confirmation_score >= confirmation["minimum_score"],
            f"Confirmation {len(stock.confirmation_signals)}/{required_confirmations}",
        ),
    )


def _option_failures(scanner: DailyScanner, spreads: tuple[OptionSpread, ...], as_of: date) -> list[str]:
    failures: list[str] = []
    for spread in spreads:
        reasons = scanner._option_rejection_reasons(spread, as_of)  # noqa: SLF001
        if score_options(spread, scanner.config.strategy["trade"], as_of) <= 0 and reasons:
            failures.extend(f"{spread.long_call:g}/{spread.short_call:g}: {reason}" for reason in reasons)
    return failures
