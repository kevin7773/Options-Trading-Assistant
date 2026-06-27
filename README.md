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

Logged scans also write per-decision JSON packets under `data/journal/decision_packets/`.

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
- Ranked candidate recommendations when setups meet thresholds.
- JSONL scan logging under `data/journal/`.
# Options-Trading-Assistant
