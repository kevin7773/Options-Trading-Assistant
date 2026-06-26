from datetime import date

from options_trading_assistant.cli import format_stock_scan, stock_rejection_reasons
from options_trading_assistant.models import StockSnapshot


def test_stock_rejection_reasons_identifies_failed_filters():
    stock = StockSnapshot(
        ticker="MSFT",
        sector="Technology",
        price=370,
        above_100dma=False,
        above_200dma=True,
        trend_90d=-0.03,
        sector_relative_strength=-0.02,
        drawdown_from_swing_high_pct=3.0,
        rsi=55,
        near_support=False,
        selling_volume_stabilizing=False,
        making_lower_lows=True,
        confirmation_signals=("higher_low",),
    )

    reasons = stock_rejection_reasons(stock, trend_score_value=9, confirmation_score_value=5, required_signals=2)

    assert "trend score below threshold" in reasons
    assert "below 100 DMA" in reasons
    assert "pullback not in 5-12% controlled range" in reasons
    assert "insufficient confirmation signals (1/2)" in reasons


def test_format_stock_scan_outputs_table_and_confirmations():
    stock = StockSnapshot(
        ticker="ISRG",
        sector="Healthcare",
        price=428.25,
        above_100dma=True,
        above_200dma=True,
        trend_90d=0.12,
        sector_relative_strength=0.08,
        drawdown_from_swing_high_pct=7.2,
        rsi=39.0,
        near_support=True,
        selling_volume_stabilizing=True,
        making_lower_lows=False,
        confirmation_signals=("green_daily_candle", "higher_low"),
    )

    output = format_stock_scan(
        "Healthcare",
        date(2026, 6, 26),
        [(stock, 18.2, 17.0, True, [])],
    )

    assert "Sector: Healthcare" in output
    assert "ISRG | $428.25" in output
    assert "eligible for options scan" in output
    assert "confirmations: green_daily_candle, higher_low" in output
