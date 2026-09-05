"""
Data layer for the IFVG + Liquidity Sweep backtest.

Network egress is restricted in this environment (Yahoo/most data hosts are not
allowlisted), so this module does two things:

  1. ``load_csv``  - load real 1-minute OHLCV data if you have it. Drop a CSV in
     ``vectorbt_ifvg/data/`` with columns: datetime, open, high, low, close,
     volume (datetime parseable by pandas; tz-naive is treated as the exchange
     timezone, i.e. America/New_York for NQ).

  2. ``synthetic_nq`` - generate a realistic, reproducible 1-minute NQ-like
     series so the whole pipeline runs end-to-end with no data file. It models
     an intraday session with a New-York-anchored regime: overnight drift, an
     08:30 expansion (killzone) with higher volatility, liquidity runs that
     poke prior swing highs/lows and reverse (so sweeps + FVGs actually form),
     and a flat afternoon. It is NOT a substitute for real data for any
     conclusion about edge - it exists purely to exercise the strategy code.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

NY_TZ = "America/New_York"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_csv(path: str, source_tz: str = "UTC", tz: str = NY_TZ) -> pd.DataFrame:
    """Load a 1-minute OHLCV CSV into a NY-tz-aware DataFrame indexed by time.

    Handles TradingView exports (a ``time`` column, UTC, possibly a UNIX timestamp,
    plus extra indicator columns which are ignored). Naive timestamps are assumed to
    be ``source_tz`` (UTC by default, which matches TradingView/Dukascopy exports),
    then converted to ``tz`` (New York) for the killzone/session logic.
    """
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get("datetime") or cols.get("date") or cols.get("time") \
        or cols.get("gmt time") or df.columns[0]
    s = df[tcol]
    # UNIX timestamp (numeric) vs ISO/string.
    if np.issubdtype(s.dtype, np.number):
        unit = "ms" if s.iloc[0] > 1e11 else "s"
        idx = pd.to_datetime(s, unit=unit, utc=True)
    else:
        idx = pd.to_datetime(s, utc=False)
    df = df.drop(columns=[tcol])
    df.index = pd.DatetimeIndex(idx)
    df = df.sort_index()
    # Normalise OHLCV names; ignore any extra (indicator) columns.
    ren = {}
    for want in ("open", "high", "low", "close", "volume"):
        for c in df.columns:
            if c.lower() == want:
                ren[c] = want
    df = df.rename(columns=ren)
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep]
    if df.index.tz is None:
        df.index = df.index.tz_localize(source_tz).tz_convert(tz)
    else:
        df.index = df.index.tz_convert(tz)
    df.index.name = "datetime"
    return df


def _session_minutes(day: pd.Timestamp, tz: str) -> pd.DatetimeIndex:
    """Full Globex-day 1-minute grid for the ICT day ending on ``day``.

    Spans 18:00 the prior evening -> 16:00 ``day`` (NY), so every ICT session is
    present and can raid the earlier one: Asian (20:00-00:00), London (02:00-05:00),
    pre-market, and the NY cash session. Weekends are skipped by the caller.
    """
    start = pd.Timestamp(day.year, day.month, day.day, 18, 0, tz=tz) - pd.Timedelta(days=1)
    end = pd.Timestamp(day.year, day.month, day.day, 16, 0, tz=tz)
    return pd.date_range(start, end, freq="1min", inclusive="left")


def synthetic_nq(
    days: int = 40,
    start: str = "2026-01-05",
    seed: int = 7,
    base_price: float = 20000.0,
    mintick: float = 0.25,
) -> pd.DataFrame:
    """Generate reproducible 1-minute NQ-like OHLCV with intraday ICT structure.

    The generator deliberately manufactures the patterns the strategy hunts for:
    a London/overnight drift, an 08:30 displacement leg that often sweeps the
    prior session's high or low and reverses, fair-value gaps inside fast legs,
    and a quieter afternoon. Prices are rounded to the NQ tick (0.25).
    """
    rng = np.random.default_rng(seed)
    day0 = pd.Timestamp(start, tz=NY_TZ)

    all_idx: list[pd.Timestamp] = []
    o_list, h_list, l_list, c_list, v_list = [], [], [], [], []

    price = base_price
    prev_day_high = price + 30
    prev_day_low = price - 30

    made = 0
    d = 0
    while made < days:
        day = day0 + pd.Timedelta(days=d)
        d += 1
        if day.weekday() >= 5:  # skip weekends
            continue
        made += 1

        idx = _session_minutes(day, NY_TZ)
        n = len(idx)

        # Daily regime: trend direction and strength for the session.
        day_dir = rng.choice([-1, 1])
        day_strength = rng.uniform(0.2, 1.0)

        # A liquidity target: today price will tend to run yesterday's high/low.
        run_high = rng.random() < 0.5
        target = prev_day_high if run_high else prev_day_low

        session_high = -np.inf
        session_low = np.inf

        for k, ts in enumerate(idx):
            minute_of_day = ts.hour * 60 + ts.minute
            # Volatility/drift envelope across the full Globex day so each ICT session
            # builds its own range for a later session to raid.
            if 510 <= minute_of_day <= 660:        # 08:30-11:00 NY AM killzone
                vol = 3.2
                drift = day_dir * day_strength * 0.9
            elif 810 <= minute_of_day <= 960:      # 13:30-16:00 NY PM
                vol = 2.0
                drift = day_dir * day_strength * 0.5
            elif 120 <= minute_of_day <= 300:      # 02:00-05:00 London
                vol = 2.4
                drift = day_dir * day_strength * 0.6
            elif minute_of_day >= 1200 or minute_of_day < 0:  # 20:00-00:00 Asian
                vol = 1.3
                drift = np.sign(target - price) * 0.15
            elif 300 <= minute_of_day < 510:       # 05:00-08:30 pre-market drift
                vol = 1.4
                drift = np.sign(target - price) * 0.35
            else:                                   # 18:00-20:00 / 00:00-02:00 calm
                vol = 1.0
                drift = 0.0

            step = rng.normal(drift, vol) * 2.0
            wick_mult = 2.0

            # Engineer occasional sweep-and-reverse near the liquidity target.
            near_target = abs(price - target) < 8
            if near_target and rng.random() < 0.25:
                poke = np.sign(target - price) * rng.uniform(2, 6)
                rev = -np.sign(target - price) * rng.uniform(4, 10)
                step = poke + rev  # spike through then snap back -> sweep + IFVG

            # Displacement burst: in the killzones, occasionally print a strong-BODY
            # candle (small wick). This is the ICT signature - the displacement leg that
            # both creates the fair-value gap and, on the reversal, inverts it. Without
            # it the strategy's "body >= ATR" filter almost never coincides with an
            # inversion (gaps would only come from wicks, which is not the real model).
            in_kz = (510 <= minute_of_day <= 960) or (120 <= minute_of_day <= 300)
            if in_kz and rng.random() < 0.10:
                step = np.sign(step if step != 0 else day_dir) * rng.uniform(7, 16)
                wick_mult = 0.4

            o = price
            c = price + step
            wick = abs(rng.normal(0, vol)) * wick_mult
            hi = max(o, c) + wick
            lo = min(o, c) - wick

            # Round to tick.
            o = round(o / mintick) * mintick
            c = round(c / mintick) * mintick
            hi = round(hi / mintick) * mintick
            lo = round(lo / mintick) * mintick

            vol_traded = int(abs(step) * 40 + rng.uniform(50, 300))

            all_idx.append(ts)
            o_list.append(o)
            h_list.append(hi)
            l_list.append(lo)
            c_list.append(c)
            v_list.append(vol_traded)

            price = c
            session_high = max(session_high, hi)
            session_low = min(session_low, lo)

        prev_day_high = session_high
        prev_day_low = session_low

    df = pd.DataFrame(
        {
            "open": o_list,
            "high": h_list,
            "low": l_list,
            "close": c_list,
            "volume": v_list,
        },
        index=pd.DatetimeIndex(all_idx, name="datetime"),
    )
    return df


def get_data(days: int = 60, seed: int = 7) -> tuple[pd.DataFrame, str]:
    """Return (df, source). Prefer a real CSV in data/, else synthetic."""
    if os.path.isdir(DATA_DIR):
        for f in sorted(os.listdir(DATA_DIR)):
            if f.lower().endswith(".csv"):
                return load_csv(os.path.join(DATA_DIR, f)), f"csv:{f}"
    return synthetic_nq(days=days, seed=seed), "synthetic"
