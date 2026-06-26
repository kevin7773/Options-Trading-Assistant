from __future__ import annotations

from datetime import date, timedelta

from options_trading_assistant.models import (
    MarketSnapshot,
    OptionSpread,
    SectorSnapshot,
    StockSnapshot,
)
from options_trading_assistant.providers.base import DataProvider


class MockDataProvider(DataProvider):
    """Deterministic local data for scanner development and tests."""

    def get_market_snapshot(self, as_of: date) -> MarketSnapshot:
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=True,
            nasdaq_above_20dma=True,
            vix=18.4,
            vix_rising=False,
            distribution_days=1,
            breadth_score=0.72,
            growth_participation_score=0.68,
        )

    def get_sector_snapshots(self, as_of: date) -> tuple[SectorSnapshot, ...]:
        return (
            SectorSnapshot("Healthcare", "XLV", 0.6, 1.8, 3.1, True, True, 0.74, 0.78, 0.81),
            SectorSnapshot("Technology", "XLK", 0.2, 0.8, 2.2, True, True, 0.69, 0.73, 0.70),
            SectorSnapshot("Semiconductors", "SMH", -0.1, 0.2, 1.4, True, True, 0.55, 0.62, 0.58),
            SectorSnapshot("Energy", "XLE", -0.5, -1.1, -2.0, False, False, 0.42, 0.35, 0.30),
        )

    def get_stocks_for_sector(self, sector_name: str, as_of: date) -> tuple[StockSnapshot, ...]:
        stocks = {
            "Healthcare": (
                StockSnapshot(
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
                    confirmation_signals=(
                        "green_daily_candle",
                        "higher_low",
                        "close_above_previous_high",
                    ),
                ),
                StockSnapshot(
                    ticker="UNH",
                    sector="Healthcare",
                    price=321.10,
                    above_100dma=False,
                    above_200dma=True,
                    trend_90d=-0.04,
                    sector_relative_strength=-0.06,
                    drawdown_from_swing_high_pct=14.0,
                    rsi=33.0,
                    near_support=False,
                    selling_volume_stabilizing=False,
                    making_lower_lows=True,
                    confirmation_signals=("rsi_turning_up",),
                ),
            ),
            "Technology": (
                StockSnapshot(
                    ticker="MSFT",
                    sector="Technology",
                    price=502.40,
                    above_100dma=True,
                    above_200dma=True,
                    trend_90d=0.09,
                    sector_relative_strength=0.03,
                    drawdown_from_swing_high_pct=5.8,
                    rsi=41.0,
                    near_support=True,
                    selling_volume_stabilizing=True,
                    making_lower_lows=False,
                    confirmation_signals=("higher_low", "stock_outperforming_sector_etf"),
                ),
            ),
            "Semiconductors": (
                StockSnapshot(
                    ticker="NVDA",
                    sector="Semiconductors",
                    price=143.35,
                    above_100dma=True,
                    above_200dma=True,
                    trend_90d=0.06,
                    sector_relative_strength=-0.02,
                    drawdown_from_swing_high_pct=10.5,
                    rsi=37.0,
                    near_support=True,
                    selling_volume_stabilizing=False,
                    making_lower_lows=False,
                    confirmation_signals=("rsi_turning_up",),
                ),
            ),
        }
        return stocks.get(sector_name, ())

    def get_option_spreads(self, ticker: str, as_of: date) -> tuple[OptionSpread, ...]:
        expiration = as_of + timedelta(days=28)
        spreads = {
            "ISRG": (
                OptionSpread(ticker, expiration, 430, 435, 2.05, 0.48, 0.35, 1820, 1510, 0.07, 0.82, 0.44, 4.8),
                OptionSpread(ticker, expiration, 435, 440, 2.35, 0.40, 0.28, 390, 220, 0.16, 0.44, 0.70, 5.2),
            ),
            "MSFT": (
                OptionSpread(ticker, expiration, 505, 510, 2.45, 0.44, 0.31, 2400, 2190, 0.08, 0.76, 0.38, 3.9),
            ),
            "NVDA": (
                OptionSpread(ticker, expiration, 145, 150, 2.80, 0.42, 0.30, 3600, 3100, 0.10, 0.72, 0.63, 6.4),
            ),
        }
        return spreads.get(ticker, ())
