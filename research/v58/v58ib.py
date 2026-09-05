"""V58 -- the Initial Balance retracement family, swept as a tensor across markets.

THE RULE, as the user's indicator states it: the Initial Balance is the high and low of the
first hour after the New York open; wait for that hour to CLOSE; wait for a break of either
edge; enter on a retracement of R% of the range back INSIDE the broken edge; stop S% of the
range from the broken edge; target T% of the range beyond it; flat at the session end.

WHY IT CAN BE A TENSOR. The entry, stop and target are pure functions of the Initial Balance,
and the Initial Balance is final at 10:30. So a day's outcome depends only on (the day, the IB
length, the side, the four geometry numbers) -- never on which indicator was consulted. Walk
each day once per geometry and every filtered configuration becomes a masked mean.

Everything a filter reads is stamped at the IB CLOSE, which is the moment the plan is made, so
no filter can see a bar the decision did not have. `ent_bar` leakage (`STUDY_AUCTION.md`) is
structurally impossible here for the same reason: there is one decision per day and it is taken
before the trade window opens.

Filters are stored SIDE-ORIENTED -- higher is always more favourable to the side being taken --
so a short reads 1 - close_position and a negated moving-average gap. Without that a single
threshold means two different things on the two sides and the sweep quietly rewards whichever
one the sample's drift prefers.

CALENDAR CONDITIONS ARE BANNED (`CLAUDE.md`): no weekday, no month.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit, prange

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v38.v38feeds import load, INSTR      # noqa: E402

IB_OPEN = 9 * 60 + 30                              # 09:30 New York

# ---- the swept axes -------------------------------------------------------------------------
IB_LEN = np.array([30, 60, 90], np.int64)                    # minutes of Initial Balance
RETR   = np.array([0.00, 0.10, 0.25, 0.40, 0.50], np.float64)  # entry, fraction of range inside
STOPF  = np.array([0.40, 0.60, 0.80, 1.00, 1.30], np.float64)  # stop, fraction of range from edge
TGT    = np.array([0.50, 0.75, 1.00, 1.50, 2.50, 99.0], np.float64)  # 99 = no target
FLAT   = np.array([13 * 60, 15 * 60, 15 * 60 + 55], np.int64)  # flatten time
NG = len(IB_LEN) * len(RETR) * len(STOPF) * len(TGT) * len(FLAT)

# ---- the filter pool, four near-independent readings ----------------------------------------
ADX_MODE  = ["off", "adx>=20", "adx>=25", "adx<=20"]
VOL_MODE  = ["off", "ibr>=0.8x", "ibr>=1.2x", "ibr<=1.2x"]
CPOS_MODE = ["off", "cpos>=0.6", "cpos>=0.5", "cpos<=0.4"]
EMA_MODE  = ["off", "13 over 48", "13 under 48"]
NF = len(ADX_MODE) * len(VOL_MODE) * len(CPOS_MODE) * len(EMA_MODE)

COST_PTS = {"US30L": 1.72, "US100L": 1.215}        # round turn, the branch's measured stack


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(name):
    """Bars, day index, per-day Initial Balances and the four causal day features."""
    f = load(name)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    wd = ix.dayofweek.to_numpy(np.int64)

    adx = _adx(h, l, c)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)),
                                          np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr14 = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    e13, e48 = _ema(c, 13), _ema(c, 48)

    # day boundaries
    edge = np.flatnonzero(np.diff(day) != 0) + 1
    starts = np.concatenate([[0], edge])
    ends = np.concatenate([edge, [len(day)]])
    keep = wd[starts] < 5                                    # weekdays only
    starts, ends = starts[keep], ends[keep]
    D = len(starts)

    ibh = np.full((D, len(IB_LEN)), np.nan)
    ibl = np.full((D, len(IB_LEN)), np.nan)
    ibe = np.full((D, len(IB_LEN)), -1, np.int64)            # first bar AFTER the IB
    fend = np.full((D, len(FLAT)), -1, np.int64)             # first bar at/after the flatten
    cpos = np.full((D, len(IB_LEN)), np.nan)
    adxd = np.full((D, len(IB_LEN)), np.nan)
    emad = np.full((D, len(IB_LEN)), np.nan)
    atrd = np.full((D, len(IB_LEN)), np.nan)

    for d in range(D):
        a, b = starts[d], ends[d]
        m = mod[a:b]
        for li, L in enumerate(IB_LEN):
            sel = (m >= IB_OPEN) & (m < IB_OPEN + L)
            if not sel.any():
                continue
            k = np.flatnonzero(sel)
            hi, lo = h[a + k].max(), l[a + k].min()
            if not (hi > lo):
                continue
            after = np.flatnonzero(m >= IB_OPEN + L)
            if len(after) == 0:
                continue
            last = a + k[-1]                                 # the bar the plan is made on
            ibh[d, li], ibl[d, li] = hi, lo
            ibe[d, li] = a + after[0]
            cpos[d, li] = (c[last] - lo) / (hi - lo)
            adxd[d, li] = adx[last]
            emad[d, li] = e13[last] - e48[last]
            atrd[d, li] = atr14[last]
        for fi, F in enumerate(FLAT):
            aft = np.flatnonzero(m >= F)
            fend[d, fi] = a + aft[0] if len(aft) else b

    return dict(o=o, h=h, l=l, c=c, mod=mod, starts=starts, ends=ends, D=D,
                ibh=ibh, ibl=ibl, ibe=ibe, fend=fend, cpos=cpos, adx=adxd, ema=emad, atr=atrd,
                dates=ix.normalize().values[starts])


@njit(cache=True, parallel=True)
def _walk(h, l, c, ibh, ibl, ibe, fend, retr, stopf, tgt, cost_pts, fillbar,
          outR, outAmb):
    """One walk per (day, ib length, side, retracement, flatten); barriers looped inside.

    A fill is never taken on the break bar: that bar spans time BEFORE the break, so a bar that
    dipped to the entry and then rallied through the edge would otherwise report a break and a
    fill that never happened in that order.

    `fillbar` selects the EXIT MODEL and the difference is the whole point of running both.
    fillbar=0 skips the fill bar for exits -- the optimistic read, and the one a bar engine
    takes by default. fillbar=1 tests the stop on the fill bar itself. When the entry level and
    the stop sit a tenth of an Initial Balance range apart they are routinely INSIDE ONE 15-MINUTE
    BAR, and skipping that bar hands the configuration a free option. Neither model can order
    intrabar events; the honest procedure is to report the gap between them.
    """
    D, NL = ibh.shape
    NR, NS, NT, NFL = len(retr), len(stopf), len(tgt), fend.shape[1]
    for d in prange(D):
        for li in range(NL):
            hi, lo = ibh[d, li], ibl[d, li]
            if not (hi > lo):
                continue
            rng = hi - lo
            b0 = ibe[d, li]
            for side in range(2):                            # 0 long, 1 short
                for fl in range(NFL):
                    b1 = fend[d, fl]
                    if b1 <= b0:
                        continue
                    # the break
                    brk = -1
                    for i in range(b0, b1):
                        if side == 0:
                            if h[i] > hi:
                                brk = i
                                break
                        else:
                            if l[i] < lo:
                                brk = i
                                break
                    if brk < 0:
                        continue
                    for ri in range(NR):
                        ent = hi - rng * retr[ri] if side == 0 else lo + rng * retr[ri]
                        fill = -1
                        for i in range(brk + 1, b1):
                            if side == 0:
                                if l[i] <= ent:
                                    fill = i
                                    break
                            else:
                                if h[i] >= ent:
                                    fill = i
                                    break
                        if fill < 0:
                            continue
                        for si in range(NS):
                            stp = hi - rng * stopf[si] if side == 0 else lo + rng * stopf[si]
                            risk = ent - stp if side == 0 else stp - ent
                            if risk <= 0:
                                continue
                            cR = cost_pts / risk
                            for ti in range(NT):
                                if tgt[ti] >= 90.0:
                                    tp = 1e18 if side == 0 else -1e18
                                else:
                                    tp = hi + rng * tgt[ti] if side == 0 else lo - rng * tgt[ti]
                                res = 0.0
                                done = False
                                amb = 0
                                if fillbar == 1:
                                    if side == 0:
                                        if l[fill] <= stp:
                                            res = -1.0
                                            done = True
                                    else:
                                        if h[fill] >= stp:
                                            res = -1.0
                                            done = True
                                    if done:
                                        amb = 1
                                for i in range(fill + 1, b1):
                                    if done:
                                        break
                                    if side == 0:
                                        hs = l[i] <= stp
                                        ht = h[i] >= tp
                                    else:
                                        hs = h[i] >= stp
                                        ht = l[i] <= tp
                                    if hs and ht:
                                        amb = 1
                                    if hs:
                                        res = -1.0
                                        done = True
                                        break
                                    if ht:
                                        res = (tp - ent) / risk if side == 0 else (ent - tp) / risk
                                        done = True
                                        break
                                if not done:
                                    px = c[b1 - 1]
                                    res = (px - ent) / risk if side == 0 else (ent - px) / risk
                                g = ((((li * 2 + side) * NR + ri) * NS + si) * NT + ti) * NFL + fl
                                outR[d, g] = res - cR
                                outAmb[d, g] = amb


def outcomes(F, cost_pts, fillbar=1):
    """R per (day, geometry) with NaN where no trade happened. Geometry index packs
    (ib length, side, retracement, stop, target, flatten) in that order."""
    G = len(IB_LEN) * 2 * len(RETR) * len(STOPF) * len(TGT) * len(FLAT)
    outR = np.full((F["D"], G), np.nan)
    amb = np.zeros((F["D"], G), np.int8)
    _walk(F["h"], F["l"], F["c"], F["ibh"], F["ibl"], F["ibe"], F["fend"],
          RETR, STOPF, TGT, float(cost_pts), int(fillbar), outR, amb)
    return outR, amb


def risk_atr(F):
    """Per (day, geometry-within-a-side) the risk IN POINTS and the ATR at the plan bar.

    RANK IN ATR UNITS, NEVER IN R. A configuration can raise its R-multiple simply by putting
    the stop closer to the entry -- at retracement 0.50 with a stop at 0.60 the risk is a TENTH
    of the Initial Balance range, so the same points move scores ten times higher. That is the
    denominator collapse `STUDY_SWEEP_110K.md` caught, and this family reaches it exactly.
    """
    D = F["D"]
    risk = np.full((D, NG), np.nan)
    atr = np.full((D, NG), np.nan)
    for li in range(len(IB_LEN)):
        rng = F["ibh"][:, li] - F["ibl"][:, li]
        for ri in range(len(RETR)):
            for si in range(len(STOPF)):
                w = STOPF[si] - RETR[ri]
                if w <= 0:
                    continue
                gs = li * 450 + ri * 90 + si * 18
                risk[:, gs:gs + 18] = (rng * w)[:, None]
                atr[:, gs:gs + 18] = F["atr"][:, li][:, None]
    return risk, atr


def filters(F):
    """(days, 192) boolean masks per side, side-oriented so higher is always more favourable.

    The volatility reading is the IB range against its own trailing 20-day median, SHIFTED one
    day -- a whole-sample quantile is the leak `STUDY_V50` had to fix.
    """
    D = F["D"]
    out = []
    for side in range(2):
        m = np.zeros((D, NF, len(IB_LEN)), bool)
        for li in range(len(IB_LEN)):
            rng = F["ibh"][:, li] - F["ibl"][:, li]
            base = pd.Series(rng).rolling(20, min_periods=10).median().shift(1).to_numpy()
            ratio = rng / np.where(np.isfinite(base) & (base > 0), base, np.nan)
            cp = F["cpos"][:, li] if side == 0 else 1.0 - F["cpos"][:, li]
            eg = F["ema"][:, li] if side == 0 else -F["ema"][:, li]
            ax = F["adx"][:, li]
            A = [np.ones(D, bool), ax >= 20, ax >= 25, ax <= 20]
            V = [np.ones(D, bool), ratio >= 0.8, ratio >= 1.2, ratio <= 1.2]
            C = [np.ones(D, bool), cp >= 0.6, cp >= 0.5, cp <= 0.4]
            E = [np.ones(D, bool), eg > 0, eg < 0]
            f = 0
            for a in A:
                for v in V:
                    for cc in C:
                        for e in E:
                            m[:, f, li] = a & v & cc & e
                            f += 1
        out.append(m)
    return out


def filter_name(f):
    e = f % len(EMA_MODE); f //= len(EMA_MODE)
    c = f % len(CPOS_MODE); f //= len(CPOS_MODE)
    v = f % len(VOL_MODE); f //= len(VOL_MODE)
    a = f % len(ADX_MODE)
    return dict(adx=ADX_MODE[a], vol=VOL_MODE[v], cpos=CPOS_MODE[c], ema=EMA_MODE[e])


def geom_name(g):
    fl = g % len(FLAT); g //= len(FLAT)
    ti = g % len(TGT); g //= len(TGT)
    si = g % len(STOPF); g //= len(STOPF)
    ri = g % len(RETR); g //= len(RETR)
    side = g % 2; g //= 2
    li = g
    return dict(ib=int(IB_LEN[li]), side="long" if side == 0 else "short", retr=float(RETR[ri]),
                stop=float(STOPF[si]), tgt=float(TGT[ti]), flat=int(FLAT[fl]))
