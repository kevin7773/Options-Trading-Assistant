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

Inspect live provider fields with:

```powershell
python -m options_trading_assistant.cli diagnose --provider moomoo --ticker MSFT
```

Inspect option spread candidates directly with:

```powershell
python -m options_trading_assistant.cli scan-options --provider moomoo --ticker MSFT
```

Rank configured sectors with:

```powershell
python -m options_trading_assistant.cli rank-sectors --provider moomoo
```

Inspect stock-level filters inside one configured sector with:

```powershell
python -m options_trading_assistant.cli scan-stocks --provider moomoo --sector Healthcare
```

Paper trading and live order placement remain intentionally separate from the market-data provider.

## Volatility Data

Moomoo OpenD may recognize `US..VIX` but still reject US index data through quote/history calls because VIX dissemination is restricted.

The provider therefore attempts true VIX first, then falls back to `VIXY` as a volatility-risk proxy. The proxy is used for direction and risk-off detection, not as a substitute for the VIX index level.
