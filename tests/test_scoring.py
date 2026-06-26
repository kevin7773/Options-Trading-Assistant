from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scoring import market_block_reason, score_market
from options_trading_assistant.models import MarketSnapshot


def test_market_block_reason_when_spy_below_20dma():
    config = load_config()
    snapshot = MarketSnapshot(
        as_of=date(2026, 6, 26),
        spy_above_20dma=False,
        nasdaq_above_20dma=True,
        vix=18,
        vix_rising=False,
        distribution_days=0,
        breadth_score=0.8,
        growth_participation_score=0.8,
    )

    assert market_block_reason(snapshot, config.strategy["market"]) == "S&P 500 is below its 20-day moving average."


def test_score_market_caps_at_30_points():
    config = load_config()
    snapshot = MarketSnapshot(
        as_of=date(2026, 6, 26),
        spy_above_20dma=True,
        nasdaq_above_20dma=True,
        vix=18,
        vix_rising=False,
        distribution_days=0,
        breadth_score=1,
        growth_participation_score=1,
    )

    assert score_market(snapshot, config.strategy["market"]) == 30
