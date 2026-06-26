from __future__ import annotations

from options_trading_assistant.config import AppConfig
from options_trading_assistant.providers.base import DataProvider
from options_trading_assistant.providers.mock import MockDataProvider
from options_trading_assistant.providers.moomoo import MoomooDataProvider


def build_provider(name: str, config: AppConfig) -> DataProvider:
    normalized = name.lower()
    if normalized == "mock":
        return MockDataProvider()
    if normalized == "moomoo":
        return MoomooDataProvider(config=config)
    available = "mock, moomoo"
    raise ValueError(f"Unknown provider '{name}'. Available providers: {available}")
