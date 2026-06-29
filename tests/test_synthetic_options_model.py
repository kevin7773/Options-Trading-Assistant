from datetime import date, timedelta

from options_trading_assistant.backtesting.models import OHLCVBar
from options_trading_assistant.backtesting.synthetic_options_model import estimate_bull_call_spread_debit
from options_trading_assistant.config import load_config
from options_trading_assistant.providers.historical import HistoricalDataProvider


def test_synthetic_debit_model_allows_high_quality_mean_reversion_pricing():
    estimate = estimate_bull_call_spread_debit(
        underlying_price=100,
        long_strike=101,
        short_strike=106,
        dte=28,
        iv_proxy=0.30,
        expected_move_pct=3.0,
    )

    assert 0.35 <= estimate.debit_pct_of_width <= 0.40
    assert estimate.estimated_reward_risk >= 1.5
    assert estimate.pricing_reason


def test_historical_provider_uses_synthetic_debit_model():
    start = date(2024, 1, 1)
    bars = [
        OHLCVBar("MSFT", start + timedelta(days=index), 100, 102, 99, 100 + (index * 0.05), 1_000_000)
        for index in range(260)
    ]
    provider = HistoricalDataProvider(load_config(), {"MSFT": bars})

    spread = provider.get_option_spreads("MSFT", bars[-1].date)[0]

    assert spread.estimated_debit == spread.debit
    assert spread.debit_pct_of_width is not None
    assert spread.expected_move is not None
    assert spread.distance_to_long_strike is not None
    assert spread.distance_to_short_strike is not None
    assert spread.estimated_reward_risk == round(spread.reward_to_risk, 2)
    assert spread.pricing_reason
