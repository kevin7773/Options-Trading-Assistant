from pathlib import Path

from options_trading_assistant.cli import parse_args
from options_trading_assistant.reports.dashboard import build_dashboard, render_dashboard_html


def test_render_dashboard_html_includes_filters_and_report_data():
    html = render_dashboard_html(
        [
            {
                "type": "html",
                "date": "2026-06-29",
                "label": "2026-06-29 · Daily HTML Report",
                "path": "data/reports/daily/report.html",
                "content": "<h1>Daily Trading Report</h1>",
            },
            {
                "type": "packet",
                "date": "2026-06-29",
                "label": "2026-06-29 · rejection · MSFT",
                "path": "data/journal/decision_packets/packet.json",
                "content": '{"ticker": "MSFT"}',
            },
            {
                "type": "backtest",
                "date": "backtest",
                "label": "balanced · slightly_itm",
                "path": "backtesting/results/run/summary.json",
                "content": "Expectancy: $125.40",
            },
            {
                "type": "universe",
                "date": "universe",
                "label": "Universe v2",
                "path": "config/universe_v2.yaml",
                "content": "tier_1_core_leaders",
            },
            {
                "type": "prospective",
                "date": "2026-06-30",
                "label": "Prospective Tracking Runbook",
                "path": "docs/prospective_tracking.md",
                "content": "INSUFFICIENT EVIDENCE",
            },
            {
                "type": "experiment",
                "date": "2026-06-30",
                "label": "EXP-2026-001 · H-005 · rejected",
                "path": "research/experiments/EXP-2026-001.yaml",
                "content": "Decision: rejected\nExpectancy: $44.98",
            },
            {
                "type": "quality",
                "date": "quality",
                "label": "Data Quality · repository health",
                "path": ".",
                "content": "Symbols hydrated | 231 / 232",
            },
        ]
    )

    assert "Options Trading Assistant Dashboard" in html
    assert "dateFilter" in html
    assert "reportSelect" in html
    assert "Daily Trading Report" in html
    assert "MSFT" in html
    assert "Backtest / benchmark summaries" in html
    assert "Prospective evidence" in html
    assert "Universe" in html
    assert "Research experiments" in html
    assert "Data quality" in html
    assert "tier_1_core_leaders" in html
    assert "EXP-2026-001" in html
    assert "Symbols hydrated" in html


def test_build_dashboard_writes_index_file(tmp_path):
    path = build_dashboard(tmp_path / "index.html")

    assert path.exists()
    assert path.name == "index.html"
    assert "Options Trading Assistant Dashboard" in path.read_text(encoding="utf-8")


def test_build_dashboard_includes_experiment_manifest():
    path = build_dashboard()
    html = path.read_text(encoding="utf-8")

    assert "EXP-2026-001" in html
    assert "Decision: rejected" in html
    assert "$-16.66 vs baseline" in html


def test_build_dashboard_includes_data_quality_report():
    path = build_dashboard()
    html = path.read_text(encoding="utf-8")

    assert "Data Quality · repository health" in html
    assert "Missing configured symbols" in html
    assert "Decision packets" in html


def test_dashboard_escapes_script_terminators_in_embedded_report_json():
    html = render_dashboard_html(
        [
            {
                "type": "packet",
                "date": "2026-06-29",
                "label": "malicious note",
                "path": "packet.json",
                "content": "</script><script>alert('xss')</script>",
            }
        ]
    )

    assert "</script><script>alert('xss')</script>" not in html
    assert "\\u003c/script\\u003e" in html


def test_dashboard_cli_accepts_serve_options(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["ota", "dashboard", "--serve", "--host", "127.0.0.1", "--port", "8766"],
    )

    args = parse_args()

    assert args.command == "dashboard"
    assert args.serve is True
    assert args.host == "127.0.0.1"
    assert args.port == 8766
