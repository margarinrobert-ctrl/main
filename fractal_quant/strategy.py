"""Regime-switching signal generation (Section 2.5).

Positions are decided at the close of bar i (executed next bar by the
backtester). Faithful port of the regime/position loop in fractal_engine.html.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fractal import frama, rolling_hurst
from .regime import RegimeThresholds, classify


@dataclass
class StrategyParams:
    hwin: int = 120          # Hurst rolling window
    framaN: int = 16         # FRAMA period
    zlook: int = 20          # z-score lookback
    allow_short: bool = False
    trend_th: float = 0.55
    revert_th: float = 0.45
    hurst_method: str = "rs"  # "rs" or "dfa"


def _pstd(a):
    return float(np.std(a))


def generate_signals(data: dict, p: StrategyParams) -> dict:
    """Compute regime, raw positions and supporting series.

    ``data`` is a dict with keys date, open, high, low, close (array-likes).
    Returns a dict of numpy arrays: ret, logr, H, fr, zsc, vol, regime, pos.
    No execution lag is applied here — that is the backtester's job.
    """
    close = np.asarray(data["close"], dtype=float)
    high = np.asarray(data["high"], dtype=float)
    low = np.asarray(data["low"], dtype=float)
    n = close.size

    # returns
    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1.0
    logr = np.log1p(ret)

    # rolling Hurst, FRAMA
    H = rolling_hurst(logr, window=p.hwin, method=p.hurst_method)
    fr = frama(high, low, close, p.framaN)

    # rolling z-score of close
    zsc = np.full(n, np.nan)
    for i in range(p.zlook, n):
        w = close[i - p.zlook + 1:i + 1]
        m = w.mean()
        sd = _pstd(w)
        zsc[i] = (close[i] - m) / sd if sd > 0 else 0.0

    # rolling 20-day annualized realized vol
    vol = np.full(n, np.nan)
    for i in range(20, n):
        vol[i] = _pstd(ret[i - 19:i + 1]) * np.sqrt(252)

    regime = classify(H, RegimeThresholds(p.trend_th, p.revert_th))
    pos = np.zeros(n)
    prev = 0.0
    for i in range(n):
        if np.isnan(H[i]) or np.isnan(fr[i]) or np.isnan(zsc[i]):
            pos[i] = 0.0
            prev = 0.0
            continue
        h, z = H[i], zsc[i]
        if h > p.trend_th:
            regime[i] = "trend"
            cur = 1.0 if close[i] > fr[i] else 0.0
        elif h < p.revert_th:
            regime[i] = "revert"
            if prev <= 0 and z < -1:
                cur = 1.0
            elif prev > 0 and z > 0:
                cur = 0.0
            elif p.allow_short and prev >= 0 and z > 1:
                cur = -1.0
            elif p.allow_short and prev < 0 and z < 0:
                cur = 0.0
            else:
                cur = prev
        else:
            regime[i] = "random"
            cur = 0.0
        pos[i] = cur
        prev = cur

    return {
        "ret": ret, "logr": logr, "H": H, "fr": fr,
        "zsc": zsc, "vol": vol, "regime": regime, "pos": pos,
    }
