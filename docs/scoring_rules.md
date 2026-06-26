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
