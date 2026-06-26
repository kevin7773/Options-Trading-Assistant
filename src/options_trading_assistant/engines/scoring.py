from __future__ import annotations

from datetime import date
from math import floor

from options_trading_assistant.models import (
    MarketSnapshot,
    OptionSpread,
    ScoreBreakdown,
    SectorSnapshot,
    StockSnapshot,
)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(value, upper))


def score_market(snapshot: MarketSnapshot, market_config: dict) -> float:
    score = 0.0
    score += 7.0 if snapshot.spy_above_20dma else 0.0
    score += 7.0 if snapshot.nasdaq_above_20dma else 0.0
    score += 5.0 if not (snapshot.vix > market_config["max_vix_if_rising"] and snapshot.vix_rising) else 0.0
    score += 4.0 if snapshot.distribution_days < market_config["max_distribution_days"] else 0.0
    score += 4.0 * clamp(snapshot.breadth_score)
    score += 3.0 * clamp(snapshot.growth_participation_score)
    return round(score, 2)


def market_block_reason(snapshot: MarketSnapshot, market_config: dict) -> str | None:
    if market_config["require_spy_above_20dma"] and not snapshot.spy_above_20dma:
        return "S&P 500 is below its 20-day moving average."
    if market_config["require_nasdaq_above_20dma"] and not snapshot.nasdaq_above_20dma:
        return "Nasdaq is below its 20-day moving average."
    if snapshot.vix > market_config["max_vix_if_rising"] and snapshot.vix_rising:
        return "VIX is above the configured limit and rising."
    if snapshot.distribution_days >= market_config["max_distribution_days"]:
        return "Distribution-day count is at or above the configured limit."
    if snapshot.breadth_score < 0.35:
        return "Market breadth is sharply negative."
    return None


def score_sector(snapshot: SectorSnapshot) -> float:
    rs_score = clamp((snapshot.relative_strength_1d + snapshot.relative_strength_5d + snapshot.relative_strength_20d + 3) / 9)
    trend_score = (1.0 if snapshot.above_20dma else 0.0) * 0.5 + (1.0 if snapshot.above_50dma else 0.0) * 0.5
    quality = (
        rs_score * 0.35
        + trend_score * 0.25
        + clamp(snapshot.volume_trend_score) * 0.15
        + clamp(snapshot.momentum_score) * 0.15
        + clamp(snapshot.recovery_score) * 0.10
    )
    return round(quality * 15, 2)


def score_trend(stock: StockSnapshot) -> float:
    score = 0.0
    score += 5.0 if stock.above_100dma else 0.0
    score += 6.0 if stock.above_200dma else 0.0
    score += 4.0 * clamp((stock.trend_90d + 0.10) / 0.25)
    score += 3.0 * clamp((stock.sector_relative_strength + 0.10) / 0.25)
    score += 2.0 if not stock.making_lower_lows else 0.0
    return round(score, 2)


def passes_mean_reversion(stock: StockSnapshot) -> bool:
    controlled_pullback = 5.0 <= stock.drawdown_from_swing_high_pct <= 12.0
    constructive_rsi = stock.rsi <= 42.0
    return (
        controlled_pullback
        and constructive_rsi
        and stock.near_support
        and stock.selling_volume_stabilizing
        and not stock.company_specific_warning
        and not stock.making_lower_lows
    )


def score_confirmation(stock: StockSnapshot, required_signals: int) -> float:
    signal_count = len(stock.confirmation_signals)
    if signal_count < required_signals:
        return round(20.0 * (signal_count / max(required_signals, 1)) * 0.5, 2)
    return round(min(20.0, 12.0 + signal_count * 2.5), 2)


def score_options(spread: OptionSpread, trade_config: dict, as_of: date) -> float:
    dte = (spread.expiration - as_of).days
    score = 0.0
    score += 2.0 if trade_config["min_days_to_expiration"] <= dte <= trade_config["max_days_to_expiration"] else 0.0
    score += 2.0 if spread.width in trade_config["preferred_spread_widths"] else 0.0
    score += 2.0 if 0.35 <= spread.long_delta <= 0.55 else 0.0
    score += 2.0 if spread.max_loss <= trade_config["max_debit_per_spread"] else 0.0
    score += 2.0 if spread.reward_to_risk >= trade_config["min_reward_to_risk"] else 0.0
    score += 2.0 if spread.long_open_interest >= 500 and spread.short_open_interest >= 500 else 0.0
    score += 1.5 if spread.bid_ask_width_pct <= 0.10 else 0.0
    score += 1.0 * clamp(spread.volume_score)
    score += 0.5 if spread.iv_rank <= 0.60 else 0.0
    return round(min(score, 15.0), 2)


def grade_for_score(total_score: float) -> str:
    rounded = floor(total_score)
    if rounded >= 95:
        return "A+"
    if rounded >= 90:
        return "A"
    if rounded >= 80:
        return "B"
    if rounded >= 70:
        return "Watchlist"
    return "No Trade"


def build_score_breakdown(
    market_score: float,
    sector_score: float,
    trend_score: float,
    confirmation_score: float,
    options_score: float,
) -> ScoreBreakdown:
    return ScoreBreakdown(
        market=round(market_score, 2),
        sector=round(sector_score, 2),
        trend=round(trend_score, 2),
        confirmation=round(confirmation_score, 2),
        options=round(options_score, 2),
    )
