from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import MarketSnapshot, RecommendationAction
from options_trading_assistant.providers.mock import MockDataProvider


def test_balanced_scan_returns_recommendation_with_mock_data():
    scanner = DailyScanner(config=load_config(), provider=MockDataProvider())

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    assert result.action == RecommendationAction.BUY
    assert result.recommendations
    assert result.recommendations[0].stock.ticker == "ISRG"


class HostileMarketProvider(MockDataProvider):
    def get_market_snapshot(self, as_of):
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=False,
            nasdaq_above_20dma=False,
            vix=26,
            vix_rising=True,
            distribution_days=3,
            breadth_score=0.2,
            growth_participation_score=0.2,
        )


def test_market_gate_returns_sit_today_out():
    scanner = DailyScanner(config=load_config(), provider=HostileMarketProvider())

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    assert result.action == RecommendationAction.SIT_TODAY_OUT
    assert "S&P 500" in result.reason
    assert not result.recommendations
