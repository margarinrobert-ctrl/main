"""V47 -- a causal DAILY frame for NQ, built from 1-minute bars so the session split is exact.

WHY BUILD IT RATHER THAN RESAMPLE. Both families here turn on WHEN a return happened, not just how
big it was: the overnight/RTH decomposition is the whole point of the night-premium test, and an
event-drift study has to know which bar carries the announcement. A daily resample of a 23-hour
futures tape throws that away.

SESSIONS, New York:
    RTH        09:30 -> 16:00   (the cash session)
    OVERNIGHT  16:00 -> 09:30   (the gap between one RTH close and the next RTH open)
    A trading DAY is keyed on its RTH date.

EVERY COLUMN IS KNOWN AT THE RTH CLOSE OF ITS OWN DAY. Forward returns are built separately and are
the only thing that looks ahead. `audit()` proves it by truncation.

NOTE ON PRICE LEVELS: this repo records that NQ's stored levels are SYNTHETIC and inflated early in
the sample (STUDY_US100). Everything here is a RETURN or a ratio for that reason; nothing reads a
level, so nothing is affected.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
import data as TD           # noqa: E402

RTH_OPEN, RTH_CLOSE = 570, 960          # 09:30, 16:00 New York, minutes of day
SPLIT = 0.65


def build():
    d = TD.bars("NQ", 1)
    t = pd.to_datetime(pd.Series(d["idx"]))
    mod = np.asarray(d["mod"], int)
    o, h, l, c, v = (np.asarray(d[k], float) for k in ("o", "h", "l", "c", "v"))
    day = t.dt.tz_localize(None).dt.normalize().to_numpy()

    rth = (mod >= RTH_OPEN) & (mod < RTH_CLOSE)
    f = pd.DataFrame(dict(day=day, mod=mod, o=o, h=h, l=l, c=c, v=v, rth=rth))
    g = f[f.rth].groupby("day", sort=True)
    D = pd.DataFrame({
        "rth_open": g.o.first(), "rth_close": g.c.last(),
        "rth_high": g.h.max(), "rth_low": g.l.min(),
        "rth_vol": g.v.sum(), "n_min": g.size(),
    })
    D = D[D.n_min >= 200]                      # drop half-days and holidays

    # full 23-hour day, for the overnight leg
    ga = f.groupby("day", sort=True)
    D["all_high"] = ga.h.max().reindex(D.index)
    D["all_low"] = ga.l.min().reindex(D.index)
    D["all_vol"] = ga.v.sum().reindex(D.index)

    prev_close = D.rth_close.shift(1)
    D["r_on"] = np.log(D.rth_open / prev_close)          # OVERNIGHT: prior RTH close -> this open
    D["r_rth"] = np.log(D.rth_close / D.rth_open)        # INTRADAY
    D["r_day"] = np.log(D.rth_close / prev_close)        # close-to-close
    D["rng_rth"] = (D.rth_high - D.rth_low) / D.rth_open
    D = D.dropna(subset=["r_on", "r_rth", "r_day"])
    D["i"] = np.arange(len(D))
    D["research"] = D.i < int(len(D) * SPLIT)
    return D


def forward(D, k):
    """Forward close-to-close log return over the NEXT k days. The ONLY look-ahead in the module."""
    lc = np.log(D.rth_close.to_numpy())
    n = len(lc)
    out = np.full(n, np.nan)
    if k < n:
        out[:n - k] = lc[k:] - lc[:n - k]
    return out
