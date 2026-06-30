from datetime import date
from types import SimpleNamespace

from options_trading_assistant.cli import format_stock_scan, run_stock_scan, stock_rejection_reasons
from options_trading_assistant.config import load_config
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

    reasons = stock_rejection_reasons(
        stock,
        trend_score_value=9,
        confirmation_score_value=5,
        required_signals=2,
        strategy_config=load_config().strategy,
    )

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


def test_run_stock_scan_lists_eligible_candidates_before_rejections(monkeypatch, capsys):
    eligible = StockSnapshot(
        ticker="GOOD",
        sector="Technology",
        price=100,
        above_100dma=True,
        above_200dma=True,
        trend_90d=0.10,
        sector_relative_strength=0.05,
        drawdown_from_swing_high_pct=7,
        rsi=38,
        near_support=True,
        selling_volume_stabilizing=True,
        making_lower_lows=False,
        confirmation_signals=("green_daily_candle", "higher_low"),
    )
    rejected = StockSnapshot(
        ticker="BAD",
        sector="Technology",
        price=100,
        above_100dma=True,
        above_200dma=True,
        trend_90d=0.10,
        sector_relative_strength=0.05,
        drawdown_from_swing_high_pct=2,
        rsi=55,
        near_support=False,
        selling_volume_stabilizing=False,
        making_lower_lows=False,
        confirmation_signals=(),
    )

    class Provider:
        def get_stocks_for_sector(self, sector_name, as_of):
            return rejected, eligible

    monkeypatch.setattr("options_trading_assistant.cli.build_provider", lambda _name, _config: Provider())
    args = SimpleNamespace(
        as_of="2026-06-26",
        mode="balanced",
        provider="mock",
        sector="Technology",
        limit=20,
    )

    run_stock_scan(args)
    output = capsys.readouterr().out

    assert output.index("GOOD") < output.index("BAD")
