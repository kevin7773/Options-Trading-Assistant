# Strategy Registry

The Strategy Registry tracks validated research hypotheses. Versions describe frozen releases; hypotheses describe what the project believes, why it believes it, and what evidence would change that belief.

This registry prevents the project from chasing a single green backtest. Every proposed strategy change should map to a hypothesis, an evidence class, and a promotion decision.

## Status Definitions

- `Proposed`: The idea is plausible but not yet tested.
- `Under investigation`: Early evidence exists, but the result is not durable enough to change the baseline.
- `Not validated`: Testing did not improve the baseline or introduced unacceptable tradeoffs.
- `Validated`: Evidence supports the hypothesis across the declared evaluation window.
- `Prospective`: The hypothesis is frozen into the active forward-tracking baseline and is being observed live.
- `Rejected`: Evidence or implementation risk makes the idea unsuitable for this strategy family.

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

## Registry

| ID | Hypothesis | Status | Evidence | Current Decision |
|---|---|---|---|---|
| H-001 | Market regime filter improves expectancy by preventing trades against broad conditions. | Prospective | Daily scanner behavior, rejection packets, v4.2 backtests. | Keep as a non-negotiable gate. |
| H-002 | ATM or slightly ITM call spreads express mean-reversion recovery better than OTM debit spreads. | Validated, pending more years | v4.1/v4.2 strike-selection comparisons and improved lifecycle results. | Use mean-reversion recovery construction for v4.2. |
| H-003 | Reachability guard reduces false positives by requiring the long strike to be reachable within expected move. | Validated | v4.1 comparison and v4.2 frozen construction. | Keep in frozen baseline. |
| H-004 | High-probability mode improves risk-adjusted returns versus balanced mode. | Not validated | 2024-2026 YTD comparison: slightly higher win rate and expectancy, but fewer trades and worse drawdown. | Do not replace balanced v4.2. Keep as research-only. |
| H-005 | Semiconductors require a separate high-beta mean-reversion profile. | Under investigation | Balanced and high-probability runs both showed weak semiconductor performance. | Test sector-specific profile in v4.3 research only. |
| H-006 | Cloud / SaaS is a priority research sector for this strategy family. | Under investigation | Strong small-sample results across v4.2 balanced and high-probability comparisons. | Track as a canary sector; do not overweight production yet. |
| H-007 | Universe v2 metadata improves research quality by making ticker treatment explicit. | Under investigation | v4.2 Universe v2 backtest completed with 182 scan stocks and positive expectancy. | Keep Universe v2 as active research asset. |

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
