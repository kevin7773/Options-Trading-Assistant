from datetime import date
import json

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.reports.decision_packets import write_decision_packets
from options_trading_assistant.reports.packet_review import update_packet_outcome


def test_write_decision_packets_creates_recommendation_and_rejection_files(tmp_path):
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))

    paths = write_decision_packets(result, tmp_path)

    assert len(paths) == len(result.recommendations) + len(result.rejections)
    assert any(path.name.startswith("recommendation-") for path in paths)
    assert any(path.name.startswith("rejection-") for path in paths)

    recommendation_path = next(path for path in paths if path.name.startswith("recommendation-"))
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))

    assert recommendation["schema_version"] == "decision_packet_v1"
    assert recommendation["engine_commit"]
    assert recommendation["strategy_commit"]
    assert recommendation["strategy_version"] == "v4.2"
    assert recommendation["research_branch"] == recommendation["engine_commit"]
    assert recommendation["dashboard_version"] == "research_dashboard_v1"
    assert recommendation["decision_type"] == "recommendation"
    assert recommendation["ticker"] == "ISRG"
    assert recommendation["scan"]["mode"] == "balanced"
    assert recommendation["scan"]["context"]["stocks_scanned"] > 0
    assert recommendation["outcome"]["status"] == "pending"
    features = recommendation["measurement_features"]
    assert features["hypothesis_id"] == "H-006"
    assert features["measurement_only"] is True
    assert features["decision_type"] == "recommendation"
    assert features["recommended"] is True
    assert features["rejected"] is False
    assert features["sit_out"] is False
    assert features["action"] == "BUY"
    assert features["score_total"] == recommendation["score"]["total"]
    assert features["score_bucket"] == "90+"
    assert features["market_score_raw"] == recommendation["scan"]["market_score"]
    assert features["stock"]["sector_relative_strength"] == recommendation["stock"]["sector_relative_strength"]
    assert features["stock"]["confirmation_score"] == recommendation["score"]["confirmation"]
    assert features["sector"]["relative_strength_20d"] == recommendation["sector_snapshot"]["relative_strength_20d"]
    assert features["spread"]["expected_move_pct"] == recommendation["spread"]["expected_move_pct"]
    assert features["spread"]["distance_to_long_strike"] is not None
    assert features["spread"]["iv_rank"] == recommendation["spread"]["iv_rank"]


def test_rejection_packet_includes_stage_reasons_and_optional_spread_shape(tmp_path):
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))

    paths = write_decision_packets(result, tmp_path)
    rejection_path = next(path for path in paths if path.name.startswith("rejection-") and "ISRG" in path.name)
    rejection = json.loads(rejection_path.read_text(encoding="utf-8"))

    assert rejection["decision_type"] == "rejection"
    assert rejection["stage"] == "options"
    assert rejection["ticker"] == "ISRG"
    assert rejection["long_call"] == 435
    assert rejection["short_call"] == 440
    assert rejection["reasons"]
    features = rejection["measurement_features"]
    assert features["hypothesis_id"] == "H-006"
    assert features["decision_type"] == "rejection"
    assert features["recommended"] is False
    assert features["rejected"] is True
    assert features["sit_out"] is False
    assert features["action"] == "BUY"
    assert features["stage"] == "options"
    assert features["ticker"] == "ISRG"
    assert features["score_observed"] == rejection["score"]


def test_market_sit_out_rejection_packet_records_skipped_environment(tmp_path):
    class MarketBlockedProvider(MockDataProvider):
        def get_market_snapshot(self, as_of):
            snapshot = super().get_market_snapshot(as_of)
            return type(snapshot)(
                **{
                    **snapshot.__dict__,
                    "spy_above_20dma": False,
                }
            )

    result = DailyScanner(load_config(), MarketBlockedProvider()).run("balanced", date(2026, 6, 26))
    paths = write_decision_packets(result, tmp_path)
    rejection = json.loads(paths[0].read_text(encoding="utf-8"))
    features = rejection["measurement_features"]

    assert rejection["decision_type"] == "rejection"
    assert rejection["engine_commit"]
    assert rejection["strategy_commit"]
    assert rejection["strategy_version"] == "v4.2"
    assert rejection["dashboard_version"] == "research_dashboard_v1"
    assert rejection["stage"] == "market"
    assert features["decision_type"] == "rejection"
    assert features["recommended"] is False
    assert features["rejected"] is True
    assert features["sit_out"] is True
    assert features["action"] == "SIT TODAY OUT"
    assert features["stage"] == "market"
    assert features["market"]["stocks_scanned"] == 0
    assert features["market"]["spreads_evaluated"] == 0


def test_repeated_scan_does_not_overwrite_reviewed_packet(tmp_path):
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))
    first_path = write_decision_packets(result, tmp_path)[0]
    update_packet_outcome(first_path, status="reviewed", notes="preserve this")

    second_path = write_decision_packets(result, tmp_path)[0]
    first_packet = json.loads(first_path.read_text(encoding="utf-8"))

    assert second_path != first_path
    assert first_packet["outcome"]["status"] == "reviewed"
    assert first_packet["outcome"]["notes"] == "preserve this"
