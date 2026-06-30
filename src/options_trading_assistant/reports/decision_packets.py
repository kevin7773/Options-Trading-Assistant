from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.models import OptionSpread, ScanResult
from options_trading_assistant.reports.journal import json_default


def write_decision_packets(result: ScanResult, output_dir: Path | None = None) -> list[Path]:
    base_dir = output_dir or PROJECT_ROOT / "data" / "journal" / "decision_packets"
    scan_dir = base_dir / result.as_of.isoformat() / _scan_slug(result)
    scan_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for index, recommendation in enumerate(result.recommendations, start=1):
        packet = {
            **_base_packet(result),
            "decision_type": "recommendation",
            "decision_id": f"recommendation-{index:03d}",
            "ticker": recommendation.stock.ticker,
            "sector": recommendation.sector.name,
            "grade": recommendation.grade,
            "score": _score_payload(recommendation.score),
            "stock": asdict(recommendation.stock),
            "sector_snapshot": asdict(recommendation.sector),
            "spread": asdict(recommendation.spread),
            "measurement_features": _measurement_features(result, recommendation),
            "rationale": recommendation.rationale,
            "risks": recommendation.risks,
        }
        paths.append(_write_packet(scan_dir / f"recommendation-{index:03d}-{recommendation.stock.ticker}.json", packet))

    for index, rejection in enumerate(result.rejections, start=1):
        label = rejection.ticker or rejection.sector or rejection.stage.value
        packet = {
            **_base_packet(result),
            "decision_type": "rejection",
            "decision_id": f"rejection-{index:03d}",
            "ticker": rejection.ticker,
            "sector": rejection.sector,
            "stage": rejection.stage,
            "score": rejection.score,
            "expiration": rejection.expiration,
            "long_call": rejection.long_call,
            "short_call": rejection.short_call,
            "reasons": rejection.reasons,
        }
        paths.append(_write_packet(scan_dir / f"rejection-{index:03d}-{_safe_filename(label)}.json", packet))

    return paths


def _base_packet(result: ScanResult) -> dict[str, Any]:
    return {
        "schema_version": "decision_packet_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scan": {
            "as_of": result.as_of,
            "mode": result.mode,
            "strategy_version": result.strategy_version,
            "action": result.action,
            "reason": result.reason,
            "market_score": result.market_score,
            "context": asdict(result.context),
        },
        "outcome": {
            "status": "pending",
            "notes": None,
            "closed_at": None,
            "final_pl": None,
        },
    }


def _measurement_features(result: ScanResult, recommendation) -> dict[str, Any]:
    stock = recommendation.stock
    sector = recommendation.sector
    spread = recommendation.spread
    return {
        "hypothesis_id": "H-006",
        "measurement_version": "trade_quality_pre_entry_v1",
        "measurement_only": True,
        "score_total": recommendation.score.total,
        "score_bucket": _score_bucket(recommendation.score.total),
        "market_score_raw": result.market_score,
        "score_breakdown": asdict(recommendation.score),
        "stock_setup_score": round(recommendation.score.trend + recommendation.score.confirmation, 2),
        "market": {
            "spy_above_20dma": result.context.spy_above_20dma,
            "nasdaq_above_20dma": result.context.nasdaq_above_20dma,
            "vix": result.context.vix,
            "vix_rising": result.context.vix_rising,
            "volatility_source": result.context.volatility_source,
            "volatility_risk_off": result.context.volatility_risk_off,
            "distribution_days": result.context.distribution_days,
            "breadth_score": result.context.breadth_score,
            "growth_participation_score": result.context.growth_participation_score,
        },
        "sector": {
            "name": sector.name,
            "primary_etf": sector.primary_etf,
            "score": recommendation.score.sector,
            "relative_strength_1d": sector.relative_strength_1d,
            "relative_strength_5d": sector.relative_strength_5d,
            "relative_strength_20d": sector.relative_strength_20d,
            "above_20dma": sector.above_20dma,
            "above_50dma": sector.above_50dma,
        },
        "stock": {
            "ticker": stock.ticker,
            "price": stock.price,
            "trend_score": recommendation.score.trend,
            "confirmation_score": recommendation.score.confirmation,
            "sector_relative_strength": stock.sector_relative_strength,
            "trend_90d": stock.trend_90d,
            "drawdown_from_swing_high_pct": stock.drawdown_from_swing_high_pct,
            "rsi": stock.rsi,
            "above_100dma": stock.above_100dma,
            "above_200dma": stock.above_200dma,
            "near_support": stock.near_support,
            "selling_volume_stabilizing": stock.selling_volume_stabilizing,
            "confirmation_signal_count": len(stock.confirmation_signals),
            "confirmation_signals": stock.confirmation_signals,
        },
        "spread": {
            "expiration": spread.expiration,
            "dte": (spread.expiration - result.as_of).days,
            "long_call": spread.long_call,
            "short_call": spread.short_call,
            "width": spread.width,
            "debit": spread.debit,
            "debit_pct_of_width": _debit_pct(spread),
            "reward_to_risk": spread.reward_to_risk,
            "expected_move_pct": spread.expected_move_pct,
            "expected_move": spread.expected_move,
            "atr_proxy_pct": spread.expected_move_pct,
            "distance_to_long_strike": _distance_to_long_strike(spread, stock.price),
            "distance_to_short_strike": _distance_to_short_strike(spread, stock.price),
            "iv_rank": spread.iv_rank,
            "long_delta": spread.long_delta,
            "short_delta": spread.short_delta,
            "long_open_interest": spread.long_open_interest,
            "short_open_interest": spread.short_open_interest,
            "bid_ask_width_pct": spread.bid_ask_width_pct,
            "volume_score": spread.volume_score,
        },
    }


def _score_payload(score) -> dict[str, Any]:
    payload = asdict(score)
    payload["total"] = score.total
    return payload


def _score_bucket(score: float) -> str:
    if score >= 90:
        return "90+"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    return "<70"


def _debit_pct(spread: OptionSpread) -> float:
    return round(spread.debit / spread.width, 4) if spread.width else 0.0


def _distance_to_long_strike(spread: OptionSpread, price: float) -> float:
    if spread.distance_to_long_strike is not None:
        return spread.distance_to_long_strike
    return _distance_pct(spread.long_call, price)


def _distance_to_short_strike(spread: OptionSpread, price: float) -> float:
    if spread.distance_to_short_strike is not None:
        return spread.distance_to_short_strike
    return _distance_pct(spread.short_call, price)


def _distance_pct(strike: float, price: float) -> float:
    return round(((strike - price) / price) * 100, 2) if price else 0.0


def _scan_slug(result: ScanResult) -> str:
    timestamp = datetime.now().strftime("%H%M%S-%f")
    return f"{result.strategy_version}-{result.mode}-{result.action.value.lower().replace(' ', '-')}-{timestamp}"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value)
    return safe.strip("-") or "unknown"


def _write_packet(path: Path, packet: dict[str, Any]) -> Path:
    path.write_text(json.dumps(packet, default=json_default, indent=2, sort_keys=True), encoding="utf-8")
    return path
