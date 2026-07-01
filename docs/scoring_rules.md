# Scoring Rules

The current scanner uses a 100-point model:

| Category | Points |
|---|---:|
| Market Environment | 30 |
| Sector Strength | 15 |
| Stock Trend | 20 |
| Confirmation | 20 |
| Options Quality | 15 |

Mode thresholds live in `config/strategy.yaml`.

The first implementation makes each score deterministic and testable. Future work should split each category into explicit sub-rules in this document before optimizing weights.

## Market Gate Notes

The market gate includes a configurable distribution-day rule under `config/strategy.yaml`:

```yaml
market:
  distribution_days:
    lookback_bars: 10
    max_count_in_window: 2
    require_consecutive: false
    min_drop_pct: 0.2
```

A distribution day qualifies when the market proxy closes down versus the prior session, volume rises versus the prior session, and the decline meets the configured minimum drop percentage.

- `lookback_bars`: rolling session window to inspect.
- `max_count_in_window`: block threshold inside that window.
- `require_consecutive`: when `true`, only consecutive flagged sessions count toward the threshold.
- `min_drop_pct`: minimum one-day decline required for a flagged distribution day.

This supports three research variants cleanly:

- Current live baseline: `2 in 10`
- Proposed candidate: `2 in 5`
- Original writeup: `2 consecutive`
