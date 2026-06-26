from datetime import date

from options_trading_assistant.cli import format_result
from options_trading_assistant.models import (
    RecommendationAction,
    RejectedCandidate,
    RejectionStage,
    ScanResult,
)


def test_format_result_includes_rejection_summary_for_sit_today_out():
    result = ScanResult(
        action=RecommendationAction.SIT_TODAY_OUT,
        mode="balanced",
        strategy_version="v4.0",
        as_of=date(2026, 6, 26),
        reason="No setups met the minimum quality threshold.",
        market_score=18.5,
        rejections=(
            RejectedCandidate(
                stage=RejectionStage.CONFIRMATION,
                ticker="ISRG",
                score=10.2,
                reasons=(
                    "Insufficient confirmation signals (0/2).",
                    "Selling volume is not stabilizing.",
                ),
            ),
        ),
        rejected_count=1,
    )

    output = format_result(result)

    assert "Rejected Candidates:" in output
    assert "[confirmation] ISRG score=10.20" in output
    assert "Insufficient confirmation signals" in output


def test_format_result_truncates_long_rejection_reasons():
    result = ScanResult(
        action=RecommendationAction.SIT_TODAY_OUT,
        mode="balanced",
        strategy_version="v4.0",
        as_of=date(2026, 6, 26),
        reason="No setups met the minimum quality threshold.",
        market_score=18.5,
        rejections=(
            RejectedCandidate(
                stage=RejectionStage.OPTIONS,
                ticker="MSFT",
                long_call=380,
                short_call=385,
                reasons=("one", "two", "three", "four", "five"),
            ),
        ),
        rejected_count=1,
    )

    output = format_result(result)

    assert "[options] MSFT 380/385" in output
    assert "one; two; three; +2 more" in output
