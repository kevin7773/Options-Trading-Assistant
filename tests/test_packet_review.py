import json
from pathlib import Path

from options_trading_assistant.reports.packet_review import (
    find_packet_files,
    format_packet_list,
    format_packet_review,
    packet_summary,
    summarize_packets,
    update_packet_outcome,
)


def write_packet(path: Path, decision_type="recommendation", ticker="MSFT", stage=None, status="pending", final_pl=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "decision_type": decision_type,
                "ticker": ticker,
                "sector": "Technology",
                "stage": stage,
                "scan": {"as_of": "2026-06-26"},
                "outcome": {
                    "status": status,
                    "notes": None,
                    "closed_at": None,
                    "final_pl": final_pl,
                },
            }
        ),
        encoding="utf-8",
    )


def test_find_packet_files_and_format_packet_list(tmp_path):
    packet = tmp_path / "2026-06-26" / "scan" / "recommendation-001-MSFT.json"
    write_packet(packet)

    paths = find_packet_files(tmp_path, scan_date="2026-06-26")
    summaries = [packet_summary(path) for path in paths]
    output = format_packet_list(summaries)

    assert paths == [packet]
    assert "recommendation | MSFT" in output
    assert str(packet) in output


def test_update_packet_outcome_sets_status_notes_closed_at_and_pl(tmp_path):
    packet = tmp_path / "packet.json"
    write_packet(packet)

    updated = update_packet_outcome(
        packet,
        status="closed",
        notes="Exited at target.",
        closed_at="2026-06-27",
        final_pl=85.5,
    )

    assert updated["outcome"]["status"] == "closed"
    assert updated["outcome"]["notes"] == "Exited at target."
    assert updated["outcome"]["closed_at"] == "2026-06-27"
    assert updated["outcome"]["final_pl"] == 85.5
    assert updated["outcome"]["updated_at"]


def test_summarize_and_format_packet_review(tmp_path):
    write_packet(tmp_path / "a.json", decision_type="recommendation", ticker="MSFT", status="closed", final_pl=85.5)
    write_packet(tmp_path / "b.json", decision_type="rejection", ticker="NVDA", stage="options", status="reviewed")

    summary = summarize_packets(sorted(tmp_path.glob("*.json")))
    output = format_packet_review(summary)

    assert summary["packet_count"] == 2
    assert summary["status_counts"]["closed"] == 1
    assert summary["decision_counts"]["rejection"] == 1
    assert summary["stage_counts"]["options"] == 1
    assert summary["total_final_pl"] == 85.5
    assert "Outcome Status:" in output
