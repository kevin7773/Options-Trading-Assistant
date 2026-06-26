from options_trading_assistant.providers.moomoo import MoomooDataProvider


def test_iv_decimal_normalizes_percentage_values():
    assert MoomooDataProvider._iv_decimal(34.18) == 0.3418
    assert MoomooDataProvider._iv_decimal(0.42) == 0.42


def test_enriched_option_chain_merges_snapshots_by_code():
    class Provider(MoomooDataProvider):
        def __init__(self):
            pass

        def _option_chain(self, ticker, expiration):
            return [
                {"code": "US.TESTC100", "strike_price": 100, "option_type": "CALL"},
                {"strike_price": 105, "option_type": "CALL"},
                {"code": "US.TESTC110", "strike_price": 110, "option_type": "CALL"},
            ]

        def _option_snapshot_rows(self, option_codes):
            assert option_codes == ["US.TESTC100", "US.TESTC110"]
            return [
                {"code": "US.TESTC100", "bid_price": 1.0},
                {"code": "US.TESTC110", "bid_price": 3.0},
            ]

    provider = Provider()

    enriched = provider._enriched_option_chain("TEST", None)

    assert enriched[0]["bid_price"] == 1.0
    assert "bid_price" not in enriched[1]
    assert enriched[2]["bid_price"] == 3.0


def test_volatility_signal_marks_true_vix_risk_off_when_high_and_rising():
    class Provider(MoomooDataProvider):
        def __init__(self):
            self.config = type(
                "Config",
                (),
                {"strategy": {"market": {"max_vix_if_rising": 22}}},
            )()

        def _history(self, ticker, as_of, days):
            return [{"close": 21.5}, {"close": 23.0}]

    signal = Provider()._volatility_signal("US..VIX", "VIXY", None)

    assert signal["vix"] == 23.0
    assert signal["rising"] is True
    assert signal["risk_off"] is True
