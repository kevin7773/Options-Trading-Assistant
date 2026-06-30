# Options Trading Assistant

This project turns the `Mean_Reversion_Bull_Call_Scanner_v4.md` strategy brief into a testable scanner.

The first implementation is intentionally broker-neutral. It uses deterministic mock data so the scoring, filtering, logging, and CLI can be validated before any live market data or paper-trading API is connected.

Read `ARCHITECTURE.md` before making strategy or provider changes. It is the project constitution.

## Run

Install the package in editable mode first:

```powershell
python -m pip install -e ".[dev]"
```

```powershell
python -m options_trading_assistant.cli --mode balanced
```

To use Moomoo OpenD for live market data, make sure OpenD is running locally and then run:

```powershell
python -m options_trading_assistant.cli --provider moomoo --mode balanced
```

Inspect Moomoo response shapes for a ticker:

```powershell
python -m options_trading_assistant.cli diagnose --provider moomoo --ticker MSFT
```

Inspect bull call spread candidates for a ticker without running the full scanner:

```powershell
python -m options_trading_assistant.cli scan-options --provider moomoo --ticker MSFT
```

Rank configured sectors with provider data:

```powershell
python -m options_trading_assistant.cli rank-sectors --provider moomoo
```

Inspect stock candidates inside a configured sector:

```powershell
python -m options_trading_assistant.cli scan-stocks --provider moomoo --sector Healthcare
```

Review logged scan outcomes and rejection patterns:

```powershell
python -m options_trading_assistant.cli review-journal --days 30
```

Logged scans also write per-decision JSON packets under `data/journal/decision_packets/` and prospective Top-10 signal snapshots under `data/journal/signal_rankings/`.

List and update decision packet outcomes:

```powershell
python -m options_trading_assistant.cli list-packets --date 2026-06-26
python -m options_trading_assistant.cli update-outcome --packet <path> --status reviewed --notes "No entry; market faded."
python -m options_trading_assistant.cli review-packets --date 2026-06-26
```

Generate the morning report:

```powershell
python -m options_trading_assistant.cli daily-report --provider moomoo --mode balanced
```

Daily reports are saved under `data/reports/daily/`.
The command writes both Markdown and HTML versions; the scheduled Gmail draft uses the HTML version for a cleaner email body.

Build the local report dashboard:

```powershell
python -m options_trading_assistant.cli dashboard --serve
```

Inspect the active tiered universe:

```powershell
python -m options_trading_assistant.cli universe-summary --show-symbols
```

`config/universe_v2.yaml` is a research asset, not only a ticker list. It defines Tier 1 core leaders, Tier 2 sector leaders, Tier 3 watchlist names, Tier 4 exclusions, benchmark ETFs, and symbol-level trading metadata such as preferred spread widths, minimum option open interest, strategy fit, and earnings buffers.

Run a historical backtest from cached OHLCV files:

```powershell
python -m options_trading_assistant.cli backtest --start 2025-01-01 --end 2025-12-31 --mode balanced --data-source cache
```

Hydrate historical bars from Massive first, respecting the default 5 calls/minute limit:

```powershell
$env:MASSIVE_API_KEY="..."
python -m options_trading_assistant.cli backtest --start 2025-01-01 --end 2025-12-31 --mode balanced --data-source massive --calls-per-minute 5
```

For indicator accuracy, hydrate enough warmup history before the backtest window. A 2025 backtest should have 2024 bars cached so 90-day trends and 100/200-day moving averages are meaningful:

```powershell
python -m options_trading_assistant.cli hydrate-history --start 2024-01-01 --end 2025-12-31 --calls-per-minute 5
python -m options_trading_assistant.cli backtest --start 2025-01-01 --end 2025-12-31 --mode balanced --data-source cache
```

Inspect why the stock-selection layer rejected candidates on a historical date:

```powershell
python -m options_trading_assistant.cli backtest-stock-diagnostics --date 2025-04-24 --mode balanced --limit 25
```

Evaluate frozen evidence against the Phase 2 edge-validation protocol:

```powershell
python -m options_trading_assistant.cli validate-edge --source backtest --runs-root backtesting/results/v4.2-strike-durability --scenario current_otm --evidence-kind retrospective
```

Save every market-pass day's top ten stocks and evaluate their forward ranking performance:

```powershell
python -m options_trading_assistant.cli ranking-experiment --start 2023-01-01 --end 2026-06-29 --cache-dir data/historical/yahoo_2022_2026 --mode balanced
```

See `docs/edge_validation.md` for the frozen-baseline protocol and change-control rules.
See `docs/prospective_tracking.md` for the after-close forward evidence collection and weekly review runbook.
See `docs/strategy_registry.md` for the evidence-driven hypothesis registry and promotion gate.
See `docs/v4_3_research_plan.md` for the research-only v4.3 experiment plan.
See `research/experiments/` for experiment manifests that preserve the audit trail behind strategy decisions.
See `research/notebooks/` for exploratory notebooks that analyze accumulated evidence without becoming production code.
See `research/roadmap.md` for the July/August research plan.

Backtest outputs are written under `backtesting/results/<run-id>/` and include `summary.json`, `trades.jsonl`, `scan_results.jsonl`, and simulated decision packets. This is still read-only research infrastructure; it does not place live or paper orders.

Historical option spreads use the v1 synthetic options model in `synthetic_options_model.py`. It estimates debit from strike moneyness, DTE, an IV proxy, expected move/ATR, and spread width, then records the estimated debit, debit percent of width, expected move, strike distances, estimated reward/risk, and pricing rationale in the spread payload.

## Test

```powershell
python -m pytest
```

## Current Scope

- Config-driven strategy thresholds and scoring weights.
- Broker-independent data provider interface.
- Mock market, sector, stock, and option spread data.
- Optional read-only Moomoo OpenD market-data provider.
- Market gate that can return `SIT TODAY OUT`.
- Cooling-off enforcement after consecutive failed bullish spreads, with technical re-entry criteria.
- Ranked candidate recommendations when setups meet thresholds.
- JSONL scan logging under `data/journal/`.
# Options-Trading-Assistant
