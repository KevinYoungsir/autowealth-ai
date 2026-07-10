"""Point-in-time selection for locally supplied macro observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import pandas as pd


PathLike = Union[str, Path]

MACRO_ASOF_COLUMNS = [
    "date",
    "available_date",
    "pmi",
    "cpi_yoy",
    "ppi_yoy",
    "m2_yoy",
    "social_financing_yoy",
    "ten_year_yield",
    "usd_cny",
    "policy_score",
    "external_risk_score",
    "source",
]


@dataclass
class MacroAsOfResult:
    as_of_date: str
    record: Optional[dict[str, object]]
    warnings: list[str] = field(default_factory=list)


def load_macro_asof_csv(path: PathLike) -> pd.DataFrame:
    """Load macro data that carries both observation and publication dates."""
    data = pd.read_csv(path, comment="#")
    for column in MACRO_ASOF_COLUMNS:
        if column not in data.columns:
            data[column] = pd.NA
    data = data[MACRO_ASOF_COLUMNS]
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["available_date"] = pd.to_datetime(data["available_date"], errors="coerce")
    for column in MACRO_ASOF_COLUMNS:
        if column not in {"date", "available_date", "source"}:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data["source"] = data["source"].fillna("local_csv").astype(str)
    return data.sort_values(["available_date", "date"], na_position="last").reset_index(drop=True)


def select_macro_asof(
    data: pd.DataFrame,
    rebalance_date: str | pd.Timestamp,
) -> MacroAsOfResult:
    """Select the latest macro row published by the rebalance date."""
    cutoff = pd.Timestamp(rebalance_date).normalize()
    normalized = _normalize_macro_frame(data)
    warnings: list[str] = []

    missing_available = int(normalized["available_date"].isna().sum())
    if missing_available:
        warnings.append(
            f"ignored {missing_available} macro rows without available_date"
        )
    future_count = int((normalized["available_date"] > cutoff).fillna(False).sum())
    if future_count:
        warnings.append(
            f"ignored {future_count} macro rows published after {cutoff.date().isoformat()}"
        )

    eligible = normalized[
        normalized["available_date"].notna()
        & (normalized["available_date"] <= cutoff)
        & normalized["date"].notna()
        & (normalized["date"] <= cutoff)
    ]
    if eligible.empty:
        warnings.append(f"no macro record available by {cutoff.date().isoformat()}")
        return MacroAsOfResult(
            as_of_date=cutoff.date().isoformat(),
            record=None,
            warnings=warnings,
        )

    row = eligible.sort_values(["available_date", "date"]).iloc[-1].to_dict()
    row["date"] = row["date"].strftime("%Y-%m-%d")
    row["available_date"] = row["available_date"].strftime("%Y-%m-%d")
    return MacroAsOfResult(
        as_of_date=cutoff.date().isoformat(),
        record=row,
        warnings=warnings,
    )


def _normalize_macro_frame(data: pd.DataFrame) -> pd.DataFrame:
    normalized = data.copy()
    for column in MACRO_ASOF_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized = normalized[MACRO_ASOF_COLUMNS]
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized["available_date"] = pd.to_datetime(
        normalized["available_date"], errors="coerce"
    )
    return normalized
