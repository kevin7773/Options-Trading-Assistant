from options_trading_assistant.cli import format_diagnostics


def test_format_diagnostics_shows_required_field_coverage():
    report = {
        "provider": "moomoo",
        "host": "127.0.0.1",
        "port": 11111,
        "ticker": "MSFT",
        "code": "US.MSFT",
        "as_of": "2026-06-26",
        "sections": {
            "history": {
                "ok": True,
                "rows": 80,
                "columns": ["close", "time_key", "volume"],
                "required_fields": {
                    "close": {"ok": True, "matched": ["close"], "aliases": ["close"]},
                    "high": {"ok": False, "matched": [], "aliases": ["high"]},
                },
                "sample": {"time_key": "2026-06-26", "close": "500.00"},
            }
        },
    }

    output = format_diagnostics(report)

    assert "Provider: moomoo" in output
    assert "[history]" in output
    assert "- close: OK (close)" in output
    assert "- high: MISSING (none)" in output
