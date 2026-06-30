from __future__ import annotations

import json
from copy import deepcopy
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from options_trading_assistant.backtesting.models import BacktestResult, BacktestTrade
from options_trading_assistant.backtesting.scenarios import BALANCED_SCENARIO, BacktestScenario
from options_trading_assistant.config import AppConfig, PROJECT_ROOT
from options_trading_assistant.engines.cooling_off import CoolingOffTracker
from options_trading_assistant.engines.scanner import DailyScanner
from options_trading_assistant.engines.scoring import score_market, score_sector
from options_trading_assistant.models import RecommendationAction, ScanResult, TradeCandidate
from options_trading_assistant.providers.historical import HistoricalDataProvider
from options_trading_assistant.reports.decision_packets import write_decision_packets
from options_trading_assistant.reports.journal import append_scan_result, json_default


class BacktestRunner:
    def __init__(
        self,
        config: AppConfig,
        provider: HistoricalDataProvider,
        output_root: Path | None = None,
        scenario: BacktestScenario | None = None,
        detailed_artifacts: bool = True,
    ):
        self.scenario = scenario or BALANCED_SCENARIO
        self.config = scenario_config(config, self.scenario)
        self.provider = provider
        self.output_root = output_root or PROJECT_ROOT / "backtesting" / "results"
        self.detailed_artifacts = detailed_artifacts

    def run(self, mode: str, start: date, end: date, run_id: str | None = None) -> BacktestResult:
        resolved_run_id = run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{mode}-{self.scenario.name}-{start}-{end}"
        output_dir = self.output_root / resolved_run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        cooling_off_tracker = CoolingOffTracker.from_config(self.config)
        scanner = DailyScanner(
            config=self.config,
            provider=self.provider,
            cooling_off_tracker=cooling_off_tracker,
        )

        scans: list[ScanResult] = []
        trades: list[BacktestTrade] = []
        pending_outcomes: list[BacktestTrade] = []
        dates = self.provider.available_dates(start, end)
        if not dates:
            raise RuntimeError(
                "No historical scan dates are available. Hydrate data first or point --cache-dir at OHLCV CSV files."
            )

        for as_of in dates:
            closed_outcomes = [trade for trade in pending_outcomes if trade.exit_date < as_of]
            for trade in closed_outcomes:
                cooling_off_tracker.record_outcome(trade.ticker, trade.final_pl)
            pending_outcomes = [trade for trade in pending_outcomes if trade.exit_date >= as_of]

            result = scanner.run(mode=mode, as_of=as_of)
            scans.append(result)
            packet_paths: list[Path] = []
            if self.detailed_artifacts:
                append_scan_result(result, journal_dir=output_dir)
                packet_paths = write_decision_packets(result, output_dir / "decision_packets")
            if result.action == RecommendationAction.BUY:
                simulated = self._simulate_recommendations(result, packet_paths)
                trades.extend(simulated)
                pending_outcomes.extend(simulated)

        self._write_trades(output_dir, trades)
        summary = summarize_backtest(scans, trades)
        summary["scenario"] = self.scenario.name
        summary["scenario_description"] = self.scenario.description
        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, default=json_default, indent=2, sort_keys=True), encoding="utf-8")
        return BacktestResult(
            run_id=resolved_run_id,
            start=start,
            end=end,
            mode=mode,
            scan_count=len(scans),
            trade_count=len(trades),
            sit_out_count=sum(1 for scan in scans if scan.action == RecommendationAction.SIT_TODAY_OUT),
            summary=summary,
            output_dir=str(output_dir),
            trades=tuple(trades),
        )

    def _simulate_recommendations(self, result: ScanResult, packet_paths: list[Path]) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []
        recommendation_paths = [path for path in packet_paths if path.name.startswith("recommendation-")]
        for index, candidate in enumerate(result.recommendations):
            trade = simulate_spread_outcome(self.provider, self.config, result, candidate)
            trades.append(trade)
            if index < len(recommendation_paths):
                _merge_packet_outcome(recommendation_paths[index], trade)
        return trades

    @staticmethod
    def _write_trades(output_dir: Path, trades: list[BacktestTrade]) -> None:
        path = output_dir / "trades.jsonl"
        with path.open("w", encoding="utf-8") as file:
            for trade in trades:
                file.write(json.dumps(asdict(trade), default=json_default, sort_keys=True))
                file.write("\n")


def run_backtest(
    config: AppConfig,
    provider: HistoricalDataProvider,
    mode: str,
    start: date,
    end: date,
    output_root: Path | None = None,
    run_id: str | None = None,
    scenario: BacktestScenario | None = None,
    detailed_artifacts: bool = True,
) -> BacktestResult:
    return BacktestRunner(
        config=config,
        provider=provider,
        output_root=output_root,
        scenario=scenario,
        detailed_artifacts=detailed_artifacts,
    ).run(
        mode=mode,
        start=start,
        end=end,
        run_id=run_id,
    )


def simulate_spread_outcome(
    provider: HistoricalDataProvider,
    config: AppConfig,
    result: ScanResult,
    candidate: TradeCandidate,
) -> BacktestTrade:
    spread = candidate.spread
    target_exit = min(spread.expiration, result.as_of + timedelta(days=14))
    planned_exit_date, planned_exit_price = provider.close_on_or_before(candidate.stock.ticker, target_exit)
    hold_bars = tuple(
        bar
        for bar in provider.bars_between(candidate.stock.ticker, result.as_of, planned_exit_date)
        if bar.date > result.as_of
    )
    entry_price = candidate.stock.price
    high_price = max((bar.high for bar in hold_bars), default=entry_price)
    low_price = min((bar.low for bar in hold_bars), default=entry_price)
    high_value = max(
        (spread_mark_at_underlying(bar.high, spread, bar.date, result.as_of) for bar in hold_bars),
        default=spread.max_loss,
    )
    low_value = min(
        (spread_mark_at_underlying(bar.low, spread, bar.date, result.as_of) for bar in hold_bars),
        default=spread.max_loss,
    )
    max_profit = spread.max_profit
    scenario = getattr(provider, "scenario", BALANCED_SCENARIO)
    profit_target_value = spread.max_loss + (max_profit * scenario.profit_target_pct_of_max_profit)
    stop_value = spread.max_loss * (1 - scenario.stop_loss_pct_of_debit)
    exit_date, exit_price, final_value, exit_reason = _scenario_exit(
        hold_bars=hold_bars,
        spread=spread,
        entry_date=result.as_of,
        planned_exit_date=planned_exit_date,
        planned_exit_price=planned_exit_price,
        profit_target_value=profit_target_value,
        stop_value=stop_value,
    )
    final_pl = final_value - spread.max_loss
    market_score_exit = score_market(provider.get_market_snapshot(exit_date), config.strategy["market"])
    sector_score_exit = _sector_score(provider, candidate.sector.name, exit_date)
    strike_variant = getattr(provider, "strike_variant", None)
    return BacktestTrade(
        scenario=scenario.name,
        strike_model=strike_variant.name if strike_variant else "unknown",
        entry_date=result.as_of,
        exit_date=exit_date,
        exit_reason=exit_reason,
        ticker=candidate.stock.ticker,
        sector=candidate.sector.name,
        score=candidate.score.total,
        score_bucket=score_bucket(candidate.score.total),
        market_regime=market_regime(result),
        expiration=spread.expiration,
        long_call=spread.long_call,
        short_call=spread.short_call,
        debit=spread.debit,
        entry_underlying_price=round(entry_price, 4),
        exit_underlying_price=exit_price,
        exit_spread_value=round(final_value, 2),
        final_value=round(final_value, 2),
        final_pl=round(final_pl, 2),
        max_favorable_excursion=round(high_value - spread.max_loss, 2),
        max_adverse_excursion=round(low_value - spread.max_loss, 2),
        highest_underlying_price=round(high_price, 4),
        lowest_underlying_price=round(low_price, 4),
        profit_target_touched=exit_reason == "profit_target" or high_value >= profit_target_value,
        stop_triggered_before_exit=exit_reason == "stop_loss",
        sector_collapse_exit=exit_reason == "sector_collapse",
        market_score_entry=result.market_score,
        market_score_exit=market_score_exit,
        sector_score_entry=round(candidate.score.sector, 2),
        sector_score_exit=round(sector_score_exit, 2),
        confirmation_signals_entry=candidate.stock.confirmation_signals,
        outcome="win" if final_pl > 0 else "loss",
    )


def scenario_config(config: AppConfig, scenario: BacktestScenario) -> AppConfig:
    strategy = deepcopy(config.strategy)
    mode_name = strategy["default_mode"]
    for mode_config in strategy["modes"].values():
        mode_config["confirmation_signals_required"] = scenario.confirmation_signals_required
    strategy["trade"]["min_reward_to_risk"] = scenario.min_reward_to_risk
    strategy["trade"]["max_iv_rank"] = scenario.max_iv_rank
    strategy["trade"]["min_debit_pct_of_width"] = scenario.min_debit_pct
    strategy["trade"]["max_debit_pct_of_width"] = scenario.max_debit_pct
    strategy["default_mode"] = mode_name
    return AppConfig(strategy=strategy, scoring=config.scoring, universe=config.universe, broker=config.broker)


def spread_value_at_underlying(underlying_price: float, long_call: float, width: float) -> float:
    intrinsic = max(min(underlying_price - long_call, width), 0.0)
    return intrinsic * 100


def spread_mark_at_underlying(underlying_price: float, spread, current_date: date, entry_date: date) -> float:
    intrinsic = spread_value_at_underlying(underlying_price, spread.long_call, spread.width)
    total_days = max((spread.expiration - entry_date).days, 1)
    remaining_ratio = max((spread.expiration - current_date).days, 0) / total_days
    distance_pct = max((spread.long_call - underlying_price) / max(underlying_price, 1) * 100, 0.0)
    expected = max(spread.expected_move_pct, 1.0)
    proximity = max(0.0, min(1.0, 1 - distance_pct / expected))
    time_value = spread.max_loss * remaining_ratio * (0.65 + 0.35 * proximity)
    return round(max(intrinsic, min(spread.width * 100, intrinsic + time_value)), 2)


def _scenario_exit(
    hold_bars,
    spread,
    entry_date: date,
    planned_exit_date: date,
    planned_exit_price: float,
    profit_target_value: float,
    stop_value: float,
) -> tuple[date, float, float, str]:
    for bar in hold_bars:
        high_mark = spread_mark_at_underlying(bar.high, spread, bar.date, entry_date)
        if high_mark >= profit_target_value:
            return bar.date, bar.high, round(profit_target_value, 2), "profit_target"
        close_mark = spread_mark_at_underlying(bar.close, spread, bar.date, entry_date)
        if bar.date != entry_date and close_mark <= stop_value:
            return bar.date, bar.close, close_mark, "stop_loss"
    planned_value = spread_mark_at_underlying(planned_exit_price, spread, planned_exit_date, entry_date)
    return planned_exit_date, planned_exit_price, planned_value, "planned_exit"


def _sector_score(provider: HistoricalDataProvider, sector_name: str, as_of: date) -> float:
    for sector in provider.get_sector_snapshots(as_of):
        if sector.name == sector_name:
            return score_sector(sector)
    return 0.0


def summarize_backtest(scans: list[ScanResult], trades: list[BacktestTrade]) -> dict[str, Any]:
    wins = [trade.final_pl for trade in trades if trade.final_pl > 0]
    losses = [trade.final_pl for trade in trades if trade.final_pl <= 0]
    trade_count = len(trades)
    win_rate = len(wins) / trade_count if trade_count else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss) if trade_count else 0.0
    return {
        "scan_count": len(scans),
        "trade_count": trade_count,
        "sit_out_count": sum(1 for scan in scans if scan.action == RecommendationAction.SIT_TODAY_OUT),
        "win_rate": round(win_rate, 4),
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_drawdown([trade.final_pl for trade in trades]), 2),
        "performance_by_sector": grouped_performance(trades, lambda trade: trade.sector),
        "performance_by_market_regime": grouped_performance(trades, lambda trade: trade.market_regime),
        "performance_by_score_bucket": grouped_performance(trades, lambda trade: trade.score_bucket),
    }


def grouped_performance(trades: list[BacktestTrade], key_fn) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[BacktestTrade]] = defaultdict(list)
    for trade in trades:
        groups[key_fn(trade)].append(trade)
    return {
        key: {
            "trades": len(values),
            "wins": sum(1 for trade in values if trade.final_pl > 0),
            "win_rate": round(sum(1 for trade in values if trade.final_pl > 0) / len(values), 4),
            "total_pl": round(sum(trade.final_pl for trade in values), 2),
            "average_pl": round(sum(trade.final_pl for trade in values) / len(values), 2),
        }
        for key, values in sorted(groups.items())
    }


def max_drawdown(pl_series: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for pl in pl_series:
        equity += pl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def market_regime(result: ScanResult) -> str:
    context = result.context
    if context.spy_above_20dma and context.nasdaq_above_20dma and not context.volatility_risk_off:
        return "risk_on"
    if context.volatility_risk_off:
        return "volatility_risk_off"
    return "mixed"


def score_bucket(score: float) -> str:
    if score >= 90:
        return "90+"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    return "<70"


def _merge_packet_outcome(path: Path, trade: BacktestTrade) -> None:
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["outcome"] = {
        "status": "closed",
        "notes": "Backtest simulated spread outcome; no live or paper order was placed.",
        "closed_at": trade.exit_date.isoformat(),
        "final_pl": trade.final_pl,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    packet["backtest"] = {
        "entry_date": trade.entry_date.isoformat(),
        "scenario": trade.scenario,
        "exit_underlying_price": trade.exit_underlying_price,
        "exit_spread_value": trade.exit_spread_value,
        "final_value": trade.final_value,
        "max_favorable_excursion": trade.max_favorable_excursion,
        "max_adverse_excursion": trade.max_adverse_excursion,
        "highest_underlying_price": trade.highest_underlying_price,
        "lowest_underlying_price": trade.lowest_underlying_price,
        "profit_target_touched": trade.profit_target_touched,
        "stop_triggered_before_exit": trade.stop_triggered_before_exit,
        "market_score_entry": trade.market_score_entry,
        "market_score_exit": trade.market_score_exit,
        "sector_score_entry": trade.sector_score_entry,
        "sector_score_exit": trade.sector_score_exit,
        "confirmation_signals_entry": trade.confirmation_signals_entry,
        "outcome": trade.outcome,
        "market_regime": trade.market_regime,
        "score_bucket": trade.score_bucket,
    }
    path.write_text(json.dumps(packet, default=json_default, indent=2, sort_keys=True), encoding="utf-8")
