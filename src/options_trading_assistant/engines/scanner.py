from __future__ import annotations

from datetime import date

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.scoring import (
    build_score_breakdown,
    grade_for_score,
    market_block_reason,
    passes_mean_reversion,
    score_confirmation,
    score_market,
    score_options,
    score_sector,
    score_trend,
)
from options_trading_assistant.models import RecommendationAction, ScanResult, TradeCandidate
from options_trading_assistant.providers.base import DataProvider


class DailyScanner:
    def __init__(self, config: AppConfig, provider: DataProvider):
        self.config = config
        self.provider = provider

    def run(self, mode: str, as_of: date) -> ScanResult:
        mode_config = self._mode_config(mode)
        market = self.provider.get_market_snapshot(as_of)
        market_score = score_market(market, self.config.strategy["market"])
        block_reason = market_block_reason(market, self.config.strategy["market"])

        if block_reason or market_score < mode_config["minimum_market_score"]:
            return ScanResult(
                action=RecommendationAction.SIT_TODAY_OUT,
                mode=mode,
                strategy_version=self.config.strategy_version,
                as_of=as_of,
                reason=block_reason or "Market score is below the mode threshold.",
                market_score=market_score,
            )

        sector_scores = [
            (sector, score_sector(sector))
            for sector in self.provider.get_sector_snapshots(as_of)
        ]
        ranked_sectors = sorted(sector_scores, key=lambda item: item[1], reverse=True)
        eligible_sectors = ranked_sectors[: mode_config["max_sectors"]]

        candidates: list[TradeCandidate] = []
        rejected_count = 0
        required_confirmations = mode_config["confirmation_signals_required"]

        for sector, sector_score in eligible_sectors:
            for stock in self.provider.get_stocks_for_sector(sector.name, as_of):
                trend_score = score_trend(stock)
                confirmation_score = score_confirmation(stock, required_confirmations)

                if trend_score < 14 or confirmation_score < 12 or not passes_mean_reversion(stock):
                    rejected_count += 1
                    continue

                spreads = self.provider.get_option_spreads(stock.ticker, as_of)
                for spread in spreads:
                    options_score = score_options(spread, self.config.strategy["trade"], as_of)
                    score = build_score_breakdown(
                        market_score=market_score,
                        sector_score=sector_score,
                        trend_score=trend_score,
                        confirmation_score=confirmation_score,
                        options_score=options_score,
                    )
                    if score.total < mode_config["minimum_trade_score"]:
                        rejected_count += 1
                        continue

                    candidates.append(
                        TradeCandidate(
                            stock=stock,
                            sector=sector,
                            spread=spread,
                            score=score,
                            grade=grade_for_score(score.total),
                            rationale=self._rationale(stock, sector.name),
                            risks=self._risks(spread),
                        )
                    )

        ranked_candidates = tuple(
            sorted(candidates, key=lambda candidate: candidate.score.total, reverse=True)[
                : mode_config["max_recommendations"]
            ]
        )

        if not ranked_candidates:
            return ScanResult(
                action=RecommendationAction.SIT_TODAY_OUT,
                mode=mode,
                strategy_version=self.config.strategy_version,
                as_of=as_of,
                reason="No setups met the minimum quality threshold.",
                market_score=market_score,
                rejected_count=rejected_count,
            )

        return ScanResult(
            action=RecommendationAction.BUY,
            mode=mode,
            strategy_version=self.config.strategy_version,
            as_of=as_of,
            reason=f"{len(ranked_candidates)} setup(s) met the configured threshold.",
            market_score=market_score,
            recommendations=ranked_candidates,
            rejected_count=rejected_count,
        )

    def _mode_config(self, mode: str) -> dict:
        modes = self.config.strategy["modes"]
        if mode not in modes:
            available = ", ".join(sorted(modes))
            raise ValueError(f"Unknown mode '{mode}'. Available modes: {available}")
        return modes[mode]

    @staticmethod
    def _rationale(stock, sector_name: str) -> tuple[str, ...]:
        return (
            f"{sector_name} is ranked as an eligible leading sector.",
            f"{stock.ticker} remains above its 100-day and 200-day moving averages.",
            f"{stock.ticker} pulled back {stock.drawdown_from_swing_high_pct:.1f}% into support.",
            f"Confirmation signals: {', '.join(stock.confirmation_signals)}.",
        )

    @staticmethod
    def _risks(spread) -> tuple[str, ...]:
        risks = []
        if spread.iv_rank > 0.55:
            risks.append("Implied volatility is elevated versus the preferred range.")
        if spread.bid_ask_width_pct > 0.08:
            risks.append("Bid/ask width requires patient limit-order execution.")
        if not risks:
            risks.append("Market or sector reversal would invalidate the bullish setup.")
        return tuple(risks)
