from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.cooling_off import CoolingOffTracker
from options_trading_assistant.engines.scoring import (
    market_block_reason,
    passes_mean_reversion,
    score_confirmation,
    score_market,
    score_sector,
    score_trend,
)
from options_trading_assistant.models import (
    RankedSector,
    RankedStockSignal,
    RejectedCandidate,
    RejectionStage,
    ScanContext,
    SignalCandidate,
    StockSnapshot,
)
from options_trading_assistant.providers.base import DataProvider


@dataclass(frozen=True)
class SignalResult:
    mode: str
    strategy_version: str
    as_of: date
    market_score: float
    context: ScanContext
    blocked_reason: str | None = None
    signals: tuple[SignalCandidate, ...] = field(default_factory=tuple)
    rankings: tuple[RankedStockSignal, ...] = field(default_factory=tuple)
    rejections: tuple[RejectedCandidate, ...] = field(default_factory=tuple)


class SignalEngine:
    """Market, sector, stock, mean-reversion, and confirmation research layer."""

    def __init__(
        self,
        config: AppConfig,
        provider: DataProvider,
        cooling_off_tracker: CoolingOffTracker | None = None,
    ):
        self.config = config
        self.provider = provider
        self.cooling_off_tracker = cooling_off_tracker or CoolingOffTracker.from_config(config)

    def run(
        self,
        mode: str,
        as_of: date,
        include_all_sectors_in_rankings: bool = False,
    ) -> SignalResult:
        mode_config = mode_settings(self.config, mode)
        market = self.provider.get_market_snapshot(as_of)
        market_score = score_market(market, self.config.strategy["market"])
        block_reason = market_block_reason(market, self.config.strategy["market"])
        context = base_context(market)
        if block_reason or market_score < mode_config["minimum_market_score"]:
            reason = block_reason or "Market score is below the mode threshold."
            rejection = RejectedCandidate(
                stage=RejectionStage.MARKET,
                score=market_score,
                reasons=(reason,),
            )
            return SignalResult(
                mode=mode,
                strategy_version=self.config.strategy_version,
                as_of=as_of,
                market_score=market_score,
                context=context,
                blocked_reason=reason,
                rejections=(rejection,),
            )

        sector_scores = [
            (sector, score_sector(sector))
            for sector in self.provider.get_sector_snapshots(as_of)
        ]
        ranked_sectors = sorted(sector_scores, key=lambda item: item[1], reverse=True)
        context = context_with_sectors(context, ranked_sectors, mode_config["max_sectors"])
        rejections: list[RejectedCandidate] = []
        signals: list[SignalCandidate] = []
        rankings: list[RankedStockSignal] = []
        stocks_scanned = 0
        required_confirmations = mode_config["confirmation_signals_required"]

        for rank, (sector, sector_score_value) in enumerate(ranked_sectors, start=1):
            sector_eligible = rank <= mode_config["max_sectors"]
            if not sector_eligible:
                rejections.append(
                    RejectedCandidate(
                        stage=RejectionStage.SECTOR,
                        sector=sector.name,
                        score=sector_score_value,
                        reasons=(f"Sector ranked outside top {mode_config['max_sectors']}.",),
                    )
                )
                if not include_all_sectors_in_rankings:
                    continue

            for stock in self.provider.get_stocks_for_sector(sector.name, as_of):
                if sector_eligible:
                    stocks_scanned += 1
                trend_score = score_trend(stock)
                confirmation_score = score_confirmation(stock, required_confirmations)
                signal = SignalCandidate(
                    stock=stock,
                    sector=sector,
                    market_score=market_score,
                    sector_score=sector_score_value,
                    trend_score=trend_score,
                    confirmation_score=confirmation_score,
                )
                rejection = None
                cooling_reason = self.cooling_off_tracker.rejection_reason(stock)
                if cooling_reason:
                    rejection = RejectedCandidate(
                        stage=RejectionStage.COOLING_OFF,
                        ticker=stock.ticker,
                        sector=stock.sector,
                        reasons=(cooling_reason,),
                    )
                else:
                    rejection = stock_rejection(
                        stock=stock,
                        trend_score=trend_score,
                        confirmation_score=confirmation_score,
                        required_confirmations=required_confirmations,
                        strategy_config=self.config.strategy,
                    )
                qualified = sector_eligible and rejection is None
                rankings.append(
                    RankedStockSignal(
                        signal=signal,
                        sector_rank=rank,
                        sector_eligible=sector_eligible,
                        qualified=qualified,
                        rejection=rejection,
                    )
                )
                if rejection and sector_eligible:
                    rejections.append(rejection)
                elif sector_eligible:
                    signals.append(signal)

        rankings.sort(
            key=lambda row: (row.signal.ranking_score, row.signal.stock.ticker),
            reverse=True,
        )
        context = context_with_counts(context, stocks_scanned, spreads_evaluated=0)
        return SignalResult(
            mode=mode,
            strategy_version=self.config.strategy_version,
            as_of=as_of,
            market_score=market_score,
            context=context,
            signals=tuple(signals),
            rankings=tuple(rankings),
            rejections=tuple(rejections),
        )


def mode_settings(config: AppConfig, mode: str) -> dict:
    modes = config.strategy["modes"]
    if mode not in modes:
        available = ", ".join(sorted(modes))
        raise ValueError(f"Unknown mode '{mode}'. Available modes: {available}")
    return modes[mode]


def stock_rejection(
    stock: StockSnapshot,
    trend_score: float,
    confirmation_score: float,
    required_confirmations: int,
    strategy_config: dict,
) -> RejectedCandidate | None:
    reasons: list[str] = []
    stage = RejectionStage.MEAN_REVERSION
    trend_config = strategy_config["trend"]
    mean_reversion_config = strategy_config["mean_reversion"]
    confirmation_config = strategy_config["confirmation"]

    if trend_score < trend_config["minimum_score"]:
        stage = RejectionStage.TREND
        reasons.append(
            f"Trend score {trend_score:.2f}/20 below threshold {trend_config['minimum_score']}."
        )
    if not stock.above_100dma:
        stage = RejectionStage.TREND
        reasons.append("Price is below the 100-day moving average.")
    if not stock.above_200dma:
        stage = RejectionStage.TREND
        reasons.append("Price is below the 200-day moving average.")
    if stock.trend_90d < 0:
        stage = RejectionStage.TREND
        reasons.append("90-day trend is negative.")
    if stock.making_lower_lows:
        stage = RejectionStage.TREND
        reasons.append("Stock is making lower lows.")

    if not (
        mean_reversion_config["min_pullback_pct"]
        <= stock.drawdown_from_swing_high_pct
        <= mean_reversion_config["max_pullback_pct"]
    ):
        reasons.append(
            "Pullback is outside the configured "
            f"{mean_reversion_config['min_pullback_pct']:g}-{mean_reversion_config['max_pullback_pct']:g}% "
            "controlled range."
        )
    if stock.rsi > mean_reversion_config["max_rsi"]:
        reasons.append("RSI is not low enough for the mean-reversion setup.")
    if not stock.near_support:
        reasons.append("Stock is not near support.")
    if not stock.selling_volume_stabilizing:
        reasons.append("Selling volume is not stabilizing.")
    if stock.company_specific_warning:
        reasons.append("Company-specific warning is present.")

    if (
        len(stock.confirmation_signals) < required_confirmations
        or confirmation_score < confirmation_config["minimum_score"]
    ):
        if stage != RejectionStage.TREND:
            stage = RejectionStage.CONFIRMATION
        reasons.append(
            f"Insufficient confirmation signals ({len(stock.confirmation_signals)}/{required_confirmations})."
        )

    if not reasons and passes_mean_reversion(stock, mean_reversion_config):
        return None
    return RejectedCandidate(
        stage=stage,
        ticker=stock.ticker,
        sector=stock.sector,
        score=trend_score + confirmation_score,
        reasons=tuple(reasons),
    )


def base_context(market) -> ScanContext:
    return ScanContext(
        spy_above_20dma=market.spy_above_20dma,
        nasdaq_above_20dma=market.nasdaq_above_20dma,
        vix=market.vix,
        vix_rising=market.vix_rising,
        volatility_source=market.volatility_source,
        volatility_risk_off=market.volatility_risk_off,
        distribution_days=market.distribution_days,
        breadth_score=market.breadth_score,
        growth_participation_score=market.growth_participation_score,
    )


def context_with_sectors(
    context: ScanContext,
    ranked_sectors,
    max_sectors: int,
) -> ScanContext:
    return ScanContext(
        spy_above_20dma=context.spy_above_20dma,
        nasdaq_above_20dma=context.nasdaq_above_20dma,
        vix=context.vix,
        vix_rising=context.vix_rising,
        volatility_source=context.volatility_source,
        volatility_risk_off=context.volatility_risk_off,
        distribution_days=context.distribution_days,
        breadth_score=context.breadth_score,
        growth_participation_score=context.growth_participation_score,
        top_sectors=tuple(
            RankedSector(
                sector=sector.name,
                etf=sector.primary_etf,
                score=round(sector_score_value, 2),
                rank=index,
                eligible=index <= max_sectors,
            )
            for index, (sector, sector_score_value) in enumerate(ranked_sectors, start=1)
        ),
        stocks_scanned=context.stocks_scanned,
        spreads_evaluated=context.spreads_evaluated,
    )


def context_with_counts(
    context: ScanContext,
    stocks_scanned: int,
    spreads_evaluated: int,
) -> ScanContext:
    return ScanContext(
        spy_above_20dma=context.spy_above_20dma,
        nasdaq_above_20dma=context.nasdaq_above_20dma,
        vix=context.vix,
        vix_rising=context.vix_rising,
        volatility_source=context.volatility_source,
        volatility_risk_off=context.volatility_risk_off,
        distribution_days=context.distribution_days,
        breadth_score=context.breadth_score,
        growth_participation_score=context.growth_participation_score,
        top_sectors=context.top_sectors,
        stocks_scanned=stocks_scanned,
        spreads_evaluated=spreads_evaluated,
    )
