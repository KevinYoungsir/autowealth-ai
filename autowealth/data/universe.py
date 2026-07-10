"""Research universe definitions with explicit survivorship-bias labeling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass(frozen=True)
class UniverseSnapshot:
    as_of_date: str
    symbols: list[str]
    source: str
    point_in_time: bool
    warnings: list[str] = field(default_factory=list)


class HistoricalUniverseProvider(Protocol):
    """Reserved interface for future historical index-constituent providers."""

    def get_universe(self, as_of_date: str) -> UniverseSnapshot: ...


class FixedStockUniverse:
    """A fixed, user-configured research universe.

    This class never queries today's listing set and never labels the fixed list
    as a historical constituent universe.
    """

    def __init__(self, symbols: Iterable[str]):
        cleaned = list(
            dict.fromkeys(
                str(symbol).strip() for symbol in symbols if str(symbol).strip()
            )
        )
        if not cleaned:
            raise ValueError("fixed candidate_symbols cannot be empty")
        self.symbols = cleaned

    @classmethod
    def from_config(cls, config: dict) -> "FixedStockUniverse":
        return cls(config.get("candidate_symbols", []))

    def get_universe(self, as_of_date: str) -> UniverseSnapshot:
        return UniverseSnapshot(
            as_of_date=str(as_of_date),
            symbols=list(self.symbols),
            source="fixed_config",
            point_in_time=False,
            warnings=[
                "fixed candidate universe may contain survivorship bias and is "
                "not historical index membership"
            ],
        )
