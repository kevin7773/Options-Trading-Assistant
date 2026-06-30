from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RecommendationAction(str, Enum):
    BUY = "BUY"
    WATCHLIST = "WATCHLIST"
    SIT_TODAY_OUT = "SIT TODAY OUT"


class RejectionStage(str, Enum):
    MARKET = "market"
    SECTOR = "sector"
    COOLING_OFF = "cooling_off"
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    CONFIRMATION = "confirmation"
    OPTIONS = "options"
    SCORING = "scoring"


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: date
    spy_above_20dma: bool
    nasdaq_above_20dma: bool
    vix: float
    vix_rising: bool
    distribution_days: int
    breadth_score: float
    growth_participation_score: float
    volatility_source: str = "VIX"
    volatility_risk_off: bool = False


@dataclass(frozen=True)
class SectorSnapshot:
    name: str
    primary_etf: str
    relative_strength_1d: float
    relative_strength_5d: float
    relative_strength_20d: float
    above_20dma: bool
    above_50dma: bool
    volume_trend_score: float
    momentum_score: float
    recovery_score: float


@dataclass(frozen=True)
class StockSnapshot:
    ticker: str
    sector: str
    price: float
    above_100dma: bool
    above_200dma: bool
    trend_90d: float
    sector_relative_strength: float
    drawdown_from_swing_high_pct: float
    rsi: float
    near_support: bool
    selling_volume_stabilizing: bool
    making_lower_lows: bool
    company_specific_warning: bool = False
    confirmation_signals: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OptionSpread:
    ticker: str
    expiration: date
    long_call: float
    short_call: float
    debit: float
    long_delta: float
    short_delta: float
    long_open_interest: int
    short_open_interest: int
    bid_ask_width_pct: float
    volume_score: float
    iv_rank: float
    expected_move_pct: float
    estimated_debit: float | None = None
    debit_pct_of_width: float | None = None
    expected_move: float | None = None
    distance_to_long_strike: float | None = None
    distance_to_short_strike: float | None = None
    estimated_reward_risk: float | None = None
    pricing_reason: str | None = None

    @property
    def width(self) -> float:
        return self.short_call - self.long_call

    @property
    def max_profit(self) -> float:
        return max(self.width - self.debit, 0) * 100

    @property
    def max_loss(self) -> float:
        return self.debit * 100

    @property
    def reward_to_risk(self) -> float:
        if self.max_loss == 0:
            return 0
        return self.max_profit / self.max_loss

    @property
    def breakeven(self) -> float:
        return self.long_call + self.debit


@dataclass(frozen=True)
class ScoreBreakdown:
    market: float
    sector: float
    trend: float
    confirmation: float
    options: float

    @property
    def total(self) -> float:
        return self.market + self.sector + self.trend + self.confirmation + self.options


@dataclass(frozen=True)
class TradeCandidate:
    stock: StockSnapshot
    sector: SectorSnapshot
    spread: OptionSpread
    score: ScoreBreakdown
    grade: str
    rationale: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class SignalCandidate:
    stock: StockSnapshot
    sector: SectorSnapshot
    market_score: float
    sector_score: float
    trend_score: float
    confirmation_score: float

    @property
    def ranking_score(self) -> float:
        return self.sector_score + self.trend_score + self.confirmation_score


@dataclass(frozen=True)
class RankedStockSignal:
    signal: SignalCandidate
    sector_rank: int
    sector_eligible: bool
    qualified: bool
    rejection: RejectedCandidate | None = None


@dataclass(frozen=True)
class RejectedCandidate:
    stage: RejectionStage
    reasons: tuple[str, ...]
    ticker: str | None = None
    sector: str | None = None
    expiration: date | None = None
    long_call: float | None = None
    short_call: float | None = None
    score: float | None = None


@dataclass(frozen=True)
class RankedSector:
    sector: str
    etf: str
    score: float
    rank: int
    eligible: bool


@dataclass(frozen=True)
class ScanContext:
    spy_above_20dma: bool | None = None
    nasdaq_above_20dma: bool | None = None
    vix: float | None = None
    vix_rising: bool | None = None
    volatility_source: str | None = None
    volatility_risk_off: bool | None = None
    distribution_days: int | None = None
    breadth_score: float | None = None
    growth_participation_score: float | None = None
    top_sectors: tuple[RankedSector, ...] = field(default_factory=tuple)
    stocks_scanned: int = 0
    spreads_evaluated: int = 0


@dataclass(frozen=True)
class ScanResult:
    action: RecommendationAction
    mode: str
    strategy_version: str
    as_of: date
    reason: str
    market_score: float
    context: ScanContext = field(default_factory=ScanContext)
    recommendations: tuple[TradeCandidate, ...] = field(default_factory=tuple)
    rejections: tuple[RejectedCandidate, ...] = field(default_factory=tuple)
    rejected_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        return payload
