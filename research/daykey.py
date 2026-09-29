"""Epoch-day keys that do not depend on pandas' datetime RESOLUTION.

WHY THIS EXISTS. Every module here keys a session as "days since 1970" and the original
construction was `idx.normalize().view("int64") // 86_400_000_000_000` -- an integer divide by
NANOSECONDS per day. pandas 2.x always stored datetimes in nanoseconds, so that was exact.
**pandas 3.0 made MICROSECONDS the default resolution**, and the same expression then divides a
microsecond count by the nanosecond constant: 2025-08-18 comes back as `20` instead of `20318`,
every bar in a 13-month file collapses into ONE session, and nothing raises. A 390,552-bar feed
silently became a 1-session feed here, and the only symptom was a session count that was obviously
wrong -- had the number been merely plausible it would have gone unnoticed.

`astype("datetime64[D]")` converts to day units from WHATEVER unit the source carries, so both
helpers below are exact under ns, us, ms and s. Use them instead of a hard-coded divisor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NS_DAY = 86_400_000_000_000   # kept only so the old constant has one documented home


def to_day(idx) -> np.ndarray:
    """DatetimeIndex (or array of datetimes) -> int64 days since the epoch, resolution-independent."""
    a = np.asarray(pd.DatetimeIndex(idx).normalize().to_numpy())
    return a.astype("datetime64[D]").astype(np.int64)


def from_day(days) -> pd.DatetimeIndex:
    """int64 days since the epoch -> DatetimeIndex. The inverse of `to_day`."""
    return pd.to_datetime(np.asarray(days, dtype=np.int64), unit="D")


def to_week(idx, shift_days: int = 4) -> np.ndarray:
    """Epoch-week key. `shift_days=4` puts the boundary on a Monday, as `turtle2/levels` had it."""
    return (to_day(idx) + shift_days) // 7
