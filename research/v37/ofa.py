"""V37 -- the IFVG model AS THE SOURCE DESCRIBES IT: three-timeframe order-flow alignment.

WHY THIS IS NOT V36. V36 tested `liquidity sweep -> IFVG` and it failed. The uploaded thread
describes a different model, and the difference is the whole strategy:

  * The trigger is NOT a sweep. It is ORDER FLOW ALIGNMENT across M15, M5 and M1 --
    "If even one timeframe is not aligned, we do not take the trade."
  * The entry timeframe is M1. V36 tested 5m and 15m only.
  * The entry is a CONFIRMATION entry: "price does not always retrace to the IFVG, so it's better
    to enter on the IFVG once it is confirmed by the next candle." V36 used retest limits.

ORDER FLOW, MADE OBJECTIVE. The source defines it as "price respects bullish PD arrays and
disrespects bearish PD arrays" for bullish, and the mirror for bearish. Disrespecting a bearish FVG
-- closing above it -- IS a bullish inversion. So order flow on a timeframe is the POLARITY OF THE
MOST RECENT INVERSION on that timeframe, which needs no extra parameter and follows directly from
the definition already used for the IFVG itself. Before any inversion has occurred the state is
NEUTRAL, which the source says to avoid, and it is excluded rather than defaulted to a side.

CISD is described in the source but is NOT implemented here, because the source uses it as
confirmation of the same order-flow shift the inversion already marks -- "a Change in State of
Delivery and inversion confirms an order flow shift". Adding it as a second reading of one event
would double-count. It is noted as untested rather than silently dropped.

Causality: every FVG is knowable at the close of its third candle, every inversion at the close of
the candle that closes through, and the confirmation entry fills at the OPEN AFTER the confirming
candle closes. Higher-timeframe state is mapped to 1-minute bars by the last COMPLETED higher bar.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402


def resample(d, tf):
    blk = np.arange(len(d["c"])) // tf
    g = pd.DataFrame(dict(blk=blk, o=d["o"], h=d["h"], l=d["l"], c=d["c"],
                          i=np.arange(len(d["c"])))).groupby("blk")
    return dict(o=g.o.first().to_numpy(), h=g.h.max().to_numpy(), l=g.l.min().to_numpy(),
                c=g.c.last().to_numpy(), last_i=g.i.max().to_numpy())


MAX_AGE = 500          # bars on the timeframe an un-inverted FVG stays live
CAP = 4096             # open-zone ring capacity; overflow drops the OLDEST, never the newest


@njit(cache=True)
def _inv(h, l, c, max_age, cap):
    n = len(c)
    zp = np.zeros(cap, np.int64)
    zlo = np.zeros(cap)
    zhi = np.zeros(cap)
    zb = np.zeros(cap, np.int64)
    nz = 0
    ib = np.zeros(n, np.int64)
    ip = np.zeros(n, np.int64)
    ilo = np.zeros(n)
    ihi = np.zeros(n)
    ibr = np.zeros(n, np.int64)
    k = 0
    for i in range(2, n):
        w = 0
        for q in range(nz):
            if i - zb[q] > max_age:
                continue                       # expired, drop
            hit = False
            if zp[q] > 0 and c[i] < zlo[q]:
                ib[k] = i; ip[k] = -1; ilo[k] = zlo[q]; ihi[k] = zhi[q]; ibr[k] = zb[q]; k += 1
                hit = True
            elif zp[q] < 0 and c[i] > zhi[q]:
                ib[k] = i; ip[k] = 1; ilo[k] = zlo[q]; ihi[k] = zhi[q]; ibr[k] = zb[q]; k += 1
                hit = True
            if not hit:
                zp[w] = zp[q]; zlo[w] = zlo[q]; zhi[w] = zhi[q]; zb[w] = zb[q]; w += 1
        nz = w
        if l[i] > h[i - 2]:
            if nz == cap:
                for q in range(cap - 1):
                    zp[q] = zp[q + 1]; zlo[q] = zlo[q + 1]; zhi[q] = zhi[q + 1]; zb[q] = zb[q + 1]
                nz = cap - 1
            zp[nz] = 1; zlo[nz] = h[i - 2]; zhi[nz] = l[i]; zb[nz] = i; nz += 1
        elif h[i] < l[i - 2]:
            if nz == cap:
                for q in range(cap - 1):
                    zp[q] = zp[q + 1]; zlo[q] = zlo[q + 1]; zhi[q] = zhi[q + 1]; zb[q] = zb[q + 1]
                nz = cap - 1
            zp[nz] = -1; zlo[nz] = h[i]; zhi[nz] = l[i - 2]; zb[nz] = i; nz += 1
    return ib[:k], ip[:k], ilo[:k], ihi[:k], ibr[:k]


def inversions(r, max_age=MAX_AGE):
    """Every FVG on a timeframe and the bar its inversion completes on.

    FVG at bar i: bullish when low[i] > high[i-2] (zone [high[i-2], low[i]]), bearish when
    high[i] < low[i-2] (zone [high[i], low[i-2]]). Knowable at the close of bar i.
    INVERSION when a later candle CLOSES through the zone; the zone then takes the opposite
    polarity. An FVG that is never inverted within `max_age` bars expires -- the source uses these
    as intraday reference points, and an un-aged pool would let a 1-minute gap from three days ago
    set today's order flow.
    Returns (inv_bar, pol, zlo, zhi, born)."""
    ib, ip, ilo, ihi, ibr = _inv(r["h"], r["l"], r["c"], int(max_age), CAP)
    return pd.DataFrame(dict(inv_bar=ib, pol=ip, zlo=ilo, zhi=ihi, born=ibr))


def of_state(d, tf, max_age=MAX_AGE):
    """Order flow on `tf`, as a per-1-minute-bar state: the polarity of the most recent inversion,
    0 before any has occurred. Mapped by the LAST COMPLETED higher-timeframe bar, so a 1-minute bar
    never reads a higher bar that has not closed."""
    r = resample(d, tf)
    iv = inversions(r, max_age)
    st = np.zeros(len(r["c"]), np.int64)
    if len(iv):
        st[iv.inv_bar.to_numpy()] = iv.pol.to_numpy()
    st = pd.Series(np.where(st == 0, np.nan, st)).ffill().fillna(0).to_numpy().astype(np.int64)
    # a state set at higher-bar j is knowable from the 1-minute bar AFTER that bar closes
    n1 = len(d["c"])
    stamp = np.full(n1, np.nan)
    pos = r["last_i"] + 1
    ok = pos < n1
    stamp[pos[ok]] = st[ok]
    out = pd.Series(stamp).ffill().fillna(0).to_numpy().astype(np.int64)
    return out, r, iv


def build(d, tfs=(15, 5, 1), max_age=MAX_AGE):
    """Order-flow state for each timeframe, and the M1 inversion table that supplies entries."""
    states = {}
    m1 = None
    for tf in tfs:
        st, r, iv = of_state(d, tf, max_age)
        states[tf] = st
        if tf == 1:
            m1 = (r, iv)
    return states, m1


def map_to_1m(d, r, x):
    """A per-higher-bar series read from 1-minute bars, exposed only AFTER that bar closes."""
    n1 = len(d["c"])
    stamp = np.full(n1, np.nan)
    pos = r["last_i"] + 1
    ok = pos < n1
    stamp[pos[ok]] = np.asarray(x, float)[ok]
    return pd.Series(stamp).ffill().to_numpy()


def tf_atr(d, r, n=14):
    """ATR on the entry timeframe, mapped to 1-minute bars. A 5-minute setup stopped at 1.5x the
    ONE-MINUTE ATR is a different strategy, not the same one on a slower chart -- comparing entry
    timeframes only means something when the barrier scales with the timeframe."""
    tr = I.true_range(r["h"], r["l"], r["c"])
    return map_to_1m(d, r, I.ema(tr, n))


def signals(d, states, ent, tfs=(15, 5), require_align=True, confirm=True):
    """An inversion on the ENTRY timeframe whose polarity matches order flow on every timeframe in
    `tfs`. `ent` is that timeframe's `(frame, inversion table)` pair from `of_state`.

    `confirm=True` is the source's own instruction -- enter once the inversion is confirmed by the
    NEXT candle -- so the signal bar is the 1-minute bar on which that candle closes and the fill is
    the open after it. `confirm=False` signals on the inversion candle itself.
    """
    r, iv = ent
    if not len(iv):
        return pd.DataFrame()
    last = r["last_i"]
    ib = iv.inv_bar.to_numpy() + (1 if confirm else 0)
    ok = ib < len(last)
    ib = np.clip(ib, 0, len(last) - 1)
    sig = last[ib]
    pol = iv.pol.to_numpy()
    ok &= (sig > 0) & (sig < len(d["c"]) - 2)
    if require_align:
        for tf in tfs:
            ok &= states[tf][np.clip(sig, 0, len(d["c"]) - 1)] == pol
    out = pd.DataFrame(dict(sig=sig[ok], side=pol[ok], zlo=iv.zlo.to_numpy()[ok],
                            zhi=iv.zhi.to_numpy()[ok], inv_bar=last[np.clip(iv.inv_bar.to_numpy(),
                                                                           0, len(last) - 1)][ok]))
    return out.sort_values("sig").reset_index(drop=True)
