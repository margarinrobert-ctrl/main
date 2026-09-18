"""GOLD, TWO PROVIDERS, AND A GENUINE FORWARD BLOCK -- the data decision, made before any feature.

THE UPLOADED FILE IS BYTE-IDENTICAL TO THE ONE ALREADY REGISTERED (sha256 fdd173af1c92a768, 100,000
rows, 2022-06-07 .. 2026-08-28 UTC) AND ITS SIXTH FIELD IS STILL NOT VOLUME: it reads exactly 15 on
**99.62%** of rows, sd 0.185, and its correlation with the bar's own range is **+0.0048** where the
ISO feed's real tick volume scores **+0.6407**. It is the bar's LENGTH IN MINUTES. Two consequences
are arithmetic, not opinion: a `V > k x SMA(V)` condition fires on essentially nothing, and a VWAP
over a constant V IS the unweighted mean of the typical price.

SO THE FILE IS USED FOR WHAT IT CAN SUPPORT, WHICH TURNS OUT TO BE THE MOST VALUABLE THING HERE.
Converted UTC -> New York it overlaps `XAU_ISO_15m` on 83,324 bars with a return correlation of
**+0.9474** and a median level gap of **-0.125 USD** (IQR 0.113) -- the same instrument, well
aligned, from a different provider. The alignment is not assumed: every neighbouring 15-minute
shift collapses the correlation to ~0.23, so shift 0 is right.

  >>> AND 13,656 OF ITS BARS -- 2026-02-01 to 2026-08-28 -- POST-DATE THE ISO FEED ENTIRELY. <<<
  That is SEVEN MONTHS of gold that no study on this branch has ever seen, from a second provider.
  It is reserved as the FORWARD BLOCK and is read once, at the end, and never searched.

THE FEATURE SET IS SPLIT ACCORDINGLY, and this is the design constraint the fake column imposes:
  `core`     OHLC-only. Runs on BOTH feeds, so anything built from it can be read forward.
  `vol_dep`  needs real volume. Runs on ISO only, and CANNOT be read on the forward block --
             so a `vol_dep` result is one block short of evidence by construction, and is
             reported separately rather than pooled.

BLOCKS, declared here before anything is computed:
  RESEARCH  ISO, 2010-01-01 .. the 65% session split          (pre-2010 excluded: the registry
  LOCKED    ISO, the remaining 35% .. 2026-01-30               records 10% zero-range bars and a
  FORWARD   MT,  2026-02-01 .. 2026-08-28, a DIFFERENT feed    median 5-minute volume of 14 ticks)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research", "vwapema"))
import vecore as V  # noqa: E402

START = "2010-01-01"
SPLIT = 0.65
COST_RT, SLIP = 0.30, 0.05          # gold's floor, USD/oz -- 17% of a median 15m ATR-based stop


def load_iso():
    f = V.load(os.path.join(ROOT, "data/XAU_ISO_15m.csv"), START)
    f = f[~f.index.duplicated(keep="first")]
    return f


def load_mt():
    """MT4 tab export, UTC-stamped. The sixth field is DROPPED, not renamed: keeping it under the
    name `volume` is how a volume rule silently becomes a constant."""
    d = pd.read_csv(os.path.join(ROOT, "data/XAUUSD15_MT.csv"), sep="\t", header=None,
                    names=["ts", "open", "high", "low", "close", "_barlen"])
    ix = (pd.DatetimeIndex(pd.to_datetime(d.ts)).tz_localize("UTC")
          .tz_convert("America/New_York").tz_localize(None))
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")}, index=ix)
    f["volume"] = np.nan                 # explicitly absent, so nothing can quietly use it
    return f.sort_index()[~f.index.duplicated(keep="first")]


def blocks():
    """The three blocks as frames, plus the session-split date, computed once."""
    iso = load_iso()
    mt = load_mt()
    ix = iso.index
    day = ix.normalize()
    rth = ((ix.hour * 60 + ix.minute >= 9 * 60 + 30) & (ix.hour * 60 + ix.minute < 16 * 60)
           & (ix.dayofweek < 5))
    us = np.unique(day[rth].values)
    cut = pd.Timestamp(us[int(SPLIT * len(us))])
    fwd = mt[mt.index > iso.index[-1]]
    return dict(research=iso[iso.index < cut], locked=iso[iso.index >= cut], forward=fwd,
                cut=cut, iso=iso, mt=mt)


def overlap_evidence():
    """The two-provider check, re-run rather than trusted: return correlation, level gap, and the
    shift sweep that proves the clock conversion."""
    iso, mt = load_iso(), load_mt()
    out = []
    for shift in (-2, -1, 0, 1, 2):
        m = mt.copy()
        m.index = mt.index + pd.Timedelta(minutes=15 * shift)
        j = m.join(iso, how="inner", lsuffix="_mt", rsuffix="_iso")
        if len(j) < 1000:
            continue
        a, b = np.log(j.close_mt).diff(), np.log(j.close_iso).diff()
        k = np.isfinite(a) & np.isfinite(b)
        out.append(dict(shift=shift, n=len(j), ret_corr=round(float(np.corrcoef(a[k], b[k])[0, 1]), 4),
                        level_gap=round(float((j.close_mt - j.close_iso).median()), 3)))
    return pd.DataFrame(out)


def volume_defect():
    """The one check that decides whether any volume rule is runnable on a feed."""
    rows = []
    for nm, f, col in (("XAU_ISO_15m", load_iso(), "volume"),
                       ("XAUUSD15_MT", pd.read_csv(os.path.join(ROOT, "data/XAUUSD15_MT.csv"),
                                                   sep="\t", header=None,
                                                   names=["ts", "o", "h", "l", "c", "v"]), "v")):
        if nm.endswith("MT"):
            r = (f.h - f.l).to_numpy()
            v = f.v.to_numpy(float)
        else:
            r = (f.high - f.low).to_numpy()
            v = f[col].to_numpy(float)
        m = np.isfinite(r) & np.isfinite(v)
        rows.append(dict(feed=nm, n=len(f), mean=round(float(v[m].mean()), 3),
                         sd=round(float(v[m].std()), 3),
                         share_modal=round(float((v[m] == np.round(np.median(v[m]))).mean()), 4),
                         corr_with_range=round(float(np.corrcoef(v[m], r[m])[0, 1]), 4),
                         usable="YES" if abs(np.corrcoef(v[m], r[m])[0, 1]) > 0.3 else "NO -- not volume"))
    return pd.DataFrame(rows)
