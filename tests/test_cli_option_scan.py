from datetime import date

from options_trading_assistant.cli import format_option_scan
from options_trading_assistant.models import OptionSpread


def test_format_option_scan_shows_spread_metrics():
    spread = OptionSpread(
        ticker="MSFT",
        expiration=date(2026, 7, 24),
        long_call=380,
        short_call=385,
        debit=2.35,
        long_delta=0.41,
        short_delta=0.36,
        long_open_interest=801,
        short_open_interest=786,
        bid_ask_width_pct=0.0736,
        volume_score=0.48,
        iv_rank=0.344,
        expected_move_pct=0,
    )

    output = format_option_scan("MSFT", date(2026, 6, 26), [(spread, 12.98)])

    assert "Ticker: MSFT" in output
    assert "380/385 bull call spread" in output
    assert "Options Score: 12.98/15" in output
    assert "Reward/Risk: 1.13" in output
