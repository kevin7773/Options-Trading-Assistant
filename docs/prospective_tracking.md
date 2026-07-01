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
- Durable milestone summaries under `research/prospective_validation.md`.
- A simple forward evidence log under `research/prospective_validation_log.csv`.

When the market gate passes, verify that the new signal-ranking snapshot contains:

- Strategy version `v4.2`.
- The Top 10 ranked stocks.
- The full contemporaneous stock universe.
- The top-ranked sector ETF.
- Component scores and qualification status.

Never rewrite or replace older signal-ranking snapshots.

Recommendation decision packets also record H-006 measurement-only pre-entry features. These features support future calibration analysis and must not change the current v4.2 trading decision.

The prospective validation log should keep future outcome columns blank until their horizons mature. This preserves what was known at decision time.

## H-008 Shadow Workflow

H-008 is an active research hypothesis, not a promoted rule change. The frozen v4.2 baseline remains the only production prospective stream.

Historical holdout:

- None predeclared. After the retrospective H-008 evaluation on 2024 through 2026 YTD, no clean untouched historical window remains designated for this hypothesis.
- Treat H-008 confirmation as a forward-evidence task starting on 2026-07-02 and keep the production baseline unchanged until promotion criteria are met.

Daily shadow collection:

- Run the normal v4.2 daily collection first.
- Then run the H-008 candidate in shadow mode using the consecutive distribution-day rule.
- Save H-008 artifacts under `data/research/h008/` only. Do not write them into the v4.2 production journal tree.

Command:

```powershell
python -m options_trading_assistant.cli h008-shadow-scan `
  --provider moomoo `
  --mode balanced `
  --date (Get-Date -Format "yyyy-MM-dd")
```

Shadow artifact locations:

- `data/research/h008/journal/scan_results.jsonl`
- `data/research/h008/decision_packets/`
- `data/research/h008/signal_rankings/`
- `data/research/h008/reports/daily/`

Interpretation rules:

- v4.2 remains the live baseline.
- H-008 shadow outcomes are measurement only.
- Do not merge, backfill, or rewrite shadow artifacts after creation.

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

For H-008, run the same forward packet validation against the shadow packet root and keep the outputs separate from v4.2:

```powershell
python -m options_trading_assistant.cli validate-edge `
  --source packets `
  --packet-root data/research/h008/decision_packets `
  --scenario h008-forward `
  --evidence-kind forward `
  --output-dir data/reports/validation/h008-forward
```

H-008 Saturday checklist:

- Confirm the baseline v4.2 run and the H-008 shadow run both exist for each completed trading day since the prior review.
- Report newly admitted H-008 buy dates: dates where v4.2 sat out but H-008 produced one or more recommendation packets.
- Report newly admitted H-008 total P/L and count only horizons that have fully matured.
- Report `Opportunity Recovery Rate` for the review window:
  - Blocked by v4.2
  - Allowed by H-008
  - Passed all downstream filters
  - Paper trades
  - Recovery rate = `paper trade dates / H-008-allowed disagreement dates`
- Use `Opportunity Recovery Rate` to answer:
  - "When H-008 disagrees with production, how often does that disagreement actually matter?"
- Compare v4.2 versus H-008 on matured packet outcomes:
  - trade count
  - expectancy
  - max drawdown
  - win rate
- Break matured H-008 comparisons down by:
  - 2024
  - 2025
  - 2026 YTD or current year-to-date
- Break matured H-008 comparisons down by sectors of interest:
  - Cloud / SaaS
  - Communication Services
  - Healthcare
  - Semiconductors
  - Utilities
  - Financials
- Compare H-006-style pre-entry features for newly admitted H-008 trades versus the v4.2 baseline trade population:
  - market score
  - sector score
  - confirmation count
  - stock setup score
  - distance to long strike versus expected move
- Include a short promotion-readiness block for H-008:
  - Retrospective Evidence: 1 to 5 stars
  - Mechanism Understood: 1 to 5 stars
  - Prospective Evidence: 1 to 5 stars
  - Promotion Readiness: percentage estimate
- The percentage is communication, not math. Use it to convey whether the idea appears strong but evidence is still immature.
- State clearly whether H-008 evidence is still:
  - insufficient
  - improving but immature
  - promotion-eligible

Earliest meaningful H-008 review:

- Do not treat 21 calendar days as sufficient.
- The earliest serious review is after the first non-trivial H-008 shadow sample has matured through the full 20-trading-day horizon.
- Promotion still requires broader forward evidence, not one matured cohort.

## Month-End Gate Effectiveness Review

At the end of each month, summarize whether the scanner's hard stops and opportunity filters avoided weak forward environments.

Use one observation per scan date. Do not count multiple packets from the same date as independent gate observations.

Measure forward market outcomes as:

- `5-Day Outcome`: SPY close-to-close return from the scan date through the fifth subsequent US trading session.
- `21-Day Outcome`: SPY close-to-close return from the scan date through the twenty-first subsequent US trading session.

Keep an outcome blank until its trading-session horizon has matured. Report both average and median returns so a single shock does not dominate interpretation.

Required table:

| Gate | Times Triggered | Average 5-Day Outcome | Median 5-Day Outcome | Average 21-Day Outcome | Median 21-Day Outcome |
|---|---:|---:|---:|---:|---:|
| Distribution Days | 0 | pending | pending | pending | pending |
| Below 20 DMA | 0 | pending | pending | pending | pending |
| High VIX | 0 | pending | pending | pending | pending |
| No Stock Setup | 0 | pending | pending | pending | pending |

The review asks whether each gate is informative, not whether it agrees with the original design. Favorable, unfavorable, and inconclusive results all remain part of the prospective research record.

Do not change a gate from one month of evidence. Any proposed change must become a documented hypothesis with predefined promotion and rejection criteria.

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
