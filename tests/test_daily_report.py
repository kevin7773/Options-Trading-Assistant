from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import MarketSnapshot
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.reports.daily_report import (
    format_daily_report_html,
    format_report_footer,
    write_daily_report,
    write_daily_report_html,
)


class MarketGateFailureProvider(MockDataProvider):
    def get_market_snapshot(self, as_of):
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=False,
            nasdaq_above_20dma=False,
            vix=26,
            vix_rising=True,
            distribution_days=3,
            breadth_score=0.2,
            growth_participation_score=0.2,
        )


def test_format_report_footer_includes_context_and_packet_count():
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))

    output = format_report_footer(result, decision_packet_count=5)

    assert "Report Context" in output
    assert "Stocks scanned: 4" in output
    assert "Option spreads evaluated: 3" in output
    assert "Decision packets written: 5" in output
    assert "Top sectors:" in output


def test_format_report_footer_explains_market_gate_skip():
    result = DailyScanner(load_config(), MarketGateFailureProvider()).run("balanced", date(2026, 6, 26))

    output = format_report_footer(result, decision_packet_count=1)

    assert "Stocks scanned: 0 — skipped due to market rejection" in output
    assert "Option spreads evaluated: 0 — skipped due to market rejection" in output
    assert "Top sectors: sector ranking skipped because market gate failed." in output


def test_write_daily_report_creates_markdown_file(tmp_path):
    path = write_daily_report(date(2026, 6, 26), "# Report", tmp_path)

    assert path.exists()
    assert path.name.endswith("-daily-report.md")
    assert path.read_text(encoding="utf-8") == "# Report"


def test_format_daily_report_html_includes_recommendations_and_rejections():
    result = DailyScanner(load_config(), MockDataProvider()).run("balanced", date(2026, 6, 26))

    html = format_daily_report_html(result, decision_packet_count=5)

    assert "Options Trading Assistant Daily Report" in html
    assert "ISRG" in html
    assert "Rejected Candidates" in html
    assert "Decision Packets" in html
    assert "<style>" in html


def test_format_daily_report_html_explains_market_gate_skip():
    result = DailyScanner(load_config(), MarketGateFailureProvider()).run("balanced", date(2026, 6, 26))

    html = format_daily_report_html(result, decision_packet_count=1)

    assert "skipped due to market rejection" in html
    assert "Sector ranking skipped because market gate failed." in html


def test_write_daily_report_html_creates_html_file(tmp_path):
    path = write_daily_report_html(date(2026, 6, 26), "<html></html>", tmp_path)

    assert path.exists()
    assert path.name.endswith("-daily-report.html")
    assert path.read_text(encoding="utf-8") == "<html></html>"
