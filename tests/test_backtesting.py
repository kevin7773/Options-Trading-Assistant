from datetime import date, timedelta

from options_trading_assistant.backtesting.diagnostics import (
    build_stock_diagnostics_report,
    format_stock_diagnostics_report,
)
from options_trading_assistant.backtesting.engine import run_backtest, scenario_config, simulate_spread_outcome
from options_trading_assistant.backtesting.models import OHLCVBar
from options_trading_assistant.backtesting.scenarios import get_scenario
from options_trading_assistant.config import load_config
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.models import MarketSnapshot, OptionSpread, SectorSnapshot, StockSnapshot
from options_trading_assistant.providers.base import DataProvider


class ScriptedBacktestProvider(DataProvider):
    def available_dates(self, start, end):
        return [start, start + timedelta(days=1)]

    def close_on_or_before(self, ticker, target):
        return target, 108.0

    def bars_between(self, ticker, start, end):
        return (
            OHLCVBar(ticker, start, 100, 103, 99, 100, 1_000_000),
            OHLCVBar(ticker, end, 104, 108, 103, 108, 1_200_000),
        )

    def get_market_snapshot(self, as_of):
        if as_of == date(2026, 1, 2):
            return MarketSnapshot(
                as_of=as_of,
                spy_above_20dma=False,
                nasdaq_above_20dma=True,
                vix=12,
                vix_rising=False,
                distribution_days=0,
                breadth_score=0.8,
                growth_participation_score=0.8,
            )
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=True,
            nasdaq_above_20dma=True,
            vix=12,
            vix_rising=False,
            distribution_days=0,
            breadth_score=0.8,
            growth_participation_score=0.8,
        )

    def get_sector_snapshots(self, as_of):
        return (
            SectorSnapshot("Technology", "XLK", 2.0, 2.0, 2.0, True, True, 0.8, 0.8, 0.8),
        )

    def get_stocks_for_sector(self, sector_name, as_of):
        return (
            StockSnapshot(
                ticker="MSFT",
                sector=sector_name,
                price=100,
                above_100dma=True,
                above_200dma=True,
                trend_90d=0.12,
                sector_relative_strength=0.12,
                drawdown_from_swing_high_pct=7,
                rsi=38,
                near_support=True,
                selling_volume_stabilizing=True,
                making_lower_lows=False,
                confirmation_signals=("green_daily_candle", "higher_low"),
            ),
        )

    def get_option_spreads(self, ticker, as_of):
        return (
            OptionSpread(
                ticker=ticker,
                expiration=as_of + timedelta(days=28),
                long_call=100,
                short_call=105,
                debit=2.0,
                long_delta=0.45,
                short_delta=0.30,
                long_open_interest=1000,
                short_open_interest=1000,
                bid_ask_width_pct=0.08,
                volume_score=0.8,
                iv_rank=0.4,
                expected_move_pct=4.0,
            ),
        )


def test_backtest_runner_writes_artifacts_and_summary(tmp_path):
    result = run_backtest(
        config=load_config(),
        provider=ScriptedBacktestProvider(),
        mode="balanced",
        start=date(2026, 1, 2),
        end=date(2026, 1, 3),
        output_root=tmp_path,
        run_id="test-run",
    )

    assert result.scan_count == 2
    assert result.trade_count == 1
    assert result.sit_out_count == 1
    assert result.summary["win_rate"] == 1.0
    assert result.summary["expectancy"] == 180.0
    assert (tmp_path / "test-run" / "summary.json").exists()
    assert (tmp_path / "test-run" / "trades.jsonl").exists()
    assert (tmp_path / "test-run" / "scan_results.jsonl").exists()
    assert list((tmp_path / "test-run" / "decision_packets").rglob("*.json"))
    trade_payload = (tmp_path / "test-run" / "trades.jsonl").read_text(encoding="utf-8")
    assert "max_favorable_excursion" in trade_payload
    assert "profit_target_touched" in trade_payload
    assert "market_score_entry" in trade_payload


def test_summary_only_backtest_skips_per_scan_artifacts(tmp_path):
    result = run_backtest(
        config=load_config(),
        provider=ScriptedBacktestProvider(),
        mode="balanced",
        start=date(2026, 1, 2),
        end=date(2026, 1, 3),
        output_root=tmp_path,
        run_id="summary-only",
        detailed_artifacts=False,
    )

    run_dir = tmp_path / "summary-only"
    assert result.trade_count == 1
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "trades.jsonl").exists()
    assert not (run_dir / "scan_results.jsonl").exists()
    assert not (run_dir / "decision_packets").exists()


def test_stock_diagnostics_rank_and_explain_candidates():
    report = build_stock_diagnostics_report(
        config=load_config(),
        provider=ScriptedBacktestProvider(),
        mode="balanced",
        as_of=date(2026, 1, 3),
        limit=5,
    )

    output = format_stock_diagnostics_report(report)

    assert report.market_passed is True
    assert report.diagnostics[0].ticker == "MSFT"
    assert "Market passed: YES" in output
    assert "Top 1 stocks ranked" in output
    assert "[pass] Above 100 DMA" in output
    assert "Eligible" in output


def test_backtest_does_not_use_entry_day_high_for_profit_target():
    class EntryDaySpikeProvider(ScriptedBacktestProvider):
        def close_on_or_before(self, ticker, target):
            return target, 100.0

        def bars_between(self, ticker, start, end):
            return (
                OHLCVBar(ticker, start, 100, 110, 99, 100, 1_000_000),
                OHLCVBar(ticker, end, 100, 100, 100, 100, 1_000_000),
            )

    provider = EntryDaySpikeProvider()
    config = load_config()
    entry_date = date(2026, 1, 3)
    result = DailyScanner(config, provider).run("balanced", entry_date)

    trade = simulate_spread_outcome(provider, config, result, result.recommendations[0])

    assert trade.profit_target_touched is False
    assert trade.highest_underlying_price == 100


def test_h005_scenario_adds_semiconductor_sector_profile_only():
    config = scenario_config(load_config(), get_scenario("semiconductor_high_beta_recovery"))

    profile = config.strategy["sector_profiles"]["Semiconductors"]

    assert profile["strategy_profile"] == "mean_reversion_high_beta"
    assert profile["confirmation_required"] == 3
    assert profile["max_vix"] == 18
    assert profile["preferred_long_strike"] == "atm"
    assert profile["pullback_range"] == [7, 15]
    assert "Cloud / SaaS" not in config.strategy["sector_profiles"]
