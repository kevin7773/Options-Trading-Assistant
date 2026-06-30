from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.signals import SignalEngine
from options_trading_assistant.engines.trade_construction import TradeConstructionEngine
from options_trading_assistant.models import RecommendationAction
from options_trading_assistant.providers.mock import MockDataProvider


class SignalOnlyProvider(MockDataProvider):
    def get_option_spreads(self, ticker, as_of):
        raise AssertionError("Signal Engine must not request option data.")


class TradeOnlyProvider(MockDataProvider):
    def get_market_snapshot(self, as_of):
        raise AssertionError("Trade Construction Engine must not rescore the market.")

    def get_sector_snapshots(self, as_of):
        raise AssertionError("Trade Construction Engine must not rerank sectors.")

    def get_stocks_for_sector(self, sector_name, as_of):
        raise AssertionError("Trade Construction Engine must not rescan stocks.")


def test_signal_engine_does_not_touch_option_provider_boundary():
    result = SignalEngine(load_config(), SignalOnlyProvider()).run(
        mode="balanced",
        as_of=date(2026, 6, 26),
    )

    assert result.signals
    assert result.signals[0].stock.ticker == "ISRG"


def test_trade_construction_consumes_existing_signals_without_rescanning():
    config = load_config()
    signal_result = SignalEngine(config, MockDataProvider()).run(
        mode="balanced",
        as_of=date(2026, 6, 26),
    )

    result = TradeConstructionEngine(config, TradeOnlyProvider()).run(signal_result)

    assert result.action == RecommendationAction.BUY
    assert result.recommendations[0].stock.ticker == "ISRG"
