from datetime import date
import json

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.signals import SignalEngine
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.reports.signal_rankings import write_signal_ranking_snapshot


def test_signal_snapshot_saves_ranked_stocks_before_trade_construction(tmp_path):
    result = SignalEngine(load_config(), MockDataProvider()).run(
        mode="balanced",
        as_of=date(2026, 6, 26),
        include_all_sectors_in_rankings=True,
    )

    path = write_signal_ranking_snapshot(result, output_dir=tmp_path, top_n=10)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["market_passed"] is True
    assert payload["strategy_version"] == "v4.2"
    assert payload["rankings"]
    assert payload["rankings"][0]["predicted_rank"] == 1
    assert "qualified_for_trade_construction" in payload["rankings"][0]
    assert payload["top_sector_etf"] == "XLV"
    assert len(payload["eligible_universe"]) == len(result.rankings)


def test_market_blocked_snapshot_records_no_rankings(tmp_path):
    class HostileProvider(MockDataProvider):
        def get_market_snapshot(self, as_of):
            snapshot = super().get_market_snapshot(as_of)
            return type(snapshot)(
                **{
                    **snapshot.__dict__,
                    "spy_above_20dma": False,
                }
            )

    result = SignalEngine(load_config(), HostileProvider()).run(
        mode="balanced",
        as_of=date(2026, 6, 26),
        include_all_sectors_in_rankings=True,
    )

    path = write_signal_ranking_snapshot(result, output_dir=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["market_passed"] is False
    assert payload["rankings"] == []
