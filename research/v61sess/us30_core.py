"""THE V61 CVD RULE ON US30 -- a market that had no part in choosing any of it.

>>> THE BINDING CONSTRAINT, AND IT IS NOT A CHOICE. CVD needs bars FINER than the chart. US30's
>>> finest feed here is 15-MINUTE, so the incumbent's 30-minute chart would get TWO sub-bars a bar,
>>> which is not a cumulative delta in any useful sense. The rule is therefore run on:
>>>     60m  chart ->  4 sub-bars a bar
>>>     240m chart -> 16 sub-bars a bar
>>> against the THIRTY one-minute sub-bars the NQ result was built on. That is the same degradation
>>> STUDY_XAU_CVD_FEATURES had to accept on gold, and it means a null here is weaker evidence
>>> against the rule than a null on NQ would be.
>>>
>>> AND US30's VOLUME IS TICK VOLUME. The `Volume` column is identically zero throughout; the real
>>> activity column is `TickVolume`. So the CVD proxy signs TICK COUNTS, not contracts, exactly as
>>> on gold. Second gold-specific degradation, now on a second market.

DATA. `data/US30_LONG_15m.csv`, the registry's US30_LONG_15m -- sha256 prefix 24dcf2e1c7ba398f,
193,942 rows, 2016-10-26 to 2025-07-15, verified byte-identical to the studied copy. TAB-separated,
DELIVERED NEWEST FIRST so it must be sorted ascending, `%Y.%m.%d %H:%M:%S`. Clock New York + 7,
derived rather than assumed: mean tick volume by minute-of-day peaks at raw 16:30-17:15 and lands on
minute 570 = 09:30 New York after the shift.

COSTS. 1.50 points a side at a point value of 1.0, plus 0.1 of slippage -- `v63feeds.COST["US30"]`,
the branch's US30 stack. A cost is a fraction of RISK, not a number of points (STUDY_TURTLE_15M), so
the cost-as-a-share-of-stop is printed beside every result.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/v54")):
    if p not in sys.path:
        sys.path.insert(0, p)

import v54cvd as C          # noqa: E402
import sess_core as S       # noqa: E402

CSV = os.path.join(ROOT, "data/US30_LONG_15m.csv")
NY_SHIFT_H = 7
COST, SLIP, PV = 1.50, 0.10, 1.0
SUB_TF = 15


def load15():
    d = pd.read_csv(CSV, sep="\t")
    ix = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=NY_SHIFT_H)
    f = pd.DataFrame({"open": d["Open"].to_numpy(float), "high": d["High"].to_numpy(float),
                      "low": d["Low"].to_numpy(float), "close": d["Close"].to_numpy(float),
                      "volume": d["TickVolume"].to_numpy(float)}, index=ix).sort_index()
    return f[~f.index.duplicated(keep="first")]


def build(tf, ent_max=80, ex_max=80, split=0.65):
    """Chart bars at `tf` minutes with the CVD built from the 15-minute sub-bars."""
    if tf % SUB_TF or tf <= SUB_TF:
        raise ValueError("tf must be a multiple of 15 and strictly coarser -- CVD needs sub-bars")
    f = load15()
    g = f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
    cvd_sub = C.cvd_1m(f)
    cv = pd.Series(cvd_sub, index=f.index).resample(f"{tf}min").last().reindex(g.index).ffill()
    o, h, l, c, v = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = pd.DatetimeIndex(g.index)
    n = len(c)
    D = dict(tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, cv=cv.to_numpy(float),
             atr=S._atr(h, l, c), mod=(ix.hour * 60 + ix.minute).to_numpy(),
             day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy(),
             sub_n=tf // SUB_TF)
    sh, sl = pd.Series(h), pd.Series(l)
    D["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, ent_max + 1)])
    D["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, ex_max + 1)])
    us = np.unique(D["day"])
    D["cut_day"] = int(us[int(split * len(us))])
    D["blk"] = (D["day"] >= D["cut_day"]).astype(np.int64)
    D["last_bar"] = n - max(120, 20000 // tf)
    return D


def gate(D, piv_min, win_min):
    """The exhausted-sellers gate, settings in MINUTES and converted by the chart timeframe."""
    tf = D["tf"]
    k = max(1, int(round(piv_min / tf)))
    w = max(1, int(round(win_min / tf)))
    P = C.patterns(D["h"], D["l"], D["cv"], k, D["n"])
    return (pd.Series(P[0].astype(float)).rolling(w).max().to_numpy() > 0), k, w


def run(D, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True,
        sess=False, s_start=7 * 60, s_stop=11 * 60, flat=False, cost=COST, slip=SLIP, g=None):
    """The SCRIPT's order model, reused verbatim from sess_core so the two markets are comparable."""
    if g is None:
        g, _k, _w = gate(D, piv_min, win_min)
    ei = int(np.clip(ent, 2, D["ent_hi"].shape[0] + 1)) - 2
    xi = int(np.clip(exN, 2, D["ex_lo"].shape[0] + 1)) - 2
    sig, xb, pts, pct, R, why = S._walk(
        D["o"], D["h"], D["l"], D["c"], D["atr"], D["mod"], D["ent_hi"][ei], D["ex_lo"][xi],
        g, 1 if touch else 0, float(stop), float(tp), int(hold),
        1 if sess else 0, int(s_start), int(s_stop), 1 if flat else 0,
        float(cost), float(slip), 300, int(D["last_bar"]))
    return pd.DataFrame(dict(sig=sig, exit_bar=xb, pts=pts, pct=pct, R=R, why=why,
                             blk=D["blk"][sig], day=D["day"][sig], ts=D["ix"][sig]))
