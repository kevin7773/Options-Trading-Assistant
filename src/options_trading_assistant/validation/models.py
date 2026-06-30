from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpreadEvidence:
    entry_date: str
    ticker: str
    final_pl: float
    risk: float
    period: str
    source_path: str


@dataclass(frozen=True)
class SetupEvidence:
    entry_date: str
    ticker: str
    gross_pl: float
    net_pl: float
    risk: float
    return_r: float
    spread_count: int
    period: str


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    sufficient: bool
    actual: Any
    required: Any
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    verdict: str
    baseline_version: str
    scenario: str
    evidence_kind: str
    metrics: dict[str, Any]
    checks: tuple[ValidationCheck, ...]
    integrity: dict[str, Any]
    setups: tuple[SetupEvidence, ...] = field(default_factory=tuple)
