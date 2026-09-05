"""EMA 13/48 crossover with the session VWAP as support / resistance, ATR stop, optional ATR trail,
intraday (RTH entries, 15:55 flatten). Reuses the parity-checked order model from scalp89.

THE PRIOR THIS BRANCH CARRIES, stated before a single number: the 13x48 cross has failed FIVE
held-back reads (V41, V51, V52, V55, V58); a 1.5xATR stop sits on the wrong side of its own marginal
curve on every market (V18); every trailing stop measured has lost to no trail; the intraday
constraint has cost 57-88% of the result on every family it was applied to. This study exists to
measure the combination, with controls, not to argue with that record.

TWO READINGS OF "VWAP AS SUPPORT AND RESISTANCE", both implemented:
  state   long only while close > session VWAP (support below), short only while close < VWAP
  touch   long when the trend is up AND the bar's low touched the VWAP from above and closed back
          above it -- a bounce off support; short mirrors
TWO READINGS OF THE CROSS: a FRESH cross within `cross_win` bars, or the STATE ema13 > ema48.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63", "research/scalp89"):
    q = os.path.join(ROOT, p)
    if q not in sys.path: sys.path.insert(0, q)
import v63feeds as FD
import s89_core as M

RTH0, RTH1, FLAT = 9 * 60 + 30, 15 * 60 + 55, 15 * 60 + 55
COST = {"NQ": (0.86, 2.0, 0.25), "US100": (0.75, 1.0, 0.1)}


def build(market="NQ", tf=5, fast=13, slow=48, atr_n=14):
    f = FD.bars(market, tf); ix = pd.DatetimeIndex(f.index)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c); mod = (ix.hour * 60 + ix.minute).to_numpy()
    sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_n, adjust=False).mean().to_numpy()
    ef = pd.Series(c).ewm(span=fast, adjust=False).mean().to_numpy()
    es = pd.Series(c).ewm(span=slow, adjust=False).mean().to_numpy()
    rth = (mod >= RTH0) & (mod < 16 * 60)
    tp = (h + l + c) / 3.0
    d = pd.DataFrame({"pv": np.where(rth, tp * v, 0.0), "v": np.where(rth, v, 0.0), "s": sess})
    g = d.groupby("s", sort=False)
    vwap = (g["pv"].cumsum() / g["v"].cumsum().replace(0, np.nan)).to_numpy(); vwap[~rth] = np.nan
    us = np.unique(sess); cut = us[int(0.65 * len(us))]
    cost, pv, tick = COST[market]
    return dict(market=market, tf=tf, ts=ix.to_numpy(), o=o, h=h, l=l, c=c, v=v, n=n, mod=mod, sess=sess,
                atr=atr, ef=ef, es=es, vwap=vwap, rth=rth, cut=int(cut), cost=cost, pv=pv, tick=tick,
                blocks={"research": sess < cut, "locked": sess >= cut},
                vol_kind="true contract volume" if market == "NQ" else "TICK volume (a proxy)")


def signals(D, cross_mode="cross", cross_win=5, vwap_mode="state", sess0=RTH0, sess1=RTH1):
    ef, es, c, l, h, w = D["ef"], D["es"], D["c"], D["l"], D["h"], D["vwap"]
    up = ef > es
    x_up = up & ~np.roll(up, 1); x_dn = ~up & np.roll(up, 1)
    if cross_mode == "cross":
        rec_up = pd.Series(x_up).rolling(cross_win, min_periods=1).max().to_numpy().astype(bool)
        rec_dn = pd.Series(x_dn).rolling(cross_win, min_periods=1).max().to_numpy().astype(bool)
        long_t, short_t = rec_up & up, rec_dn & ~up
    else:
        long_t, short_t = up, ~up
    if vwap_mode == "state":
        vl, vs = c > w, c < w
    elif vwap_mode == "touch":
        vl = (l <= w) & (c > w); vs = (h >= w) & (c < w)
    else:
        vl = vs = np.ones(D["n"], bool)
    ins = (D["mod"] >= sess0) & (D["mod"] < sess1) & np.isfinite(w) & np.isfinite(D["atr"]) & (D["atr"] > 0)
    ins[:300] = False
    lo = long_t & vl & ins; sh = short_t & vs & ins
    if cross_mode == "cross":
        # fire ONCE per cross: the first bar in the window that qualifies
        lo = lo & ~np.roll(lo, 1); sh = sh & ~np.roll(sh, 1)
    return np.where(lo, 1, np.where(sh, -1, 0)).astype(np.int64)


def run(D, side, stop=1.5, trail=True, t_arm=1.0, t_off=1.0, flat=True, tgt=99.0, cost=None, slip=None,
        protect_fill=1):
    cfg = dict(M.CFG, stop_mult=stop, tgt_mult=tgt, trail_on=1 if trail else 0, trail_arm=t_arm, trail_off=t_off,
               pv=D["pv"], qty=1)
    Dm = dict(D)  # M.run needs these keys
    t = M.run(Dm, cfg=cfg, side_override=side, use_flat=1 if flat else 0, flat_mod=FLAT, cost=cost, slip=slip,
              protect_fill=protect_fill, trail_atr=1)
    return t


def stats(t):
    return M.stats(t)
