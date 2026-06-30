from pathlib import Path

from options_trading_assistant.validation.engine import (
    aggregate_independent_setups,
    calculate_metrics,
    create_baseline_manifest,
    evaluate_edge,
    verify_baseline_manifest,
)
from options_trading_assistant.validation.models import SpreadEvidence
from options_trading_assistant.validation.ranking import (
    evaluate_ranking_criteria,
    summarize_ranking_records,
)


def _spread(
    entry_date: str,
    ticker: str,
    final_pl: float,
    risk: float = 100,
    period: str = "2025",
) -> SpreadEvidence:
    return SpreadEvidence(
        entry_date=entry_date,
        ticker=ticker,
        final_pl=final_pl,
        risk=risk,
        period=period,
        source_path="test",
    )


def test_correlated_spreads_count_as_one_independent_setup():
    setups = aggregate_independent_setups(
        [
            _spread("2025-01-02", "MSFT", 20),
            _spread("2025-01-02", "MSFT", 40, risk=200),
            _spread("2025-01-03", "NVDA", -10),
        ],
        round_trip_cost_per_spread=4,
    )

    assert len(setups) == 2
    assert setups[0].spread_count == 2
    assert setups[0].gross_pl == 60
    assert setups[0].net_pl == 52
    assert setups[0].risk == 300


def test_metrics_are_setup_level_and_include_costs():
    setups = aggregate_independent_setups(
        [
            _spread("2025-01-02", "MSFT", 24),
            _spread("2025-01-03", "NVDA", -6),
        ],
        round_trip_cost_per_spread=4,
    )

    metrics = calculate_metrics(setups, bootstrap_samples=100, confidence_level=0.95)

    assert metrics["independent_setups"] == 2
    assert metrics["spreads"] == 2
    assert metrics["net_total_pl"] == 10
    assert metrics["setup_win_rate"] == 0.5


def test_retrospective_evidence_cannot_receive_pass_verdict(tmp_path):
    tracked = tmp_path / "strategy.txt"
    tracked.write_text("frozen", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    create_baseline_manifest(
        strategy_version="v4.1",
        files=["strategy.txt"],
        output_path=manifest,
        project_root=tmp_path,
    )
    protocol = {
        "baseline_version": "v4.1",
        "baseline_manifest": "manifest.json",
        "evidence": {"pass_eligible_kinds": ["holdout", "forward"]},
        "costs": {"round_trip_cost_per_spread": 0},
        "acceptance": {
            "minimum_independent_setups": 1,
            "minimum_active_periods": 1,
            "minimum_profitable_period_ratio": 0,
            "minimum_expectancy_r": -1,
            "minimum_profit_factor": 0,
            "minimum_bootstrap_expectancy_r": -1,
            "maximum_drawdown_r": 10,
            "confidence_level": 0.95,
            "bootstrap_samples": 100,
            "require_benchmark": False,
            "minimum_benchmark_lift_r": 0,
        },
    }

    result = evaluate_edge(
        evidence=[_spread("2025-01-02", "MSFT", 20)],
        scenario="baseline",
        evidence_kind="retrospective",
        protocol=protocol,
        project_root=tmp_path,
    )

    assert result.verdict == "INSUFFICIENT EVIDENCE"


def test_benchmark_lift_uses_only_paired_setups(tmp_path):
    tracked = tmp_path / "strategy.txt"
    tracked.write_text("frozen", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    create_baseline_manifest("v4.1", ["strategy.txt"], manifest, project_root=tmp_path)
    protocol = {
        "baseline_version": "v4.1",
        "baseline_manifest": "manifest.json",
        "evidence": {"pass_eligible_kinds": ["holdout"]},
        "costs": {"round_trip_cost_per_spread": 0},
        "acceptance": {
            "minimum_independent_setups": 1,
            "minimum_active_periods": 1,
            "minimum_profitable_period_ratio": 0,
            "minimum_expectancy_r": -1,
            "minimum_profit_factor": 0,
            "minimum_bootstrap_expectancy_r": -1,
            "maximum_drawdown_r": 10,
            "confidence_level": 0.95,
            "bootstrap_samples": 100,
            "require_benchmark": True,
            "minimum_benchmark_lift_r": 0.05,
        },
    }

    result = evaluate_edge(
        evidence=[
            _spread("2025-01-02", "MSFT", 20),
            _spread("2025-01-03", "NVDA", 100),
        ],
        benchmark_evidence=[
            _spread("2025-01-02", "MSFT", 10),
            _spread("2025-01-04", "AAPL", -100),
        ],
        scenario="baseline",
        evidence_kind="holdout",
        protocol=protocol,
        project_root=tmp_path,
    )

    assert result.metrics["benchmark_paired_setups"] == 1
    assert result.metrics["benchmark_lift_r"] == 0.1


def test_manifest_detects_frozen_file_change(tmp_path):
    tracked = tmp_path / "strategy.txt"
    tracked.write_text("frozen", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    create_baseline_manifest("v4.1", ["strategy.txt"], manifest, project_root=tmp_path)
    tracked.write_text("changed", encoding="utf-8")

    integrity = verify_baseline_manifest(
        {"baseline_manifest": "manifest.json"},
        project_root=tmp_path,
    )

    assert integrity["valid"] is False
    assert integrity["mismatches"][0]["path"] == "strategy.txt"


def test_ranking_summary_measures_rank1_and_top3_capture():
    records = [
        {
            "as_of": "2025-01-02",
            "scan_index": 0,
            "benchmarks": {
                "20": {
                    "random_eligible": 0.05,
                    "oracle_return": 0.20,
                    "oracle_ticker": "ONE",
                    "spy": 0.03,
                    "qqq": 0.04,
                    "top_sector_etf": 0.02,
                }
            },
            "rankings": [
                {"ticker": "ONE", "ranking_score": 10, "forward_returns": {"20": 0.20}},
                {"ticker": "TWO", "ranking_score": 9, "forward_returns": {"20": 0.10}},
                {"ticker": "THREE", "ranking_score": 8, "forward_returns": {"20": -0.05}},
            ],
        },
        {
            "as_of": "2025-01-03",
            "scan_index": 20,
            "benchmarks": {
                "20": {
                    "random_eligible": 0.02,
                    "oracle_return": 0.04,
                    "oracle_ticker": "TWO",
                    "spy": 0.01,
                    "qqq": 0.02,
                    "top_sector_etf": 0.01,
                }
            },
            "rankings": [
                {"ticker": "ONE", "ranking_score": 10, "forward_returns": {"20": 0.01}},
                {"ticker": "TWO", "ranking_score": 9, "forward_returns": {"20": 0.04}},
                {"ticker": "THREE", "ranking_score": 8, "forward_returns": {"20": 0.02}},
            ],
        },
    ]

    summary = summarize_ranking_records(
        records,
        top_n=3,
        horizons=[20],
        total_scan_days=2,
        market_pass_days=2,
    )

    metrics = summary["horizons"]["20"]
    assert metrics["rank1_best_rate"] == 0.5
    assert metrics["top3_capture_rate"] == 1.0
    assert metrics["random_rank1_baseline"] == round(1 / 3, 6)


def test_ranking_verdict_requires_predeclared_sample_size():
    summary = {
        "horizons": {
                "20": {
                    "evaluated_days": 10,
                    "rank1_best_rate": 0.8,
                    "top3_capture_rate": 0.9,
                    "mean_rank_correlation": 0.2,
                    "independent_cohorts": 10,
                    "independent_rank1_best_rate": 0.8,
                    "independent_top3_capture_rate": 0.9,
                    "independent_mean_rank_correlation": 0.2,
                    "independent_complexity_benchmarks": {
                        name: {"rank1_lift": 0.01}
                        for name in ("random_eligible", "spy", "qqq", "top_sector_etf")
                    },
                }
        }
    }
    protocol = {
        "ranking_experiment": {
            "primary_horizon": 20,
            "minimum_evaluated_days": 100,
            "minimum_independent_cohorts": 30,
            "minimum_rank1_best_rate": 0.55,
            "minimum_top3_capture_rate": 0.75,
            "minimum_mean_rank_correlation": 0.10,
            "complexity_benchmarks": {
                "required": ["random_eligible", "spy", "qqq", "top_sector_etf"],
                "minimum_average_return_lift": 0.0,
            },
        }
    }

    result = evaluate_ranking_criteria(summary, protocol)

    assert result["verdict"] == "INSUFFICIENT EVIDENCE"
