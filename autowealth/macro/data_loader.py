"""
Local CSV loader for macro indicators.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd


PathLike = Union[str, Path]


MACRO_CSV_COLUMNS = [
    "date",
    "pmi",
    "cpi_yoy",
    "ppi_yoy",
    "m2_yoy",
    "social_financing_yoy",
    "ten_year_yield",
    "usd_cny",
    "policy_score",
    "external_risk_score",
]


def load_macro_csv(path: PathLike) -> pd.DataFrame:
    """
    Load local macro indicators from CSV.
    """
    df = pd.read_csv(path)
    for column in MACRO_CSV_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    df = df[MACRO_CSV_COLUMNS]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in MACRO_CSV_COLUMNS:
        if column != "date":
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def latest_macro_indicators(path: PathLike) -> dict:
    """
    Return the latest non-empty macro row as a dictionary.
    """
    df = load_macro_csv(path).dropna(subset=["date"])
    if df.empty:
        raise ValueError("macro CSV contains no valid date rows")
    row = df.iloc[-1].to_dict()
    row["date"] = row["date"].strftime("%Y-%m-%d")
    return row

