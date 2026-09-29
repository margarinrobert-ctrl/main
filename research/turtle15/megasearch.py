"""A 144,000-configuration search on US30 15m, with 2026 held back as the judge.

THE REQUEST WAS "do 100,000 combinations until you get the best version possible and repeat".
That instruction, followed literally, is the mechanism that manufactures a false result: search
until something passes, and something always passes. `STUDY_SWEEP_110K.md` on this branch already
ran 110,250 configurations and the best in-sample one gave +0.098 R out of sample against +0.097
for not sweeping at all. So the search is run -- in full, as asked -- but under three rules that
decide whether its answer means anything:

  1. THE JUDGE BLOCK IS NEVER SEARCHED. Everything from 2026-01-01 is excluded from ranking and
     read ONCE, at the end, for a handful of finalists. It is the only slice of this feed that
     post-dates every study on this branch.
  2. THE MULTIPLICITY IS CARRIED, not forgotten. With 144,000 cells, the best train result is the
     maximum of 144,000 draws; at a 5% level roughly 7,200 of them clear any fixed threshold by
     chance. A finalist has to beat its own selectivity control, not just look good.
  3. RANKED ON RISK-ADJUSTED TERMS, not profit. Return-over-drawdown was the one structural
     criterion on this branch whose in-sample ordering survived out of sample.

WHAT IS ALREADY KNOWN AND SHOULD NOT BE RE-DISCOVERED HERE: on this same feed, the frozen
NQ-derived gate returns PF 1.60 in the era matching NQ's research block, 0.91 and 1.13 in the
middle, and **0.83 in 2026 -- the only slice beyond all data used anywhere**. The rule decays as
it moves away from where it was found. Any configuration this search likes needs to be read
against that.
"""
from __future__ import annotations

import sys
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15")
import markets, mirror, feats, ablate, fastbars  # noqa: E402

JUDGE_FROM = pd.Timestamp("2026-01-01")

E1   = (10, 20, 30, 55)
X1   = (5, 10, 20)
AMUL = (1.0, 1.5, 2.0, 2.5, 3.0)
UNIT = (1, 2, 3)
ADX  = (0.0, 15.0, 20.0, 25.0, 30.0)
DIST = (0.0, 1.0, 2.0, 3.0, 4.0)
VOL  = (0.0, 1.0, 1.1, 1.2)
TP   = (None, 1.0, 2.0, 3.0)
SESS = (None, (360, 720))          # all hours, or 06:00-12:00 New York flat at noon


def context():
    d, si, cut = markets.load_iso()
    ts = pd.to_datetime(d["ts"])
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    a0 = mirror.wilder_atr(*[fastbars.bars(15)[k] for k in ("h", "l", "c")], 20)
    cost = (1.72 / (2 * np.nanmedian(a0))) * 2 * np.nanmedian(atr)   # same % of risk as NQ
    F = feats.build(d, atr, C := mirror.channels(d["h"], d["l"]))
    train = np.asarray(ts < JUDGE_FROM)
    return d, ts, atr, C, F, cost, train


def grid():
    return list(itertools.product(E1, X1, AMUL, UNIT, ADX, DIST, VOL, TP, SESS))


_CTX = None


def _init():
    global _CTX
    _CTX = context()


def _one(p):
    d, ts, atr, C, F, cost, train = _CTX
    e1, x1, am, mu, adx, dist, vol, tp, sess = p
    g = train.copy()
    if adx > 0:
        g &= np.nan_to_num(F["adx"] >= adx, nan=False)
    if dist > 0:
        g &= np.nan_to_num(F["ema_dist_atr"] >= dist, nan=False)
    if vol > 0:
        g &= np.nan_to_num(F["atr_ratio"] >= vol, nan=False)
    flat = None
    if sess is not None:
        a, b = sess
        g &= (d["mod"] >= a) & (d["mod"] < b - 15)
        flat = b
    Cx = C if (e1, x1) == (20, 10) else mirror.channels(d["h"], d["l"], e1, 55, x1, 20)
    t = mirror.run(d, 1, g, atr, Cx, atr_mult=am, max_units=mu, cost=cost,
                   flat_mod=flat, tp_r=tp)
    if len(t) < 40:
        return None
    s = ablate.stats(t)
    return (e1, x1, am, mu, adx, dist, vol, -1.0 if tp is None else tp,
            0 if sess is None else 1, s["n"], s["per"], s["win"], s["pf"], s["dd"], s["net"],
            s["net"] / s["dd"] if s["dd"] > 0 else 0.0, s["streak"])


COLS = ["e1", "x1", "atr_mult", "units", "adx", "dist", "vol", "tp", "sess",
        "n", "per", "win", "pf", "dd", "net", "ret_dd", "streak"]


def run_all(workers=4, chunk=400):
    import multiprocessing as mp
    G = grid()
    print(f"{len(G):,} configurations, {workers} workers, judge block held back from {JUDGE_FROM.date()}")
    out = []
    with mp.Pool(workers, initializer=_init) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, G, chunksize=chunk)):
            if r is not None:
                out.append(r)
            if (i + 1) % 20000 == 0:
                print(f"  {i+1:,} / {len(G):,}   kept {len(out):,}", flush=True)
    return pd.DataFrame(out, columns=COLS)
