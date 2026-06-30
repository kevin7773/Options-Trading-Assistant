from __future__ import annotations

import json
from pathlib import Path

from options_trading_assistant.backtesting.engine import max_drawdown, run_backtest
from options_trading_assistant.backtesting.scenarios import get_scenario
from options_trading_assistant.config import PROJECT_ROOT, load_config
from options_trading_assistant.providers.historical import HistoricalDataProvider
from options_trading_assistant.reports.journal import json_default


CACHE_DIR = PROJECT_ROOT / "data" / "historical" / "yahoo_2022_2026"
OUTPUT_ROOT = PROJECT_ROOT / "backtesting" / "results" / "v4.1-strike-durability"
SCENARIOS = ("slightly_itm", "atm", "current_otm")
PERIODS = {
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_ytd": ("2026-01-01", "2026-06-29"),
}


def main() -> None:
    from datetime import date

    config = load_config()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cells: list[dict] = []
    all_trades: dict[str, list] = {name: [] for name in SCENARIOS}

    for scenario_name in SCENARIOS:
        scenario = get_scenario(scenario_name)
        print(f"Loading cache for {scenario_name}...", flush=True)
        provider = HistoricalDataProvider.from_cache(
            config=config,
            cache_dir=CACHE_DIR,
            scenario=scenario,
        )
        for period_name, (start_text, end_text) in PERIODS.items():
            print(f"Running {scenario_name} / {period_name}...", flush=True)
            result = run_backtest(
                config=config,
                provider=provider,
                mode="balanced",
                start=date.fromisoformat(start_text),
                end=date.fromisoformat(end_text),
                output_root=OUTPUT_ROOT,
                run_id=f"{scenario_name}-{period_name}",
                scenario=scenario,
                detailed_artifacts=False,
            )
            all_trades[scenario_name].extend(result.trades)
            setup_pl: dict[tuple, float] = {}
            for trade in result.trades:
                key = (trade.entry_date, trade.ticker)
                setup_pl[key] = setup_pl.get(key, 0.0) + trade.final_pl
            cells.append(
                {
                    "scenario": scenario_name,
                    "period": period_name,
                    "start": start_text,
                    "end": end_text,
                    **result.summary,
                    "total_pl": round(sum(trade.final_pl for trade in result.trades), 2),
                    "independent_setups": len(setup_pl),
                    "profitable_setups": sum(1 for value in setup_pl.values() if value > 0),
                    "setup_win_rate": (
                        sum(1 for value in setup_pl.values() if value > 0) / len(setup_pl)
                        if setup_pl
                        else 0.0
                    ),
                    "output_dir": result.output_dir,
                }
            )
            print(
                f"Completed {scenario_name} / {period_name}: "
                f"trades={result.trade_count}, win_rate={result.summary['win_rate']:.1%}, "
                f"expectancy=${result.summary['expectancy']:.2f}",
                flush=True,
            )

    aggregate = {}
    for scenario_name, trades in all_trades.items():
        ordered = sorted(trades, key=lambda trade: (trade.entry_date, trade.ticker))
        wins = [trade for trade in ordered if trade.final_pl > 0]
        total_pl = sum(trade.final_pl for trade in ordered)
        setup_pl: dict[tuple, float] = {}
        for trade in ordered:
            key = (trade.entry_date, trade.ticker)
            setup_pl[key] = setup_pl.get(key, 0.0) + trade.final_pl
        aggregate[scenario_name] = {
            "trade_count": len(ordered),
            "win_rate": len(wins) / len(ordered) if ordered else 0.0,
            "independent_setups": len(setup_pl),
            "setup_win_rate": (
                sum(1 for value in setup_pl.values() if value > 0) / len(setup_pl)
                if setup_pl
                else 0.0
            ),
            "total_pl": round(total_pl, 2),
            "expectancy": round(total_pl / len(ordered), 2) if ordered else 0.0,
            "max_drawdown": round(max_drawdown([trade.final_pl for trade in ordered]), 2),
            "profitable_periods": sum(
                1
                for cell in cells
                if cell["scenario"] == scenario_name
                and cell["trade_count"] > 0
                and cell["expectancy"] > 0
            ),
        }

    payload = {
        "strategy_version": config.strategy_version,
        "mode": "balanced",
        "data_source": "Yahoo adjusted daily OHLCV",
        "cache_dir": str(CACHE_DIR),
        "scenarios": {
            "slightly_itm": "-1% long-strike moneyness",
            "atm": "0% long-strike moneyness",
            "current_otm": "+1% long-strike moneyness",
        },
        "cells": cells,
        "aggregate": aggregate,
    }
    (OUTPUT_ROOT / "comparison.json").write_text(
        json.dumps(payload, default=json_default, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (OUTPUT_ROOT / "comparison.md").write_text(format_markdown(payload), encoding="utf-8")
    print(f"Comparison written to {OUTPUT_ROOT}", flush=True)


def format_markdown(payload: dict) -> str:
    lines = [
        "# v4.1 Strike Placement Durability",
        "",
        f"Data source: {payload['data_source']}",
        "",
        "| Scenario | Period | Setups | Setup win rate | Spreads | Spread win rate | Total P/L | Expectancy | Max drawdown |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in payload["cells"]:
        lines.append(
            f"| {cell['scenario']} | {cell['period']} | {cell['independent_setups']} | "
            f"{cell['setup_win_rate']:.1%} | {cell['trade_count']} | {cell['win_rate']:.1%} | "
            f"${cell['total_pl']:.2f} | ${cell['expectancy']:.2f} | "
            f"${cell['max_drawdown']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            "| Scenario | Setups | Setup win rate | Spreads | Spread win rate | Total P/L | Expectancy | Max drawdown | Profitable periods |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario_name, metrics in payload["aggregate"].items():
        lines.append(
            f"| {scenario_name} | {metrics['independent_setups']} | {metrics['setup_win_rate']:.1%} | "
            f"{metrics['trade_count']} | {metrics['win_rate']:.1%} | "
            f"${metrics['total_pl']:.2f} | ${metrics['expectancy']:.2f} | "
            f"${metrics['max_drawdown']:.2f} | {metrics['profitable_periods']}/4 |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
