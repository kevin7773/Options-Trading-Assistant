# v4.2 Prospective Tracking

This runbook governs forward evidence collection for the frozen v4.2 scanner on the desktop where Moomoo OpenD is installed.

The purpose is evidence collection, not strategy development. Do not tune ranking logic, scoring rules, strategy thresholds, validation thresholds, or the frozen baseline while this protocol is active.

## Current Branch State

The `codex/edge-validation-framework` branch has been merged into `main`. The branch may still exist locally and remotely as a historical working branch, but the edge-validation framework is present in the repository.

Before a prospective run, confirm the current working tree is on the intended branch and the baseline manifest passes.

## Daily Collection

Run once after the US market closes, Monday through Friday.

Recommended time:

```text
4:30 PM America/New_York
```

Prerequisites:

- Moomoo OpenD is running and logged in.
- OpenD is reachable at the configured host and port, normally `127.0.0.1:11111`.
- The latest SPY daily bar belongs to the current US trading session.
- `validation/baselines/v4.2-manifest.json` passes integrity verification.

Run:

```powershell
python -m options_trading_assistant.cli validate-edge `
  --source packets `
  --packet-root data/journal/decision_packets `
  --scenario v4.2-forward `
  --evidence-kind forward

python -m options_trading_assistant.cli daily-report `
  --provider moomoo `
  --mode balanced `
  --date (Get-Date -Format "yyyy-MM-dd")
```

The daily report writes:

- Scan journal records under `data/journal/`.
- Decision packets under `data/journal/decision_packets/`.
- Prospective signal-ranking snapshots under `data/journal/signal_rankings/`.
- Daily reports under `data/reports/daily/`.

When the market gate passes, verify that the new signal-ranking snapshot contains:

- Strategy version `v4.2`.
- The Top 10 ranked stocks.
- The full contemporaneous stock universe.
- The top-ranked sector ETF.
- Component scores and qualification status.

Never rewrite or replace older signal-ranking snapshots.

## Weekly Review

Run every Saturday after the week's daily snapshots are complete.

Recommended time:

```text
9:00 AM America/New_York
```

Use immutable snapshots under:

```text
data/journal/signal_rankings/
```

Mature a snapshot horizon only after the required number of subsequent US trading sessions has completed:

- 5 trading days.
- 10 trading days.
- 20 trading days.

For each mature horizon, compare rank 1 with:

1. Uniform random selection from the saved universe.
2. The best-performing stock in the saved universe, used as an oracle upper bound.
3. SPY.
4. QQQ.
5. The saved top-ranked sector ETF.

Report:

- Rank-1 winner rate.
- Wilson confidence interval.
- Top-3 capture rate.
- Spearman rank correlation.
- Rank-1 return lift.
- Outperformance rate against each investable benchmark.
- Oracle regret.
- Descriptive daily observations.
- Non-overlapping cohorts.
- Year-to-date and cumulative results.

Save dated Markdown and JSON reports under:

```text
data/reports/validation/weekly/
```

Also evaluate completed recommendation outcomes:

```powershell
python -m options_trading_assistant.cli validate-edge `
  --source packets `
  --packet-root data/journal/decision_packets `
  --scenario v4.2-forward `
  --evidence-kind forward `
  --output-dir data/reports/validation/forward
```

## Rules

Do not:

- Change v4.2 ranking logic during evidence collection.
- Change validation thresholds during evidence collection.
- Backfill missing days with mock data.
- Rewrite prior snapshots or reports.
- Count overlapping horizons as independent observations.
- Count multiple spreads from one ticker/date as independent setups.
- Interpret retrospective evidence as a validation pass.

If a strategy change becomes necessary, assign a new version, create a new frozen manifest, and start a separate evidence record.

## Status

Current retrospective evidence remains:

```text
INSUFFICIENT EVIDENCE
```

That is expected. The next task is accumulation, not optimization.
