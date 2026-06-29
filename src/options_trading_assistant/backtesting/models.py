from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class OHLCVBar:
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class BacktestTrade:
    scenario: str
    entry_date: date
    exit_date: date
    ticker: str
    sector: str
    score: float
    score_bucket: str
    market_regime: str
    expiration: date
    long_call: float
    short_call: float
    debit: float
    entry_underlying_price: float
    exit_underlying_price: float
    exit_spread_value: float
    final_value: float
    final_pl: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    highest_underlying_price: float
    lowest_underlying_price: float
    profit_target_touched: bool
    stop_triggered_before_exit: bool
    market_score_entry: float
    market_score_exit: float
    sector_score_entry: float
    sector_score_exit: float
    confirmation_signals_entry: tuple[str, ...]
    outcome: str

    @property
    def return_pct(self) -> float:
        risk = self.debit * 100
        return 0.0 if risk == 0 else self.final_pl / risk


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    start: date
    end: date
    mode: str
    scan_count: int
    trade_count: int
    sit_out_count: int
    summary: dict[str, Any]
    output_dir: str
    trades: tuple[BacktestTrade, ...] = field(default_factory=tuple)
