# Options Trading Assistant

This project turns the `Mean_Reversion_Bull_Call_Scanner_v4.md` strategy brief into a testable scanner.

The first implementation is intentionally broker-neutral. It uses deterministic mock data so the scoring, filtering, logging, and CLI can be validated before any live market data or paper-trading API is connected.

## Run

```powershell
python -m options_trading_assistant.cli --mode balanced
```

## Test

```powershell
python -m pytest
```

## Current Scope

- Config-driven strategy thresholds and scoring weights.
- Broker-independent data provider interface.
- Mock market, sector, stock, and option spread data.
- Market gate that can return `SIT TODAY OUT`.
- Ranked candidate recommendations when setups meet thresholds.
- JSONL scan logging under `data/journal/`.
# Options-Trading-Assistant
