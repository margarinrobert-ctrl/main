"""Bar-level shape check of the MRL design on the 15-minute feeds (US100, US30, XAUUSD).

No 1-minute path exists for these feeds, so this is a SIGN AND SHAPE check, never the number:
the limit fills when the bar trades through the level (fill at the open if it gapped), the stop
is live on the fill bar, the TARGET MAY FIRE ONLY FROM THE NEXT BAR (the fill-bar high was made
before the dip that filled the order -- STUDY_V10's first artifact, which at 1-minute scale
turned an 81% win rate into 71% and PF 1.9 into 0.92), a bar touching both barriers is a stop,
and the order lives `expiry` bars from the close it was placed at. Costs are the retail CFD
assumptions in index points from `scalp.core.COSTS`, a limit entry paying nothing, a stop
paying half a spread plus stop slippage, a target half a spread, a flatten half a spread plus
entry slippage. Gold's clock is UTC (registry), the CFDs' New York + 7.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ibs import ibs_core as IC  # noqa: E402
from scalp.core import COSTS  # noqa: E402
import indicators as I  # noqa: E402


def load(market):
    if market == "XAUUSD":
        d = pd.read_csv(
            "data/XAUUSD15_MT.csv",
            sep="\t",
            header=None,
            names=["ts", "open", "high", "low", "close", "vol"],
        )
        ix = (
            pd.DatetimeIndex(pd.to_datetime(d["ts"], utc=True))
            .tz_convert("America/New_York")
            .tz_localize(None)
        )
        f = pd.DataFrame(
            {k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")}, index=ix
        )
        f["volume"] = d["vol"].to_numpy(float)
        f = f.sort_index()
        f = f[~f.index.duplicated(keep="first")]
        return f
    f, tf = IC.load(market)
    f["volume"] = 1.0
    return f


@njit(cache=True)
def walk(
    o,
    h,
    l,
    c,
    mod,
    atr_sig,
    atr_lim,
    trig,
    side,
    lim_mult,
    stop_mult,
    tp_r,
    flat_min,
    expiry,
    cancel_mod,
    sp_rth,
    sp_pre,
    sp_off,
    slip_e,
    slip_s,
    through,
):
    n = len(trig)
    N = len(c)
    pnl = np.zeros(n)
    sb = np.zeros(n, np.int64)
    xb = np.zeros(n, np.int64)
    why = np.zeros(n, np.int64)
    risk = np.zeros(n)
    k = 0
    nf = 0
    nt = 0
    free = -1
    busy_until = -1
    for t in range(n):
        i = trig[t]
        if i < free or i < busy_until:
            continue
        a = atr_sig[i]
        al = atr_lim[i]
        if np.isnan(a) or a <= 0 or np.isnan(al) or al <= 0 or i + 1 >= N:
            continue
        nt += 1
        limit = c[i] - side * lim_mult * al
        busy_until = i + expiry
        f = -1
        px = 0.0
        j = i + 1
        while j <= i + expiry and j < N:
            if cancel_mod > 0 and mod[j] >= cancel_mod:
                break
            if side == 1 and l[j] <= limit - through:
                f = j
                px = o[j] if o[j] < limit else limit
                break
            if side == -1 and h[j] >= limit + through:
                f = j
                px = o[j] if o[j] > limit else limit
                break
            j += 1
        if f < 0:
            continue
        nf += 1
        entry = px
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a
        jj = f
        done = 0
        while jj < N:
            m = mod[jj]
            tier = (
                sp_rth
                if (m >= 570 and m < 960)
                else (sp_pre if (m >= 240 and m < 1080) else sp_off)
            )
            hit = (l[jj] <= st) if side == 1 else (h[jj] >= st)
            won = (h[jj] >= tg) if side == 1 else (l[jj] <= tg)
            if jj == f:
                won = False
            if hit:
                q = o[jj] if ((side == 1 and o[jj] < st) or (side == -1 and o[jj] > st)) else st
                q -= side * (tier / 2.0 + slip_s)
                pnl[k] = side * (q - entry)
                why[k] = 1
                done = 1
            elif won:
                q = o[jj] if ((side == 1 and o[jj] > tg) or (side == -1 and o[jj] < tg)) else tg
                q -= side * (tier / 2.0)
                pnl[k] = side * (q - entry)
                why[k] = 2
                done = 1
            elif flat_min > 0 and mod[jj] >= flat_min:
                q = c[jj] - side * (tier / 2.0 + slip_e)
                pnl[k] = side * (q - entry)
                why[k] = 3
                done = 1
            if done == 1:
                xb[k] = jj
                sb[k] = i
                risk[k] = stop_mult * a
                free = jj
                k += 1
                break
            jj += 1
    return pnl[:k], sb[:k], xb[:k], why[:k], risk[:k], nf, nt


class Feed:
    def __init__(self, market, tf_min=15):
        self.market = market
        self.f = load(market)
        f = self.f
        self.o, self.h, self.l, self.c, self.v = (
            f[k].to_numpy() for k in ("open", "high", "low", "close", "volume")
        )
        ix = f.index
        self.mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
        self.atr = I.ema(I.true_range(self.h, self.l, self.c), 14)
        self.atr_lim = I.ema(I.true_range(self.h, self.l, self.c), 5)
        self.dates = ix
        self.tf = tf_min
        cst = COSTS[
            "XAUUSD" if market == "XAUUSD" else ("US30" if market.startswith("US30") else market)
        ]
        self.cost = cst
        # session ids on the New York calendar day (the 17:00 roll is not needed for a
        # 09:30-15:00 window)
        day = ix.normalize()
        self.sess = pd.factorize(day)[0]
        self.F = self._features()

    def _features(self):
        o, h, l, c, v, mod, si = self.o, self.h, self.l, self.c, self.v, self.mod, self.sess
        n = len(c)
        a = np.where(self.atr > 0, self.atr, np.nan)
        sh = np.full(n, np.nan)
        sl = np.full(n, np.nan)
        vw = np.full(n, np.nan)
        pdh = np.full(n, np.nan)
        pdl = np.full(n, np.nan)
        cur = -1
        H = -np.inf
        L = np.inf
        TV = 0.0
        V = 0.0
        last_h = np.nan
        last_l = np.nan
        rh = -np.inf
        rl = np.inf
        for i in range(n):
            if si[i] != cur:
                if rh > -np.inf:
                    last_h, last_l = rh, rl
                cur = si[i]
                H = -np.inf
                L = np.inf
                TV = 0.0
                V = 0.0
                rh = -np.inf
                rl = np.inf
            if 570 <= mod[i] < 960:
                H = max(H, h[i])
                L = min(L, l[i])
                TV += (h[i] + l[i] + c[i]) / 3 * v[i]
                V += v[i]
                rh = max(rh, h[i])
                rl = min(rl, l[i])
                sh[i] = H
                sl[i] = L
                vw[i] = TV / V if V > 0 else np.nan
            pdh[i] = last_h
            pdl[i] = last_l
        rng = sh - sl
        F = dict(
            retr_from_high=np.where(rng > 0, (sh - c) / rng, np.nan),
            retr_from_low=np.where(rng > 0, (c - sl) / rng, np.nan),
            vwap_dist=(c - vw) / a,
            ret30=(c - np.roll(c, 2)) / a,
            ret5=(c - np.roll(c, 1)) / a,
            pdh_dist=(c - pdh) / a,
            pdl_dist=(c - pdl) / a,
            sess_range_atr=rng / a,
            hour=mod / 60.0,
            bar_range_atr=(h - l) / a,
            close_pos_bar=np.where(h > l, (c - l) / (h - l), np.nan),
        )
        s = pd.Series(self.atr)
        F["atr_regime"] = self.atr / s.rolling(26 * 20, min_periods=100).mean().to_numpy()
        return F

    def run(
        self,
        trig,
        side,
        lim,
        stop,
        tp,
        expiry=1,
        flat=955,
        cancel_mod=900,
        cost_mult=1.0,
        through_pts=None,
    ):
        cst = self.cost
        thr = 0.0 if through_pts is None else through_pts
        return walk(
            self.o,
            self.h,
            self.l,
            self.c,
            self.mod,
            self.atr,
            self.atr_lim,
            np.asarray(trig, np.int64),
            np.int64(side),
            float(lim),
            float(stop),
            float(tp),
            np.int64(flat),
            np.int64(expiry),
            np.int64(cancel_mod),
            cst.spread_rth * cost_mult,
            cst.spread_pre * cost_mult,
            cst.spread_off * cost_mult,
            cst.slip_entry * cost_mult,
            cst.slip_stop * cost_mult,
            thr,
        )


def stats(pnl, risk, why, nt):
    if len(pnl) == 0:
        return dict(n=0)
    r = pnl / risk
    w = pnl > 0
    return dict(
        n=int(len(pnl)),
        fill=len(pnl) / max(nt, 1),
        win=float(w.mean()),
        pf=float(pnl[w].sum() / max(-pnl[~w].sum(), 1e-9)),
        R=float(r.mean()),
        pts=float(pnl.mean()),
        tgt_share=float((why == 2).mean()),
    )
