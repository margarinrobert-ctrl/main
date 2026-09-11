"""THE VWAP-EMA RULE ON THE THREE EQUITY-INDEX FEEDS -- the same construction, three new markets.

WHY THIS IS A REAL TEST AND THE GOLD STUDY WAS NOT. `STUDY_VWAP_EMA_GOLD.md` measured Bhatti's
spec on XAU/USD, the instrument it was written for, and every number there had to carry the
objection that the paper's own conditions were chosen with gold in mind. US100 and US30 had NO
part in writing the rule and no part in any tuning of it here until they are searched in their own
right, so the FROZEN read on them is the cleanest test the spec can be given.

THE FEEDS, all registry-verified before use (`python research/datasets.py`):
  US100_LONG_15m   206,703 bars 2016-11 .. 2025-10, sha256 c449dddfbc06a943   [ok]
  US30_LONG_15m    193,942 bars 2016-10 .. 2025-07, sha256 24dcf2e1c7ba398f   [ok]
  US30_ISO_15m      48,937 bars 2024-08 .. 2026-08 (RTF-wrapped; bytes are of the derivative,
                    so rows+span are its identity)                             [rows+span checked]

THREE THINGS THAT ARE NOT THE SAME AS GOLD, each of which changes an answer:
  1. VOLUME. Both LONG feeds carry `Volume` identically ZERO and `TickVolume` as the real column.
     Reading the wrong one makes C5 (`V > 1.1 x SMA20(V)`) fire on nothing and makes the VWAP an
     unweighted mean -- exactly the `XAUUSD15_MT` defect. `corr(volume, high-low)` is printed for
     every feed as the check.
  2. CLOCK. The LONG feeds are stamped New York + 7 (registry, DERIVED from the 09:30 volatility
     step); the ISO feed carries its own -04:00/-05:00 offset. Both are converted to New York wall
     clock, and the conversion is re-verified here rather than trusted.
  3. COST. The branch's stack: 0.75 points a side on US100 and 1.50 on US30 at a point value of
     1.0, plus 0.10 of slippage a side (`research/v63/v63feeds.COST`, `research/v61sess/us30_core`).
     Cost is reported as a FRACTION OF RISK, never as points, because that is the only unit
     comparable across markets (STUDY_TURTLE_15M charged NQ's points in gold's and read PF 0.35).

BLOCK DESIGN. US100_LONG and US30_LONG each split 65/35 on NY sessions, as gold did. US30_ISO is
NOT split: it begins 2024-08 and 27,436 of its bars post-date every other file on this branch, so
it is held as a RESERVED FORWARD BLOCK -- read once, after everything else, and never searched.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for q in (ROOT, os.path.join(ROOT, "research"), os.path.dirname(os.path.abspath(__file__))):
    if q not in sys.path:
        sys.path.insert(0, q)

import vecore as V  # noqa: E402

# points of cost per SIDE, slippage per SIDE, point value for one unit
SPEC = {
    "US100": dict(cost_side=0.75, slip=0.10, pv=1.0, csv="data/US100_LONG_15m.csv", kind="tab"),
    "US30":  dict(cost_side=1.50, slip=0.10, pv=1.0, csv="data/US30_LONG_15m.csv", kind="tab"),
    "US30_ISO": dict(cost_side=1.50, slip=0.10, pv=1.0, csv="data/us30_2_year_data.rtf", kind="rtf"),
    "XAU":   dict(cost_side=0.15, slip=0.05, pv=1.0, csv="data/XAU_ISO_15m.csv", kind="xau"),
}
START = {"US100": "2016-11-01", "US30": "2016-11-01", "US30_ISO": "2024-08-19", "XAU": "2010-01-01"}


def _tab(path):
    d = pd.read_csv(os.path.join(ROOT, path), sep="\t")
    d.columns = [c.strip().lower() for c in d.columns]
    tc = [c for c in d.columns if "date" in c or "time" in c][0]
    ix = pd.DatetimeIndex(pd.to_datetime(d[tc])) - pd.Timedelta(hours=7)   # registry: New York + 7
    vol = d["tickvolume"] if "tickvolume" in d.columns else d["volume"]
    return pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                         "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                         "volume": vol.to_numpy(float)}, index=ix)


def _rtf(path):
    """Unwrap exactly as the registry prescribes: strip the RTF header and control words, keep the
    lines that start with an ISO date, then convert the stated offset to New York."""
    raw = open(os.path.join(ROOT, path), "r", errors="ignore").read()
    body = raw.replace("\\par", "\n")
    body = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", body).replace("{", "").replace("}", "")
    rows = [ln.strip() for ln in body.split("\n") if re.match(r"^\d{4}-\d{2}-\d{2}T", ln.strip())]
    d = pd.DataFrame([r.split(",") for r in rows],
                     columns=["time", "open", "high", "low", "close", "volume"])
    ix = (pd.DatetimeIndex(pd.to_datetime(d["time"], utc=True, format="ISO8601"))
          .tz_convert("America/New_York").tz_localize(None))
    return pd.DataFrame({k: d[k].to_numpy(float) for k in
                         ("open", "high", "low", "close", "volume")}, index=ix)


def raw(market):
    s = SPEC[market]
    if s["kind"] == "xau":
        f = V.load(s["csv"], START[market])
    else:
        f = _tab(s["csv"]) if s["kind"] == "tab" else _rtf(s["csv"])
        f = f.sort_index()
        f = f[~f.index.duplicated(keep="first")]
        f = f[f.index >= START[market]]
    return f


def build(market, sess="ny", split=0.65):
    D = V.assemble(raw(market), sess=sess, split=split)
    D["market"] = market
    D["cost_rt"] = 2 * SPEC[market]["cost_side"]
    D["slip"] = SPEC[market]["slip"]
    return D


def run(D, sig, **kw):
    kw.setdefault("cost_rt", D["cost_rt"])
    kw.setdefault("slip", D["slip"])
    return V.run(D, sig, **kw)


def clock_evidence(f):
    """Re-derive the clock rather than trust it: mean bar RANGE by minute-of-day must peak at the
    equity open. On a New York wall-clock index that is minute 570."""
    mod = (f.index.hour * 60 + f.index.minute).to_numpy()
    rng = (f["high"] - f["low"]).to_numpy()
    wd = f.index.dayofweek.to_numpy()
    m = wd < 5
    s = pd.Series(rng[m]).groupby(pd.Series(mod[m])).mean()
    return int(s.idxmax()), float(s.max()), float(s.mean())


def volume_check(f):
    """corr(volume, bar range). A real activity column scores ~+0.6; the `XAUUSD15_MT` sixth field
    -- which is the bar's LENGTH IN MINUTES -- scores +0.005 and makes C5 and the VWAP meaningless."""
    r = (f["high"] - f["low"]).to_numpy()
    v = f["volume"].to_numpy()
    m = np.isfinite(r) & np.isfinite(v)
    return float(np.corrcoef(r[m], v[m])[0, 1]), float(np.median(v[m])), float((v[m] == 0).mean())
