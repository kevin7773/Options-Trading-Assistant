from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticOptionEstimate:
    estimated_debit: float
    debit_pct_of_width: float
    expected_move: float
    distance_to_long_strike: float
    distance_to_short_strike: float
    estimated_reward_risk: float
    pricing_reason: str


def estimate_bull_call_spread_debit(
    underlying_price: float,
    long_strike: float,
    short_strike: float,
    dte: int,
    iv_proxy: float,
    expected_move_pct: float,
    base_debit_pct: float = 0.35,
    min_debit_pct: float = 0.25,
    max_debit_pct: float = 0.60,
) -> SyntheticOptionEstimate:
    width = short_strike - long_strike
    if width <= 0 or underlying_price <= 0:
        raise ValueError("Synthetic spread estimate requires positive price and spread width.")

    distance_to_long = ((long_strike - underlying_price) / underlying_price) * 100
    distance_to_short = ((short_strike - underlying_price) / underlying_price) * 100
    expected_move = underlying_price * (expected_move_pct / 100)

    moneyness_adjustment = _clamp((distance_to_long / 100) * 1.20, -0.04, 0.08)
    iv_adjustment = _clamp((iv_proxy - 0.30) * 0.12, -0.03, 0.05)
    time_adjustment = _clamp((dte - 28) / 400, -0.025, 0.025)
    expected_move_adjustment = _clamp(((expected_move_pct - max(distance_to_long, 0)) / 100) * 0.60, 0.0, 0.06)

    debit_pct = _clamp(
        base_debit_pct
        + moneyness_adjustment
        + iv_adjustment
        + time_adjustment
        - expected_move_adjustment,
        min_debit_pct,
        max_debit_pct,
    )
    estimated_debit = round(width * debit_pct, 2)
    estimated_reward_risk = 0.0 if estimated_debit <= 0 else round((width - estimated_debit) / estimated_debit, 2)
    reason = (
        f"base={base_debit_pct:.2f}, moneyness={moneyness_adjustment:+.3f}, iv={iv_adjustment:+.3f}, "
        f"time={time_adjustment:+.3f}, expected_move={-expected_move_adjustment:+.3f}"
    )
    return SyntheticOptionEstimate(
        estimated_debit=estimated_debit,
        debit_pct_of_width=round(debit_pct, 4),
        expected_move=round(expected_move, 2),
        distance_to_long_strike=round(distance_to_long, 2),
        distance_to_short_strike=round(distance_to_short, 2),
        estimated_reward_risk=estimated_reward_risk,
        pricing_reason=reason,
    )


def estimate_iv_proxy_from_expected_move(expected_move_pct: float) -> float:
    return _clamp(expected_move_pct / 10, 0.20, 0.60)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
