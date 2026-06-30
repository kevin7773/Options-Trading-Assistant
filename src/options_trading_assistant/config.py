from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    strategy: dict[str, Any]
    scoring: dict[str, Any]
    universe: dict[str, Any]
    broker: dict[str, Any]

    @property
    def strategy_version(self) -> str:
        return str(self.strategy.get("strategy_version", "unknown"))


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data or {}


def load_config(config_dir: Path | None = None) -> AppConfig:
    base = config_dir or PROJECT_ROOT / "config"
    strategy = load_yaml(base / "strategy.yaml")
    universe_file = strategy.get("universe_file", "universe.yaml")
    return AppConfig(
        strategy=strategy,
        scoring=load_yaml(base / "scoring.yaml"),
        universe=normalize_universe(load_yaml(base / universe_file)),
        broker=load_yaml(base / "broker.yaml"),
    )


def normalize_universe(universe: dict[str, Any]) -> dict[str, Any]:
    """Expose tiered universe configs through the legacy provider shape."""
    sectors = universe.get("sectors", {})
    global_exclusions = set(_symbols(universe.get("exclusions", {}).get("symbols", [])))
    explicit_metadata = _explicit_symbol_metadata(universe.get("symbols", []))
    scan_tiers = set(_symbols(universe.get("scan_tiers", [])))
    normalized = dict(universe)
    normalized["research_slices"] = _normalize_research_slices(universe.get("research_slices", {}))
    normalized_sectors: dict[str, Any] = {}
    symbol_metadata: dict[str, Any] = {}
    for sector_name, sector_config in sectors.items():
        config = dict(sector_config or {})
        sector_exclusions = global_exclusions | set(_symbols(config.get("exclusions", [])))
        tiers = config.get("tiers", {})
        tier_symbols = {tier: _symbols(values) for tier, values in tiers.items()}
        core = _symbols(tiers.get("core", config.get("core", [])))
        expansion = _symbols(tiers.get("expansion", config.get("expansion", [])))
        eligible_tier_symbols = [
            symbol
            for tier, symbols in tier_symbols.items()
            if not _excluded_tier(tier) and _scan_tier(tier, scan_tiers)
            for symbol in symbols
        ]
        research_tier_symbols = [
            symbol
            for tier, symbols in tier_symbols.items()
            if not _excluded_tier(tier)
            for symbol in symbols
        ]
        excluded_tier_symbols = [
            symbol
            for tier, symbols in tier_symbols.items()
            if _excluded_tier(tier)
            for symbol in symbols
        ]
        legacy_tickers = _symbols(config.get("tickers", []))
        tickers = _dedupe([*legacy_tickers, *core, *expansion, *eligible_tier_symbols])
        sector_exclusions |= set(excluded_tier_symbols)
        tickers = [ticker for ticker in tickers if ticker not in sector_exclusions]

        benchmark_etfs = _symbols(config.get("benchmark_etfs", []))
        sector_etfs = _symbols(config.get("sector_etfs", []))
        legacy_etfs = _symbols(config.get("etfs", []))
        etfs = _dedupe([*legacy_etfs, *benchmark_etfs, *sector_etfs])

        config["tickers"] = tickers
        config["research_tickers"] = [
            ticker for ticker in _dedupe([*tickers, *research_tier_symbols]) if ticker not in sector_exclusions
        ]
        config["etfs"] = etfs
        normalized_sectors[sector_name] = config
        benchmark = (benchmark_etfs or legacy_etfs or etfs or [None])[0]
        for ticker in config["research_tickers"]:
            tier = _tier_for_symbol(tier_symbols, ticker) or (
                "core" if ticker in core else "expansion" if ticker in expansion else "legacy"
            )
            metadata = {
                "ticker": ticker,
                "sector": sector_name,
                "tier": tier,
                "benchmark_etf": benchmark,
                **_tier_defaults(universe, tier),
                **_sector_defaults(config, tier),
                **explicit_metadata.get(ticker, {}),
            }
            symbol_metadata[ticker] = metadata
        for ticker in excluded_tier_symbols:
            tier = _tier_for_symbol(tier_symbols, ticker) or "tier_4_excluded"
            symbol_metadata[ticker] = {
                "ticker": ticker,
                "sector": sector_name,
                "tier": tier,
                "benchmark_etf": benchmark,
                "excluded": True,
                **_tier_defaults(universe, tier),
                **_sector_defaults(config, tier),
                **explicit_metadata.get(ticker, {}),
            }
    normalized["sectors"] = normalized_sectors
    normalized["symbol_metadata"] = symbol_metadata
    return normalized


def symbol_metadata(universe: dict[str, Any], ticker: str) -> dict[str, Any]:
    return dict(universe.get("symbol_metadata", {}).get(ticker.upper(), {}))


def trade_config_for_symbol(config: AppConfig, ticker: str) -> dict[str, Any]:
    trade_config = dict(config.strategy["trade"])
    metadata = symbol_metadata(config.universe, ticker)
    if "min_option_open_interest" in metadata:
        trade_config["min_open_interest"] = metadata["min_option_open_interest"]
    if "preferred_spread_widths" in metadata:
        trade_config["preferred_spread_widths"] = metadata["preferred_spread_widths"]
    if "max_bid_ask_pct" in metadata:
        trade_config["max_bid_ask_width_pct"] = metadata["max_bid_ask_pct"]
    return trade_config


def _explicit_symbol_metadata(symbols: Any) -> dict[str, Any]:
    if isinstance(symbols, dict):
        records = [{**value, "ticker": key} for key, value in symbols.items()]
    else:
        records = list(symbols or [])
    return {
        str(record["ticker"]).upper(): {**record, "ticker": str(record["ticker"]).upper()}
        for record in records
        if isinstance(record, dict) and record.get("ticker")
    }


def _tier_defaults(universe: dict[str, Any], tier: str) -> dict[str, Any]:
    defaults = universe.get("tier_defaults", {})
    return dict(defaults.get(tier, {}))


def _sector_defaults(sector_config: dict[str, Any], tier: str) -> dict[str, Any]:
    defaults = dict(sector_config.get("symbol_defaults", {}))
    tier_defaults = sector_config.get("tier_defaults", {})
    defaults.update(tier_defaults.get(tier, {}))
    return defaults


def _normalize_research_slices(slices: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, slice_config in (slices or {}).items():
        config = dict(slice_config or {})
        excluded = set(_symbols(config.get("excluded_symbols", [])))
        tracked_symbols = [
            symbol for symbol in _symbols(config.get("tracked_symbols", []))
            if symbol not in excluded
        ]
        benchmark_etfs = _symbols(config.get("benchmark_etfs", []))
        sector_etfs = _symbols(config.get("sector_etfs", []))
        legacy_etfs = _symbols(config.get("etfs", []))
        config["tracked_symbols"] = tracked_symbols
        config["excluded_symbols"] = _symbols(config.get("excluded_symbols", []))
        config["etfs"] = _dedupe([*legacy_etfs, *benchmark_etfs, *sector_etfs])
        normalized[str(name)] = config
    return normalized


def _symbols(values: list[Any] | tuple[Any, ...]) -> list[str]:
    return [str(value).upper() for value in values or []]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _excluded_tier(tier: str) -> bool:
    return "excluded" in tier.lower() or tier.lower() in {"tier4", "tier_4"}


def _scan_tier(tier: str, scan_tiers: set[str]) -> bool:
    return not scan_tiers or tier.upper() in scan_tiers


def _tier_for_symbol(tier_symbols: dict[str, list[str]], ticker: str) -> str | None:
    for tier, symbols in tier_symbols.items():
        if ticker in symbols:
            return tier
    return None
