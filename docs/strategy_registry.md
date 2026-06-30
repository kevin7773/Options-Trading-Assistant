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

## Registry

| ID | Hypothesis | Status | Baseline | Evidence | Decision |
|---|---|---|---|---|---|
| H-001 | Market regime filter improves expectancy by preventing trades against broad conditions. | Accepted | v3.0 | Backtest plus prospective rejection evidence. | Production: keep as a non-negotiable gate. |
| H-002 | ATM or slightly ITM call spreads improve mean-reversion construction versus OTM debit spreads. | Accepted | v4.0 | Multi-year backtest and lifecycle diagnostics. | Production: use mean-reversion recovery construction. |
| H-003 | Reachability guard reduces false positives by requiring the long strike to be reachable within expected move. | Accepted | v4.1 | Backtest comparison and v4.2 frozen construction. | Production: keep reachability guard. |
| H-004 | High-probability mode improves overall performance versus balanced mode. | Rejected | v4.2 | Higher drawdown and fewer trades despite slightly higher expectancy. | Stay on balanced; keep high-probability research-only unless new evidence appears. |
| H-005 | Semiconductors require a high-beta recovery profile. | Active | v4.2 | v4.3 research branch; balanced and high-probability runs both showed weak semiconductor results. | Pending: test sector-specific profile before changing production. |
| H-006 | Cloud / SaaS is a priority research sector for this strategy family. | Active | v4.2 | Strong small-sample results across v4.2 balanced and high-probability comparisons. | Track as a canary sector; do not overweight production yet. |
| H-007 | Universe v2 metadata improves research quality by making ticker treatment explicit. | Active | v4.2 | Universe v2 backtest completed with 182 scan stocks and positive expectancy. | Keep Universe v2 as active research asset. |

## H-005 Success And Failure Conditions

```yaml
hypothesis_id: H-005

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
```

## Candidate v4.3 Research Hypotheses

These ideas are explicitly research-only. They must not modify v4.2 prospective tracking.

| ID | Hypothesis | Test Shape | Promotion Concern |
|---|---|---|---|
| H-008 | Semiconductors improve under a `mean_reversion_high_beta` profile with stronger confirmation, lower volatility tolerance, ATM strikes, and deeper pullback range. | Compare semiconductor-only and portfolio-level performance against v4.2. | Must improve semiconductors without hurting total drawdown or concentrating edge. |
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
