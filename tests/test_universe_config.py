from options_trading_assistant.config import load_config, trade_config_for_symbol
from options_trading_assistant.providers.historical import historical_tickers


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
    assert "measurement_only" in config.universe["lifecycle_statuses"]
    assert semis["lifecycle_status"] == "production"
    assert semis["research_history"]["hypotheses"] == ["H-005"]
    assert semis["research_history"]["experiments"] == ["EXP-2026-001"]


def test_universe_v2_tracks_gold_precious_metals_as_research_slice():
    config = load_config()
    metals = config.universe["research_slices"]["Gold / Precious Metals"]

    assert metals["status"] == "measurement_only"
    assert metals["etfs"] == ["GLD", "GDX", "IAU", "GDXJ", "SLV"]
    assert "NEM" in metals["tracked_symbols"]
    assert "NUGT" not in metals["tracked_symbols"]
    assert metals["promotion_requirements"]["minimum_completed_trades"] == 25
    assert metals["promotion_requirements"]["research_hypothesis_required"] is True
    assert metals["research_history"]["prospective_observations"] == 0
    assert "Gold / Precious Metals" not in config.universe["sectors"]
    assert "GLD" in historical_tickers(config)
    assert "AEM" in historical_tickers(config)


def test_symbol_metadata_overrides_trade_construction_rules():
    config = load_config()

    avgo_rules = trade_config_for_symbol(config, "AVGO")
    watchlist_rules = trade_config_for_symbol(config, "DOCU")

    assert avgo_rules["min_open_interest"] == 1000
    assert avgo_rules["preferred_spread_widths"] == [5, 10]
    assert watchlist_rules["min_open_interest"] == 500
    assert 1 in watchlist_rules["preferred_spread_widths"]
