from __future__ import annotations

import csv
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import urlopen

from options_trading_assistant.backtesting.models import OHLCVBar
from options_trading_assistant.backtesting.scenarios import BALANCED_SCENARIO, BacktestScenario
from options_trading_assistant.backtesting.synthetic_options_model import (
    estimate_bull_call_spread_debit,
    estimate_iv_proxy_from_expected_move,
)
from options_trading_assistant.config import AppConfig, PROJECT_ROOT, trade_config_for_symbol
from options_trading_assistant.models import MarketSnapshot, OptionSpread, SectorSnapshot, StockSnapshot
from options_trading_assistant.providers.base import DataProvider


@dataclass
class MassiveHistoricalClient:
    api_key: str
    cache_dir: Path
    calls_per_minute: int = 5
    base_url: str = "https://api.massive.com"
    _last_call_at: float = 0.0

    def fetch_stock_bars(self, ticker: str, start: date, end: date) -> list[OHLCVBar]:
        cached = self.cache_dir / "ohlcv" / f"{ticker.upper()}_{start.isoformat()}_{end.isoformat()}.csv"
        if cached.exists():
            return read_bars_csv(cached)

        path = f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        query = urlencode({"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key})
        url = f"{self.base_url}{path}?{query}"
        payload = self._get_json(url)

        bars = [
            OHLCVBar(
                ticker=ticker.upper(),
                date=datetime.fromtimestamp(row["t"] / 1000, tz=timezone.utc).date(),
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
                volume=int(row.get("v") or 0),
            )
            for row in payload.get("results", [])
        ]
        write_bars_csv(cached, bars)
        return bars

    def _rate_limit(self) -> None:
        min_interval = 60.0 / max(self.calls_per_minute, 1)
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call_at = time.monotonic()

    def _get_json(self, url: str, retries: int = 2) -> dict[str, Any]:
        for attempt in range(retries + 1):
            self._rate_limit()
            try:
                with urlopen(url, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429 and attempt < retries:
                    time.sleep(65)
                    continue
                raise
        raise RuntimeError("Massive request failed after retries.")


class HistoricalDataProvider(DataProvider):
    """Daily OHLCV-backed provider for scanner backtests.

    This provider reconstructs the existing scanner snapshots from historical bars.
    It intentionally does not call any broker APIs and does not place orders.
    """

    def __init__(
        self,
        config: AppConfig,
        bars: dict[str, list[OHLCVBar]],
        vix_proxy: str = "VIXY",
        scenario: BacktestScenario | None = None,
    ):
        self.config = config
        self.bars = {ticker.upper(): sorted(series, key=lambda bar: bar.date) for ticker, series in bars.items()}
        self.by_date = {
            ticker: {bar.date: bar for bar in series}
            for ticker, series in self.bars.items()
        }
        self.vix_proxy = vix_proxy.upper()
        self.scenario = scenario or BALANCED_SCENARIO

    @classmethod
    def from_cache(
        cls,
        config: AppConfig,
        cache_dir: Path | None = None,
        vix_proxy: str = "VIXY",
        scenario: BacktestScenario | None = None,
    ) -> "HistoricalDataProvider":
        base = _ohlcv_cache_dir(cache_dir)
        bars_by_date: dict[str, dict[date, OHLCVBar]] = {}
        for path in base.glob("*.csv") if base.exists() else []:
            series = read_bars_csv(path)
            if series:
                ticker = series[0].ticker.upper()
                bars_by_date.setdefault(ticker, {})
                for bar in series:
                    bars_by_date[ticker][bar.date] = bar
        bars = {
            ticker: [bars_by_day[day] for day in sorted(bars_by_day)]
            for ticker, bars_by_day in bars_by_date.items()
        }
        return cls(config=config, bars=bars, vix_proxy=vix_proxy, scenario=scenario)

    @classmethod
    def from_massive(
        cls,
        config: AppConfig,
        start: date,
        end: date,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        calls_per_minute: int = 5,
        vix_proxy: str = "VIXY",
        scenario: BacktestScenario | None = None,
    ) -> "HistoricalDataProvider":
        key = api_key or os.environ.get("MASSIVE_API_KEY")
        if not key:
            raise RuntimeError("Set MASSIVE_API_KEY or pass api_key before hydrating Massive historical data.")
        cache = cache_dir or PROJECT_ROOT / "data" / "historical"
        client = MassiveHistoricalClient(key, cache, calls_per_minute=calls_per_minute)
        bars = {ticker: client.fetch_stock_bars(ticker, start, end) for ticker in historical_tickers(config, vix_proxy)}
        return cls(config=config, bars=bars, vix_proxy=vix_proxy, scenario=scenario)

    def available_dates(self, start: date, end: date) -> list[date]:
        spy_dates = set(self.by_date.get("SPY", {}))
        return sorted(day for day in spy_dates if start <= day <= end)

    def get_market_snapshot(self, as_of: date) -> MarketSnapshot:
        spy = self._series_until("SPY", as_of)
        qqq = self._series_until("QQQ", as_of)
        vol = self._series_until(self.vix_proxy, as_of)
        spy_bar = self._bar_on("SPY", as_of)
        qqq_bar = self._bar_on("QQQ", as_of)
        vol_bar = self._bar_on(self.vix_proxy, as_of)

        vix_proxy_value = _pct_change(vol, 20) if len(vol) >= 21 else 0.0
        distribution_days = sum(
            1
            for bar, prev in zip(spy[-10:], spy[-11:-1])
            if bar.close < prev.close and bar.volume > prev.volume
        )
        breadth_score = _ratio_above_ma(self._all_configured_tickers(), as_of, 20, provider=self)
        growth_score = _ratio_above_ma(["QQQ", "XLK", "SMH"], as_of, 20, provider=self)
        risk_off = vix_proxy_value > self.config.strategy["market"]["max_vix_if_rising"] and _rising(vol)
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=_above_sma(spy, 20),
            nasdaq_above_20dma=_above_sma(qqq, 20),
            vix=max(vix_proxy_value, 0.0),
            vix_rising=_rising(vol),
            volatility_source=self.vix_proxy,
            volatility_risk_off=risk_off,
            distribution_days=distribution_days,
            breadth_score=breadth_score,
            growth_participation_score=growth_score,
        )

    def get_sector_snapshots(self, as_of: date) -> tuple[SectorSnapshot, ...]:
        spy = self._bar_on("SPY", as_of)
        snapshots: list[SectorSnapshot] = []
        for sector_name, sector_config in self.config.universe["sectors"].items():
            etf = sector_config["etfs"][0].upper()
            series = self._series_until(etf, as_of)
            bar = self._bar_on(etf, as_of)
            snapshots.append(
                SectorSnapshot(
                    name=sector_name,
                    primary_etf=etf,
                    relative_strength_1d=_relative_return(series, self._series_until("SPY", as_of), 1),
                    relative_strength_5d=_relative_return(series, self._series_until("SPY", as_of), 5),
                    relative_strength_20d=_relative_return(series, self._series_until("SPY", as_of), 20),
                    above_20dma=_above_sma(series, 20),
                    above_50dma=_above_sma(series, 50),
                    volume_trend_score=_volume_trend_score(series),
                    momentum_score=_bounded_score(_pct_change(series, 20), -10, 10),
                    recovery_score=_bounded_score((bar.close / max(spy.close, 1)) * 10, 0, 10),
                )
            )
        return tuple(snapshots)

    def get_stocks_for_sector(self, sector_name: str, as_of: date) -> tuple[StockSnapshot, ...]:
        sector_config = self.config.universe["sectors"].get(sector_name)
        if not sector_config:
            return ()
        sector_etf = sector_config["etfs"][0].upper()
        sector_series = self._series_until(sector_etf, as_of)
        stocks: list[StockSnapshot] = []
        for ticker in sector_config["tickers"]:
            ticker = ticker.upper()
            if ticker not in self.by_date or as_of not in self.by_date[ticker]:
                continue
            series = self._series_until(ticker, as_of)
            bar = self._bar_on(ticker, as_of)
            rsi = _rsi(series, 14)
            confirmation = []
            if bar.close > bar.open:
                confirmation.append("green_daily_candle")
            if len(series) >= 3 and series[-1].low > series[-2].low:
                confirmation.append("higher_low")
            if len(series) >= 2 and bar.close > series[-2].high:
                confirmation.append("close_above_previous_high")
            if (
                len(series) >= 21
                and bar.close > _sma(series, 20)
                and series[-2].close <= _sma(series[:-1], 20)
            ):
                confirmation.append("reclaim_of_20_day_moving_average")
            if len(series) >= 21 and bar.close > max(item.high for item in series[-21:-1]):
                confirmation.append("break_above_recent_swing_high")
            stocks.append(
                StockSnapshot(
                    ticker=ticker,
                    sector=sector_name,
                    price=bar.close,
                    above_100dma=_above_sma(series, 100),
                    above_200dma=_above_sma(series, 200),
                    trend_90d=_pct_change(series, 90) / 100,
                    sector_relative_strength=_relative_return(series, sector_series, 20) / 100,
                    drawdown_from_swing_high_pct=_drawdown_from_high(series, 30),
                    rsi=rsi,
                    near_support=bar.close <= _sma(series, 20) * 1.03,
                    selling_volume_stabilizing=_selling_volume_stabilizing(series),
                    making_lower_lows=_making_lower_lows(series),
                    confirmation_signals=tuple(confirmation),
                )
            )
        return tuple(stocks)

    def get_option_spreads(self, ticker: str, as_of: date) -> tuple[OptionSpread, ...]:
        bar = self._bar_on(ticker.upper(), as_of)
        expiration = _next_expiration(as_of, self.config.strategy["trade"]["min_days_to_expiration"])
        dte = (expiration - as_of).days
        expected_move_pct = max(_average_true_range_pct(self._series_until(ticker.upper(), as_of), 14), 2.0)
        iv_proxy = estimate_iv_proxy_from_expected_move(expected_move_pct)
        spreads: list[OptionSpread] = []
        trade_config = trade_config_for_symbol(self.config, ticker)
        sector_profile = _sector_profile_for_ticker(self.config, ticker)
        long_moneyness = _long_strike_moneyness(self.scenario, sector_profile)
        for width in trade_config["preferred_spread_widths"]:
            long_call = _round_strike(bar.close * (1 + long_moneyness), width)
            short_call = long_call + width
            estimate = estimate_bull_call_spread_debit(
                underlying_price=bar.close,
                long_strike=long_call,
                short_strike=short_call,
                dte=dte,
                iv_proxy=iv_proxy,
                expected_move_pct=expected_move_pct,
                base_debit_pct=self.scenario.synthetic_base_debit_pct,
                min_debit_pct=self.scenario.synthetic_min_debit_pct,
                max_debit_pct=self.scenario.synthetic_max_debit_pct,
            )
            spreads.append(
                OptionSpread(
                    ticker=ticker.upper(),
                    expiration=expiration,
                    long_call=long_call,
                    short_call=short_call,
                    debit=estimate.estimated_debit,
                    long_delta=0.45,
                    short_delta=0.31,
                    long_open_interest=1000,
                    short_open_interest=900,
                    bid_ask_width_pct=0.08,
                    volume_score=0.70,
                    iv_rank=iv_proxy,
                    expected_move_pct=expected_move_pct,
                    estimated_debit=estimate.estimated_debit,
                    debit_pct_of_width=estimate.debit_pct_of_width,
                    expected_move=estimate.expected_move,
                    distance_to_long_strike=estimate.distance_to_long_strike,
                    distance_to_short_strike=estimate.distance_to_short_strike,
                    estimated_reward_risk=estimate.estimated_reward_risk,
                    pricing_reason=estimate.pricing_reason,
                )
            )
        return tuple(spreads)

    def close_on_or_before(self, ticker: str, target: date) -> tuple[date, float]:
        series = [bar for bar in self.bars.get(ticker.upper(), []) if bar.date <= target]
        if not series:
            raise RuntimeError(f"No historical close available for {ticker} on or before {target}.")
        bar = series[-1]
        return bar.date, bar.close

    def bars_between(self, ticker: str, start: date, end: date) -> tuple[OHLCVBar, ...]:
        return tuple(
            bar
            for bar in self.bars.get(ticker.upper(), [])
            if start <= bar.date <= end
        )

    def _all_configured_tickers(self) -> list[str]:
        tickers: list[str] = []
        for sector in self.config.universe["sectors"].values():
            tickers.extend(sector.get("tickers", []))
        return [ticker.upper() for ticker in tickers]

    def _bar_on(self, ticker: str, as_of: date) -> OHLCVBar:
        try:
            return self.by_date[ticker.upper()][as_of]
        except KeyError as exc:
            raise RuntimeError(f"Missing historical OHLCV for {ticker.upper()} on {as_of}.") from exc

    def _series_until(self, ticker: str, as_of: date) -> list[OHLCVBar]:
        return [bar for bar in self.bars.get(ticker.upper(), []) if bar.date <= as_of]


def historical_tickers(config: AppConfig, vix_proxy: str = "VIXY") -> list[str]:
    tickers = {"SPY", "QQQ", vix_proxy.upper()}
    for sector in config.universe["sectors"].values():
        tickers.update(etf.upper() for etf in sector.get("etfs", []))
        tickers.update(ticker.upper() for ticker in sector.get("tickers", []))
    return sorted(tickers)


def hydrate_massive_ohlcv(
    config: AppConfig,
    start: date,
    end: date,
    api_key: str | None = None,
    cache_dir: Path | None = None,
    calls_per_minute: int = 5,
    vix_proxy: str = "VIXY",
    tickers: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    key = api_key or os.environ.get("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("Set MASSIVE_API_KEY before hydrating Massive historical data.")

    cache = cache_dir or PROJECT_ROOT / "data" / "historical"
    client = MassiveHistoricalClient(key, cache, calls_per_minute=calls_per_minute)
    requested = [ticker.upper() for ticker in (tickers or historical_tickers(config, vix_proxy))]
    fetched: list[str] = []
    cached: list[str] = []
    failed: dict[str, str] = {}

    for ticker in requested:
        path = cache / "ohlcv" / f"{ticker}_{start.isoformat()}_{end.isoformat()}.csv"
        if path.exists():
            cached.append(ticker)
            continue
        if limit is not None and len(fetched) + len(failed) >= limit:
            continue
        try:
            client.fetch_stock_bars(ticker, start, end)
            fetched.append(ticker)
        except Exception as exc:  # noqa: BLE001 - preserve ticker-level failure details for CLI output.
            failed[ticker] = str(exc)

    return {
        "requested": len(requested),
        "processed": len(cached) + len(fetched) + len(failed),
        "remaining": max(len(requested) - len(cached) - len(fetched) - len(failed), 0),
        "cached": cached,
        "fetched": fetched,
        "failed": failed,
        "cache_dir": str(cache / "ohlcv"),
    }


def _ohlcv_cache_dir(cache_dir: Path | None) -> Path:
    if cache_dir is None:
        return PROJECT_ROOT / "data" / "historical" / "ohlcv"
    return cache_dir / "ohlcv" if (cache_dir / "ohlcv").exists() else cache_dir


def read_bars_csv(path: Path) -> list[OHLCVBar]:
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = csv.DictReader(file)
        return [
            OHLCVBar(
                ticker=row["ticker"].upper(),
                date=date.fromisoformat(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(float(row["volume"])),
            )
            for row in rows
        ]


def write_bars_csv(path: Path, bars: Iterable[OHLCVBar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["ticker", "date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "ticker": bar.ticker,
                    "date": bar.date.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )


def _sma(series: list[OHLCVBar], window: int) -> float:
    if not series:
        return 0.0
    values = series[-window:]
    return sum(bar.close for bar in values) / len(values)


def _above_sma(series: list[OHLCVBar], window: int) -> bool:
    return len(series) >= window and series[-1].close > _sma(series, window)


def _pct_change(series: list[OHLCVBar], window: int) -> float:
    if len(series) <= window:
        return 0.0
    start = series[-window - 1].close
    return 0.0 if start == 0 else ((series[-1].close / start) - 1) * 100


def _relative_return(series: list[OHLCVBar], benchmark: list[OHLCVBar], window: int) -> float:
    return _pct_change(series, window) - _pct_change(benchmark, window)


def _ratio_above_ma(tickers: list[str], as_of: date, window: int, provider: HistoricalDataProvider | None = None) -> float:
    if provider is None:
        return 0.0
    available = [ticker for ticker in tickers if ticker in provider.by_date and as_of in provider.by_date[ticker]]
    if not available:
        return 0.0
    passed = 0
    for ticker in available:
        series = provider._series_until(ticker, as_of)
        if _above_sma(series, window):
            passed += 1
    return passed / len(available)


def _rising(series: list[OHLCVBar]) -> bool:
    return len(series) >= 2 and series[-1].close > series[-2].close


def _volume_trend_score(series: list[OHLCVBar]) -> float:
    if len(series) < 20:
        return 0.5
    recent = sum(bar.volume for bar in series[-5:]) / 5
    longer = sum(bar.volume for bar in series[-20:]) / 20
    return _bounded_score((recent / max(longer, 1) - 1) * 100, -25, 25)


def _bounded_score(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _rsi(series: list[OHLCVBar], window: int) -> float:
    if len(series) <= window:
        return 50.0
    changes = [series[index].close - series[index - 1].close for index in range(len(series) - window, len(series))]
    gains = [change for change in changes if change > 0]
    losses = [-change for change in changes if change < 0]
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _drawdown_from_high(series: list[OHLCVBar], window: int) -> float:
    values = series[-window:]
    if not values:
        return 0.0
    high = max(bar.high for bar in values)
    return 0.0 if high == 0 else max(0.0, (1 - values[-1].close / high) * 100)


def _selling_volume_stabilizing(series: list[OHLCVBar]) -> bool:
    if len(series) < 6:
        return True
    return series[-1].volume <= max(bar.volume for bar in series[-6:-1])


def _making_lower_lows(series: list[OHLCVBar]) -> bool:
    return len(series) >= 3 and series[-1].low < series[-2].low < series[-3].low


def _average_true_range_pct(series: list[OHLCVBar], window: int) -> float:
    if len(series) <= window:
        return 3.0
    ranges = [bar.high - bar.low for bar in series[-window:]]
    return (sum(ranges) / len(ranges)) / max(series[-1].close, 1) * 100


def _next_expiration(as_of: date, min_days: int) -> date:
    target = as_of + timedelta(days=min_days)
    while target.weekday() != 4:
        target += timedelta(days=1)
    return target


def _round_strike(value: float, width: float) -> float:
    increment = 5 if value >= 100 else max(width, 1)
    return round(value / increment) * increment


def _sector_profile_for_ticker(config: AppConfig, ticker: str) -> dict:
    symbol = ticker.upper()
    for sector_name, sector_config in config.universe["sectors"].items():
        if symbol in {item.upper() for item in sector_config.get("tickers", [])}:
            return dict((config.strategy.get("sector_profiles") or {}).get(sector_name, {}))
    return {}


def _long_strike_moneyness(scenario: BacktestScenario, sector_profile: dict) -> float:
    preference = str(sector_profile.get("preferred_long_strike") or "").lower()
    if preference == "atm":
        return 0.0
    if preference in {"slightly_itm", "itm"}:
        return -0.01
    if preference in {"slightly_otm", "otm"}:
        return 0.01
    return scenario.long_strike_moneyness_pct
