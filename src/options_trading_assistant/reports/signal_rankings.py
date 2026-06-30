from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.engines.signals import SignalResult


def write_signal_ranking_snapshot(
    result: SignalResult,
    output_dir: Path | None = None,
    top_n: int = 10,
) -> Path:
    base = output_dir or PROJECT_ROOT / "data" / "journal" / "signal_rankings"
    base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S-%f")
    path = base / f"{result.as_of.isoformat()}-{timestamp}-top{top_n}.json"
    rankings = []
    eligible_universe = []
    if not result.blocked_reason:
        for predicted_rank, ranked in enumerate(result.rankings[:top_n], start=1):
            signal = ranked.signal
            rankings.append(
                {
                    "predicted_rank": predicted_rank,
                    "ticker": signal.stock.ticker,
                    "sector": signal.stock.sector,
                    "price": signal.stock.price,
                    "ranking_score": round(signal.ranking_score, 4),
                    "market_score": signal.market_score,
                    "sector_score": signal.sector_score,
                    "trend_score": signal.trend_score,
                    "confirmation_score": signal.confirmation_score,
                    "sector_rank": ranked.sector_rank,
                    "sector_eligible": ranked.sector_eligible,
                    "qualified_for_trade_construction": ranked.qualified,
                    "rejection_stage": ranked.rejection.stage.value if ranked.rejection else None,
                    "rejection_reasons": list(ranked.rejection.reasons) if ranked.rejection else [],
                }
            )
        for ranked in result.rankings:
            signal = ranked.signal
            eligible_universe.append(
                {
                    "ticker": signal.stock.ticker,
                    "sector": signal.stock.sector,
                    "price": signal.stock.price,
                    "ranking_score": round(signal.ranking_score, 4),
                    "sector_rank": ranked.sector_rank,
                    "sector_eligible": ranked.sector_eligible,
                    "qualified_for_trade_construction": ranked.qualified,
                }
            )
    payload = {
        "schema_version": "signal_ranking_snapshot_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": result.as_of.isoformat(),
        "strategy_version": result.strategy_version,
        "mode": result.mode,
        "market_passed": result.blocked_reason is None,
        "market_score": result.market_score,
        "blocked_reason": result.blocked_reason,
        "top_sector_etf": (
            result.context.top_sectors[0].etf
            if result.context.top_sectors
            else None
        ),
        "rankings": rankings,
        "eligible_universe": eligible_universe,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
