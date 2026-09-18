"""The 30-SECOND US30 feed in the shape `na_core` expects, so the 09:00-range rule can be walked
on it without any change to the engine.

WHAT THIS BLOCK IS AND IS NOT. `US30_30s` spans 2025-08-18 to 2026-09-16 and `US30_LONG_15m` ends
2025-07-15, so it post-dates the whole search -- but it OVERLAPS `US30_ISO_15m`, whose reserved
forward block begins 2025-07-16, from 2025-08-18 to 2026-08-26. Two providers over one calendar
are a feed-parity check and not two tests (`STUDY_TREND_LONG`, and US30/US30_ISO already measured
at daily leg correlation +0.922), so a read here AFTER a read on US30_ISO is a SECOND read of the
same weeks and is descriptive. Only 2026-08-27 onward is genuinely fresh, and that is 15 sessions.

WHAT IT DOES SETTLE is the MEASUREMENT: a 09:00-range trade with a stop and a target both inside
one 15-minute bar has an intrabar ordering a 15-minute file cannot resolve, and this file can.

TWO DEFECTS THAT MATTER HERE, both from `research/us30s/us30s.py` rather than re-derived:
  * bars with no activity are OMITTED (34.4% coverage of the 30-second grid), so a BAR COUNT is
    not a clock -- the ATR period and the fresh-cross reach are converted from minutes, and the
    ATR at 30 seconds is a materially different indicator from the ATR at 15 minutes even at the
    same period number (`STUDY_V57`). Both readings are therefore run and printed.
  * volume is identically zero before 2026-04-27, so nothing here may use a VWMA.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research", "us30s"))
import na_core as N  # noqa: E402
import us30s as S    # noqa: E402


def frame(tf=0.5, atr_n=14):
    """Bars at `tf` minutes with the columns `na_core.load` produces, from the 30-second file."""
    d = S.load(tf=tf)
    f = pd.DataFrame({c: d[c].to_numpy(float) for c in
                      ("open", "high", "low", "close", "volume")},
                     index=pd.DatetimeIndex(d["ny"]))
    f = f.sort_index()
    f = f[~f.index.duplicated(keep="first")]
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    f["tr"] = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(f["tr"].to_numpy()).ewm(span=int(atr_n), adjust=False).mean().to_numpy()
    f["mod"] = f.index.hour * 60 + f.index.minute
    f["day"] = (f.index.normalize().view("int64") // 86_400_000_000_000).astype(np.int64)
    return f


def bars_per_minute(tf=0.5):
    return 1.0 / tf
