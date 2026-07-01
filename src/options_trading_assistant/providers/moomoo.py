from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import socket
import time
from typing import Any

from options_trading_assistant.config import AppConfig
from options_trading_assistant.engines.distribution_days import evaluate_distribution_days_from_rows, rule_from_market_config
from options_trading_assistant.models import (
    MarketSnapshot,
    OptionSpread,
    SectorSnapshot,
    StockSnapshot,
)
from options_trading_assistant.providers.base import DataProvider


class MoomooProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class MoomooSettings:
    host: str
    port: int
    connect_timeout_seconds: float
    market_prefix: str = "US"


class MoomooDataProvider(DataProvider):
    """Moomoo OpenD-backed, read-only market data provider."""

    _history_retry_attempts = 3
    _history_retry_sleep_seconds = 15.0

    def __init__(self, config: AppConfig):
        broker_config = config.broker["providers"]["moomoo"]
        self.config = config
        self.market_index = broker_config.get("market_index", {})
        self.settings = MoomooSettings(
            host=str(broker_config.get("host", "127.0.0.1")),
            port=int(broker_config.get("port", 11111)),
            connect_timeout_seconds=float(broker_config.get("connect_timeout_seconds", 3)),
            market_prefix=str(broker_config.get("market_prefix", "US")),
        )
        self._quote_ctx = None

    def close(self) -> None:
        if self._quote_ctx is not None:
            self._quote_ctx.close()
            self._quote_ctx = None

    def get_market_snapshot(self, as_of: date) -> MarketSnapshot:
        spy_symbol = self.market_index.get("spy", "SPY")
        nasdaq_symbol = self.market_index.get("nasdaq_proxy", "QQQ")
        vix_symbol = self.market_index.get("vix", "US..VIX")
        volatility_proxy_symbol = self.market_index.get("volatility_proxy", "VIXY")
        spy = self._history(spy_symbol, as_of, days=80)
        qqq = self._history(nasdaq_symbol, as_of, days=80)
        volatility = self._volatility_signal(vix_symbol, volatility_proxy_symbol, as_of)

        breadth_proxy = self._breadth_proxy(as_of)
        growth_proxy = 1.0 if self._last_close(qqq) > self._moving_average(qqq, 20) else 0.35

        distribution_state = evaluate_distribution_days_from_rows(
            spy,
            close_names=["close", "last_close", "close_price"],
            volume_names=["volume"],
            date_names=["time_key", "date", "time"],
            rule=rule_from_market_config(self.config.strategy["market"]),
        )
        return MarketSnapshot(
            as_of=as_of,
            spy_above_20dma=self._last_close(spy) > self._moving_average(spy, 20),
            nasdaq_above_20dma=self._last_close(qqq) > self._moving_average(qqq, 20),
            vix=volatility["vix"],
            vix_rising=volatility["rising"],
            volatility_source=volatility["source"],
            volatility_risk_off=volatility["risk_off"],
            distribution_days=distribution_state.count_in_window,
            breadth_score=breadth_proxy,
            growth_participation_score=growth_proxy,
            distribution_day_triggered=distribution_state.triggered,
        )

    def get_sector_snapshots(self, as_of: date) -> tuple[SectorSnapshot, ...]:
        spy = self._history("SPY", as_of, days=90)
        snapshots: list[SectorSnapshot] = []
        for sector_name, sector_config in self.config.universe["sectors"].items():
            primary_etf = sector_config["etfs"][0]
            history = self._history(primary_etf, as_of, days=90)
            snapshots.append(
                SectorSnapshot(
                    name=sector_name,
                    primary_etf=primary_etf,
                    relative_strength_1d=self._relative_strength(history, spy, 1),
                    relative_strength_5d=self._relative_strength(history, spy, 5),
                    relative_strength_20d=self._relative_strength(history, spy, 20),
                    above_20dma=self._last_close(history) > self._moving_average(history, 20),
                    above_50dma=self._last_close(history) > self._moving_average(history, 50),
                    volume_trend_score=self._volume_trend_score(history),
                    momentum_score=self._momentum_score(history),
                    recovery_score=self._recovery_score(history),
                )
            )
        return tuple(snapshots)

    def get_stocks_for_sector(self, sector_name: str, as_of: date) -> tuple[StockSnapshot, ...]:
        sector_config = self.config.universe["sectors"].get(sector_name)
        if not sector_config:
            return ()

        sector_history = self._history(sector_config["etfs"][0], as_of, days=230)
        stocks: list[StockSnapshot] = []
        for ticker in sector_config["tickers"]:
            try:
                history = self._history(ticker, as_of, days=230)
            except MoomooProviderError:
                continue
            stocks.append(
                StockSnapshot(
                    ticker=ticker,
                    sector=sector_name,
                    price=self._last_close(history),
                    above_100dma=self._last_close(history) > self._moving_average(history, 100),
                    above_200dma=self._last_close(history) > self._moving_average(history, 200),
                    trend_90d=self._pct_change(history, 90) / 100,
                    sector_relative_strength=(self._pct_change(history, 20) - self._pct_change(sector_history, 20)) / 100,
                    drawdown_from_swing_high_pct=self._drawdown_from_high(history, 30),
                    rsi=self._rsi(history, 14),
                    near_support=self._near_support(history),
                    selling_volume_stabilizing=self._selling_volume_stabilizing(history),
                    making_lower_lows=self._making_lower_lows(history),
                    confirmation_signals=self._confirmation_signals(history, sector_history),
                )
            )
        return tuple(stocks)

    def get_option_spreads(self, ticker: str, as_of: date) -> tuple[OptionSpread, ...]:
        expirations = self._option_expirations(ticker)
        eligible = [
            expiry for expiry in expirations
            if self.config.strategy["trade"]["min_days_to_expiration"]
            <= (expiry - as_of).days
            <= self.config.strategy["trade"]["max_days_to_expiration"]
        ]
        if not eligible:
            return ()

        expiration = min(eligible, key=lambda item: abs((item - as_of).days - 28))
        chain = self._enriched_option_chain(ticker, expiration)
        calls = self._call_rows(chain)
        if not calls:
            return ()

        underlying_price = self._last_close(self._history(ticker, as_of, days=10))
        candidates: list[OptionSpread] = []
        for long_leg in calls:
            long_strike = self._row_number(long_leg, ["strike_price", "strike"], default=0.0)
            if long_strike < underlying_price * 0.98 or long_strike > underlying_price * 1.05:
                continue
            for width in self.config.strategy["trade"]["preferred_spread_widths"]:
                short_leg = self._find_leg_by_strike(calls, long_strike + width)
                if not short_leg:
                    continue
                spread = self._spread_from_legs(ticker, expiration, long_leg, short_leg)
                if spread.debit > 0:
                    candidates.append(spread)
        return tuple(candidates[:8])

    def diagnose_ticker(self, ticker: str, as_of: date) -> dict[str, Any]:
        """Inspect live Moomoo response shapes for one ticker."""
        report: dict[str, Any] = {
            "provider": "moomoo",
            "host": self.settings.host,
            "port": self.settings.port,
            "ticker": ticker,
            "code": self._code(ticker),
            "as_of": as_of.isoformat(),
            "sections": {},
        }

        report["sections"]["history"] = self._diagnose_history(ticker, as_of)
        report["sections"]["quote_snapshot"] = self._diagnose_snapshot(ticker)
        report["sections"]["option_expirations"] = self._diagnose_option_expirations(ticker, as_of)

        expiration = report["sections"]["option_expirations"].get("selected_expiration")
        if expiration:
            report["sections"]["option_chain"] = self._diagnose_option_chain(ticker, date.fromisoformat(expiration))
        else:
            report["sections"]["option_chain"] = {
                "ok": False,
                "error": "No eligible expiration was available for option-chain diagnostics.",
            }

        return report

    def _quote(self):
        if self._quote_ctx is None:
            self._preflight_connection()
            try:
                from moomoo import OpenQuoteContext
            except ImportError as exc:
                raise MoomooProviderError(
                    'Moomoo SDK is not installed. Run: python -m pip install -e ".[moomoo]"'
                ) from exc
            self._quote_ctx = OpenQuoteContext(host=self.settings.host, port=self.settings.port)
        return self._quote_ctx

    def _preflight_connection(self) -> None:
        try:
            with socket.create_connection(
                (self.settings.host, self.settings.port),
                timeout=self.settings.connect_timeout_seconds,
            ):
                return
        except OSError as exc:
            raise MoomooProviderError(
                f"Cannot connect to Moomoo OpenD at {self.settings.host}:{self.settings.port}. "
                "Start Moomoo OpenD, log in locally, and confirm the OpenAPI port is enabled."
            ) from exc

    def _code(self, ticker: str) -> str:
        if "." in ticker:
            return ticker
        return f"{self.settings.market_prefix}.{ticker}"

    def _call(self, method_name: str, *args, **kwargs):
        try:
            from moomoo import RET_OK
        except ImportError as exc:
            raise MoomooProviderError(
                'Moomoo SDK is not installed. Run: python -m pip install -e ".[moomoo]"'
            ) from exc

        method = getattr(self._quote(), method_name)
        for attempt in range(1, self._history_retry_attempts + 1):
            response = method(*args, **kwargs)
            if not isinstance(response, tuple) or len(response) < 2:
                raise MoomooProviderError(f"Moomoo {method_name} returned an unexpected response: {response!r}")
            ret, data = response[0], response[1]
            if ret == RET_OK:
                return data
            if (
                method_name == "request_history_kline"
                and attempt < self._history_retry_attempts
                and "high frequency" in str(data).lower()
            ):
                time.sleep(self._history_retry_sleep_seconds)
                continue
            raise MoomooProviderError(
                f"Moomoo {method_name} failed: {data}. Confirm Moomoo OpenD is running at "
                f"{self.settings.host}:{self.settings.port} and the requested data is enabled."
            )
        raise MoomooProviderError(
            f"Moomoo {method_name} failed after retries. Confirm Moomoo OpenD is running at "
            f"{self.settings.host}:{self.settings.port} and the requested data is enabled."
        )

    def _diagnose_history(self, ticker: str, as_of: date) -> dict[str, Any]:
        try:
            records = self._history(ticker, as_of, days=80)
        except MoomooProviderError as exc:
            return {"ok": False, "error": str(exc)}
        columns = sorted(records[0].keys()) if records else []
        return {
            "ok": True,
            "rows": len(records),
            "columns": columns,
            "required_fields": self._field_coverage(
                columns,
                {
                    "date/time": ["time_key", "date", "datetime"],
                    "open": ["open"],
                    "high": ["high"],
                    "low": ["low"],
                    "close": ["close", "last_close", "close_price"],
                    "volume": ["volume"],
                },
            ),
            "sample": self._sample_row(records),
        }

    def _diagnose_snapshot(self, ticker: str) -> dict[str, Any]:
        try:
            records = self._snapshot([ticker])
        except MoomooProviderError as exc:
            return {"ok": False, "error": str(exc)}
        columns = sorted(records[0].keys()) if records else []
        return {
            "ok": True,
            "rows": len(records),
            "columns": columns,
            "required_fields": self._field_coverage(
                columns,
                {
                    "last price": ["last_price", "cur_price", "price"],
                    "previous close": ["prev_close_price", "prev_close"],
                    "volume": ["volume"],
                },
            ),
            "sample": self._sample_row(records),
        }

    def _diagnose_option_expirations(self, ticker: str, as_of: date) -> dict[str, Any]:
        try:
            records = self._records(self._call("get_option_expiration_date", self._code(ticker)))
        except MoomooProviderError as exc:
            return {"ok": False, "error": str(exc)}

        expirations: list[date] = []
        for row in records:
            raw = self._row_value(row, ["strike_time", "expiration_date", "date"])
            if raw:
                expirations.append(date.fromisoformat(str(raw)[:10]))

        eligible = [
            expiry for expiry in expirations
            if self.config.strategy["trade"]["min_days_to_expiration"]
            <= (expiry - as_of).days
            <= self.config.strategy["trade"]["max_days_to_expiration"]
        ]
        selected = min(eligible, key=lambda item: abs((item - as_of).days - 28)) if eligible else None
        columns = sorted(records[0].keys()) if records else []
        return {
            "ok": True,
            "rows": len(records),
            "columns": columns,
            "expirations": [expiry.isoformat() for expiry in sorted(set(expirations))[:12]],
            "eligible_expirations": [expiry.isoformat() for expiry in sorted(set(eligible))],
            "selected_expiration": selected.isoformat() if selected else None,
            "sample": self._sample_row(records),
        }

    def _diagnose_option_chain(self, ticker: str, expiration: date) -> dict[str, Any]:
        try:
            records = self._enriched_option_chain(ticker, expiration)
        except MoomooProviderError as exc:
            return {"ok": False, "error": str(exc)}
        columns = sorted(records[0].keys()) if records else []
        calls = self._call_rows(records)
        return {
            "ok": True,
            "expiration": expiration.isoformat(),
            "rows": len(records),
            "call_rows": len(calls),
            "columns": columns,
            "required_fields": self._field_coverage(
                columns,
                {
                    "option type": ["option_type", "type"],
                    "strike": ["strike_price", "option_strike_price", "strike"],
                    "bid": ["bid_price", "bid"],
                    "ask": ["ask_price", "ask"],
                    "last": ["last_price", "price", "mark_price"],
                    "mid": ["mid_price"],
                    "delta": ["delta", "option_delta"],
                    "open interest": ["open_interest", "option_open_interest", "oi"],
                    "volume": ["volume"],
                    "implied volatility": ["implied_volatility", "option_implied_volatility", "iv"],
                },
            ),
            "sample": self._sample_row(records),
        }

    def _snapshot(self, tickers: list[str]) -> list[dict[str, Any]]:
        data = self._call("get_market_snapshot", [self._code(ticker) for ticker in tickers])
        return self._records(data)

    def _history(self, ticker: str, as_of: date, days: int):
        start = as_of - timedelta(days=round(days * 1.7))
        data = self._call(
            "request_history_kline",
            self._code(ticker),
            start=start.isoformat(),
            end=as_of.isoformat(),
            max_count=max(days + 20, 260),
        )
        records = self._records(data)
        if len(records) < days:
            raise MoomooProviderError(
                f"Not enough historical bars returned for {ticker}: requested {days}, received {len(records)}."
            )
        return records

    def _option_expirations(self, ticker: str) -> list[date]:
        data = self._call("get_option_expiration_date", self._code(ticker))
        expirations = []
        for row in self._records(data):
            raw = self._row_value(row, ["strike_time", "expiration_date", "date"])
            if raw:
                expirations.append(date.fromisoformat(str(raw)[:10]))
        return sorted(set(expirations))

    def _option_chain(self, ticker: str, expiration: date):
        data = self._call(
            "get_option_chain",
            self._code(ticker),
            start=expiration.isoformat(),
            end=expiration.isoformat(),
        )
        return self._records(data)

    def _enriched_option_chain(self, ticker: str, expiration: date) -> list[dict[str, Any]]:
        chain = self._option_chain(ticker, expiration)
        if not chain:
            return []

        enriched: list[dict[str, Any]] = []
        batch_size = 4
        for index in range(0, len(chain), batch_size):
            batch = chain[index : index + batch_size]
            option_codes = [str(row["code"]) for row in batch if row.get("code")]
            snapshot_rows = self._option_snapshot_rows(option_codes)
            snapshots_by_code = {
                str(snapshot_row.get("code")): snapshot_row
                for snapshot_row in snapshot_rows
                if snapshot_row.get("code")
            }
            for chain_row in batch:
                merged = dict(chain_row)
                snapshot_row = snapshots_by_code.get(str(chain_row.get("code")), {})
                merged.update({key: value for key, value in snapshot_row.items() if value not in (None, "")})
                merged["code"] = chain_row.get("code")
                merged["strike_price"] = chain_row.get("strike_price")
                merged["option_type"] = chain_row.get("option_type")
                enriched.append(merged)
        return enriched

    def _option_snapshot_rows(self, option_codes: list[str]) -> list[dict[str, Any]]:
        if not option_codes:
            return []
        rows = self._snapshot(option_codes)
        if len(rows) != len(option_codes):
            by_code = {str(row.get("code")): row for row in rows}
            return [by_code.get(code, {"code": code}) for code in option_codes]
        return rows

    @staticmethod
    def _records(data) -> list[dict[str, Any]]:
        if hasattr(data, "to_dict"):
            return data.to_dict("records")
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def _field_coverage(columns: list[str], field_aliases: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
        column_set = set(columns)
        coverage = {}
        for field, aliases in field_aliases.items():
            matched = [alias for alias in aliases if alias in column_set]
            coverage[field] = {
                "ok": bool(matched),
                "matched": matched,
                "aliases": aliases,
            }
        return coverage

    @staticmethod
    def _sample_row(records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}
        row = records[0]
        return {key: str(value)[:80] for key, value in row.items()}

    @staticmethod
    def _row_value(row: dict[str, Any], names: list[str], default=None):
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return default

    @classmethod
    def _row_number(cls, row: dict[str, Any], names: list[str], default: float = 0.0) -> float:
        value = cls._row_value(row, names, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _close_series(cls, history: list[dict[str, Any]]) -> list[float]:
        return [cls._row_number(row, ["close", "last_close", "close_price"]) for row in history]

    @classmethod
    def _volume_series(cls, history: list[dict[str, Any]]) -> list[float]:
        return [cls._row_number(row, ["volume"]) for row in history]

    @classmethod
    def _last_close(cls, history: list[dict[str, Any]]) -> float:
        return cls._close_series(history)[-1]

    @classmethod
    def _moving_average(cls, history: list[dict[str, Any]], window: int) -> float:
        closes = cls._close_series(history)[-window:]
        return sum(closes) / len(closes)

    @classmethod
    def _pct_change(cls, history: list[dict[str, Any]], periods: int) -> float:
        closes = cls._close_series(history)
        if len(closes) <= periods or closes[-periods - 1] == 0:
            return 0.0
        return (closes[-1] / closes[-periods - 1] - 1.0) * 100

    @classmethod
    def _relative_strength(cls, history, benchmark_history, periods: int) -> float:
        return round(cls._pct_change(history, periods) - cls._pct_change(benchmark_history, periods), 2)

    @classmethod
    def _drawdown_from_high(cls, history, window: int) -> float:
        closes = cls._close_series(history)[-window:]
        recent_high = max(closes)
        if recent_high == 0:
            return 0.0
        return round((recent_high - closes[-1]) / recent_high * 100, 2)

    @classmethod
    def _rsi(cls, history, window: int) -> float:
        closes = cls._close_series(history)
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent = changes[-window:]
        gains = [change for change in recent if change > 0]
        losses = [-change for change in recent if change < 0]
        avg_gain = sum(gains) / window
        avg_loss = sum(losses) / window
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @classmethod
    def _volume_trend_score(cls, history) -> float:
        volumes = cls._volume_series(history)
        recent = sum(volumes[-5:]) / 5
        base = sum(volumes[-30:-5]) / 25 if len(volumes) >= 30 else recent
        if base == 0:
            return 0.5
        return max(0.0, min(recent / base, 1.5)) / 1.5

    @classmethod
    def _momentum_score(cls, history) -> float:
        change = cls._pct_change(history, 20)
        return max(0.0, min((change + 5) / 15, 1.0))

    @classmethod
    def _recovery_score(cls, history) -> float:
        closes = cls._close_series(history)
        recent_low = min(closes[-10:])
        recent_high = max(closes[-20:])
        if recent_high == recent_low:
            return 0.5
        return max(0.0, min((closes[-1] - recent_low) / (recent_high - recent_low), 1.0))

    def _breadth_proxy(self, as_of: date) -> float:
        tickers = ["SPY", "QQQ", "IWM", "DIA"]
        scores = []
        for ticker in tickers:
            try:
                history = self._history(ticker, as_of, days=60)
            except MoomooProviderError:
                continue
            scores.append(1.0 if self._last_close(history) > self._moving_average(history, 20) else 0.0)
        return sum(scores) / len(scores) if scores else 0.5

    def _volatility_signal(self, vix_symbol: str, proxy_symbol: str, as_of: date) -> dict[str, Any]:
        try:
            vix_history = self._history(vix_symbol, as_of, days=30)
        except MoomooProviderError:
            return self._volatility_proxy_signal(proxy_symbol, as_of)
        vix_closes = self._close_series(vix_history)
        vix = vix_closes[-1]
        previous_vix = vix_closes[-2] if len(vix_closes) >= 2 else vix
        rising = vix > previous_vix
        max_vix_if_rising = self.config.strategy["market"]["max_vix_if_rising"]
        return {
            "vix": vix,
            "rising": rising,
            "source": vix_symbol,
            "risk_off": vix > max_vix_if_rising and rising,
        }

    def _volatility_proxy_signal(self, proxy_symbol: str, as_of: date) -> dict[str, Any]:
        try:
            proxy_history = self._history(proxy_symbol, as_of, days=40)
        except MoomooProviderError:
            return {
                "vix": 0.0,
                "rising": False,
                "source": "unavailable",
                "risk_off": False,
            }
        closes = self._close_series(proxy_history)
        rising = closes[-1] > closes[-2] if len(closes) >= 2 else False
        above_20dma = closes[-1] > self._moving_average(proxy_history, 20)
        return {
            "vix": 0.0,
            "rising": rising,
            "source": proxy_symbol,
            "risk_off": rising and above_20dma,
        }

    @classmethod
    def _near_support(cls, history) -> bool:
        closes = cls._close_series(history)
        last = closes[-1]
        recent_support = min(closes[-20:])
        ma50 = cls._moving_average(history, 50)
        return abs(last - recent_support) / last <= 0.035 or abs(last - ma50) / last <= 0.035

    @classmethod
    def _selling_volume_stabilizing(cls, history) -> bool:
        closes = cls._close_series(history)
        volumes = cls._volume_series(history)
        down_volumes = [volumes[i] for i in range(-10, 0) if closes[i] < closes[i - 1]]
        if len(down_volumes) < 2:
            return True
        return down_volumes[-1] <= (sum(down_volumes[:-1]) / len(down_volumes[:-1])) * 1.1

    @classmethod
    def _making_lower_lows(cls, history) -> bool:
        if len(history) < 15:
            return False
        lows = [
            cls._row_number(row, ["low", "close", "last_close", "close_price"])
            for row in history[-15:]
        ]
        older_low = min(lows[:5])
        middle_low = min(lows[5:10])
        recent_low = min(lows[10:])
        return recent_low < middle_low < older_low

    @classmethod
    def _confirmation_signals(cls, history, sector_history) -> tuple[str, ...]:
        closes = cls._close_series(history)
        signals = []
        current_open = cls._row_number(history[-1], ["open"])
        if current_open > 0 and closes[-1] > current_open:
            signals.append("green_daily_candle")
        if min(closes[-3:]) > min(closes[-6:-3]):
            signals.append("higher_low")
        previous_high = cls._row_number(history[-2], ["high"])
        if closes[-1] > previous_high:
            signals.append("close_above_previous_high")
        if cls._rsi(history, 14) > cls._rsi(history[:-1], 14):
            signals.append("rsi_turning_up")
        if cls._pct_change(history, 5) > cls._pct_change(sector_history, 5):
            signals.append("stock_outperforming_sector_etf")
        if (
            len(history) >= 21
            and closes[-1] > cls._moving_average(history, 20)
            and closes[-2] <= cls._moving_average(history[:-1], 20)
        ):
            signals.append("reclaim_of_20_day_moving_average")
        prior_highs = [cls._row_number(row, ["high"]) for row in history[-21:-1]]
        if prior_highs and all(value > 0 for value in prior_highs) and closes[-1] > max(prior_highs):
            signals.append("break_above_recent_swing_high")
        return tuple(signals)

    @classmethod
    def _call_rows(cls, chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls = []
        for row in chain:
            option_type = str(cls._row_value(row, ["option_type", "type"], "")).upper()
            if option_type in {"CALL", "C", "1"} or "CALL" in option_type:
                calls.append(row)
        return sorted(calls, key=lambda row: cls._row_number(row, ["strike_price", "strike"]))

    @classmethod
    def _find_leg_by_strike(cls, calls: list[dict[str, Any]], strike: float):
        for row in calls:
            row_strike = cls._row_number(row, ["strike_price", "strike"])
            if abs(row_strike - strike) < 0.01:
                return row
        return None

    @classmethod
    def _spread_from_legs(cls, ticker: str, expiration: date, long_leg: dict[str, Any], short_leg: dict[str, Any]) -> OptionSpread:
        long_ask = cls._row_number(long_leg, ["ask_price", "ask", "mid_price", "mark_price", "price"], default=0.0)
        short_bid = cls._row_number(short_leg, ["bid_price", "bid", "mid_price", "mark_price", "price"], default=0.0)
        debit = max(long_ask - short_bid, 0.0)
        long_mid = cls._mid_price(long_leg)
        short_mid = cls._mid_price(short_leg)
        if debit == 0 and long_mid > short_mid:
            debit = long_mid - short_mid

        return OptionSpread(
            ticker=ticker,
            expiration=expiration,
            long_call=cls._row_number(long_leg, ["strike_price", "option_strike_price", "strike"]),
            short_call=cls._row_number(short_leg, ["strike_price", "option_strike_price", "strike"]),
            debit=round(debit, 2),
            long_delta=abs(cls._row_number(long_leg, ["delta", "option_delta"], default=0.0)),
            short_delta=abs(cls._row_number(short_leg, ["delta", "option_delta"], default=0.0)),
            long_open_interest=int(cls._row_number(long_leg, ["open_interest", "option_open_interest", "oi"], default=0)),
            short_open_interest=int(cls._row_number(short_leg, ["open_interest", "option_open_interest", "oi"], default=0)),
            bid_ask_width_pct=cls._bid_ask_width_pct(long_leg, short_leg),
            volume_score=min(
                (
                    cls._row_number(long_leg, ["volume"], default=0)
                    + cls._row_number(short_leg, ["volume"], default=0)
                )
                / 1000,
                1.0,
            ),
            iv_rank=max(
                cls._iv_decimal(cls._row_number(long_leg, ["implied_volatility", "option_implied_volatility", "iv"], default=0.0)),
                cls._iv_decimal(cls._row_number(short_leg, ["implied_volatility", "option_implied_volatility", "iv"], default=0.0)),
            ),
            expected_move_pct=0.0,
        )

    @classmethod
    def _mid_price(cls, row: dict[str, Any]) -> float:
        bid = cls._row_number(row, ["bid_price", "bid"], default=0.0)
        ask = cls._row_number(row, ["ask_price", "ask"], default=0.0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return cls._row_number(row, ["mid_price", "mark_price", "price", "last_price"], default=0.0)

    @staticmethod
    def _iv_decimal(value: float) -> float:
        return value / 100 if value > 1 else value

    @classmethod
    def _bid_ask_width_pct(cls, long_leg: dict[str, Any], short_leg: dict[str, Any]) -> float:
        widths = []
        for leg in (long_leg, short_leg):
            bid = cls._row_number(leg, ["bid_price", "bid"], default=0.0)
            ask = cls._row_number(leg, ["ask_price", "ask"], default=0.0)
            mid = (bid + ask) / 2
            if mid > 0:
                widths.append((ask - bid) / mid)
        return round(max(widths), 4) if widths else 0.25
