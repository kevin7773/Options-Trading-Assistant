from options_trading_assistant.config import load_config, trade_config_for_symbol


def test_universe_v2_normalizes_four_tiers_and_metadata():
    config = load_config()
    semis = config.universe["sectors"]["Semiconductors"]
    metadata = config.universe["symbol_metadata"]

    assert config.universe["version"] == "v2"
    assert "AVGO" in semis["tickers"]
    assert "LSCC" not in semis["tickers"]
    assert "LSCC" in semis["research_tickers"]
    assert "UVXY" not in config.universe["sectors"]["Real Estate"]["tickers"]
    assert metadata["AVGO"]["industry"] == "Networking & ASICs"
    assert metadata["AVGO"]["tier"] == "tier_1_core_leaders"
    assert metadata["AVGO"]["benchmark_etf"] == "SMH"
    assert metadata["UVXY"]["excluded"] is True


def test_symbol_metadata_overrides_trade_construction_rules():
    config = load_config()

    avgo_rules = trade_config_for_symbol(config, "AVGO")
    watchlist_rules = trade_config_for_symbol(config, "DOCU")

    assert avgo_rules["min_open_interest"] == 1000
    assert avgo_rules["preferred_spread_widths"] == [5, 10]
    assert watchlist_rules["min_open_interest"] == 500
    assert 1 in watchlist_rules["preferred_spread_widths"]
