# Broker Integration

Broker and market-data providers must stay replaceable.

The strategy engine depends on `DataProvider`, not on MooMoo, Futu, Interactive Brokers, Schwab, or any single vendor. Real provider adapters should be added under `src/options_trading_assistant/providers/`.

## Moomoo OpenD

The first real provider is read-only and uses Moomoo OpenD for market data.

Expected local defaults:

- Host: `127.0.0.1`
- Port: `11111`
- US ticker format: `US.MSFT`

Run with:

```powershell
python -m options_trading_assistant.cli --provider moomoo --mode balanced
```

Paper trading and live order placement remain intentionally separate from the market-data provider.
