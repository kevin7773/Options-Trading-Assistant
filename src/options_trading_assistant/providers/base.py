from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from options_trading_assistant.models import (
    MarketSnapshot,
    OptionSpread,
    SectorSnapshot,
    StockSnapshot,
)


class DataProvider(ABC):
    """Read-only market data boundary for strategy code."""

    @abstractmethod
    def get_market_snapshot(self, as_of: date) -> MarketSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_sector_snapshots(self, as_of: date) -> tuple[SectorSnapshot, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_stocks_for_sector(self, sector_name: str, as_of: date) -> tuple[StockSnapshot, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_option_spreads(self, ticker: str, as_of: date) -> tuple[OptionSpread, ...]:
        raise NotImplementedError
