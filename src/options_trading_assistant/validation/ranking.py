from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.signals import SignalEngine
from options_trading_assistant.providers.historical import HistoricalDataProvider


def run_ranking_experiment(
    config: AppConfig,
    provider: HistoricalDataProvider,
    mode: str,
    start: date,
    end: date,
    top_n: int,
    horizons: list[int],
    output_dir: Path,
) -> dict[str, Any]:
    signal_engine = SignalEngine(config=config, provider=provider)
    records: list[dict[str, Any]] = []
    market_pass_days = 0
    all_dates = provider.available_dates(start, end)

    for scan_index, as_of in enumerate(all_dates):
        signal_result = signal_engine.run(
            mode=mode,
            as_of=as_of,
            include_all_sectors_in_rankings=True,
        )
        if signal_result.blocked_reason:
            continue
        market_pass_days += 1
        stocks = []
        for ranked in signal_result.rankings:
            signal = ranked.signal
            rejection = ranked.rejection
            stocks.append(
                {
                    "ticker": signal.stock.ticker,
                    "sector": signal.stock.sector,
                    "price": signal.stock.price,
                    "sector_rank": ranked.sector_rank,
                    "sector_eligible": ranked.sector_eligible,
                    "sector_score": signal.sector_score,
                    "trend_score": signal.trend_score,
                    "confirmation_score": signal.confirmation_score,
                    "ranking_score": round(signal.ranking_score, 4),
                    "qualified_for_trade_construction": ranked.qualified,
                    "rejection_stage": (
                        rejection.stage.value
                        if rejection
                        else ("sector" if not ranked.sector_eligible else None)
                    ),
                    "rejection_reasons": (
                        list(rejection.reasons)
                        if rejection
                        else (
                            ["Sector ranked outside the eligible set."]
                            if not ranked.sector_eligible
                            else []
                        )
                    ),
                }
            )
        eligible_universe = stocks
        top_rows = stocks[:top_n]
        for rank, row in enumerate(top_rows, start=1):
            row["predicted_rank"] = rank
            row["forward_returns"] = {
                str(horizon): _forward_return(provider, row["ticker"], as_of, horizon)
                for horizon in horizons
            }
        top_sector_etf = (
            signal_result.context.top_sectors[0].etf
            if signal_result.context.top_sectors
            else None
        )
        benchmark_returns = {}
        for horizon in horizons:
            universe_returns = [
                (row["ticker"], _forward_return(provider, row["ticker"], as_of, horizon))
                for row in eligible_universe
            ]
            available_returns = [
                (ticker, value)
                for ticker, value in universe_returns
                if value is not None
            ]
            oracle = (
                max(available_returns, key=lambda item: item[1])
                if available_returns
                else (None, None)
            )
            benchmark_returns[str(horizon)] = {
                "eligible_universe_size": len(available_returns),
                "random_eligible": (
                    round(mean(value for _ticker, value in available_returns), 8)
                    if available_returns
                    else None
                ),
                "oracle_ticker": oracle[0],
                "oracle_return": oracle[1],
                "spy": _forward_return(provider, "SPY", as_of, horizon),
                "qqq": _forward_return(provider, "QQQ", as_of, horizon),
                "top_sector_etf": (
                    _forward_return(provider, top_sector_etf, as_of, horizon)
                    if top_sector_etf
                    else None
                ),
                "top_sector_etf_ticker": top_sector_etf,
            }
        records.append(
            {
                "as_of": as_of.isoformat(),
                "scan_index": scan_index,
                "market_score": signal_result.market_score,
                "rankings": top_rows,
                "benchmarks": benchmark_returns,
            }
        )

    summary = summarize_ranking_records(
        records=records,
        top_n=top_n,
        horizons=horizons,
        total_scan_days=len(all_dates),
        market_pass_days=market_pass_days,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    rankings_path = output_dir / "daily_top10.jsonl"
    with rankings_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, sort_keys=True))
            file.write("\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        format_ranking_report(summary),
        encoding="utf-8",
    )
    return summary


def summarize_ranking_records(
    records: list[dict[str, Any]],
    top_n: int,
    horizons: list[int],
    total_scan_days: int,
    market_pass_days: int,
) -> dict[str, Any]:
    by_horizon: dict[str, Any] = {}
    for horizon in horizons:
        key = str(horizon)
        evaluated = []
        returns_by_rank: dict[int, list[float]] = defaultdict(list)
        for record in records:
            rankings = record["rankings"]
            if len(rankings) != top_n:
                continue
            returns = [row["forward_returns"].get(key) for row in rankings]
            if any(value is None for value in returns):
                continue
            numeric_returns = [float(value) for value in returns]
            benchmark = record.get("benchmarks", {}).get(key, {})
            required_benchmarks = (
                benchmark.get("random_eligible"),
                benchmark.get("oracle_return"),
                benchmark.get("spy"),
                benchmark.get("qqq"),
                benchmark.get("top_sector_etf"),
            )
            if any(value is None for value in required_benchmarks):
                continue
            winner_index = max(range(len(numeric_returns)), key=numeric_returns.__getitem__)
            predicted_scores = [float(row["ranking_score"]) for row in rankings]
            correlation = _spearman_correlation(predicted_scores, numeric_returns)
            for rank, value in enumerate(numeric_returns, start=1):
                returns_by_rank[rank].append(value)
            evaluated.append(
                {
                    "as_of": record["as_of"],
                    "scan_index": record.get("scan_index"),
                    "winner_rank": winner_index + 1,
                    "rank1_best": winner_index == 0,
                    "top3_captured": winner_index < min(3, top_n),
                    "rank_correlation": correlation,
                    "rank1_return": numeric_returns[0],
                    "top10_average_return": mean(numeric_returns),
                    "random_eligible_return": float(benchmark["random_eligible"]),
                    "oracle_return": float(benchmark["oracle_return"]),
                    "rank1_is_oracle": rankings[0]["ticker"] == benchmark["oracle_ticker"],
                    "spy_return": float(benchmark["spy"]),
                    "qqq_return": float(benchmark["qqq"]),
                    "top_sector_etf_return": float(benchmark["top_sector_etf"]),
                }
            )

        count = len(evaluated)
        rank1_hits = sum(1 for row in evaluated if row["rank1_best"])
        top3_hits = sum(1 for row in evaluated if row["top3_captured"])
        hit_rate = rank1_hits / count if count else 0.0
        confidence_low, confidence_high = _wilson_interval(rank1_hits, count)
        independent = _non_overlapping_rows(evaluated, horizon)
        independent_summary = _summarize_evaluated_rows(independent, top_n)
        independent_hits = sum(1 for row in independent if row["rank1_best"])
        independent_low, independent_high = _wilson_interval(
            independent_hits,
            len(independent),
        )
        by_horizon[key] = {
            "evaluated_days": count,
            "rank1_best_count": rank1_hits,
            "rank1_best_rate": round(hit_rate, 6),
            "rank1_best_wilson_low": confidence_low,
            "rank1_best_wilson_high": confidence_high,
            "independent_cohorts": len(independent),
            "independent_rank1_best_rate": independent_summary["rank1_best_rate"],
            "independent_rank1_wilson_low": independent_low,
            "independent_rank1_wilson_high": independent_high,
            "independent_top3_capture_rate": independent_summary["top3_capture_rate"],
            "independent_mean_rank_correlation": independent_summary["mean_rank_correlation"],
            "random_rank1_baseline": round(1 / top_n, 6),
            "top3_capture_count": top3_hits,
            "top3_capture_rate": round(top3_hits / count, 6) if count else 0.0,
            "random_top3_baseline": round(min(3, top_n) / top_n, 6),
            "mean_rank_correlation": round(
                mean(row["rank_correlation"] for row in evaluated),
                6,
            )
            if evaluated
            else 0.0,
            "rank1_average_return": round(
                mean(row["rank1_return"] for row in evaluated),
                6,
            )
            if evaluated
            else 0.0,
            "top10_average_return": round(
                mean(row["top10_average_return"] for row in evaluated),
                6,
            )
            if evaluated
            else 0.0,
            "rank1_return_lift": round(
                mean(
                    row["rank1_return"] - row["top10_average_return"]
                    for row in evaluated
                ),
                6,
            )
            if evaluated
            else 0.0,
            "average_return_by_predicted_rank": {
                str(rank): round(mean(values), 6)
                for rank, values in sorted(returns_by_rank.items())
            },
            "complexity_benchmarks": _complexity_benchmark_summary(evaluated),
            "independent_complexity_benchmarks": _complexity_benchmark_summary(independent),
            "by_year": {
                year: _summarize_evaluated_rows(
                    [row for row in evaluated if row["as_of"].startswith(year)],
                    top_n,
                )
                for year in sorted({row["as_of"][:4] for row in evaluated})
            },
        }
    return {
        "top_n": top_n,
        "total_scan_days": total_scan_days,
        "market_pass_days": market_pass_days,
        "saved_ranking_days": len(records),
        "horizons": by_horizon,
    }


def evaluate_ranking_criteria(summary: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    criteria = protocol["ranking_experiment"]
    primary = summary["horizons"][str(criteria["primary_horizon"])]
    checks = {
        "minimum_evaluated_days": (
            primary["evaluated_days"] >= int(criteria["minimum_evaluated_days"])
        ),
        "minimum_independent_cohorts": (
            primary["independent_cohorts"] >= int(criteria["minimum_independent_cohorts"])
        ),
        "minimum_rank1_best_rate": (
            primary["independent_rank1_best_rate"] >= float(criteria["minimum_rank1_best_rate"])
        ),
        "minimum_top3_capture_rate": (
            primary["independent_top3_capture_rate"] >= float(criteria["minimum_top3_capture_rate"])
        ),
        "minimum_mean_rank_correlation": (
            primary["independent_mean_rank_correlation"]
            >= float(criteria["minimum_mean_rank_correlation"])
        ),
    }
    benchmark_config = criteria["complexity_benchmarks"]
    minimum_lift = float(benchmark_config["minimum_average_return_lift"])
    for benchmark_name in benchmark_config["required"]:
        checks[f"beat_{benchmark_name}"] = (
            primary["independent_complexity_benchmarks"][benchmark_name]["rank1_lift"]
            > minimum_lift
        )
    return {
        "verdict": (
            "INSUFFICIENT EVIDENCE"
            if not checks["minimum_evaluated_days"] or not checks["minimum_independent_cohorts"]
            else ("PASS" if all(checks.values()) else "FAIL")
        ),
        "primary_horizon": criteria["primary_horizon"],
        "checks": checks,
    }


def format_ranking_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Stock Ranking Forward-Performance Experiment",
        "",
        f"Total scan days: {summary['total_scan_days']}",
        f"Market-pass days saved: {summary['market_pass_days']}",
        "",
        "| Horizon | Days | Independent cohorts | #1 rate | Independent #1 | Independent 95% CI | Random | Top-3 | Independent top-3 | Rank correlation | #1 return lift |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for horizon, metrics in summary["horizons"].items():
        lines.append(
            f"| {horizon}d | {metrics['evaluated_days']} | {metrics['independent_cohorts']} | "
            f"{metrics['rank1_best_rate']:.1%} | {metrics['independent_rank1_best_rate']:.1%} | "
            f"{metrics['independent_rank1_wilson_low']:.1%}–{metrics['independent_rank1_wilson_high']:.1%} | "
            f"{metrics['random_rank1_baseline']:.1%} | {metrics['top3_capture_rate']:.1%} | "
            f"{metrics['independent_top3_capture_rate']:.1%} | "
            f"{metrics['independent_mean_rank_correlation']:.3f} | "
            f"{metrics['rank1_return_lift']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Complexity Benchmarks (Non-Overlapping Cohorts)",
            "",
            "| Horizon | Benchmark | Benchmark return | Rank-1 lift | Rank-1 outperform rate |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for horizon, metrics in summary["horizons"].items():
        benchmarks = metrics["independent_complexity_benchmarks"]
        for name in ("random_eligible", "spy", "qqq", "top_sector_etf"):
            benchmark = benchmarks[name]
            lines.append(
                f"| {horizon}d | {name} | {benchmark['average_return']:.2%} | "
                f"{benchmark['rank1_lift']:.2%} | {benchmark['rank1_outperform_rate']:.1%} |"
            )
        oracle = benchmarks["oracle"]
        lines.append(
            f"| {horizon}d | oracle | {oracle['average_return']:.2%} | "
            f"{-oracle['rank1_regret']:.2%} | {oracle['rank1_capture_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Year-by-Year",
            "",
            "| Horizon | Year | Days | #1 rate | Top-3 capture | Rank correlation | #1 return lift |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for horizon, metrics in summary["horizons"].items():
        for year, year_metrics in metrics["by_year"].items():
            lines.append(
                f"| {horizon}d | {year} | {year_metrics['evaluated_days']} | "
                f"{year_metrics['rank1_best_rate']:.1%} | "
                f"{year_metrics['top3_capture_rate']:.1%} | "
                f"{year_metrics['mean_rank_correlation']:.3f} | "
                f"{year_metrics['rank1_return_lift']:.2%} |"
            )
    return "\n".join(lines) + "\n"


def _summarize_evaluated_rows(rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    count = len(rows)
    rank1_hits = sum(1 for row in rows if row["rank1_best"])
    top3_hits = sum(1 for row in rows if row["top3_captured"])
    return {
        "evaluated_days": count,
        "rank1_best_rate": round(rank1_hits / count, 6) if count else 0.0,
        "random_rank1_baseline": round(1 / top_n, 6),
        "top3_capture_rate": round(top3_hits / count, 6) if count else 0.0,
        "random_top3_baseline": round(min(3, top_n) / top_n, 6),
        "mean_rank_correlation": (
            round(mean(row["rank_correlation"] for row in rows), 6)
            if rows
            else 0.0
        ),
        "rank1_return_lift": (
            round(
                mean(
                    row["rank1_return"] - row["top10_average_return"]
                    for row in rows
                ),
                6,
            )
            if rows
            else 0.0
        ),
    }


def _non_overlapping_rows(
    rows: list[dict[str, Any]],
    horizon: int,
) -> list[dict[str, Any]]:
    selected = []
    next_eligible_index = -1
    for row in rows:
        scan_index = row.get("scan_index")
        if scan_index is None:
            continue
        if scan_index < next_eligible_index:
            continue
        selected.append(row)
        next_eligible_index = int(scan_index) + horizon
    return selected


def _complexity_benchmark_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mapping = {
        "random_eligible": "random_eligible_return",
        "spy": "spy_return",
        "qqq": "qqq_return",
        "top_sector_etf": "top_sector_etf_return",
    }
    for name, field in mapping.items():
        result[name] = {
            "average_return": (
                round(mean(row[field] for row in rows), 6)
                if rows
                else 0.0
            ),
            "rank1_lift": (
                round(mean(row["rank1_return"] - row[field] for row in rows), 6)
                if rows
                else 0.0
            ),
            "rank1_outperform_rate": (
                round(
                    sum(1 for row in rows if row["rank1_return"] > row[field]) / len(rows),
                    6,
                )
                if rows
                else 0.0
            ),
        }
    result["oracle"] = {
        "average_return": (
            round(mean(row["oracle_return"] for row in rows), 6)
            if rows
            else 0.0
        ),
        "rank1_regret": (
            round(mean(row["oracle_return"] - row["rank1_return"] for row in rows), 6)
            if rows
            else 0.0
        ),
        "rank1_capture_rate": (
            round(sum(1 for row in rows if row["rank1_is_oracle"]) / len(rows), 6)
            if rows
            else 0.0
        ),
    }
    return result


def _forward_return(
    provider: HistoricalDataProvider,
    ticker: str,
    as_of: date,
    horizon: int,
) -> float | None:
    series = provider.bars.get(ticker.upper(), [])
    index_by_date = provider.by_date.get(ticker.upper(), {})
    if as_of not in index_by_date:
        return None
    index = next(
        (position for position, bar in enumerate(series) if bar.date == as_of),
        None,
    )
    if index is None or index + horizon >= len(series):
        return None
    start_close = series[index].close
    end_close = series[index + horizon].close
    if start_close <= 0:
        return None
    return round(end_close / start_close - 1, 8)


def _spearman_correlation(scores: list[float], outcomes: list[float]) -> float:
    if len(scores) < 2:
        return 0.0
    score_ranks = _ranks(scores)
    outcome_ranks = _ranks(outcomes)
    score_mean = mean(score_ranks)
    outcome_mean = mean(outcome_ranks)
    numerator = sum(
        (score_rank - score_mean) * (outcome_rank - outcome_mean)
        for score_rank, outcome_rank in zip(score_ranks, outcome_ranks)
    )
    score_variance = sum((value - score_mean) ** 2 for value in score_ranks)
    outcome_variance = sum((value - outcome_mean) ** 2 for value in outcome_ranks)
    denominator = math.sqrt(score_variance * outcome_variance)
    return numerator / denominator if denominator else 0.0


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for position in range(index, end):
            ranks[ordered[position][0]] = average_rank
        index = end
    return ranks


def _wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 0.0
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / trials
            + z**2 / (4 * trials**2)
        )
        / denominator
    )
    return round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)
