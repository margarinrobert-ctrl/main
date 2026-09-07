"""Data loading and the New York session clock, for the Python research layer.

The TypeScript engine carries a hand-rolled DST rule verified against `Intl`; this side uses the
IANA database through pandas. Agreement between them is a check, not a coincidence, so nothing here
reimplements the offset arithmetic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"


def load_bars(path: str) -> pd.DataFrame:
    """Load the exported OHLCV csv, indexed by New York wall-clock time."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "t"})
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.set_index(df["t"].dt.tz_convert(NY)).drop(columns=["t"])
    df.index.name = "ny"
    return df.sort_index()


def minute_of_day(idx: pd.DatetimeIndex) -> np.ndarray:
    return (idx.hour * 60 + idx.minute).to_numpy(dtype=np.int32)


def in_window(mod: np.ndarray, start: int, end: int) -> np.ndarray:
    """Half-open [start, end) in minutes since local midnight, wrapping past midnight."""
    if start <= end:
        return (mod >= start) & (mod < end)
    return (mod >= start) | (mod < end)


def session_index(idx: pd.DatetimeIndex, start_min: int) -> np.ndarray:
    """Session id with the day boundary moved to the session open, so an overnight session is one
    session rather than two halves split at midnight. Mirrors `sessionIndex` in clock.ts."""
    mod = minute_of_day(idx)
    # Local WALL-CLOCK days since epoch, matching dayIndex in clock.ts (which floors local time,
    # not UTC). Dropping the tz after conversion is what makes it wall-clock rather than absolute.
    local_midnight = np.asarray(idx.tz_localize(None).normalize(), dtype="datetime64[ns]")
    day = local_midnight.astype("int64") // 86_400_000_000_000
    return (day - (mod < start_min).astype(np.int64)).astype(np.int64)


def minutes_since_open(mod: np.ndarray, start_min: int) -> np.ndarray:
    return (mod - start_min + 1440) % 1440


def session_slice(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Filter to the trading window, exactly as the TypeScript studies do before backtesting."""
    return df[in_window(minute_of_day(df.index), start, end)]
