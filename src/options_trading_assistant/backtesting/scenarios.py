from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BacktestScenario:
    name: str
    description: str
    min_debit_pct: float
    max_debit_pct: float
    min_reward_to_risk: float
    confirmation_signals_required: int
    max_iv_rank: float
    long_strike_moneyness_pct: float
    synthetic_base_debit_pct: float
    synthetic_min_debit_pct: float
    synthetic_max_debit_pct: float
    profit_target_pct_of_max_profit: float
    stop_loss_pct_of_debit: float


BALANCED_SCENARIO = BacktestScenario(
    name="balanced",
    description="Current balanced rules with v1 synthetic pricing and lifecycle diagnostics.",
    min_debit_pct=0.25,
    max_debit_pct=0.60,
    min_reward_to_risk=1.50,
    confirmation_signals_required=2,
    max_iv_rank=0.60,
    long_strike_moneyness_pct=0.01,
    synthetic_base_debit_pct=0.35,
    synthetic_min_debit_pct=0.25,
    synthetic_max_debit_pct=0.60,
    profit_target_pct_of_max_profit=0.60,
    stop_loss_pct_of_debit=0.50,
)


SCENARIOS = {
    "balanced": BALANCED_SCENARIO,
    "slightly_itm": replace(
        BALANCED_SCENARIO,
        name="slightly_itm",
        description="Balanced v4.2 rules with the long strike placed 1% in the money.",
        long_strike_moneyness_pct=-0.01,
    ),
    "atm": replace(
        BALANCED_SCENARIO,
        name="atm",
        description="Balanced v4.2 rules with the long strike placed at the money.",
        long_strike_moneyness_pct=0.00,
    ),
    "current_otm": replace(
        BALANCED_SCENARIO,
        name="current_otm",
        description="Balanced v4.2 rules with the current long strike placement 1% out of the money.",
        long_strike_moneyness_pct=0.01,
    ),
    "high_probability": replace(
        BALANCED_SCENARIO,
        name="high_probability",
        description="Higher debit, lower payoff, stricter confirmation profile.",
        min_debit_pct=0.40,
        max_debit_pct=0.50,
        min_reward_to_risk=1.00,
        confirmation_signals_required=3,
        max_iv_rank=0.55,
        long_strike_moneyness_pct=0.00,
        synthetic_base_debit_pct=0.45,
        synthetic_min_debit_pct=0.40,
        synthetic_max_debit_pct=0.50,
        profit_target_pct_of_max_profit=0.80,
        stop_loss_pct_of_debit=0.55,
    ),
    "aggressive": replace(
        BALANCED_SCENARIO,
        name="aggressive",
        description="Lower debit, higher payoff, looser confirmation, higher volatility tolerance.",
        min_debit_pct=0.25,
        max_debit_pct=0.35,
        min_reward_to_risk=2.00,
        confirmation_signals_required=1,
        max_iv_rank=0.75,
        long_strike_moneyness_pct=0.02,
        synthetic_base_debit_pct=0.30,
        synthetic_min_debit_pct=0.25,
        synthetic_max_debit_pct=0.35,
        profit_target_pct_of_max_profit=0.60,
        stop_loss_pct_of_debit=0.60,
    ),
}


def get_scenario(name: str) -> BacktestScenario:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        available = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown backtest scenario '{name}'. Available scenarios: {available}") from exc


def scenario_names(value: str) -> list[str]:
    if value == "all":
        return list(SCENARIOS)
    return [name.strip() for name in value.split(",") if name.strip()]
