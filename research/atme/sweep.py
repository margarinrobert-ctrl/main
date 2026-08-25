"""The ATME grid: ~98,000 management/execution configurations per pass, across four markets.

The grid is deduplicated where a knob is inert -- entry_k and entry_wait do nothing for a MARKET
order, so MARKET contributes one entry configuration rather than eight. The exact evaluated count
is printed, because a search's multiplicity has to be carried into every p-value it produces.

BASE SIGNALS. Two are run deliberately:
  "every bar"  -- the null signal. If execution alone carries an edge it must show here.
  H5 / H6      -- the two entries that were positive on all four markets GROSS.
The comparison between them is the test of whether the execution edge is ADDITIVE to a signal or a
SUBSTITUTE for one, which is the open question `STUDY_LIMIT_ENTRY.md` left.
"""
from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import feeds, fast
from scalp import core
from hypo import hypotheses as H
from hypo.metrics import suite
from atme.engine import walk, MARKET, LIMIT, STOPENTRY

WINDOW = (540, 780)

ENTRY_CFG = [(MARKET, 0.0, 1)] + [(m, k, w)
                                  for m in (LIMIT, STOPENTRY)
                                  for k in (0.25, 0.5, 0.75, 1.0)
                                  for w in (3, 6)]
STOPS = (1.0, 1.5, 2.0, 3.0, 4.0)
TRAILS = (0.0, 1.5, 2.5)
BES = (0.0, 0.5, 1.0)
TPS = (1.0, 1.5, 2.0, 3.0)
PARTIALS = ((0.0, 0.0), (0.5, 1.0))
GIVEUPS = ((0.0, 0), (0.0, 6))
HOLDS = (24, 48)


def grid():
    for ec, sk, tk, be, tp, pa, gu, mh in itertools.product(
            ENTRY_CFG, STOPS, TRAILS, BES, TPS, PARTIALS, GIVEUPS, HOLDS):
        yield ec, sk, tk, be, tp, pa, gu, mh


def n_configs():
    return sum(1 for _ in grid())


def signal_mask(d, which):
    W = core.window(d, *WINDOW)
    if which == "every bar":
        return W
    m, _ = H.LIBRARY[which](d)
    return np.nan_to_num(m).astype(bool) & W


def run(inst, tf, which="every bar", block="research", cost_mult=1.0,
        min_trades=60, progress=None, stride=1):
    """`stride` subsamples a DENSE signal (every-bar) to keep 24,480 configurations tractable.

    Taking every k-th eligible bar is an unbiased sample of the same population -- it changes the
    standard error, not the estimate -- and the every-bar null has 64k triggers on US30 where a
    setup signal has a few thousand. The stride actually used is recorded on every row.
    """
    lo, hi = WINDOW
    d = feeds.bars(inst, tf)
    B = core.blocks(inst, d)
    blk = B[block]
    days = fast.day_index(d)
    ck = core.COSTS[inst]
    hs = ck.spread_at(d["mod"]) * cost_mult
    m = signal_mask(d, which) & blk
    m[:300] = False
    trig = np.flatnonzero(m & np.isfinite(d["atr"]) & (d["atr"] > 0)).astype(np.int64)
    if stride > 1:
        trig = trig[::stride]
    if len(trig) < min_trades:
        return pd.DataFrame()
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = d["atr"]; mod = np.asarray(d["mod"], np.int64)
    tdays = days[trig]
    rows = []
    for idx, ((em, ek, ew), sk, tk, be, tp, (pf, pr), (gr, gb), mh) in enumerate(grid()):
        R, filled, why, held, mfe, mae = walk(
            o, h, l, c, atr, mod, trig,
            np.int64(em), float(ek), np.int64(ew),
            float(sk), float(tk), float(be), 0.0,
            float(tp), float(pf), float(pr),
            np.int64(mh), np.int64(hi), float(gr), np.int64(gb),
            hs, ck.slip_entry * cost_mult, ck.slip_stop * cost_mult,
            ck.commission * cost_mult)
        got = filled == 1
        if got.sum() < min_trades:
            continue
        s = suite(R[got], tdays[:len(R)][got], min_trades=min_trades)
        if s is None:
            continue
        s.update(entry_mode=("market" if em == MARKET else ("limit" if em == LIMIT else "stop")),
                 entry_k=ek, entry_wait=ew, stop_atr=sk, trail_atr=tk, be_trig=be,
                 tp_r=tp, partial=pf, partial_r=pr, give_up_bar=gb, hold=mh,
                 fill_rate=100.0 * float(got.mean()),
                 market=inst, signal=which, block=block, cost_mult=cost_mult, stride=stride)
        rows.append(s)
        if progress and (idx + 1) % progress == 0:
            print(f"      {idx+1} configs", flush=True)
    return pd.DataFrame(rows)
