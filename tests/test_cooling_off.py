from dataclasses import replace
from datetime import date
import json

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.cooling_off import CoolingOffTracker
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import RecommendationAction, RejectionStage
from options_trading_assistant.providers.mock import MockDataProvider


def test_tracker_pauses_after_configured_failures_and_clears_on_reentry_signal():
    tracker = CoolingOffTracker(enabled=True, failed_trades_before_pause=2)
    stock = MockDataProvider().get_stocks_for_sector("Healthcare", date(2026, 6, 26))[0]

    tracker.record_outcome("ISRG", -100)
    assert tracker.rejection_reason(stock) is None

    tracker.record_outcome("ISRG", -50)
    assert "cooling off" in tracker.rejection_reason(stock)

    recovered = replace(
        stock,
        confirmation_signals=stock.confirmation_signals + ("reclaim_of_20_day_moving_average",),
    )
    assert tracker.rejection_reason(recovered) is None
    assert tracker.failure_streaks.get("ISRG") is None


def test_scanner_enforces_cooling_off_before_options_scan():
    tracker = CoolingOffTracker(
        enabled=True,
        failed_trades_before_pause=2,
        failure_streaks={"ISRG": 2},
    )
    scanner = DailyScanner(
        config=load_config(),
        provider=MockDataProvider(),
        cooling_off_tracker=tracker,
    )

    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    assert result.action == RecommendationAction.SIT_TODAY_OUT
    assert any(
        rejection.stage == RejectionStage.COOLING_OFF and rejection.ticker == "ISRG"
        for rejection in result.rejections
    )


def test_tracker_rebuilds_failure_streak_from_completed_packets(tmp_path):
    for index, final_pl in enumerate((-100, -50), start=1):
        packet = {
            "created_at": f"2026-06-2{index}T16:00:00",
            "decision_type": "recommendation",
            "ticker": "ISRG",
            "scan": {"as_of": f"2026-06-2{index}"},
            "outcome": {
                "status": "closed",
                "closed_at": f"2026-06-2{index + 1}",
                "final_pl": final_pl,
            },
        }
        (tmp_path / f"packet-{index}.json").write_text(json.dumps(packet), encoding="utf-8")

    tracker = CoolingOffTracker.from_decision_packets(load_config(), tmp_path)

    assert tracker.failure_streaks["ISRG"] == 2
