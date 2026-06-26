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
    return AppConfig(
        strategy=load_yaml(base / "strategy.yaml"),
        scoring=load_yaml(base / "scoring.yaml"),
        universe=load_yaml(base / "universe.yaml"),
        broker=load_yaml(base / "broker.yaml"),
    )
