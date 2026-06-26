from datetime import date

from options_trading_assistant.reports.journal_review import (
    filter_scan_records,
    format_journal_review,
    summarize_scan_records,
)


def sample_records():
    return [
        {
            "as_of": "2026-06-25",
            "action": "SIT TODAY OUT",
            "context": {
                "volatility_source": "VIXY",
                "stocks_scanned": 0,
                "spreads_evaluated": 0,
                "top_sectors": [],
            },
            "recommendations": [],
            "rejections": [
                {
                    "stage": "market",
                    "ticker": None,
                    "reasons": ["S&P 500 is below its 20-day moving average."],
                }
            ],
        },
        {
            "as_of": "2026-06-26",
            "action": "BUY",
            "context": {
                "volatility_source": "VIXY",
                "stocks_scanned": 4,
                "spreads_evaluated": 8,
                "top_sectors": [{"sector": "Healthcare", "score": 13.87, "rank": 1, "eligible": True}],
            },
            "recommendations": [{"stock": {"ticker": "ISRG"}}],
            "rejections": [
                {
                    "stage": "options",
                    "ticker": "MSFT",
                    "reasons": ["Reward/risk 1.04 below configured minimum 1.50."],
                },
                {
                    "stage": "confirmation",
                    "ticker": "NVDA",
                    "reasons": ["Insufficient confirmation signals (1/2)."],
                },
            ],
        },
    ]


def test_filter_scan_records_by_days_ticker_and_stage():
    records = sample_records()

    filtered = filter_scan_records(records, days=1, ticker="MSFT", stage="options", today=date(2026, 6, 26))

    assert len(filtered) == 1
    assert filtered[0]["as_of"] == "2026-06-26"


def test_summarize_scan_records_counts_actions_rejections_and_reasons():
    summary = summarize_scan_records(sample_records())

    assert summary["scan_count"] == 2
    assert summary["stocks_scanned"] == 4
    assert summary["spreads_evaluated"] == 8
    assert summary["volatility_sources"]["VIXY"] == 2
    assert summary["leading_sectors"]["Healthcare"] == 1
    assert summary["action_counts"]["BUY"] == 1
    assert summary["stage_counts"]["options"] == 1
    assert summary["ticker_counts"]["MSFT"] == 1
    assert summary["reason_counts"]["Insufficient confirmation signals (1/2)."] == 1


def test_format_journal_review_outputs_sections():
    summary = summarize_scan_records(sample_records())

    output = format_journal_review(summary, limit=5)

    assert "Journal Review" in output
    assert "Actions:" in output
    assert "Stocks Scanned: 4" in output
    assert "Volatility Sources:" in output
    assert "- Healthcare: 1" in output
    assert "- BUY: 1" in output
    assert "Options Rejection Reasons:" in output
