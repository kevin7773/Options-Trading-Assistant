from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from options_trading_assistant.config import AppConfig, PROJECT_ROOT
from options_trading_assistant.models import StockSnapshot


REENTRY_SIGNALS = frozenset(
    {
        "reclaim_of_20_day_moving_average",
        "break_above_recent_swing_high",
    }
)


@dataclass
class CoolingOffTracker:
    enabled: bool
    failed_trades_before_pause: int
    failure_streaks: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: AppConfig) -> "CoolingOffTracker":
        cooling_config = config.strategy.get("cooling_off", {})
        return cls(
            enabled=bool(cooling_config.get("enabled", False)),
            failed_trades_before_pause=max(int(cooling_config.get("failed_trades_before_pause", 2)), 1),
        )

    @classmethod
    def from_decision_packets(
        cls,
        config: AppConfig,
        packet_root: Path | None = None,
    ) -> "CoolingOffTracker":
        tracker = cls.from_config(config)
        if not tracker.enabled:
            return tracker

        root = packet_root or PROJECT_ROOT / "data" / "journal" / "decision_packets"
        outcomes: list[tuple[str, str, str, float]] = []
        for path in root.rglob("*.json") if root.exists() else []:
            try:
                packet: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if packet.get("decision_type") != "recommendation":
                continue
            ticker = str(packet.get("ticker") or "").upper()
            final_pl = (packet.get("outcome") or {}).get("final_pl")
            if not ticker or final_pl is None:
                continue
            scan = packet.get("scan") or {}
            outcome = packet.get("outcome") or {}
            outcomes.append(
                (
                    str(outcome.get("closed_at") or packet.get("created_at") or ""),
                    str(scan.get("as_of") or ""),
                    ticker,
                    float(final_pl),
                )
            )

        for _closed_at, _scan_date, ticker, final_pl in sorted(outcomes):
            tracker.record_outcome(ticker, final_pl)
        return tracker

    def record_outcome(self, ticker: str, final_pl: float) -> None:
        if not self.enabled:
            return
        normalized = ticker.upper()
        if final_pl > 0:
            self.failure_streaks.pop(normalized, None)
            return
        self.failure_streaks[normalized] = self.failure_streaks.get(normalized, 0) + 1

    def rejection_reason(self, stock: StockSnapshot) -> str | None:
        if not self.enabled:
            return None
        ticker = stock.ticker.upper()
        failures = self.failure_streaks.get(ticker, 0)
        if failures < self.failed_trades_before_pause:
            return None
        if REENTRY_SIGNALS.intersection(stock.confirmation_signals):
            self.failure_streaks.pop(ticker, None)
            return None
        return (
            f"{ticker} is cooling off after {failures} consecutive failed bullish spreads; "
            "require a 20-day moving-average reclaim or break above a recent swing high before re-entry."
        )
