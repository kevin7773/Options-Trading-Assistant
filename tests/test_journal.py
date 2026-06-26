from datetime import date

from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.reports.journal import append_scan_result


def test_append_scan_result_writes_jsonl(tmp_path):
    scanner = DailyScanner(config=load_config(), provider=MockDataProvider())
    result = scanner.run(mode="balanced", as_of=date(2026, 6, 26))

    path = append_scan_result(result, tmp_path)

    content = path.read_text(encoding="utf-8")
    assert '"action": "BUY"' in content
    assert '"ticker": "ISRG"' in content
