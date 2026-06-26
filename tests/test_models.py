from datetime import date
import json

from options_trading_assistant.models import RankedSector, RejectedCandidate, RejectionStage, ScanContext, ScanResult, RecommendationAction
from options_trading_assistant.reports.journal import json_default


def test_rejected_candidate_captures_stage_reasons_and_optional_trade_shape():
    rejection = RejectedCandidate(
        stage=RejectionStage.OPTIONS,
        ticker="MSFT",
        sector="Technology",
        expiration=date(2026, 7, 24),
        long_call=380,
        short_call=385,
        score=0,
        reasons=("reward/risk below 1.5", "max loss above limit"),
    )

    assert rejection.stage == RejectionStage.OPTIONS
    assert rejection.ticker == "MSFT"
    assert rejection.reasons == ("reward/risk below 1.5", "max loss above limit")


def test_scan_result_serializes_rejections_with_action_value():
    result = ScanResult(
        action=RecommendationAction.SIT_TODAY_OUT,
        mode="balanced",
        strategy_version="v4.0",
        as_of=date(2026, 6, 26),
        reason="No setups met the minimum quality threshold.",
        market_score=18.5,
        context=ScanContext(
            volatility_source="VIXY",
            stocks_scanned=3,
            spreads_evaluated=5,
            top_sectors=(RankedSector("Healthcare", "XLV", 13.87, 1, True),),
        ),
        rejections=(
            RejectedCandidate(
                stage=RejectionStage.CONFIRMATION,
                ticker="ISRG",
                reasons=("insufficient confirmation signals",),
            ),
        ),
        rejected_count=1,
    )

    payload = result.to_dict()

    assert payload["action"] == "SIT TODAY OUT"
    assert payload["context"]["volatility_source"] == "VIXY"
    assert payload["context"]["top_sectors"][0]["sector"] == "Healthcare"
    assert payload["rejections"][0]["stage"] == RejectionStage.CONFIRMATION
    encoded = json.dumps(payload, default=json_default)
    assert '"stage": "confirmation"' in encoded
