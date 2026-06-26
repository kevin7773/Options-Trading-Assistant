# Mean Reversion Bull Call Spread Scanner v4.0

## Project Purpose

Build a disciplined, data-driven options trading engine focused on high-quality bull call spread opportunities.

The system should prioritize capital preservation, quality, and repeatability over trade frequency. It should be comfortable recommending:

> SIT TODAY OUT

when no high-quality setup exists.

This project began as a mean reversion bull call spread scanner, but the long-term goal is to create a broader trading decision engine that can later support multiple options strategies.

---

## Core Philosophy

The scanner should not simply find oversold stocks.

It should find stocks that are:

1. In a supportive market.
2. In a leading sector.
3. In a longer-term uptrend.
4. Experiencing a controlled pullback.
5. Showing confirmation that buyers are returning.
6. Supported by liquid, fairly priced options.
7. Paired with a clear entry, exit, and risk-management plan.

Mean reversion should mean:

> Entering after a pullback begins to stabilize.

It should not mean:

> Catching falling knives.

---

## Key Lessons From Recent NVDA Trades

The recent NVDA trades exposed weaknesses in the first version of the strategy.

### Lessons Learned

1. Oversold is not enough.
2. Pullbacks can become downtrends.
3. Sector weakness can overwhelm individual stock strength.
4. Options spreads deteriorate quickly when price and time both move against the trade.
5. Profit-taking rules matter.
6. Confirmation should be required before entry.
7. The scanner should recommend no trade more often than it recommends a trade.
8. Capital preservation is part of the strategy.
9. Re-entering the same ticker too quickly can become revenge trading.
10. The system needs objective post-trade review.

---

## Recommended Project Architecture

Start with the data model and project structure before building the scanner.

Suggested repository layout:

```text
/config
    strategy.yaml
    scoring.yaml
    universe.yaml
    broker.yaml

/data
    market/
    sectors/
    stocks/
    options/
    journal/
    backtests/

/docs
    strategy_spec.md
    scoring_rules.md
    trade_management.md
    broker_integration.md

/src
    market_filter.py
    sector_ranker.py
    stock_scanner.py
    confirmation_engine.py
    option_scanner.py
    scoring_engine.py
    trade_manager.py
    paper_trader.py
    journal.py
    postmortem.py
    reporting.py

/backtesting
    backtest_runner.py
    strategy_versions/
    results/

/excel
    templates/
    outputs/

/tests
    test_market_filter.py
    test_sector_ranker.py
    test_scoring_engine.py
    test_trade_manager.py
```

---

## Strategy Versioning

Do not overwrite strategy logic without tracking versions.

Maintain strategy versions such as:

```text
Strategy v1: Original mean reversion
Strategy v2: Added confirmation filters
Strategy v3: Added sector rotation
Strategy v4: Configurable weights and post-trade analysis
Strategy v5: Optimized / machine-learned weighting
```

Each strategy version should be backtestable against the same historical periods.

The system should answer:

> Did this change actually improve performance?

---

## Configuration-Driven Design

Avoid hard-coding weights and thresholds.

Use configuration files so thresholds can be tuned later.

Example `strategy.yaml`:

```yaml
strategy_name: mean_reversion_bull_call_v4
mode: balanced

market:
  require_nasdaq_above_20dma: true
  require_spy_above_20dma: true
  max_vix_if_rising: 22
  max_distribution_days: 2

trade:
  min_days_to_expiration: 21
  max_days_to_expiration: 35
  max_debit_per_spread: 250
  min_reward_to_risk: 1.5
  preferred_spread_widths: [1, 5]

confirmation:
  minimum_signals_required: 2

cooling_off:
  enabled: true
  failed_trades_before_pause: 2
```

Example `scoring.yaml`:

```yaml
weights:
  market: 0.30
  sector: 0.15
  trend: 0.20
  confirmation: 0.20
  options: 0.15

thresholds:
  strong_buy: 90
  buy: 80
  watchlist: 70
```

---

## Operating Modes

The system should support three operating modes.

### Conservative

- A+ setups only.
- Highest quality.
- Few trades.
- Ideal for real-money deployment after validation.

### Balanced

- A and strong B setups.
- Moderate trade frequency.
- Default paper-trading mode.

### Aggressive

- B setups and above.
- More trades.
- Useful for comparison testing, not preferred for real money until validated.

Paper trade all three modes if possible and compare results.

---

## Daily Workflow

Each trading morning, the system should:

1. Evaluate market environment.
2. Rank sectors.
3. Identify leading sectors.
4. Scan strong stocks within leading sectors.
5. Apply trend filters.
6. Apply mean reversion filters.
7. Require confirmation signals.
8. Analyze options chains.
9. Score all candidates.
10. Recommend 0–3 trades.
11. If no trades qualify, output `SIT TODAY OUT`.
12. Log all recommendations, including rejected candidates.

---

## Market Filter

No new bullish spreads should be recommended when the broader market is hostile.

### Check

- Nasdaq relative to 20-day moving average.
- S&P 500 relative to 20-day moving average.
- VIX level and direction.
- Distribution days.
- Market breadth.
- Growth sector participation.
- Premarket futures if running before the open.

### Block Trades If

- Nasdaq is below the 20-day moving average.
- S&P 500 is below the 20-day moving average.
- VIX is above 22 and rising.
- Two consecutive distribution days occurred.
- Breadth is sharply negative.
- Risk-off action is broad-based.

### Output If Failed

```text
Today's Recommendation: SIT TODAY OUT
Reason: Market conditions are unfavorable for new bullish mean reversion spreads.
```

---

## Sector Rotation Filter

The scanner should begin with sector leadership.

It should not default to semiconductors just because they are familiar.

### Sectors To Track

- Technology
- Semiconductors
- Cybersecurity
- Cloud / SaaS
- Industrials
- Aerospace & Defense
- Financials
- Healthcare
- Energy
- Utilities
- Consumer Discretionary
- Consumer Staples
- Communication Services

### Suggested Sector ETFs

```text
Technology: XLK
Semiconductors: SMH, SOXX
Cybersecurity: CIBR, HACK
Cloud / SaaS: SKYY, WCLD
Industrials: XLI
Aerospace & Defense: ITA, XAR
Financials: XLF
Healthcare: XLV
Energy: XLE
Utilities: XLU
Consumer Discretionary: XLY
Consumer Staples: XLP
Communication Services: XLC
```

### Sector Score Inputs

- 1-day relative strength vs. SPY.
- 5-day relative strength vs. SPY.
- 20-day relative strength vs. SPY.
- Price relative to 20-day moving average.
- Price relative to 50-day moving average.
- Volume trend.
- Momentum.
- Whether sector is recovering or still breaking down.

Only the top 3–5 sectors should move to stock scanning.

---

## Stock Trend Filter

A stock must remain in a longer-term uptrend.

### Requirements

- Price above 100-day moving average.
- Price above 200-day moving average.
- Positive 90-day trend.
- Not making repeated lower lows.
- Not underperforming its sector badly.

### Reject If

- Price is below the 200-day moving average.
- 90-day trend is negative.
- Stock has broken major support.
- Stock is underperforming both SPY and its sector ETF.

---

## Mean Reversion Filter

The ideal candidate is a strong stock pulling back into support.

### Requirements

- 5–12% below recent swing high.
- RSI below approximately 40.
- Pullback near logical support.
- Selling volume declining or stabilizing.
- Long-term trend structure still intact.

### Reject If

- Company-specific fundamentals deteriorated.
- Stock is falling on expanding volume.
- No buyer response is visible.
- Stock is still making new lows without stabilization.

---

## Confirmation Filter

This is mandatory.

Do not buy only because a stock is oversold.

### Require At Least Two

- Green daily candle.
- Higher low.
- Close above previous day's high.
- RSI turning upward.
- MACD histogram improving.
- Stock outperforming Nasdaq.
- Stock outperforming sector ETF.
- Reclaim of 20-day moving average.
- Reclaim of VWAP.
- Strong close in upper half of daily range.

### Ideal Confirmation

- Pullback into support.
- Reversal candle.
- Improving relative strength.
- Sector participation.
- Favorable options pricing.

---

## Options Filter

Only consider liquid, fairly priced spreads.

### Preferred Structure

- Bull call spread.
- 21–35 days to expiration.
- $5-wide spreads as default.
- $1-wide spreads allowed for lower-cost testing.
- Long call delta around 0.35–0.55.
- Short call near realistic upside target or resistance.
- Debit generally 35–55% of spread width.

### Liquidity Requirements

- Open interest above 500 on both legs when possible.
- Tight bid/ask spread.
- Good option volume.
- Avoid illiquid contracts.

### Risk / Reward Requirements

- Reward-to-risk at least 1.5:1.
- Max loss under $250 per spread unless explicitly approved.
- Breakeven must be realistic based on expected move and ATR.
- Avoid spreads requiring extreme price movement.

### Implied Volatility Rules

Prefer:

- IV not excessively inflated versus historical volatility.
- Avoid entering immediately before major binary events unless intentionally trading the event.
- Avoid paying extreme premium after volatility spikes.

---

## Scoring Model

Each trade receives a 100-point score.

| Category | Points |
|---|---:|
| Market Environment | 30 |
| Sector Strength | 15 |
| Stock Trend | 20 |
| Confirmation | 20 |
| Options Quality | 15 |
| **Total** | **100** |

### Interpretation

| Score | Action |
|---:|---|
| 95–100 | A+ setup. Rare, highest quality. |
| 90–94 | A setup. Strong candidate. |
| 80–89 | B setup. Tradable if risk is acceptable. |
| 70–79 | Watchlist only. |
| Below 70 | No trade. |

### Recommendation Rules

- Recommend only trades scoring 80+.
- Prefer trades scoring 90+.
- If no trades score 80+, output `SIT TODAY OUT`.
- If market filter fails, output `SIT TODAY OUT` regardless of individual scores.

---

## Trade Recommendation Format

Each recommendation should include:

```text
Ticker:
Sector:
Setup Grade:
Confidence Score:
Expiration:
Long Call:
Short Call:
Spread Width:
Target Debit:
Max Profit:
Max Loss:
Breakeven:
Why This Trade:
Key Risks:
Entry Trigger:
Profit Target:
Stop / Invalidating Condition:
Management Plan:
```

---

## Example Recommendation

```text
Ticker: XYZ
Sector: Healthcare
Setup Grade: A
Confidence Score: 92/100

Trade:
Buy XYZ 100 Call
Sell XYZ 105 Call
Expiration: YYYY-MM-DD
Target Debit: $2.00–$2.20
Max Value: $5.00
Max Profit: $280–$300
Max Loss: $200–$220
Breakeven: $102.10

Why:
- Healthcare is a top-ranked sector today.
- XYZ remains above its 100-day and 200-day moving averages.
- Stock pulled back 7% into support.
- RSI turned upward from oversold territory.
- Stock closed above the previous day's high.
- Options are liquid with acceptable bid/ask spreads.

Entry Trigger:
Only enter if XYZ holds above $100 after the first 30–60 minutes of trading.

Profit Plan:
Consider taking profits if the spread reaches 60–75% of max gain.

Stop / Invalidating Condition:
Exit or reassess if XYZ closes below $97 or if market filter flips bearish.
```

---

## Exit Rules

Every trade must have exit rules before entry.

### Profit Taking

- Take profits at 60–75% of max possible gain.
- Do not require holding to expiration.
- If the spread gains 40–50% quickly, consider scaling out or tightening stop rules.

### Loss Management

Exit or reassess if:

- Stock violates the technical reason for entry.
- Sector falls out of leadership.
- Market filter turns bearish.
- Spread loses 50–60% of value with no recovery evidence.
- Stock closes below support level that justified entry.

### Time Management

Avoid holding into final week unless:

- Stock is above short strike.
- Spread is already profitable.
- Market and sector conditions remain favorable.

---

## Cooling-Off Rule

If two consecutive bullish spreads fail in the same ticker, place that ticker on a cooling-off list.

### Cooling-Off Exit Criteria

Do not consider another bullish spread in that ticker until:

- Stock reclaims the 20-day moving average, or
- Stock breaks above a recent swing high, or
- Stock outperforms both SPY and its sector ETF for several sessions.

This prevents repeatedly buying a stock simply because it looks cheaper.

---

## Paper Trading Integration

Use paper trading before risking real money.

MooMoo / Futu OpenAPI can be evaluated for:

- Market data.
- Historical data.
- Options chains.
- Paper order placement.
- Position monitoring.
- Trade logging.

Codex should build the system so broker integration is modular.

Suggested interface:

```python
class BrokerInterface:
    def get_quote(self, symbol): ...
    def get_option_chain(self, symbol, expiration): ...
    def place_paper_order(self, order): ...
    def get_positions(self): ...
    def close_position(self, position_id): ...
```

This allows replacing MooMoo later if needed.

---

## Paper Trading Requirements

Every recommendation should be paper tradable.

The system should log:

- Recommendation generated.
- Whether trade was entered.
- Entry price.
- Simulated fill.
- Position Greeks.
- Daily mark-to-market.
- Exit price.
- Final P/L.
- Reason for exit.

---

## Trade Journal

Every recommendation and trade should be logged.

### Required Columns

- Date
- Strategy Version
- Mode
- Ticker
- Sector
- Trade Type
- Expiration
- Long Strike
- Short Strike
- Entry Debit
- Exit Credit
- Max Profit
- Max Loss
- Breakeven
- Market Score
- Sector Score
- Trend Score
- Confirmation Score
- Options Score
- Total Score
- Entry Rationale
- Exit Rationale
- Outcome
- Notes
- Mistakes / Lessons

### Review Cadence

Review after:

- Every 10 trades.
- Every 25 trades.
- Every 50 trades.
- Every strategy version change.

Track:

- Win rate.
- Average win.
- Average loss.
- Profit factor.
- Average holding time.
- Best sectors.
- Worst sectors.
- Best score ranges.
- Trades avoided by filters.
- Whether confirmation filters improved results.

---

## Post-Mortem Generator

Every closed trade should generate a post-mortem.

Especially losing trades.

Example:

```text
Trade #42
Ticker: NVDA
Result: -48%

Market Score: Weak
Sector Score: Weak
Trend Score: Broken
Confirmation Score: Failed
Options Score: Acceptable

Primary Failure:
Entered before confirmation.

Secondary Failure:
Sector remained weak after entry.

Recommended Rule Change:
Require reclaim of 20-day moving average before re-entering a ticker with two recent failed bullish spreads.
```

The post-mortem engine should identify recurring failure patterns.

---

## Position Management Engine

The system should evaluate every open trade daily.

For each position, output:

```text
Ticker:
Current Spread Value:
Entry Debit:
Current P/L:
Days to Expiration:
Stock Price:
Distance to Breakeven:
Market Status:
Sector Status:
Technical Status:
Greeks:
Recommendation:
Reason:
```

Possible recommendations:

- Hold.
- Take profit.
- Scale out.
- Tighten stop.
- Reassess.
- Close.
- Let expire only if risk/reward justifies it.

---

## Excel Workbook Structure

Recommended tabs:

1. `Market Dashboard`
2. `Sector Rankings`
3. `Candidate Stocks`
4. `Options Spreads`
5. `Trade Journal`
6. `Rules and Scoring`
7. `Closed Trade Review`
8. `Cooling-Off List`
9. `Paper Trades`
10. `Backtest Results`
11. `Strategy Versions`

---

## Suggested Build Plan

### Phase 1: Project Skeleton

- Create folders.
- Create config files.
- Define data models.
- Create basic CLI or notebook entrypoint.

### Phase 2: Excel Workbook

- Build workbook tabs.
- Add formulas where useful.
- Add export/report functions.

### Phase 3: Market and Sector Engine

- Score market environment.
- Rank sectors.
- Output top sectors.

### Phase 4: Stock Scanner

- Scan stocks within top sectors.
- Apply trend and mean reversion filters.
- Apply confirmation rules.

### Phase 5: Options Scanner

- Pull option chains.
- Generate candidate bull call spreads.
- Score liquidity, debit, breakeven, and risk/reward.

### Phase 6: Scoring Engine

- Combine market, sector, trend, confirmation, and options scores.
- Produce ranked candidates.
- Output `SIT TODAY OUT` if no candidate qualifies.

### Phase 7: Paper Trading

- Connect to broker interface.
- Place simulated trades.
- Track open positions.
- Mark to market daily.

### Phase 8: Backtesting

- Backtest historical setups.
- Compare strategy versions.
- Track performance by market regime and sector.

### Phase 9: Post-Mortems

- Generate post-trade analysis.
- Identify recurring failure modes.
- Recommend rule improvements.

### Phase 10: Optimization

- Adjust weights based on historical performance.
- Compare conservative, balanced, and aggressive modes.
- Validate before any real-money deployment.

---

## High-Level Pseudocode

```python
def run_daily_scanner(mode="balanced"):
    config = load_strategy_config(mode)

    market_score = score_market_environment(config)

    if market_score < config.minimum_market_threshold:
        return sit_today_out("Market filter failed")

    sectors = rank_sectors()
    eligible_sectors = sectors.top(config.max_sectors)

    candidates = []

    for sector in eligible_sectors:
        stocks = get_sector_leaders(sector)

        for stock in stocks:
            trend_score = score_trend(stock)
            mean_reversion_score = score_mean_reversion(stock)
            confirmation_score = score_confirmation(stock)

            if trend_score < config.trend_threshold:
                continue

            if confirmation_score < config.confirmation_threshold:
                continue

            option_spreads = scan_bull_call_spreads(stock)

            for spread in option_spreads:
                options_score = score_options_quality(spread)

                total_score = calculate_weighted_score(
                    market_score=market_score,
                    sector_score=sector.score,
                    trend_score=trend_score,
                    confirmation_score=confirmation_score,
                    options_score=options_score,
                    weights=config.weights
                )

                if total_score >= config.minimum_trade_score:
                    candidates.append({
                        "stock": stock,
                        "sector": sector,
                        "spread": spread,
                        "score": total_score
                    })

    if not candidates:
        return sit_today_out("No setups met the minimum quality threshold")

    return rank_candidates(candidates)
```

---

## Broker Integration Notes

Broker integration should be treated as replaceable infrastructure.

Do not couple the strategy logic directly to MooMoo, Futu, Interactive Brokers, Schwab, or any single provider.

Use adapters.

Example:

```text
Strategy Engine
      |
Broker Interface
      |
MooMoo Adapter / Futu Adapter / Future Broker Adapter
```

The strategy engine should not care where the data comes from.

---

## Risk Management Principles

The system should act like a disciplined risk manager, not an idea generator.

### Rules

- No trade is always an acceptable answer.
- Never force a trade.
- Never recommend a trade solely because a stock is down.
- Never re-enter a cooling-off ticker without confirmation.
- Never ignore market regime.
- Always define max loss.
- Always define invalidation.
- Always log the result.

---

## Long-Term Expansion

The market, sector, trend, and confirmation engine can later support:

- Bull call spreads.
- Bull put spreads.
- Covered calls.
- Cash-secured puts.
- LEAPS.
- Long stock swing trades.
- Portfolio exposure monitoring.

Start with bull call spreads, but design the system so it can expand.

---

## Final Design Goal

The system should become a disciplined trading assistant.

It should:

- Protect capital.
- Prefer high-quality setups.
- Say `SIT TODAY OUT` often.
- Track every recommendation.
- Learn from every trade.
- Improve through evidence.
- Avoid emotional or revenge trading.
- Support paper trading before real capital is risked.

A quiet scanner is a feature, not a bug.
