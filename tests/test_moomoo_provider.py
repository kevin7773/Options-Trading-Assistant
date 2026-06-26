from options_trading_assistant.providers.moomoo import MoomooDataProvider


def test_iv_decimal_normalizes_percentage_values():
    assert MoomooDataProvider._iv_decimal(34.18) == 0.3418
    assert MoomooDataProvider._iv_decimal(0.42) == 0.42
