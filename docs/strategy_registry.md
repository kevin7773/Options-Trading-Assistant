# Strategy Registry

The Strategy Registry tracks validated research hypotheses. Versions describe frozen releases; hypotheses describe what the project believes, why it believes it, and what evidence would change that belief.

This registry prevents the project from chasing a single green backtest. Every proposed strategy change should map to a hypothesis, an evidence class, and a promotion decision.

## Status Definitions

- `Accepted`: Evidence supports the hypothesis and the decision is part of the production baseline.
- `Active`: The hypothesis is currently being tested and must not be promoted without satisfying its success criteria.
- `Rejected`: Testing did not improve the baseline, introduced unacceptable tradeoffs, or hit its failure condition.
- `Proposed`: The idea is plausible but not yet tested.

## Evidence Classes

- `Diagnostic`: Useful for explaining behavior, not sufficient for promotion.
- `Retrospective`: Multi-year backtest or historical ranking evidence.
- `Holdout`: Predeclared untouched historical period.
- `Prospective`: Immutable forward snapshots and decision packets collected after the hypothesis was frozen.

Only holdout and prospective evidence can validate a production baseline. Retrospective evidence can justify freezing a hypothesis for prospective tracking, but it should not be treated as proof by itself.

## Promotion Gate

A candidate baseline must outperform the current frozen baseline before it can replace it.

For the current project stage, a future version must:

- Outperform v4.2 on expectancy.
- Maintain or improve maximum drawdown.
- Produce at least 40 trades over the 2024 through 2026 YTD evaluation window.
- Demonstrate improvement across multiple years, not a single favorable period.
- Avoid relying on one sector or a small group of tickers.
- Preserve or explain any degradation in Cloud / SaaS performance.
- Preserve the market-regime hard stop and frozen-baseline validation discipline.

## Hypothesis Requirements

Every hypothesis should include:

- A stable hypothesis ID.
- A baseline comparator.
- A success condition that defines promotion.
- A failure condition that defines when to stop pursuing the idea.
- Evidence links or artifact names.
- A decision that can be understood without rerunning the experiment.

Rejected hypotheses are institutional knowledge. They should remain in the registry so the project does not revisit the same idea without new evidence.

Material tests should also create an experiment manifest under `research/experiments/`. The manifest records datasets, artifacts, metrics, success criteria, failure criteria, and the final decision.

## Registry

| ID | Hypothesis | Status | Baseline | Evidence | Decision |
|---|---|---|---|---|---|
| H-001 | Market regime filter improves expectancy by preventing trades against broad conditions. | Accepted | v3.0 | Backtest plus prospective rejection evidence. | Production: keep as a non-negotiable gate. |
| H-002 | ATM or slightly ITM call spreads improve mean-reversion construction versus OTM debit spreads. | Accepted | v4.0 | Multi-year backtest and lifecycle diagnostics. | Production: use mean-reversion recovery construction. |
| H-003 | Reachability guard reduces false positives by requiring the long strike to be reachable within expected move. | Accepted | v4.1 | Backtest comparison and v4.2 frozen construction. | Production: keep reachability guard. |
| H-004 | High-probability mode improves overall performance versus balanced mode. | Rejected | v4.2 | Higher drawdown and fewer trades despite slightly higher expectancy. | Stay on balanced; keep high-probability research-only unless new evidence appears. |
| H-005 | Semiconductors require the tested high-beta recovery profile. | Rejected | v4.2 | `EXP-2026-001`: expectancy declined, drawdown worsened, and semiconductor losses increased. | Do not promote this profile; open a new hypothesis for any different semiconductor treatment. |
| H-006 | Pre-entry scores, rejection context, and skipped environments can predict future trade quality. | Active | v4.2 | Prospective decision packets now record measurement-only features before outcomes are known. | Collect data only; compare recommendations, near-misses, and sit-out environments before changing rules. |
| H-012 | Cloud / SaaS is a priority research sector for this strategy family. | Active | v4.2 | Strong small-sample results across v4.2 balanced and high-probability comparisons. | Track as a canary sector; do not overweight production yet. |
| H-013 | Universe v2 metadata improves research quality by making ticker treatment explicit. | Active | v4.2 | Universe v2 backtest completed with 182 scan stocks and positive expectancy. | Keep Universe v2 as active research asset. |

## H-005 Success And Failure Conditions

```yaml
hypothesis_id: H-005
status: rejected

success:
  semiconductor_expectancy_gt_baseline: true
  semiconductor_drawdown_lte_baseline: true
  overall_strategy_expectancy_gte_baseline: true
  overall_strategy_drawdown_lte_baseline: true
  minimum_total_trades: 40

failure:
  overall_expectancy_declines: true
  overall_drawdown_increases_materially: true
  trade_count_drops_below_minimum_threshold: true
  semiconductor_results_do_not_improve: true

decision:
  status: rejected
  experiment: EXP-2026-001
  rationale: >
    Overall expectancy declined from 61.64 to 44.98, maximum drawdown worsened
    from -362.57 to -528.82, and semiconductor total P/L worsened from -203.29
    to -590.62.
```

## H-006 Measurement Plan

H-006 does not change strategy behavior. It asks whether the existing scoring system is calibrated enough to predict trade quality before entry.

```yaml
hypothesis_id: H-006
name: pre_entry_trade_quality_calibration
status: active
baseline: v4.2
measurement_only: true

features_recorded:
  provenance:
    - engine_commit
    - strategy_commit
    - strategy_version
    - research_branch
    - dashboard_version
  decision_context:
    - decision_type
    - recommended
    - rejected
    - sit_out
    - action
    - reason
    - stage
    - score_observed
  scores:
    - score_total
    - score_bucket
    - market_score_raw
    - score_breakdown.market
    - score_breakdown.sector
    - score_breakdown.trend
    - score_breakdown.confirmation
    - score_breakdown.options
    - stock_setup_score
  market:
    - vix
    - vix_rising
    - distribution_days
    - breadth_score
    - growth_participation_score
  sector:
    - sector_score
    - relative_strength_1d
    - relative_strength_5d
    - relative_strength_20d
  stock:
    - sector_relative_strength
    - trend_90d
    - drawdown_from_swing_high_pct
    - rsi
    - confirmation_signal_count
  spread:
    - expected_move_pct
    - atr_proxy_pct
    - distance_to_long_strike
    - distance_to_short_strike
    - iv_rank
    - debit_pct_of_width
    - reward_to_risk

future_questions:
  - Do 90+ score trades outperform 80-89 score trades?
  - Does confirmation score predict win rate or average loss?
  - Does distance to long strike predict max adverse excursion?
  - Does IV rank or expected move identify fragile entries?
  - Do rejected near-misses outperform completed recommendations?
  - Do sit-out days avoid worse forward market environments?
```

## Candidate v4.3 Research Hypotheses

These ideas are explicitly research-only. They must not modify v4.2 prospective tracking.

| ID | Hypothesis | Test Shape | Promotion Concern |
|---|---|---|---|
| H-008 | A different semiconductor treatment may improve results after H-005 failed. | Declare a new profile before testing; do not reuse the failed H-005 assumptions. | Must explain why it should avoid the H-005 failure mode. |
| H-009 | Expected-move-based strike selection improves spread construction durability. | Compare fixed moneyness versus expected-move-derived long strike placement. | Must improve expectancy without reducing trade count below promotion gate. |
| H-010 | Sector-collapse exits reduce losses after the original sector thesis fails. | Compare lifecycle outcomes with and without stricter post-entry sector deterioration exits. | Must reduce drawdown without cutting winners too early. |
| H-011 | Improved synthetic option pricing changes trade selection quality. | Replace v1 pricing assumptions with calibrated IV/expected-move/debit estimates and compare identical signals. | Must separate pricing improvement from strategy-rule changes. |

## Change Control

When a hypothesis changes rules, thresholds, construction, universe treatment, exits, or validation criteria:

1. Assign or update a hypothesis ID.
2. Declare the expected improvement before running the experiment.
3. Run the candidate against the same evaluation window as v4.2.
4. Compare against the frozen v4.2 baseline.
5. Record the decision in this registry.
6. If promoted, create a new strategy version and frozen baseline manifest.

The registry should preserve rejected and inconclusive ideas. Negative evidence is a project asset.
