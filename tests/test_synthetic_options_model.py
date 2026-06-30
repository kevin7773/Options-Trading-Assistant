from datetime import date, datetime, timedelta, timezone

from options_trading_assistant.backtesting.models import OHLCVBar
from options_trading_assistant.backtesting.synthetic_options_model import estimate_bull_call_spread_debit
from options_trading_assistant.config import AppConfig, load_config
from options_trading_assistant.providers.historical import HistoricalDataProvider, MassiveHistoricalClient


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


def test_synthetic_debit_decreases_as_long_strike_moves_farther_otm():
    at_the_money = estimate_bull_call_spread_debit(
        underlying_price=100,
        long_strike=100,
        short_strike=105,
        dte=28,
        iv_proxy=0.30,
        expected_move_pct=3.0,
    )
    out_of_the_money = estimate_bull_call_spread_debit(
        underlying_price=100,
        long_strike=102,
        short_strike=107,
        dte=28,
        iv_proxy=0.30,
        expected_move_pct=3.0,
    )

    assert out_of_the_money.estimated_debit < at_the_money.estimated_debit


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


def test_historical_confirmation_uses_current_open_for_green_candle():
    base_config = load_config()
    config = AppConfig(
        strategy=base_config.strategy,
        scoring=base_config.scoring,
        universe={
            "sectors": {
                "Technology": {
                    "etfs": ["XLK"],
                    "tickers": ["MSFT"],
                }
            }
        },
        broker=base_config.broker,
    )
    start = date(2026, 1, 1)
    stock_bars = [
        OHLCVBar("MSFT", start + timedelta(days=index), 100, 101, 99, 100, 1_000_000)
        for index in range(30)
    ]
    stock_bars[-1] = OHLCVBar(
        "MSFT",
        stock_bars[-1].date,
        102,
        103,
        100,
        101,
        1_000_000,
    )
    sector_bars = [
        OHLCVBar("XLK", start + timedelta(days=index), 100, 101, 99, 100, 1_000_000)
        for index in range(30)
    ]
    provider = HistoricalDataProvider(config, {"MSFT": stock_bars, "XLK": sector_bars})

    snapshot = provider.get_stocks_for_sector("Technology", stock_bars[-1].date)[0]

    assert "green_daily_candle" not in snapshot.confirmation_signals


def test_historical_stock_returns_use_decimal_units():
    base_config = load_config()
    config = AppConfig(
        strategy=base_config.strategy,
        scoring=base_config.scoring,
        universe={
            "sectors": {
                "Technology": {
                    "etfs": ["XLK"],
                    "tickers": ["MSFT"],
                }
            }
        },
        broker=base_config.broker,
    )
    start = date(2025, 1, 1)
    stock_bars = [
        OHLCVBar("MSFT", start + timedelta(days=index), 100, 101, 99, 100 + index, 1_000_000)
        for index in range(220)
    ]
    sector_bars = [
        OHLCVBar("XLK", start + timedelta(days=index), 100, 101, 99, 100 + index * 0.5, 1_000_000)
        for index in range(220)
    ]
    provider = HistoricalDataProvider(config, {"MSFT": stock_bars, "XLK": sector_bars})

    snapshot = provider.get_stocks_for_sector("Technology", stock_bars[-1].date)[0]

    assert 0 < snapshot.trend_90d < 1
    assert 0 < snapshot.sector_relative_strength < 1


def test_massive_daily_timestamp_is_converted_in_utc(tmp_path):
    client = MassiveHistoricalClient("test-key", tmp_path, calls_per_minute=1000)
    timestamp = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
    client._get_json = lambda _url: {
        "results": [
            {
                "t": timestamp,
                "o": 100,
                "h": 101,
                "l": 99,
                "c": 100,
                "v": 1_000_000,
            }
        ]
    }

    bars = client.fetch_stock_bars("MSFT", date(2026, 1, 1), date(2026, 1, 3))

    assert bars[0].date == date(2026, 1, 2)
