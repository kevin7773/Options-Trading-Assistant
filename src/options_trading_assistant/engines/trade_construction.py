from __future__ import annotations

from datetime import date

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.scoring import (
    build_score_breakdown,
    grade_for_score,
    score_options,
)
from options_trading_assistant.engines.signals import SignalResult, context_with_counts, mode_settings
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


class TradeConstructionEngine:
    """Expiration, strike, width, debit, liquidity, and risk research layer."""

    def __init__(self, config: AppConfig, provider: DataProvider):
        self.config = config
        self.provider = provider

    def run(self, signal_result: SignalResult) -> ScanResult:
        if signal_result.blocked_reason:
            return ScanResult(
                action=RecommendationAction.SIT_TODAY_OUT,
                mode=signal_result.mode,
                strategy_version=signal_result.strategy_version,
                as_of=signal_result.as_of,
                reason=signal_result.blocked_reason,
                market_score=signal_result.market_score,
                context=signal_result.context,
                rejections=signal_result.rejections,
                rejected_count=len(signal_result.rejections),
            )

        mode_config = mode_settings(self.config, signal_result.mode)
        candidates: list[TradeCandidate] = []
        rejections = list(signal_result.rejections)
        spreads_evaluated = 0

        for signal in signal_result.signals:
            stock = signal.stock
            spreads = self.provider.get_option_spreads(stock.ticker, signal_result.as_of)
            spreads_evaluated += len(spreads)
            if not spreads:
                rejections.append(
                    RejectedCandidate(
                        stage=RejectionStage.OPTIONS,
                        ticker=stock.ticker,
                        sector=signal.sector.name,
                        reasons=("No option spreads matched the configured expiration and width filters.",),
                    )
                )
                continue

            for spread in spreads:
                options_score = score_options(
                    spread,
                    self.config.strategy["trade"],
                    signal_result.as_of,
                )
                score = build_score_breakdown(
                    market_score=signal.market_score,
                    sector_score=signal.sector_score,
                    trend_score=signal.trend_score,
                    confirmation_score=signal.confirmation_score,
                    options_score=options_score,
                    scoring_config=self.config.scoring,
                )
                if self.hard_rejection_reasons(spread, signal_result.as_of):
                    rejections.append(
                        self.spread_rejection(
                            stage=RejectionStage.OPTIONS,
                            stock=stock,
                            spread=spread,
                            score=options_score,
                            reasons=self.rejection_reasons(spread, signal_result.as_of),
                        )
                    )
                    continue
                if score.total < mode_config["minimum_trade_score"]:
                    rejections.append(
                        self.spread_rejection(
                            stage=RejectionStage.SCORING,
                            stock=stock,
                            spread=spread,
                            score=score.total,
                            reasons=(
                                f"Total score {score.total:.2f} below mode threshold "
                                f"{mode_config['minimum_trade_score']}.",
                            ),
                        )
                    )
                    continue
                candidates.append(
                    TradeCandidate(
                        stock=stock,
                        sector=signal.sector,
                        spread=spread,
                        score=score,
                        grade=grade_for_score(
                            score.total,
                            thresholds=self.config.scoring.get("thresholds"),
                        ),
                        rationale=self.rationale(stock, signal.sector.name),
                        risks=self.risks(spread),
                    )
                )

        ranked_candidates = tuple(
            sorted(candidates, key=lambda candidate: candidate.score.total, reverse=True)[
                : mode_config["max_recommendations"]
            ]
        )
        context = context_with_counts(
            signal_result.context,
            stocks_scanned=signal_result.context.stocks_scanned,
            spreads_evaluated=spreads_evaluated,
        )
        if not ranked_candidates:
            return ScanResult(
                action=RecommendationAction.SIT_TODAY_OUT,
                mode=signal_result.mode,
                strategy_version=signal_result.strategy_version,
                as_of=signal_result.as_of,
                reason="No setups met the minimum quality threshold.",
                market_score=signal_result.market_score,
                context=context,
                rejections=tuple(rejections),
                rejected_count=len(rejections),
            )
        return ScanResult(
            action=RecommendationAction.BUY,
            mode=signal_result.mode,
            strategy_version=signal_result.strategy_version,
            as_of=signal_result.as_of,
            reason=f"{len(ranked_candidates)} setup(s) met the configured threshold.",
            market_score=signal_result.market_score,
            context=context,
            recommendations=ranked_candidates,
            rejections=tuple(rejections),
            rejected_count=len(rejections),
        )

    def rejection_reasons(self, spread: OptionSpread, as_of: date) -> tuple[str, ...]:
        trade_config = self.config.strategy["trade"]
        reasons = list(self.hard_rejection_reasons(spread, as_of))
        dte = (spread.expiration - as_of).days
        if not (trade_config["min_days_to_expiration"] <= dte <= trade_config["max_days_to_expiration"]):
            reasons.append(
                f"Days to expiration {dte} outside configured range "
                f"{trade_config['min_days_to_expiration']}-{trade_config['max_days_to_expiration']}."
            )
        if spread.width not in trade_config["preferred_spread_widths"]:
            reasons.append(f"Spread width {spread.width:g} is not preferred.")
        if not (trade_config["min_long_delta"] <= spread.long_delta <= trade_config["max_long_delta"]):
            reasons.append(
                f"Long call delta {spread.long_delta:.3f} outside "
                f"{trade_config['min_long_delta']:.2f}-{trade_config['max_long_delta']:.2f} range."
            )
        if (
            spread.long_open_interest < trade_config["min_open_interest"]
            or spread.short_open_interest < trade_config["min_open_interest"]
        ):
            reasons.append(
                f"Open interest {spread.long_open_interest}/{spread.short_open_interest} below preferred "
                f"{trade_config['min_open_interest']} per leg."
            )
        if spread.bid_ask_width_pct > trade_config["max_bid_ask_width_pct"]:
            reasons.append(
                f"Bid/ask width {spread.bid_ask_width_pct:.2%} above preferred "
                f"{trade_config['max_bid_ask_width_pct']:.0%}."
            )
        if spread.iv_rank > trade_config["max_iv_rank"]:
            reasons.append(f"IV {spread.iv_rank:.2%} above preferred {trade_config['max_iv_rank']:.0%}.")
        return tuple(reasons)

    def hard_rejection_reasons(self, spread: OptionSpread, as_of: date) -> tuple[str, ...]:
        trade_config = self.config.strategy["trade"]
        reasons: list[str] = []
        if spread.debit <= 0:
            reasons.append("Debit is zero or negative.")
        if spread.debit >= spread.width:
            reasons.append("Debit is at or above spread width.")
        debit_pct = spread.debit / spread.width if spread.width else 0.0
        min_debit_pct = trade_config.get("min_debit_pct_of_width")
        max_debit_pct = trade_config.get("max_debit_pct_of_width")
        if min_debit_pct is not None and debit_pct < min_debit_pct:
            reasons.append(f"Debit {debit_pct:.2%} below scenario minimum {min_debit_pct:.0%}.")
        if max_debit_pct is not None and debit_pct > max_debit_pct:
            reasons.append(f"Debit {debit_pct:.2%} above scenario maximum {max_debit_pct:.0%}.")
        if spread.max_loss > trade_config["max_debit_per_spread"]:
            reasons.append(
                f"Max loss ${spread.max_loss:.0f} exceeds configured limit ${trade_config['max_debit_per_spread']}."
            )
        if spread.reward_to_risk < trade_config["min_reward_to_risk"]:
            reasons.append(
                f"Reward/risk {spread.reward_to_risk:.2f} below configured minimum "
                f"{trade_config['min_reward_to_risk']:.2f}."
            )
        return tuple(reasons)

    @staticmethod
    def spread_rejection(
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

    @staticmethod
    def rationale(stock: StockSnapshot, sector_name: str) -> tuple[str, ...]:
        return (
            f"{sector_name} is ranked as an eligible leading sector.",
            f"{stock.ticker} remains above its 100-day and 200-day moving averages.",
            f"{stock.ticker} pulled back {stock.drawdown_from_swing_high_pct:.1f}% into support.",
            f"Confirmation signals: {', '.join(stock.confirmation_signals)}.",
        )

    def risks(self, spread: OptionSpread) -> tuple[str, ...]:
        risks = []
        if spread.iv_rank > self.config.strategy["trade"]["max_iv_rank"]:
            risks.append("Implied volatility is elevated versus the preferred range.")
        if spread.bid_ask_width_pct > 0.08:
            risks.append("Bid/ask width requires patient limit-order execution.")
        if not risks:
            risks.append("Market or sector reversal would invalidate the bullish setup.")
        return tuple(risks)
