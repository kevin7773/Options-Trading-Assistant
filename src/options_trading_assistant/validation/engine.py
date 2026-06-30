from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.validation.models import (
    SetupEvidence,
    SpreadEvidence,
    ValidationCheck,
    ValidationResult,
)


def load_validation_protocol(path: Path | None = None) -> dict[str, Any]:
    protocol_path = path or PROJECT_ROOT / "config" / "validation.yaml"
    return yaml.safe_load(protocol_path.read_text(encoding="utf-8")) or {}


def load_backtest_evidence(runs_root: Path, scenario: str) -> list[SpreadEvidence]:
    evidence: list[SpreadEvidence] = []
    for path in sorted(runs_root.rglob("trades.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            trade = json.loads(line)
            if str(trade.get("scenario")) != scenario:
                continue
            entry_date = str(trade["entry_date"])
            evidence.append(
                SpreadEvidence(
                    entry_date=entry_date,
                    ticker=str(trade["ticker"]).upper(),
                    final_pl=float(trade["final_pl"]),
                    risk=float(trade["debit"]) * 100,
                    period=_period_from_entry(entry_date),
                    source_path=str(path),
                )
            )
    return evidence


def load_packet_evidence(packet_root: Path) -> list[SpreadEvidence]:
    evidence: list[SpreadEvidence] = []
    for path in sorted(packet_root.rglob("*.json")) if packet_root.exists() else []:
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if packet.get("decision_type") != "recommendation":
            continue
        outcome = packet.get("outcome") or {}
        spread = packet.get("spread") or {}
        final_pl = outcome.get("final_pl")
        debit = spread.get("debit")
        if final_pl is None or debit in (None, 0):
            continue
        entry_date = str((packet.get("scan") or {}).get("as_of") or "")
        if not entry_date:
            continue
        evidence.append(
            SpreadEvidence(
                entry_date=entry_date,
                ticker=str(packet.get("ticker") or "").upper(),
                final_pl=float(final_pl),
                risk=float(debit) * 100,
                period=entry_date[:7],
                source_path=str(path),
            )
        )
    return evidence


def evaluate_edge(
    evidence: Iterable[SpreadEvidence],
    scenario: str,
    evidence_kind: str,
    protocol: dict[str, Any] | None = None,
    benchmark_evidence: Iterable[SpreadEvidence] | None = None,
    project_root: Path | None = None,
) -> ValidationResult:
    resolved_protocol = protocol or load_validation_protocol()
    costs = resolved_protocol["costs"]
    acceptance = resolved_protocol["acceptance"]
    setups = aggregate_independent_setups(
        evidence,
        round_trip_cost_per_spread=float(costs["round_trip_cost_per_spread"]),
    )
    metrics = calculate_metrics(
        setups,
        bootstrap_samples=int(acceptance["bootstrap_samples"]),
        confidence_level=float(acceptance["confidence_level"]),
    )
    benchmark_metrics = None
    benchmark_available = False
    if benchmark_evidence is not None:
        benchmark_setups = aggregate_independent_setups(
            benchmark_evidence,
            round_trip_cost_per_spread=float(costs["round_trip_cost_per_spread"]),
        )
        benchmark_metrics = calculate_metrics(
            benchmark_setups,
            bootstrap_samples=int(acceptance["bootstrap_samples"]),
            confidence_level=float(acceptance["confidence_level"]),
        )
        baseline_by_key = {
            (setup.entry_date, setup.ticker): setup
            for setup in setups
        }
        benchmark_by_key = {
            (setup.entry_date, setup.ticker): setup
            for setup in benchmark_setups
        }
        paired_keys = sorted(set(baseline_by_key).intersection(benchmark_by_key))
        paired_lifts = [
            baseline_by_key[key].return_r - benchmark_by_key[key].return_r
            for key in paired_keys
        ]
        metrics["benchmark_expectancy_r"] = benchmark_metrics["expectancy_r"]
        metrics["benchmark_paired_setups"] = len(paired_keys)
        metrics["benchmark_lift_r"] = (
            round(sum(paired_lifts) / len(paired_lifts), 6)
            if paired_lifts
            else None
        )
        benchmark_available = bool(paired_lifts)

    integrity = verify_baseline_manifest(resolved_protocol, project_root=project_root)
    checks = _validation_checks(
        metrics=metrics,
        evidence_kind=evidence_kind,
        acceptance=acceptance,
        pass_eligible_kinds=resolved_protocol["evidence"]["pass_eligible_kinds"],
        integrity=integrity,
        benchmark_available=benchmark_available,
    )
    verdict = _verdict(checks)
    return ValidationResult(
        verdict=verdict,
        baseline_version=str(resolved_protocol["baseline_version"]),
        scenario=scenario,
        evidence_kind=evidence_kind,
        metrics=metrics,
        checks=tuple(checks),
        integrity=integrity,
        setups=tuple(setups),
    )


def aggregate_independent_setups(
    evidence: Iterable[SpreadEvidence],
    round_trip_cost_per_spread: float,
) -> list[SetupEvidence]:
    grouped: dict[tuple[str, str], list[SpreadEvidence]] = defaultdict(list)
    for spread in evidence:
        grouped[(spread.entry_date, spread.ticker)].append(spread)

    setups = []
    for (entry_date, ticker), spreads in sorted(grouped.items()):
        gross_pl = sum(spread.final_pl for spread in spreads)
        risk = sum(spread.risk for spread in spreads)
        net_pl = gross_pl - round_trip_cost_per_spread * len(spreads)
        setups.append(
            SetupEvidence(
                entry_date=entry_date,
                ticker=ticker,
                gross_pl=round(gross_pl, 2),
                net_pl=round(net_pl, 2),
                risk=round(risk, 2),
                return_r=round(net_pl / risk, 6) if risk else 0.0,
                spread_count=len(spreads),
                period=spreads[0].period,
            )
        )
    return setups


def calculate_metrics(
    setups: list[SetupEvidence],
    bootstrap_samples: int,
    confidence_level: float,
) -> dict[str, Any]:
    returns = [setup.return_r for setup in setups]
    net_values = [setup.net_pl for setup in setups]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value <= 0]
    periods: dict[str, float] = defaultdict(float)
    for setup in setups:
        periods[setup.period] += setup.net_pl
    active_periods = len(periods)
    profitable_periods = sum(1 for value in periods.values() if value > 0)
    lower, upper = _bootstrap_mean_interval(returns, bootstrap_samples, confidence_level)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "independent_setups": len(setups),
        "spreads": sum(setup.spread_count for setup in setups),
        "net_total_pl": round(sum(net_values), 2),
        "expectancy_per_setup": round(sum(net_values) / len(setups), 2) if setups else 0.0,
        "expectancy_r": round(sum(returns) / len(returns), 6) if returns else 0.0,
        "bootstrap_expectancy_r_lower": lower,
        "bootstrap_expectancy_r_upper": upper,
        "setup_win_rate": round(len(wins) / len(setups), 6) if setups else 0.0,
        "profit_factor": (
            round(gross_profit / gross_loss, 6)
            if gross_loss
            else (math.inf if gross_profit else 0.0)
        ),
        "max_drawdown_r": round(abs(_max_drawdown(returns)), 6),
        "active_periods": active_periods,
        "profitable_periods": profitable_periods,
        "profitable_period_ratio": (
            round(profitable_periods / active_periods, 6)
            if active_periods
            else 0.0
        ),
        "period_net_pl": {period: round(value, 2) for period, value in sorted(periods.items())},
    }


def verify_baseline_manifest(
    protocol: dict[str, Any],
    project_root: Path | None = None,
) -> dict[str, Any]:
    root = project_root or PROJECT_ROOT
    manifest_path = root / str(protocol["baseline_manifest"])
    if not manifest_path.exists():
        return {"valid": False, "reason": f"Baseline manifest not found: {manifest_path}", "mismatches": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for relative_path, expected_hash in manifest.get("files", {}).items():
        path = root / relative_path
        actual_hash = sha256_file(path) if path.exists() else None
        if actual_hash != expected_hash:
            mismatches.append(
                {
                    "path": relative_path,
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )
    return {
        "valid": not mismatches,
        "manifest_path": str(manifest_path),
        "mismatches": mismatches,
        "strategy_version": manifest.get("strategy_version"),
    }


def create_baseline_manifest(
    strategy_version: str,
    files: Iterable[str],
    output_path: Path,
    project_root: Path | None = None,
) -> Path:
    root = project_root or PROJECT_ROOT
    payload = {
        "schema_version": "frozen_baseline_v1",
        "strategy_version": strategy_version,
        "files": {
            relative_path: sha256_file(root / relative_path)
            for relative_path in sorted(files)
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def format_validation_report(result: ValidationResult) -> str:
    metrics = result.metrics
    lines = [
        f"# Edge Validation: {result.scenario}",
        "",
        f"Verdict: **{result.verdict}**",
        f"Baseline: {result.baseline_version}",
        f"Evidence kind: {result.evidence_kind}",
        f"Baseline integrity: {'PASS' if result.integrity.get('valid') else 'FAIL'}",
        "",
        "## Metrics",
        "",
        f"- Independent setups: {metrics['independent_setups']}",
        f"- Spreads: {metrics['spreads']}",
        f"- Net P/L after configured costs: ${metrics['net_total_pl']:.2f}",
        f"- Expectancy: {metrics['expectancy_r']:.3f}R per setup",
        (
            f"- Bootstrap confidence interval: "
            f"{metrics['bootstrap_expectancy_r_lower']:.3f}R to "
            f"{metrics['bootstrap_expectancy_r_upper']:.3f}R"
        ),
        f"- Profit factor: {_format_number(metrics['profit_factor'])}",
        f"- Maximum drawdown: {metrics['max_drawdown_r']:.3f}R",
        f"- Profitable periods: {metrics['profitable_periods']}/{metrics['active_periods']}",
        "",
        "## Predeclared Checks",
        "",
    ]
    for check in result.checks:
        status = "PASS" if check.passed else ("INSUFFICIENT" if not check.sufficient else "FAIL")
        lines.append(f"- [{status}] {check.name}: {check.detail}")
    return "\n".join(lines) + "\n"


def result_to_dict(result: ValidationResult) -> dict[str, Any]:
    return asdict(result)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validation_checks(
    metrics: dict[str, Any],
    evidence_kind: str,
    acceptance: dict[str, Any],
    pass_eligible_kinds: list[str],
    integrity: dict[str, Any],
    benchmark_available: bool,
) -> list[ValidationCheck]:
    checks = [
        _check(
            "Frozen baseline integrity",
            bool(integrity.get("valid")),
            True,
            integrity.get("valid"),
            True,
            "All frozen strategy and engine hashes must match.",
        ),
        _check(
            "Pass-eligible evidence",
            evidence_kind in pass_eligible_kinds,
            evidence_kind in pass_eligible_kinds,
            evidence_kind,
            pass_eligible_kinds,
            "Retrospective evidence may falsify the strategy but cannot validate it.",
        ),
        _check(
            "Independent sample size",
            metrics["independent_setups"] >= int(acceptance["minimum_independent_setups"]),
            metrics["independent_setups"] >= int(acceptance["minimum_independent_setups"]),
            metrics["independent_setups"],
            acceptance["minimum_independent_setups"],
            "Correlated spreads from one ticker/date count as one setup.",
        ),
        _check(
            "Active periods",
            metrics["active_periods"] >= int(acceptance["minimum_active_periods"]),
            metrics["active_periods"] >= int(acceptance["minimum_active_periods"]),
            metrics["active_periods"],
            acceptance["minimum_active_periods"],
            "Evidence must span multiple periods.",
        ),
        _check(
            "Expectancy",
            metrics["expectancy_r"] >= float(acceptance["minimum_expectancy_r"]),
            True,
            metrics["expectancy_r"],
            acceptance["minimum_expectancy_r"],
            "Average net return per independent setup after configured costs.",
        ),
        _check(
            "Bootstrap lower bound",
            metrics["bootstrap_expectancy_r_lower"]
            > float(acceptance["minimum_bootstrap_expectancy_r"]),
            True,
            metrics["bootstrap_expectancy_r_lower"],
            acceptance["minimum_bootstrap_expectancy_r"],
            "The lower confidence bound must remain above zero.",
        ),
        _check(
            "Profit factor",
            metrics["profit_factor"] >= float(acceptance["minimum_profit_factor"]),
            True,
            metrics["profit_factor"],
            acceptance["minimum_profit_factor"],
            "Gross wins divided by gross losses.",
        ),
        _check(
            "Maximum drawdown",
            metrics["max_drawdown_r"] <= float(acceptance["maximum_drawdown_r"]),
            True,
            metrics["max_drawdown_r"],
            acceptance["maximum_drawdown_r"],
            "Cumulative setup-level drawdown in R.",
        ),
        _check(
            "Profitable-period ratio",
            metrics["profitable_period_ratio"]
            >= float(acceptance["minimum_profitable_period_ratio"]),
            True,
            metrics["profitable_period_ratio"],
            acceptance["minimum_profitable_period_ratio"],
            "Positive expectancy must not come from one isolated period.",
        ),
    ]
    require_benchmark = bool(acceptance.get("require_benchmark", False))
    benchmark_lift = metrics.get("benchmark_lift_r")
    checks.append(
        _check(
            "Benchmark improvement",
            (
                benchmark_lift is not None
                and benchmark_lift >= float(acceptance["minimum_benchmark_lift_r"])
            )
            if require_benchmark
            else True,
            benchmark_lift is not None or not require_benchmark,
            benchmark_lift,
            acceptance.get("minimum_benchmark_lift_r"),
            "A scanner edge requires improvement over a predeclared control.",
        )
    )
    return checks


def _check(
    name: str,
    passed: bool,
    sufficient: bool,
    actual: Any,
    required: Any,
    detail: str,
) -> ValidationCheck:
    return ValidationCheck(
        name=name,
        passed=passed,
        sufficient=sufficient,
        actual=actual,
        required=required,
        detail=f"{detail} Actual={actual!r}; required={required!r}.",
    )


def _verdict(checks: list[ValidationCheck]) -> str:
    if any(not check.sufficient for check in checks):
        return "INSUFFICIENT EVIDENCE"
    if any(not check.passed for check in checks):
        return "FAIL"
    return "PASS"


def _bootstrap_mean_interval(
    values: list[float],
    samples: int,
    confidence_level: float,
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(41)
    means = []
    for _ in range(max(samples, 1)):
        draw = [rng.choice(values) for _ in values]
        means.append(sum(draw) / len(draw))
    means.sort()
    tail = (1 - confidence_level) / 2
    lower_index = max(0, min(int(tail * len(means)), len(means) - 1))
    upper_index = max(0, min(int((1 - tail) * len(means)) - 1, len(means) - 1))
    return round(means[lower_index], 6), round(means[upper_index], 6)


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _period_from_entry(entry_date: str) -> str:
    return entry_date[:4] if len(entry_date) >= 4 else "unknown"


def _format_number(value: float) -> str:
    return "∞" if math.isinf(value) else f"{value:.2f}"
