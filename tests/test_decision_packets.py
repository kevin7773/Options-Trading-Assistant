from datetime import date
import json

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.reports.decision_packets import write_decision_packets


def test_write_decision_packets_creates_recommendation_and_rejection_files(tmp_path):
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))

    paths = write_decision_packets(result, tmp_path)

    assert len(paths) == len(result.recommendations) + len(result.rejections)
    assert any(path.name.startswith("recommendation-") for path in paths)
    assert any(path.name.startswith("rejection-") for path in paths)

    recommendation_path = next(path for path in paths if path.name.startswith("recommendation-"))
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))

    assert recommendation["schema_version"] == "decision_packet_v1"
    assert recommendation["decision_type"] == "recommendation"
    assert recommendation["ticker"] == "ISRG"
    assert recommendation["scan"]["mode"] == "balanced"
    assert recommendation["scan"]["context"]["stocks_scanned"] > 0
    assert recommendation["outcome"]["status"] == "pending"


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
