"""Data layer: yfinance loader with local cache (Section 3).

In Python the browser CORS problem disappears — yfinance pulls OHLCV directly
for SPY/QQQ/^GSPC/^NDX/ES=F/NQ=F (no API key). Results are cached to parquet
(falls back to CSV if pyarrow is unavailable) so re-runs are fast and
reproducible.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

SYMBOLS = ["SPY", "^GSPC", "ES=F", "QQQ", "^NDX", "NQ=F"]

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "_cache")


def _cache_path(symbol: str, suffix: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    safe = symbol.replace("^", "_idx_").replace("=", "_")
    return os.path.join(_CACHE_DIR, f"{safe}.{suffix}")


def _save(df: pd.DataFrame, symbol: str) -> str:
    try:
        path = _cache_path(symbol, "parquet")
        df.to_parquet(path)
        return path
    except Exception:
        path = _cache_path(symbol, "csv")
        df.to_csv(path)
        return path


def _load_cache(symbol: str, max_age_hours: float = 12.0):
    for suffix, reader in (("parquet", pd.read_parquet), ("csv", _read_csv)):
        path = _cache_path(symbol, suffix)
        if os.path.exists(path):
            age = (datetime.now()
                   - datetime.fromtimestamp(os.path.getmtime(path)))
            if age < timedelta(hours=max_age_hours):
                try:
                    return reader(path)
                except Exception:
                    pass
    return None


def _read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df


def to_dict(df: pd.DataFrame) -> dict:
    """Convert an OHLCV DataFrame to the dict the model expects."""
    dates = [d.strftime("%Y-%m-%d") for d in pd.to_datetime(df.index)]
    return {
        "date": dates,
        "open": df["Open"].to_numpy(float),
        "high": df["High"].to_numpy(float),
        "low": df["Low"].to_numpy(float),
        "close": df["Close"].to_numpy(float),
    }


def load(symbol: str, start: str | None = None, period: str = "5y",
         use_cache: bool = True, verbose: bool = True) -> dict:
    """Load daily OHLCV for ``symbol`` via yfinance with local caching.

    Uses adjusted close (auto_adjust) where available. Returns the model dict.
    """
    if use_cache:
        cached = _load_cache(symbol)
        if cached is not None and len(cached) > 200:
            if verbose:
                print(f"[data] {symbol}: {len(cached)} bars from cache")
            return to_dict(cached)

    import yfinance as yf

    kwargs = dict(interval="1d", auto_adjust=True, progress=False)
    if start:
        kwargs["start"] = start
    else:
        kwargs["period"] = period

    df = yf.download(symbol, **kwargs)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        raise RuntimeError(
            f"yfinance returned only {len(df)} rows for {symbol}; "
            "check the symbol or network access.")
    _save(df, symbol)
    if verbose:
        print(f"[data] {symbol}: {len(df)} bars downloaded "
              f"({df.index[0].date()} -> {df.index[-1].date()})")
    return to_dict(df)


def load_csv(path: str) -> dict:
    """Load a CSV with at least Date,Close (Open/High/Low optional)."""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    dcol = next((cols[c] for c in cols if "date" in c), None)
    ccol = cols.get("adj close") or cols.get("close")
    if dcol is None or ccol is None:
        raise ValueError("Need at least Date and Close columns")
    close = df[ccol].astype(float)
    out = pd.DataFrame({
        "Open": df[cols["open"]].astype(float) if "open" in cols else close,
        "High": df[cols["high"]].astype(float) if "high" in cols else close,
        "Low": df[cols["low"]].astype(float) if "low" in cols else close,
        "Close": close,
    })
    out.index = pd.to_datetime(df[dcol])
    out = out.sort_index()
    if len(out) < 60:
        raise ValueError("Need >= 60 rows of data")
    return to_dict(out)


def random_walk(n: int = 1500, seed: int = 0, sigma: float = 0.01,
                start_price: float = 100.0) -> dict:
    """Generate a pure Gaussian random walk (for the H~0.5 sanity test)."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, sigma, n)
    close = start_price * np.cumprod(1.0 + rets)
    dates = pd.bdate_range("2010-01-01", periods=n).strftime("%Y-%m-%d").tolist()
    return {"date": dates, "open": close.copy(), "high": close.copy(),
            "low": close.copy(), "close": close}
