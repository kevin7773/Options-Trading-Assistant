from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.distribution_days import evaluate_distribution_days_from_rows, rule_from_market_config
from options_trading_assistant.engines.scoring import (
    build_score_breakdown,
    grade_for_score,
    market_block_reason,
    passes_mean_reversion,
    score_market,
    score_options,
)
from options_trading_assistant.models import MarketSnapshot, OptionSpread, StockSnapshot


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


def test_market_block_reason_honors_volatility_proxy_risk_off():
    config = load_config()
    snapshot = MarketSnapshot(
        as_of=date(2026, 6, 26),
        spy_above_20dma=True,
        nasdaq_above_20dma=True,
        vix=0,
        vix_rising=True,
        distribution_days=0,
        breadth_score=0.8,
        growth_participation_score=0.8,
        volatility_source="VIXY",
        volatility_risk_off=True,
    )

    reason = market_block_reason(snapshot, config.strategy["market"])

    assert reason == "VIXY volatility proxy is signaling risk-off conditions."


def test_distribution_day_rule_current_2_in_10_triggers_on_two_nonconsecutive_days():
    rule = rule_from_market_config(load_config().strategy["market"])
    rows = [
        {"date": date(2026, 6, 20), "close": 100, "volume": 100},
        {"date": date(2026, 6, 21), "close": 99, "volume": 120},
        {"date": date(2026, 6, 22), "close": 101, "volume": 110},
        {"date": date(2026, 6, 23), "close": 100, "volume": 130},
    ]

    state = evaluate_distribution_days_from_rows(
        rows,
        close_names=["close"],
        volume_names=["volume"],
        date_names=["date"],
        rule=rule,
    )

    assert state.count_in_window == 2
    assert state.triggered is True


def test_distribution_day_rule_consecutive_only_requires_adjacent_flags():
    rule = {
        "lookback_bars": 10,
        "max_count_in_window": 2,
        "require_consecutive": True,
        "min_drop_pct": 0.2,
    }
    rows = [
        {"date": date(2026, 6, 20), "close": 100, "volume": 100},
        {"date": date(2026, 6, 21), "close": 99, "volume": 120},
        {"date": date(2026, 6, 22), "close": 101, "volume": 110},
        {"date": date(2026, 6, 23), "close": 100, "volume": 130},
    ]

    state = evaluate_distribution_days_from_rows(
        rows,
        close_names=["close"],
        volume_names=["volume"],
        date_names=["date"],
        rule=rule_from_market_config({"distribution_days": rule, "max_distribution_days": 2}),
    )

    assert state.count_in_window == 2
    assert state.triggered is False


def test_score_options_zeroes_spread_with_poor_reward_to_risk():
    config = load_config()
    spread = OptionSpread(
        ticker="MSFT",
        expiration=date(2026, 7, 24),
        long_call=380,
        short_call=385,
        debit=3.85,
        long_delta=0.456,
        short_delta=0.404,
        long_open_interest=801,
        short_open_interest=786,
        bid_ask_width_pct=0.1881,
        volume_score=0.83,
        iv_rank=0.3574,
        expected_move_pct=0,
    )

    assert score_options(spread, config.strategy["trade"], date(2026, 6, 26)) == 0


def test_score_options_accepts_valid_priced_spread():
    config = load_config()
    spread = OptionSpread(
        ticker="MSFT",
        expiration=date(2026, 7, 24),
        long_call=385,
        short_call=390,
        debit=1.85,
        long_delta=0.42,
        short_delta=0.31,
        long_open_interest=900,
        short_open_interest=1200,
        bid_ask_width_pct=0.05,
        volume_score=0.8,
        iv_rank=0.35,
        expected_move_pct=0,
    )

    assert score_options(spread, config.strategy["trade"], date(2026, 6, 26)) > 0


def test_passes_mean_reversion_uses_configured_pullback_and_rsi_thresholds():
    stock = StockSnapshot(
        ticker="TEST",
        sector="Technology",
        price=100,
        above_100dma=True,
        above_200dma=True,
        trend_90d=0.1,
        sector_relative_strength=0.1,
        drawdown_from_swing_high_pct=4.5,
        rsi=43,
        near_support=True,
        selling_volume_stabilizing=True,
        making_lower_lows=False,
    )

    strict_config = {"min_pullback_pct": 5.0, "max_pullback_pct": 12.0, "max_rsi": 42.0}
    loose_config = {"min_pullback_pct": 4.0, "max_pullback_pct": 12.0, "max_rsi": 45.0}

    assert passes_mean_reversion(stock, strict_config) is False
    assert passes_mean_reversion(stock, loose_config) is True


def test_score_breakdown_applies_configured_weights_and_grade_thresholds():
    score = build_score_breakdown(
        market_score=30,
        sector_score=15,
        trend_score=20,
        confirmation_score=20,
        options_score=15,
        scoring_config={
            "weights": {
                "market": 1,
                "sector": 0,
                "trend": 0,
                "confirmation": 0,
                "options": 0,
            }
        },
    )

    assert score.market == 100
    assert score.sector == 0
    assert score.total == 100
    assert grade_for_score(88, {"strong_buy": 85, "buy": 75, "watchlist": 65}) == "A"
