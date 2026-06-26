from datetime import date

from options_trading_assistant.cli import format_sector_ranking
from options_trading_assistant.models import SectorSnapshot


def test_format_sector_ranking_outputs_table():
    sector = SectorSnapshot(
        name="Technology",
        primary_etf="XLK",
        relative_strength_1d=0.4,
        relative_strength_5d=1.2,
        relative_strength_20d=2.8,
        above_20dma=True,
        above_50dma=True,
        volume_trend_score=0.72,
        momentum_score=0.81,
        recovery_score=0.67,
    )

    output = format_sector_ranking(date(2026, 6, 26), [(sector, 12.34)])

    assert "Date: 2026-06-26" in output
    assert "Technology | XLK | 12.34/15" in output
    assert "RS 20D" in output
    assert "Y | Y" in output
