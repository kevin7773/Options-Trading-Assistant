from dataclasses import replace
from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import MarketSnapshot, RecommendationAction, RejectionStage
from options_trading_assistant.providers.mock import MockDataProvider


def test_balanced_scan_returns_recommendation_with_mock_data():
    scanner = DailyScanner(config=load_config(), provider=MockDataProvider())

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    assert result.action == RecommendationAction.BUY
    assert result.recommendations
    assert result.recommendations[0].stock.ticker == "ISRG"
    assert result.context.stocks_scanned > 0
    assert result.context.spreads_evaluated > 0
    assert result.context.top_sectors
    assert result.rejections
    assert result.rejected_count == len(result.rejections)
    assert any(rejection.stage == RejectionStage.OPTIONS for rejection in result.rejections)


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
    assert result.rejections
    assert result.rejections[0].stage == RejectionStage.MARKET
    assert result.context.spy_above_20dma is False
    assert result.context.stocks_scanned == 0
    assert result.rejected_count == 1


def test_scanner_collects_stock_rejection_reasons():
    scanner = DailyScanner(config=load_config(), provider=MockDataProvider())

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    stock_rejections = [
        rejection for rejection in result.rejections
        if rejection.stage in {RejectionStage.TREND, RejectionStage.MEAN_REVERSION, RejectionStage.CONFIRMATION}
    ]
    assert stock_rejections
    assert any(rejection.ticker == "UNH" for rejection in stock_rejections)
    assert all(rejection.reasons for rejection in stock_rejections)


class SoftOptionPreferenceProvider(MockDataProvider):
    def get_option_spreads(self, ticker, as_of):
        spreads = super().get_option_spreads(ticker, as_of)
        if ticker != "ISRG":
            return spreads
        return (
            replace(
                spreads[0],
                long_open_interest=10,
                short_open_interest=10,
                bid_ask_width_pct=0.12,
            ),
        )


def test_soft_option_preferences_reduce_score_without_forcing_rejection():
    scanner = DailyScanner(config=load_config(), provider=SoftOptionPreferenceProvider())

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    assert result.action == RecommendationAction.BUY
    assert result.recommendations[0].stock.ticker == "ISRG"
