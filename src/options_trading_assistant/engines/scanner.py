from __future__ import annotations

from datetime import date

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.cooling_off import CoolingOffTracker
from options_trading_assistant.engines.signals import SignalEngine, stock_rejection
from options_trading_assistant.engines.trade_construction import TradeConstructionEngine
from options_trading_assistant.models import OptionSpread, RejectedCandidate, RejectionStage, ScanResult, StockSnapshot
from options_trading_assistant.providers.base import DataProvider


class DailyScanner:
    """Thin coordinator between signal research and trade construction."""

    def __init__(
        self,
        config: AppConfig,
        provider: DataProvider,
        cooling_off_tracker: CoolingOffTracker | None = None,
    ):
        self.config = config
        self.provider = provider
        self.signal_engine = SignalEngine(
            config=config,
            provider=provider,
            cooling_off_tracker=cooling_off_tracker,
        )
        self.trade_engine = TradeConstructionEngine(config=config, provider=provider)
        self.last_signal_result = None

    @property
    def cooling_off_tracker(self) -> CoolingOffTracker:
        return self.signal_engine.cooling_off_tracker

    def run(
        self,
        mode: str,
        as_of: date,
        include_all_signal_rankings: bool = False,
    ) -> ScanResult:
        signals = self.signal_engine.run(
            mode=mode,
            as_of=as_of,
            include_all_sectors_in_rankings=include_all_signal_rankings,
        )
        self.last_signal_result = signals
        return self.trade_engine.run(signals)

    @staticmethod
    def _stock_rejection(
        stock: StockSnapshot,
        trend_score: float,
        confirmation_score: float,
        required_confirmations: int,
        strategy_config: dict,
    ) -> RejectedCandidate | None:
        return stock_rejection(
            stock=stock,
            trend_score=trend_score,
            confirmation_score=confirmation_score,
            required_confirmations=required_confirmations,
            strategy_config=strategy_config,
        )

    def _option_rejection_reasons(self, spread: OptionSpread, as_of: date) -> tuple[str, ...]:
        return self.trade_engine.rejection_reasons(spread, as_of)

    def _option_hard_rejection_reasons(self, spread: OptionSpread, as_of: date) -> tuple[str, ...]:
        return self.trade_engine.hard_rejection_reasons(spread, as_of)

    @staticmethod
    def _spread_rejection(
        stage: RejectionStage,
        stock: StockSnapshot,
        spread: OptionSpread,
        score: float,
        reasons: tuple[str, ...],
    ) -> RejectedCandidate:
        return TradeConstructionEngine.spread_rejection(
            stage=stage,
            stock=stock,
            spread=spread,
            score=score,
            reasons=reasons,
        )
