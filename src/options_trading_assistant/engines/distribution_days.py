from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DistributionDayRule:
    lookback_bars: int
    max_count_in_window: int
    require_consecutive: bool = False
    min_drop_pct: float = 0.2


@dataclass(frozen=True)
class DistributionDayState:
    count_in_window: int
    triggered: bool
    flagged_dates: tuple[date, ...] = ()


def rule_from_market_config(market_config: dict[str, Any]) -> DistributionDayRule:
    explicit = market_config.get("distribution_days") or {}
    if explicit:
        return DistributionDayRule(
            lookback_bars=int(explicit.get("lookback_bars", 10)),
            max_count_in_window=int(explicit.get("max_count_in_window", market_config.get("max_distribution_days", 2))),
            require_consecutive=bool(explicit.get("require_consecutive", False)),
            min_drop_pct=float(explicit.get("min_drop_pct", 0.2)),
        )
    return DistributionDayRule(
        lookback_bars=10,
        max_count_in_window=int(market_config.get("max_distribution_days", 2)),
        require_consecutive=False,
        min_drop_pct=0.2,
    )


def evaluate_distribution_days_from_rows(
    rows: list[dict[str, Any]],
    close_names: list[str],
    volume_names: list[str],
    date_names: list[str],
    rule: DistributionDayRule,
) -> DistributionDayState:
    if len(rows) < 2:
        return DistributionDayState(count_in_window=0, triggered=False)

    flagged_indices: list[int] = []
    flagged_dates: list[date] = []
    start = max(1, len(rows) - rule.lookback_bars)
    for index in range(start, len(rows)):
        close = _row_number(rows[index], close_names)
        prev_close = _row_number(rows[index - 1], close_names)
        volume = _row_number(rows[index], volume_names)
        prev_volume = _row_number(rows[index - 1], volume_names)
        if prev_close <= 0:
            continue
        pct_change = (close / prev_close - 1.0) * 100
        if close < prev_close and volume > prev_volume and pct_change <= -abs(rule.min_drop_pct):
            flagged_indices.append(index)
            raw_date = _row_value(rows[index], date_names)
            flagged_dates.append(_coerce_date(raw_date))

    triggered = len(flagged_indices) >= rule.max_count_in_window
    if rule.require_consecutive and rule.max_count_in_window > 1:
        streak = 1
        triggered = False
        for current, previous in zip(flagged_indices[1:], flagged_indices[:-1]):
            if current - previous == 1:
                streak += 1
            else:
                streak = 1
            if streak >= rule.max_count_in_window:
                triggered = True
                break
    return DistributionDayState(
        count_in_window=len(flagged_indices),
        triggered=triggered,
        flagged_dates=tuple(day for day in flagged_dates if day is not None),
    )


def _row_value(row: dict[str, Any], names: list[str], default=None):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _row_number(row: dict[str, Any], names: list[str], default: float = 0.0) -> float:
    value = _row_value(row, names, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    raw = str(value)[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
