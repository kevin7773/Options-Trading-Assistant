# Trade Management

Every recommendation includes:

- Entry trigger.
- Profit target.
- Stop or invalidating condition.
- Management plan.

The current implementation prints conservative default management text. Future work should move exit and position monitoring rules into a dedicated trade manager.

## Cooling-Off Enforcement

When enabled in `config/strategy.yaml`, live scans rebuild ticker failure streaks from completed recommendation decision packets. After the configured number of consecutive non-profitable bullish spreads, the scanner rejects that ticker until it records either:

- A reclaim of the 20-day moving average.
- A break above a recent swing high.

Backtests apply cooling-off outcomes only after each simulated trade's exit date so future results cannot affect earlier scans.
