# v4.3 Research Plan

v4.3 is a research branch, not a production baseline.

v4.2 remains frozen for prospective evidence collection. v4.3 exists to test declared hypotheses against the v4.2 benchmark without contaminating the live evidence stream.

## Baseline Comparator

All v4.3 experiments compare against:

- Version: `v4.2`
- Mode: `balanced`
- Universe: `universe_v2.yaml`
- Evaluation window: `2024-01-01` through `2026-06-30`
- Baseline run: `backtesting/results/v4.2-universe-v2-balanced-2024-2026ytd`

Baseline metrics:

| Metric | v4.2 Balanced |
|---|---:|
| Trades | 48 |
| Win rate | 60.4% |
| Expectancy | $61.64 |
| Average win | $145.76 |
| Average loss | -$66.75 |
| Max drawdown | -$362.57 |

## Promotion Gate

A v4.3 candidate must:

- Outperform v4.2 on expectancy.
- Maintain or improve maximum drawdown.
- Produce at least 40 trades over the evaluation window.
- Demonstrate improvement across multiple years, not a single favorable period.
- Avoid relying on one sector or a small group of tickers.
- Preserve or explain any degradation in Cloud / SaaS performance.
- Preserve the market-regime hard stop.
- Preserve decision packets, rejected candidates, lifecycle reports, and validation artifacts.

If a candidate fails any gate, it remains research-only.

## Primary Hypotheses

### H-005: Semiconductors Require a High-Beta Profile

Observation:

- v4.2 balanced Semiconductors: 8 trades, 25.0% win rate, -$203.29 total P/L.
- v4.2 high-probability Semiconductors: 7 trades, 28.6% win rate, -$293.68 total P/L.

Research profile:

```yaml
Semiconductors:
  strategy_profile: mean_reversion_high_beta
  confirmation_required: 3
  max_vix: 18
  preferred_long_strike: atm
  pullback_range: [7, 15]
```

Test question:

Does a higher-beta mean-reversion profile improve semiconductor outcomes without harming total portfolio expectancy, drawdown, or trade count?

### H-006: Cloud / SaaS Is a Canary Sector

Observation:

- v4.2 balanced Cloud / SaaS: 6 trades, 100.0% win rate, $907.20 total P/L.
- v4.2 high-probability Cloud / SaaS: 6 trades, 100.0% win rate, $986.40 total P/L.

Test question:

Do v4.3 changes preserve Cloud / SaaS performance, or do they degrade one of the strongest observed areas of the system?

Cloud / SaaS is not a production overweight until prospective evidence supports it. It is a sensitivity check for research changes.

### H-009: Expected-Move-Based Strike Selection

Test question:

Does selecting the long strike from expected move and reachability, instead of fixed moneyness alone, improve trade durability?

Candidate comparisons:

- Fixed slightly ITM.
- ATM.
- Expected-move adjusted.
- Sector-specific expected-move adjusted.

### H-010: Sector-Collapse Exit Enhancement

Test question:

Can stricter sector deterioration exits reduce losses when the original sector thesis fails after entry?

Candidate comparisons:

- Current sector-collapse exit.
- Earlier exit on sharper sector-score deterioration.
- Sector-relative exit against SPY and primary sector ETF.

### H-011: Synthetic Option Pricing v2

Test question:

Does a better synthetic options model improve trade selection without changing stock signals?

Candidate inputs:

- Strike moneyness.
- DTE.
- IV proxy.
- ATR / expected move.
- Distance to breakeven.
- Spread width.
- Sector volatility profile.

Pricing changes must be tested separately from signal-rule changes.

## Experiment Rules

1. Declare the hypothesis before running the test.
2. Change one concept at a time when possible.
3. Run the same date range and universe as v4.2.
4. Compare against v4.2 balanced and, when relevant, v4.2 high-probability.
5. Record the result in `docs/strategy_registry.md`.
6. Do not merge v4.3 evidence into v4.2 prospective tracking.
7. Do not update the frozen v4.2 baseline manifest.

## First Experiment Order

1. Add sector-specific profile support without enabling behavior changes by default.
2. Add a semiconductor `mean_reversion_high_beta` research profile.
3. Run v4.3 semiconductor-profile backtests over 2024 through 2026 YTD.
4. Compare total portfolio and semiconductor-only metrics against v4.2.
5. Update the Strategy Registry with the result.

## Current Decision

v4.3 is open for research. v4.2 remains the only prospective tracking baseline.
