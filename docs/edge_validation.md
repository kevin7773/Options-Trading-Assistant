# Phase 2: Edge Validation

The scanner is now a frozen hypothesis. Phase 2 asks whether it has measurable edge.

Improving rules and validating rules are separate activities. Do not tune v4.2 while it is under validation. A changed rule becomes a new version with a new manifest and a new evidence record.

## Evidence Classes

- `retrospective`: useful for falsification and diagnostics, never sufficient for a pass.
- `holdout`: untouched historical evidence declared before evaluation.
- `forward`: immutable paper recommendations evaluated after outcomes occur.

Only holdout and forward evidence can earn `PASS`.

## Independent Unit

The independent observation is one ticker on one signal date.

Multiple spread widths or strikes generated from that ticker/date are correlated trade constructions. They are grouped into one setup before sample size, expectancy, confidence intervals, or win rate are calculated.

## Predeclared Decision Rule

The complete protocol lives in `config/validation.yaml`. It currently requires:

- At least 30 independent setups.
- At least three active periods.
- Positive expectancy after configured round-trip costs.
- At least 0.05R expectancy per setup.
- A positive lower bootstrap confidence bound.
- Profit factor of at least 1.20.
- Drawdown no worse than 5R.
- Profitable results across at least 60% of active periods.
- At least 0.05R improvement over a predeclared benchmark.
- A valid frozen-baseline manifest.

If sample, evidence class, or benchmark data is missing, the verdict is `INSUFFICIENT EVIDENCE`, not `PASS`.

## Signal Ranking Experiment

On every market-pass day:

1. Run the Signal Engine across every configured sector and stock.
2. Save the top ten stocks even when they fail a stock or confirmation gate.
3. Record component scores, sector rank, qualification status, and rejection reasons.
4. Measure close-to-close stock returns after 5, 10, and 20 trading days.
5. Report rank-1 winner frequency, top-3 capture, rank correlation, rank-1 return lift, and average return by predicted rank.

The primary horizon is 20 trading days. All market-pass days are saved, but overlapping forward windows are not statistically independent. The verdict therefore uses non-overlapping cohorts in addition to descriptive daily results.

Logged daily scans save prospective Top-10 snapshots under `data/journal/signal_rankings/` before future outcomes are known. These files are the forward ranking evidence and must not be rewritten after creation.

## Phase 3: Complexity Benchmarks

Beating random selection is necessary but not sufficient. The ranking experiment compares rank 1 with:

1. `random_eligible`: the exact average return of all configured stocks available on that market-pass day, equivalent to the expected return from uniform random selection.
2. `oracle`: the best-performing stock in that same universe, used only as an unattainable upper bound and regret measure.
3. `SPY`: the simplest broad-market alternative.
4. `QQQ`: the simple growth-market alternative.
5. `top_sector_etf`: buying the highest-ranked sector ETF instead of selecting an individual stock.

The investable controls must be beaten on average in non-overlapping cohorts. The oracle is diagnostic and cannot be a pass requirement.

## Commands

Evaluate retrospective backtest evidence:

```powershell
python -m options_trading_assistant.cli validate-edge `
  --source backtest `
  --runs-root backtesting/results/v4.2-strike-durability `
  --scenario current_otm `
  --evidence-kind retrospective
```

Evaluate completed forward decision packets:

```powershell
python -m options_trading_assistant.cli validate-edge `
  --source packets `
  --packet-root data/journal/decision_packets `
  --scenario v4.2-forward `
  --evidence-kind forward
```

Run the stock-ranking experiment:

```powershell
python -m options_trading_assistant.cli ranking-experiment `
  --start 2023-01-01 `
  --end 2026-06-29 `
  --cache-dir data/historical/yahoo_2022_2026 `
  --mode balanced `
  --output-dir backtesting/results/v4.2-ranking-edge
```

## Change Control

The manifest under `validation/baselines/` hashes strategy configuration and the core signal, trade-construction, provider, and backtesting files. Validation reports fail integrity when those files differ from the frozen version.

When a rule changes:

1. Assign a new strategy version.
2. Freeze a new manifest.
3. Preserve all earlier reports.
4. Declare new acceptance criteria before evaluating the new version.
5. Never merge evidence across materially different strategy versions.
