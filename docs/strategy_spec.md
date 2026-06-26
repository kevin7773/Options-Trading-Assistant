# Strategy Spec

The source strategy brief is `Mean_Reversion_Bull_Call_Scanner_v4.md`.

This implementation starts with the v4 bull call spread workflow:

1. Score the market environment.
2. Block new bullish trades when the market gate fails.
3. Rank sectors and only scan the strongest sectors.
4. Require longer-term stock trend, controlled pullback, and confirmation.
5. Score candidate bull call spreads for liquidity, pricing, and risk/reward.
6. Return `SIT TODAY OUT` when no candidate clears the configured mode threshold.

The scanner currently uses deterministic mock data while the code shape is validated.
