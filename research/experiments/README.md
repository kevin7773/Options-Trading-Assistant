# Experiment Manifests

Experiment manifests are the permanent audit trail for strategy research.

The Strategy Registry records what the project believes. Experiment manifests record the specific tests that created or changed those beliefs.

## Purpose

Every material experiment should answer:

- What hypothesis was tested?
- What baseline was used?
- What dataset and period were evaluated?
- What artifacts were produced?
- What metrics were observed?
- What decision was made?
- Why should a future contributor trust or ignore the result?

## Manifest Schema

```yaml
experiment_id: EXP-YYYY-NNN
strategy: v4.3
baseline: v4.2
status: planned
layer: opportunity_visibility

hypotheses:
  - H-005

date_started:
date_completed:

owner: Options Trading Assistant

datasets:
  - name: 2023
    start: 2023-01-01
    end: 2023-12-31
  - name: 2024
    start: 2024-01-01
    end: 2024-12-31
  - name: 2025
    start: 2025-01-01
    end: 2025-12-31
  - name: 2026_ytd
    start: 2026-01-01
    end: 2026-06-30

inputs:
  strategy_config:
  universe_config:
  baseline_manifest:
  cache_dir:

artifacts:
  backtest_runs: []
  validation_reports: []
  decision_packets: []
  lifecycle_reports: []

results:
  expectancy:
  drawdown:
  win_rate:
  trade_count:
  average_win:
  average_loss:
  sector_results: {}
  score_bucket_results: {}

comparison:
  baseline_expectancy:
  baseline_drawdown:
  baseline_win_rate:
  baseline_trade_count:

success_criteria: {}
failure_criteria: {}

decision:
  status: pending
  rationale:
  decided_at:
```

## Layer Field

Every experiment manifest should declare the primary architectural layer it operates on.

Allowed values:

- `market`
- `opportunity_visibility`
- `opportunity_edge`
- `expression_edge`
- `execution`
- `outcome`
- `evidence`

Use the primary layer, not every downstream effect. For example:

- A distribution-day gate experiment belongs to `opportunity_visibility`.
- A confirmation-threshold experiment belongs to `opportunity_edge`.
- A strike-selection experiment belongs to `expression_edge`.
- An exit-rule experiment belongs to `execution`.

This makes the research archive navigable by decision-pipeline layer rather than only by chronology or strategy version.

## Decision Status

- `pending`: Experiment has not produced a final decision.
- `accepted`: Evidence supports promotion or adoption into a future frozen baseline.
- `rejected`: Evidence hit a failure condition or did not clear the promotion gate.
- `inconclusive`: Evidence is useful but insufficient.
- `superseded`: A newer experiment replaced this test.

Rejected and inconclusive manifests should remain in the repository. They are part of the research memory.
