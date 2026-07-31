from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Quote:
    symbol: str
    name: str
    category: str
    source: str
    observed_at: datetime
    value: float | None = None
    change_percent: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    previous_close: float | None = None
    currency: str | None = None
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["observed_at"] = self.observed_at.isoformat()
        return data


@dataclass(slots=True)
class SourceResult:
    name: str
    ok: bool
    fetched_at: datetime
    complete: bool = False
    quotes: list[Quote] = field(default_factory=list)
    groups: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0

    def status_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "complete": self.complete,
            "partial": self.ok and not self.complete,
            "fetched_at": self.fetched_at.isoformat(),
            "quote_count": len(self.quotes),
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
