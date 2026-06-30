# Architecture Constitution

This document is the project constitution. It should guide every feature, refactor, provider integration, test, and strategy change.

When implementation details are unclear, prefer the choice that preserves discipline, testability, and capital protection.

## Mission

Build a disciplined options trading assistant that identifies high-quality bull call spread opportunities while protecting capital.

The system must be comfortable saying:

```text
SIT TODAY OUT
```

A quiet scanner is a feature, not a bug.

## Design Principles

1. Never recommend bullish trades against the market regime.
2. Never recommend a trade solely because a stock is down.
3. Sector leadership matters before individual stock selection.
4. Longer-term trend must remain intact before mean reversion is considered.
5. Confirmation is mandatory before entry.
6. Options structure must be liquid, fairly priced, and realistic.
7. Every recommendation must include risk, invalidation, and management logic.
8. Every scan and trade decision should be explainable after the fact.
9. Broker/data providers are replaceable infrastructure, not strategy logic.
10. Paper trading and live trading must remain explicitly separate.
11. No trade is always an acceptable answer.
12. Backtests evaluate strategy rules; they must not silently change those rules.

## Research Principles

These principles are off limits unless the project explicitly changes its constitution:

1. Price outperformance alone is never sufficient evidence for production.
2. Every production change must trace back to a documented hypothesis.
3. Every hypothesis must have predefined promotion and rejection criteria.
4. Rejected hypotheses remain institutional knowledge.
5. Prospective evidence outweighs retrospective optimization.

The current operating rule is to spend at least 80% of project effort learning from the engine and no more than 20% changing it. The framework, governance, data quality, and tests are mature enough that evidence collection is now the limiting factor.

Optimization comes after validation, not before it.

## Pipeline

The scanner pipeline runs in this order:

1. Market regime
2. Sector ranking
3. Stock trend
4. Mean reversion setup
5. Confirmation
6. Signal Engine output
7. Trade Construction Engine
8. Options spread quality
9. Final scoring and recommendation
10. Journaling and review

Later stages must not override hard failures from earlier stages. For example, a strong option chain cannot rescue a hostile market regime.

## Stage Responsibilities

### Market Regime

Purpose: decide whether new bullish risk is acceptable.

Inputs include SPY/QQQ trend, distribution behavior, breadth proxy, growth participation, and volatility signal/proxy.

If the market gate fails, the scanner returns `SIT TODAY OUT` before evaluating individual trades.

### Sector Ranking

Purpose: identify leadership before scanning stocks.

Sector scores use relative strength vs SPY, moving-average status, volume trend, momentum, and recovery behavior.

Only top-ranked sectors should advance into stock scanning.

### Stock Trend

Purpose: ensure the stock is still structurally healthy.

The stock layer checks long-term moving averages, 90-day trend, sector-relative strength, and lower-low behavior.

### Mean Reversion

Purpose: find controlled pullbacks, not falling knives.

A candidate should show a pullback of roughly 5-12%, constructive RSI, proximity to support, stabilizing selling volume, and no company-specific warning.

### Confirmation

Purpose: require evidence that buyers are returning.

Examples include green daily candle, higher low, close above prior high, RSI turning up, relative strength vs sector, and reclaim of key moving averages.

### Options Quality

Purpose: ensure the spread is tradable.

Hard failures include invalid debit, debit at or above spread width, max loss above configured limit, and reward/risk below the configured minimum.

Other inputs include expiration, spread width, long-leg delta, open interest, bid/ask width, volume, and IV.

## Independent Research Layers

The scanner is split into two research projects with a one-way boundary:

```text
Signal Engine
  Market -> Sector -> Stock -> Confirmation
                    |
                    v
            SignalCandidate
                    |
                    v
Trade Construction Engine
  Expiration -> Strikes -> Width -> Debit -> Risk
```

`SignalEngine` must not request option-chain data. It produces provider-neutral stock signals and full stock rankings, including rejected stocks for research.

`TradeConstructionEngine` must not rescore the market, rerank sectors, or rescan stocks. It consumes qualified signals and evaluates spread structures.

Research must report the two layers separately. A good stock signal with a poor spread is a trade-construction failure, not evidence that the signal was wrong. A profitable spread cannot rescue a failed signal.

## Module Boundaries

### `options_trading_assistant.models`

Owns typed domain data such as:

- `MarketSnapshot`
- `SectorSnapshot`
- `StockSnapshot`
- `OptionSpread`
- `ScoreBreakdown`
- `TradeCandidate`
- `ScanResult`

Models should stay provider-neutral.

### `options_trading_assistant.providers`

Owns data acquisition.

Providers must implement `DataProvider` and return project models or raw provider diagnostics. Strategy rules should not live here except minimal data normalization required to produce models.

Current providers:

- `MockDataProvider`
- `MoomooDataProvider`
- `HistoricalDataProvider`

### `options_trading_assistant.engines`

Owns strategy logic.

- `signals.py` owns market, sector, stock, mean-reversion, and confirmation research.
- `trade_construction.py` owns expiration, strike, width, debit, liquidity, and risk research.
- `scanner.py` only coordinates the two layers.
- Scoring and future trade-management logic remain explicit supporting modules.

### `options_trading_assistant.reports`

Owns durable output and human/machine-readable reports.

Journal output should preserve enough information for later post-trade analysis.

### `options_trading_assistant.backtesting`

Owns historical scanner orchestration, simulated spread outcomes, and summary metrics.

Backtesting code may reconstruct provider snapshots and estimate outcomes, but it must call the existing scanner rather than duplicating or bypassing strategy rules.

### `options_trading_assistant.cli`

Owns command-line orchestration and formatting.

CLI commands should call providers and engines; they should not hide strategy logic inside argument handling.

## Data Flow

```text
config/*.yaml
    |
    v
DataProvider
    |
    v
Market / Sector / Stock / Option models
    |
    v
Scoring and scanner engines
    |
    v
ScanResult / workbench output
    |
    v
Journal / reports / future paper trading
```

Historical research follows the same scanner path:

```text
Historical OHLCV cache / Massive hydrate
    |
    v
HistoricalDataProvider
    |
    v
DailyScanner
    |
    v
Backtest artifacts / metrics / simulated decision packets
```

Edge validation consumes frozen outputs without retuning either engine:

```text
Frozen v4.2 baseline
    |
    +--> Signal ranking experiment -> forward stock returns
    |
    +--> Trade evidence -> independent setups -> costs / confidence / benchmarks
```

Prospective tracking is governed by `docs/prospective_tracking.md`. Daily evidence collection and weekly review must treat snapshots, packets, and validation reports as immutable evidence, not as tuning prompts.

Strategy research is governed by `docs/strategy_registry.md`. Versions are frozen releases; registry hypotheses are the evidence ledger that explains which ideas are validated, rejected, prospective, or still under investigation.

v4.3 research is governed by `docs/v4_3_research_plan.md`. It may test new hypotheses, but it must compare against v4.2 and must not alter v4.2 prospective evidence collection.

## Workbench Commands

Workbench commands exist to inspect one pipeline layer at a time:

```powershell
python -m options_trading_assistant.cli diagnose --provider moomoo --ticker MSFT
python -m options_trading_assistant.cli rank-sectors --provider moomoo
python -m options_trading_assistant.cli scan-stocks --provider moomoo --sector Healthcare
python -m options_trading_assistant.cli scan-options --provider moomoo --ticker MSFT
```

These commands are not side quests. They are required tools for tuning and validating the full scanner.

## Provider Rules

Providers may normalize vendor-specific field names into project models.

Providers must not:

- Place orders unless they are explicit trading adapters.
- Mix paper trading with live trading.
- Decide whether a trade is strategically acceptable.
- Swallow unavailable data in a way that falsely improves a score.

Known Moomoo details:

- VIX index data is restricted, so `VIXY` is used as a volatility-risk proxy when true VIX is unavailable.
- Option chains provide contract identity and strikes.
- Option contract snapshots provide bid, ask, delta, open interest, volume, and implied volatility.
- Moomoo option IV is returned as a percentage and must be normalized to decimal form before scoring.

Known historical provider details:

- Massive stock aggregate bars are cached locally before scanner execution.
- The default Massive throttle is 5 calls per minute.
- Historical options are initially modeled with simplified spread assumptions; this is a research approximation, not executable trading output.

## Configuration

Strategy thresholds, weights, universe definitions, and broker/provider settings belong in `config/*.yaml`.

Avoid hard-coding values that represent strategy policy. If a number changes the trading behavior, it should probably be configurable.

`config/universe_v2.yaml` is a versioned research asset, not only a ticker list. It should preserve why a ticker exists, how it should be treated, and when it should not be scanned. The active scanner uses Tier 1 core leaders and Tier 2 sector leaders by default; Tier 3 watchlist names remain available for research and promotion, while Tier 4 exclusions are retained as explicit no-scan metadata.

## Coding Conventions

- Prefer small, explicit functions over clever abstractions.
- Keep provider-specific quirks isolated in provider modules.
- Keep scoring deterministic and easy to test.
- Add comments only when they clarify non-obvious logic.
- Preserve ASCII in source files unless a file already requires otherwise.
- Do not introduce live-trading behavior without explicit user approval.

## Testing Philosophy

Tests should protect behavior, not implementation trivia.

Required coverage areas:

- Market gate behavior.
- Sector scoring behavior.
- Stock rejection reasons.
- Options hard-fail rules.
- Provider normalization helpers.
- Journal serialization.
- CLI formatting for workbench commands.
- Backtest metrics and artifact creation.

Mock data must represent valid and invalid cases honestly. If a mock candidate claims to be tradable, it must satisfy the same hard rules as a live candidate.

## Performance Goals

Initial goal: correctness and explainability over speed.

Near-term goals:

- A full morning scan should complete comfortably within a few minutes.
- Workbench commands should return fast enough for interactive tuning.
- Provider calls should be batched where the vendor API allows it.
- Repeated calls should avoid unnecessary duplication once caching is introduced.

Do not sacrifice correctness or risk discipline for speed.

## Journaling And Review

Every recommendation and rejection should eventually be reviewable.

The journal should support:

- Daily scan reconstruction.
- Candidate rejection analysis.
- Paper-trade tracking.
- Closed-trade post-mortems.
- Strategy version comparison.

## Known Limitations

- Backtesting uses simplified option-spread outcome assumptions first.
- Paper trading is not implemented yet.
- Live trading is intentionally not implemented.
- VIX is not directly available through the current Moomoo OpenD route.
- Sector breadth is currently a proxy, not a full market breadth model.
- Support detection is simple and should be improved before relying on real-money decisions.
- Options scoring does not yet model expected move or ATR-based breakeven realism.

## Change Rule

Any change that alters trade selection must answer:

```text
Does this improve capital protection, repeatability, or evidence-based decision quality?
```

If the answer is unclear, add a workbench view, test, or backtest before changing production scanner behavior.
