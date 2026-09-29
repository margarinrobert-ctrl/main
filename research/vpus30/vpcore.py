"""Volume profile on US30 15m, built from Max Anderson's six strategies (pages 1-21).

WHAT THE BOOK GIVES THAT IS MECHANICAL, and how each is expressed here:
  1 HVN retracement   local maxima of the session volume histogram; price above one -> support,
                      below -> resistance. Traded as a mean-reversion primary.
  2 LVN breakout      local minima; "price passes through with minimal effort". Momentum primary.
  3 distribution      bullish/bearish = close near the profile extreme with value eroding away
                      from it; neutral = close inside a value area sitting mid-profile
                      ("trapped traders"). Expressed as close-position-in-profile + VA centring.
  4 stacked POCs      count of prior sessions whose POC sits within a tolerance of price.
  5 stop behind POC   a trailing stop anchored to the developing POC.
  6 R at the next HVN a target placed at the nearest HVN in the trade's direction.

THREE DEGRADATIONS THAT STAY ATTACHED TO EVERY NUMBER.

  a. `Volume` IS ZERO ON 100% OF ROWS in this file. `TickVolume` is the real activity column
     (correlation with the bar's own range +0.7661), so every "volume" profile here is a TICK
     COUNT profile. A tick is not a contract and the two are not interchangeable.
  b. THE FINEST US30 DATA ON DISK IS 15 MINUTES. A real footprint needs intrabar prints; this
     spreads each bar's tick count UNIFORMLY across its [low, high]. That is what charting
     packages do without tick data, and it is an approximation -- the NQ volume-profile work on
     this branch used a 1-minute source mapped onto 15m bars and had no such gap.
  c. `STUDY_AUCTION` already tested 47 auction conditions (POC, value area, VAH/VAL, opening
     classification, naked edges, LVN/HVN) and found 7 of 172 passes on research against ~8.6
     expected by chance, 0 surviving the holdout. Distribution SHAPE and STACKED POCs are the two
     constructions in this book that were not in that pool.

Bins are SCALE-FREE: 0.10 x the session's own ATR, so the same code is valid on any instrument
and the bin count does not drift with the index level over nine years.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
from v38 import v38feeds as F  # noqa: E402

RTH0, RTH1 = 9 * 60 + 30, 16 * 60
VA_FRAC = 0.70          # the book's "traditionalists use 70%"
BIN_ATR = 0.10          # bin width as a fraction of session ATR -- scale free
RT_POINTS = 2.29        # US30/YM all-in round turn, this branch's convention


def load():
    """US30_LONG_15m in New York time. Clock is NY+7 and DST-stable (research/datasets.py)."""
    f = F.load("US30L")
    f = f.rename(columns={"volume": "tv"})
    mod = f.index.hour * 60 + f.index.minute
    f = f.assign(mod=mod, sess=f.index.normalize())
    return f


def atr(f, n=14):
    h, lo, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


@njit(cache=True)
def _profile(h, l, tv, i0, i1, binw, lo0, nb):
    """Spread each bar's tick count uniformly over its [low, high] into `nb` bins."""
    hist = np.zeros(nb, np.float64)
    for i in range(i0, i1):
        a = int((l[i] - lo0) / binw)
        b = int((h[i] - lo0) / binw)
        if a < 0:
            a = 0
        if b >= nb:
            b = nb - 1
        if b < a:
            b = a
        w = tv[i] / (b - a + 1)
        for k in range(a, b + 1):
            hist[k] += w
    return hist


def _va(hist, frac=VA_FRAC):
    """Value area: grow outward from the POC bin, always taking the richer neighbour."""
    poc = int(np.argmax(hist))
    tot = hist.sum()
    if tot <= 0:
        return poc, poc, poc
    got = hist[poc]
    lo = hi = poc
    n = len(hist)
    while got < frac * tot and (lo > 0 or hi < n - 1):
        dn = hist[lo - 1] if lo > 0 else -1.0
        up = hist[hi + 1] if hi < n - 1 else -1.0
        if up >= dn:
            hi += 1
            got += hist[hi]
        else:
            lo -= 1
            got += hist[lo]
    return poc, lo, hi


def _nodes(hist, k=2):
    """HVN = local maximum over +/-k bins; LVN = local minimum. The book's own definition:
    'a region of high/low volume IN RELATION TO NEARBY price action'."""
    n = len(hist)
    hv, lv = [], []
    for i in range(k, n - k):
        w = hist[i - k:i + k + 1]
        if hist[i] == w.max() and hist[i] > 0 and hist[i] > np.median(hist) :
            hv.append(i)
        if hist[i] == w.min() and hist[i] < np.median(hist):
            lv.append(i)
    return np.array(hv, np.int64), np.array(lv, np.int64)


def sessions(f):
    """Per RTH session: the completed profile, frozen. Everything is read the NEXT session."""
    g = f[(f["mod"] >= RTH0) & (f["mod"] < RTH1)]
    h = g["high"].to_numpy(); l = g["low"].to_numpy(); tv = g["tv"].to_numpy()
    keys = g["sess"].to_numpy()
    a = atr(g)
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    ends = np.r_[starts[1:], len(keys)]
    rows = []
    for s, e in zip(starts, ends):
        if e - s < 8:
            continue
        lo0, hi0 = l[s:e].min(), h[s:e].max()
        rngp = hi0 - lo0
        binw = max(BIN_ATR * np.nanmean(a[s:e]), 1e-6)
        nb = int(np.ceil(rngp / binw)) + 1
        if nb < 5 or nb > 4000:
            continue
        hist = _profile(h, l, tv, s, e, binw, lo0, nb)
        poc, val_i, vah_i = _va(hist)
        hv, lv = _nodes(hist)
        rows.append(dict(
            sess=pd.Timestamp(keys[s]), i0=s, i1=e,
            lo=lo0, hi=hi0, rng=rngp, binw=binw, nb=nb,
            poc=lo0 + (poc + 0.5) * binw,
            val=lo0 + (val_i + 0.5) * binw,
            vah=lo0 + (vah_i + 0.5) * binw,
            close=g["close"].to_numpy()[e - 1],
            open=g["open"].to_numpy()[s],
            tvsum=tv[s:e].sum(), atr=float(np.nanmean(a[s:e])),
            n_hvn=len(hv), n_lvn=len(lv),
            hvn=(lo0 + (hv + 0.5) * binw) if len(hv) else np.array([]),
            lvn=(lo0 + (lv + 0.5) * binw) if len(lv) else np.array([]),
        ))
    d = pd.DataFrame(rows)
    # --- the book's distribution taxonomy, expressed as numbers
    d["close_pos"] = (d["close"] - d["lo"]) / d["rng"].replace(0, np.nan)   # 0 low, 1 high
    d["va_centre"] = (0.5 * (d["vah"] + d["val"]) - d["lo"]) / d["rng"].replace(0, np.nan)
    d["va_width"] = (d["vah"] - d["val"]) / d["rng"].replace(0, np.nan)
    d["in_va"] = ((d["close"] >= d["val"]) & (d["close"] <= d["vah"])).astype(int)
    d["poc_pos"] = (d["poc"] - d["lo"]) / d["rng"].replace(0, np.nan)
    # bullish/bearish = close at an extreme AND value eroded away from centre; neutral = inside VA
    d["shape"] = np.where(d["in_va"] == 1, "neutral",
                          np.where(d["close_pos"] >= 0.5, "bullish", "bearish"))
    d["balance"] = d["va_width"]              # wide VA = balanced, narrow = imbalanced/trending
    return d


def features(f, d):
    """Causal features at every RTH bar. PRIOR-session profile values are frozen and read from the
    NEXT session's first bar onward; developing values use only bars closed so far today."""
    g = f[(f["mod"] >= RTH0) & (f["mod"] < RTH1)].copy()
    a = atr(g)
    g["atr"] = a
    d = d.sort_values("sess").reset_index(drop=True)
    prev = d.shift(1)                       # yesterday's completed profile
    m = pd.DataFrame(dict(sess=d["sess"], p_poc=prev["poc"], p_vah=prev["vah"], p_val=prev["val"],
                          p_lo=prev["lo"], p_hi=prev["hi"], p_rng=prev["rng"],
                          p_shape=prev["shape"], p_vaw=prev["va_width"],
                          p_cpos=prev["close_pos"], p_pocpos=prev["poc_pos"],
                          p_nhvn=prev["n_hvn"], p_nlvn=prev["n_lvn"], p_atr=prev["atr"]))
    g = g.merge(m, on="sess", how="left")
    g.index = f[(f["mod"] >= RTH0) & (f["mod"] < RTH1)].index
    c = g["close"].to_numpy(); at = np.where(g["atr"].to_numpy() > 0, g["atr"].to_numpy(), np.nan)

    # --- book strategy 1 and 4: distance to the prior POC / value edges, in ATR
    for nm, col in (("d_poc", "p_poc"), ("d_vah", "p_vah"), ("d_val", "p_val")):
        g[nm] = (c - g[col].to_numpy()) / at
    g["above_va"] = (c > g["p_vah"].to_numpy()).astype(float)
    g["below_va"] = (c < g["p_val"].to_numpy()).astype(float)
    g["inside_va"] = 1.0 - g["above_va"] - g["below_va"]

    # --- nearest prior-session HVN / LVN above and below, in ATR (book strategies 1, 2, 6)
    nodes = {r.sess: (r.hvn, r.lvn) for r in d.itertuples()}
    keys = d["sess"].to_numpy()
    pmap = {keys[i]: keys[i - 1] for i in range(1, len(keys))}
    hu = np.full(len(g), np.nan); hd = np.full(len(g), np.nan)
    lu = np.full(len(g), np.nan); ld = np.full(len(g), np.nan)
    sess_arr = g["sess"].to_numpy()
    for i in range(len(g)):
        pk = pmap.get(sess_arr[i])
        if pk is None:
            continue
        hv, lv = nodes.get(pk, (np.array([]), np.array([])))
        px = c[i]
        if len(hv):
            up = hv[hv > px]; dn = hv[hv < px]
            if len(up):
                hu[i] = (up.min() - px)
            if len(dn):
                hd[i] = (px - dn.max())
        if len(lv):
            up = lv[lv > px]; dn = lv[lv < px]
            if len(up):
                lu[i] = (up.min() - px)
            if len(dn):
                ld[i] = (px - dn.max())
    g["hvn_up"] = hu / at; g["hvn_dn"] = hd / at
    g["lvn_up"] = lu / at; g["lvn_dn"] = ld / at

    # --- book strategy 4: STACKED POCs -- prior sessions whose POC sits near current price
    pocs = d["poc"].to_numpy()
    sidx = {k: i for i, k in enumerate(keys)}
    for K in (5, 20):
        out = np.full(len(g), np.nan)
        for i in range(len(g)):
            j = sidx.get(sess_arr[i])
            if j is None or j < K:
                continue
            w = pocs[j - K:j]                       # STRICTLY prior sessions
            out[i] = float((np.abs(w - c[i]) <= 0.5 * at[i]).sum())
        g[f"stack{K}"] = out

    # --- book strategy 3: the prior distribution's shape, as numbers
    g["p_bull"] = (g["p_shape"] == "bullish").astype(float)
    g["p_bear"] = (g["p_shape"] == "bearish").astype(float)
    g["p_neut"] = (g["p_shape"] == "neutral").astype(float)

    # --- developing (today-so-far) profile: POC and value, recomputed causally each bar
    dev_poc = np.full(len(g), np.nan); dev_pos = np.full(len(g), np.nan)
    hh = g["high"].to_numpy(); ll = g["low"].to_numpy(); tvv = g["tv"].to_numpy()
    st = np.flatnonzero(np.r_[True, sess_arr[1:] != sess_arr[:-1]])
    en = np.r_[st[1:], len(g)]
    for s, e in zip(st, en):
        for t in range(s + 3, e):
            lo0 = ll[s:t + 1].min(); hi0 = hh[s:t + 1].max()
            if hi0 <= lo0 or not np.isfinite(at[t]):
                continue
            bw = max(BIN_ATR * at[t], 1e-6)
            nb = int((hi0 - lo0) / bw) + 1
            if nb < 3 or nb > 4000:
                continue
            hist = _profile(hh, ll, tvv, s, t + 1, bw, lo0, nb)
            pi = int(np.argmax(hist))
            dev_poc[t] = lo0 + (pi + 0.5) * bw
            dev_pos[t] = (c[t] - lo0) / (hi0 - lo0)
    g["dev_poc"] = (c - dev_poc) / at
    g["dev_pos"] = dev_pos
    g["bar_in_sess"] = np.concatenate([np.arange(e - s) for s, e in zip(st, en)])
    return g


FEATS = ["d_poc", "d_vah", "d_val", "above_va", "below_va", "inside_va",
         "hvn_up", "hvn_dn", "lvn_up", "lvn_dn", "stack5", "stack20",
         "p_bull", "p_bear", "p_neut", "p_vaw", "p_cpos", "p_pocpos",
         "p_nhvn", "p_nlvn", "dev_poc", "dev_pos"]


def events(g, kind, tol_atr=0.15):
    """The book's two tradeable primaries, as event streams on completed bars.

    HVN  price returns to a prior-session high-volume node. The book: above an HVN it is SUPPORT,
         below it is RESISTANCE -- so the side is set by which side price approached from.
    LVN  price closes THROUGH a low-volume node: "price passes through with minimal effort".
    """
    c = g["close"].to_numpy(); h = g["high"].to_numpy(); l = g["low"].to_numpy()
    at = g["atr"].to_numpy()
    hu, hd = g["hvn_up"].to_numpy(), g["hvn_dn"].to_numpy()
    lu, ld = g["lvn_up"].to_numpy(), g["lvn_dn"].to_numpy()
    bar = g["bar_in_sess"].to_numpy()
    n = len(c)
    idx, side = [], []
    for i in range(1, n):
        if bar[i] < 2 or not np.isfinite(at[i]) or at[i] <= 0:
            continue
        if kind == "hvn":
            # approaching an HVN from ABOVE -> it is support -> long
            if np.isfinite(hd[i]) and hd[i] <= tol_atr and (not np.isfinite(hd[i-1]) or hd[i-1] > tol_atr):
                idx.append(i); side.append(1)
            elif np.isfinite(hu[i]) and hu[i] <= tol_atr and (not np.isfinite(hu[i-1]) or hu[i-1] > tol_atr):
                idx.append(i); side.append(-1)
        else:
            # a close that has just crossed an LVN -> momentum through the low-liquidity pocket
            if np.isfinite(lu[i-1]) and lu[i-1] <= tol_atr and np.isfinite(ld[i]) and ld[i] <= 1.0:
                idx.append(i); side.append(1)
            elif np.isfinite(ld[i-1]) and ld[i-1] <= tol_atr and np.isfinite(lu[i]) and lu[i] <= 1.0:
                idx.append(i); side.append(-1)
    return np.array(idx, np.int64), np.array(side, np.int64)


@njit(cache=True)
def _walk(o, h, l, c, at, bar, nb, idx, side, sl, tp, cost, lock):
    """Fill at open[i+1]. Flat at the session's last RTH bar. One live position."""
    m = len(idx)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    ep = np.zeros(m); xp = np.zeros(m); rk = np.zeros(m)
    wy = np.zeros(m, np.int64); tk = np.zeros(m, np.int64)
    last = -1
    n = len(c)
    for q in range(m):
        i = idx[q]
        j = i + 1
        if j >= n - 1:
            continue
        if bar[j] <= bar[i] and bar[j] != bar[i] + 1:   # fill would land in a new session
            continue
        if lock == 1 and j <= last:
            continue
        s = side[q]
        ent = o[j]
        stop = ent - s * sl * at[i]
        tgt = ent + s * tp * at[i] if tp > 0 else 0.0
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        x = -1; px = 0.0; w = 2
        for t in range(j, n):
            if bar[t] >= nb[t] - 1:                     # last RTH bar -> flat at its close
                x = t; px = c[t]; w = 2
                break
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = False
            if tp > 0:
                ht = (h[t] >= tgt) if s > 0 else (l[t] <= tgt)
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = tgt; w = 1
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[q] = j; xb[q] = x; ep[q] = ent; xp[q] = px
        rk[q] = risk; wy[q] = w; tk[q] = 1
        last = x
    return eb, xb, ep, xp, rk, wy, tk


def walk(g, idx, side, sl=1.5, tp=0.0, cost=RT_POINTS, lock=True):
    o = g["open"].to_numpy(); h = g["high"].to_numpy()
    l = g["low"].to_numpy(); c = g["close"].to_numpy()
    at = g["atr"].to_numpy(); bar = g["bar_in_sess"].to_numpy()
    sess = g["sess"].to_numpy()
    st = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    en = np.r_[st[1:], len(g)]
    nb = np.zeros(len(g), np.int64)
    for s, e in zip(st, en):
        nb[s:e] = e - s
    eb, xb, ep, xp, rk, wy, tk = _walk(o, h, l, c, at, bar, nb, idx, side,
                                       float(sl), float(tp), float(cost), 1 if lock else 0)
    k = tk == 1
    t = pd.DataFrame(dict(e_bar=eb[k], x_bar=xb[k], ent=ep[k], out=xp[k], risk=rk[k],
                          side=side[k], why=wy[k]))
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["R"] = t.net_pts / t.risk
    t["cost_frac"] = cost / t.risk
    t["ts"] = g.index[t.e_bar.to_numpy()]
    return t


def pf(t, col="pct"):
    x = t[col].to_numpy()
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan


def events_guide(f, g, d, kind, shift_atr=1.0, win=40, tol_atr=0.20):
    """The three setups the US30 study guide names as precisely definable (its Part 10 test list).

    pocshift  5.4 "the best trend-entry signal in the book". A FLEXIBLE profile over the last
              `win` bars; the POC relocates wholesale by >= shift_atr ATR between consecutive
              bars. Trade in the direction of the shift.
    nakedpoc  5.5 a prior-session POC never traded through since it formed. When price finally
              reaches it, FADE -- the guide calls it "a magnet with unfinished business" and
              directs you to look for a reversal there.
    openrej   5.6 open rejection reverse: the session opens OUTSIDE yesterday's range, is
              rejected, and re-enters. Trade the re-entry direction. Forthmann rates this the
              best opportunity available.
    """
    c = g["close"].to_numpy(); h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); tv = g["tv"].to_numpy(); at = g["atr"].to_numpy()
    bar = g["bar_in_sess"].to_numpy(); sess = g["sess"].to_numpy()
    n = len(c)
    idx, side = [], []

    if kind == "pocshift":
        poc = np.full(n, np.nan)
        for i in range(win, n):
            lo0, hi0 = l[i - win:i + 1].min(), h[i - win:i + 1].max()
            if hi0 <= lo0 or not np.isfinite(at[i]) or at[i] <= 0:
                continue
            bw = max(BIN_ATR * at[i], 1e-6)
            nb = int((hi0 - lo0) / bw) + 1
            if nb < 3 or nb > 4000:
                continue
            hist = _profile(h, l, tv, i - win, i + 1, bw, lo0, nb)
            poc[i] = lo0 + (np.argmax(hist) + 0.5) * bw
        for i in range(win + 2, n):
            if bar[i] < 2 or not np.isfinite(poc[i]) or not np.isfinite(poc[i - 1]):
                continue
            jump = (poc[i] - poc[i - 1]) / at[i]
            if jump >= shift_atr:
                idx.append(i); side.append(1)
            elif jump <= -shift_atr:
                idx.append(i); side.append(-1)

    elif kind == "nakedpoc":
        keys = d["sess"].to_numpy(); pocs = d["poc"].to_numpy()
        touched = np.zeros(len(d), bool)
        sidx = {k: i for i, k in enumerate(keys)}
        for i in range(1, n):
            if bar[i] < 2 or not np.isfinite(at[i]) or at[i] <= 0:
                continue
            j = sidx.get(sess[i])
            if j is None or j < 1:
                continue
            for q in range(max(0, j - 20), j):          # 2-3 sessions is Forthmann; 20 is generous
                if touched[q]:
                    continue
                p = pocs[q]
                if l[i] <= p <= h[i]:
                    touched[q] = True
                    if abs(c[i - 1] - p) / at[i] > tol_atr:
                        idx.append(i); side.append(1 if c[i - 1] < p else -1)
                    break

    else:  # openrej
        keys = d["sess"].to_numpy(); plo = d["lo"].shift(1).to_numpy(); phi = d["hi"].shift(1).to_numpy()
        sidx = {k: i for i, k in enumerate(keys)}
        st = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
        for s in st:
            j = sidx.get(sess[s])
            if j is None or j < 1 or not np.isfinite(plo[j]) or not np.isfinite(phi[j]):
                continue
            above = o[s] > phi[j]
            below = o[s] < plo[j]
            if not (above or below):
                continue
            e = s + 1
            while e < n and sess[e] == sess[s]:
                if not np.isfinite(at[e]) or at[e] <= 0:
                    e += 1
                    continue
                if above and c[e] < phi[j]:             # rejected back INTO yesterday's range
                    idx.append(e); side.append(-1)
                    break
                if below and c[e] > plo[j]:
                    idx.append(e); side.append(1)
                    break
                e += 1
    return np.array(idx, np.int64), np.array(side, np.int64)
