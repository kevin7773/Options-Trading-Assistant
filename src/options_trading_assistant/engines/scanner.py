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
from options_trading_assistant.models import (
    OptionSpread,
    RecommendationAction,
    RejectedCandidate,
    RejectionStage,
    ScanResult,
    StockSnapshot,
    TradeCandidate,
)
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
            reason = block_reason or "Market score is below the mode threshold."
            rejection = RejectedCandidate(
                stage=RejectionStage.MARKET,
                score=market_score,
                reasons=(reason,),
            )
            return ScanResult(
                action=RecommendationAction.SIT_TODAY_OUT,
                mode=mode,
                strategy_version=self.config.strategy_version,
                as_of=as_of,
                reason=reason,
                market_score=market_score,
                rejections=(rejection,),
                rejected_count=1,
            )

        sector_scores = [
            (sector, score_sector(sector))
            for sector in self.provider.get_sector_snapshots(as_of)
        ]
        ranked_sectors = sorted(sector_scores, key=lambda item: item[1], reverse=True)
        eligible_sectors = ranked_sectors[: mode_config["max_sectors"]]

        candidates: list[TradeCandidate] = []
        rejections: list[RejectedCandidate] = []
        required_confirmations = mode_config["confirmation_signals_required"]

        for sector, sector_score in ranked_sectors[mode_config["max_sectors"] :]:
            rejections.append(
                RejectedCandidate(
                    stage=RejectionStage.SECTOR,
                    sector=sector.name,
                    score=sector_score,
                    reasons=(f"Sector ranked outside top {mode_config['max_sectors']}.",),
                )
            )

        for sector, sector_score in eligible_sectors:
            for stock in self.provider.get_stocks_for_sector(sector.name, as_of):
                trend_score = score_trend(stock)
                confirmation_score = score_confirmation(stock, required_confirmations)

                stock_rejection = self._stock_rejection(
                    stock=stock,
                    trend_score=trend_score,
                    confirmation_score=confirmation_score,
                    required_confirmations=required_confirmations,
                )
                if stock_rejection:
                    rejections.append(stock_rejection)
                    continue

                spreads = self.provider.get_option_spreads(stock.ticker, as_of)
                if not spreads:
                    rejections.append(
                        RejectedCandidate(
                            stage=RejectionStage.OPTIONS,
                            ticker=stock.ticker,
                            sector=sector.name,
                            reasons=("No option spreads matched the configured expiration and width filters.",),
                        )
                    )
                    continue

                for spread in spreads:
                    options_score = score_options(spread, self.config.strategy["trade"], as_of)
                    option_reasons = self._option_rejection_reasons(spread, as_of)
                    score = build_score_breakdown(
                        market_score=market_score,
                        sector_score=sector_score,
                        trend_score=trend_score,
                        confirmation_score=confirmation_score,
                        options_score=options_score,
                    )
                    if option_reasons:
                        rejections.append(
                            self._spread_rejection(
                                stage=RejectionStage.OPTIONS,
                                stock=stock,
                                spread=spread,
                                score=options_score,
                                reasons=option_reasons,
                            )
                        )
                        continue

                    if score.total < mode_config["minimum_trade_score"]:
                        rejections.append(
                            self._spread_rejection(
                                stage=RejectionStage.SCORING,
                                stock=stock,
                                spread=spread,
                                score=score.total,
                                reasons=(f"Total score {score.total:.2f} below mode threshold {mode_config['minimum_trade_score']}.",),
                            )
                        )
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
                rejections=tuple(rejections),
                rejected_count=len(rejections),
            )

        return ScanResult(
            action=RecommendationAction.BUY,
            mode=mode,
            strategy_version=self.config.strategy_version,
            as_of=as_of,
            reason=f"{len(ranked_candidates)} setup(s) met the configured threshold.",
            market_score=market_score,
            recommendations=ranked_candidates,
            rejections=tuple(rejections),
            rejected_count=len(rejections),
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

    @staticmethod
    def _stock_rejection(
        stock: StockSnapshot,
        trend_score: float,
        confirmation_score: float,
        required_confirmations: int,
    ) -> RejectedCandidate | None:
        reasons: list[str] = []
        stage = RejectionStage.MEAN_REVERSION

        if trend_score < 14:
            stage = RejectionStage.TREND
            reasons.append(f"Trend score {trend_score:.2f}/20 below threshold 14.")
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

        if not (5.0 <= stock.drawdown_from_swing_high_pct <= 12.0):
            reasons.append("Pullback is outside the configured 5-12% controlled range.")
        if stock.rsi > 42.0:
            reasons.append("RSI is not low enough for the mean-reversion setup.")
        if not stock.near_support:
            reasons.append("Stock is not near support.")
        if not stock.selling_volume_stabilizing:
            reasons.append("Selling volume is not stabilizing.")
        if stock.company_specific_warning:
            reasons.append("Company-specific warning is present.")

        if len(stock.confirmation_signals) < required_confirmations or confirmation_score < 12:
            if stage != RejectionStage.TREND:
                stage = RejectionStage.CONFIRMATION
            reasons.append(
                f"Insufficient confirmation signals ({len(stock.confirmation_signals)}/{required_confirmations})."
            )

        if not reasons and passes_mean_reversion(stock):
            return None

        return RejectedCandidate(
            stage=stage,
            ticker=stock.ticker,
            sector=stock.sector,
            score=trend_score + confirmation_score,
            reasons=tuple(reasons),
        )

    def _option_rejection_reasons(self, spread: OptionSpread, as_of: date) -> tuple[str, ...]:
        trade_config = self.config.strategy["trade"]
        reasons: list[str] = []
        dte = (spread.expiration - as_of).days

        if spread.debit <= 0:
            reasons.append("Debit is zero or negative.")
        if spread.debit >= spread.width:
            reasons.append("Debit is at or above spread width.")
        if not (trade_config["min_days_to_expiration"] <= dte <= trade_config["max_days_to_expiration"]):
            reasons.append(
                f"Days to expiration {dte} outside configured range "
                f"{trade_config['min_days_to_expiration']}-{trade_config['max_days_to_expiration']}."
            )
        if spread.width not in trade_config["preferred_spread_widths"]:
            reasons.append(f"Spread width {spread.width:g} is not preferred.")
        if not (0.35 <= spread.long_delta <= 0.55):
            reasons.append(f"Long call delta {spread.long_delta:.3f} outside 0.35-0.55 range.")
        if spread.max_loss > trade_config["max_debit_per_spread"]:
            reasons.append(
                f"Max loss ${spread.max_loss:.0f} exceeds configured limit ${trade_config['max_debit_per_spread']}."
            )
        if spread.reward_to_risk < trade_config["min_reward_to_risk"]:
            reasons.append(
                f"Reward/risk {spread.reward_to_risk:.2f} below configured minimum "
                f"{trade_config['min_reward_to_risk']:.2f}."
            )
        if spread.long_open_interest < 500 or spread.short_open_interest < 500:
            reasons.append(
                f"Open interest {spread.long_open_interest}/{spread.short_open_interest} below preferred 500 per leg."
            )
        if spread.bid_ask_width_pct > 0.10:
            reasons.append(f"Bid/ask width {spread.bid_ask_width_pct:.2%} above preferred 10%.")
        if spread.iv_rank > 0.60:
            reasons.append(f"IV {spread.iv_rank:.2%} above preferred 60%.")

        return tuple(reasons)

    @staticmethod
    def _spread_rejection(
        stage: RejectionStage,
        stock: StockSnapshot,
        spread: OptionSpread,
        score: float,
        reasons: tuple[str, ...],
    ) -> RejectedCandidate:
        return RejectedCandidate(
            stage=stage,
            ticker=stock.ticker,
            sector=stock.sector,
            expiration=spread.expiration,
            long_call=spread.long_call,
            short_call=spread.short_call,
            score=score,
            reasons=reasons,
        )
