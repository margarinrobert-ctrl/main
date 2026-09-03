"""V61 -- the CVD exhausted-sellers rule optimised, with the branch's own guard rails on.

WHAT IS BEING OPTIMISED. `STUDY_V54`/`STUDY_V55`/`STUDY_V56` shipped one cell: NQ 30m, Donchian
20 entry / 20 exit, 2.0 x ATR14 stop, no target, long only, gated on price making a lower low
while the CVD proxy makes a higher low, at pivot half-width k=3 within a 20-bar window. It scores
+0.3051 R research / +0.3125 R locked under the script's own order model. This study asks whether
a better cell exists and what the answer is worth.

THE AXES ARE DECLARED AND EVERY ADDITIVE FILTER IS SOMETHING THIS BRANCH ALREADY MEASURED
ELSEWHERE, so nothing here is a fishing expedition dressed as a search:

  geometry   timeframe 15/30/60, Donchian entry 15/20/30/40/55, channel exit 10/20/30,
             stop 1.5/2.0/2.5/3.0 x ATR14, target none/3/4/6 x ATR, maximum hold 240/480/960 bars
  signal     pivot half-width k 2/3/4/5, recency window w 5/10/20/30/40, plus the CVD gate OFF
             as the ablation that makes the gate's own contribution readable
  filters    MA200 distance (close - SMA200)/ATR >= off/0/1/2   (`STUDY_V40`: the only filter of
             seventeen that earned a place, and it is a FLOOR, not support)
             CHOP(14) <= off/45/40                              (`STUDY_V21`, `STUDY_V39`: the
             best-behaved family on this branch and the only one to clear both blocks)
             close > the prior completed RTH session high        (`STUDY_V17`: the one engineered
             feature that survived, and it is a LEVEL not a trend)
             adaptive stop: the stop tightens by 1.0 ATR when the volatility percentile is above
             its median                                          (`STUDY_V22`, shipped)

  2,073,600 nominal cells a timeframe. Inert combinations are counted, not hidden: with the CVD
  gate OFF the k and w axes collapse to one cell, so the EFFECTIVE count is 5 x 24 x (1 + 20) x
  288 = 725,760 a timeframe and 2,177,280 in total.

HOW IT IS READ. Research only, until a small declared set of finalists is fixed. Grid shape and
the marginal average per axis first -- the top row is the maximum of a million draws and this
branch has been caught reading it before. Then ONE locked read, with the multiplicity stated.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v53", "research/v54", "research/v56"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

TFS = (15, 30, 60)
ENTS = (15, 20, 30, 40, 55)
EXITS = (10, 20, 30)
STOPS = (1.5, 2.0, 2.5, 3.0)
TPS = (0.0, 3.0, 4.0, 6.0)
HOLDS = (240, 480, 960)
ADAPT = (0, 1)                       # 0 fixed stop, 1 tighten by 1.0 ATR above the vol median
KS = (2, 3, 4, 5)
WS = (5, 10, 20, 30, 40)
MA200 = (-99.0, 0.0, 1.0, 2.0)       # -99 = off
CHOPS = (99.0, 45.0, 40.0)           # 99 = off
PSH = (0, 1)

COST, SLIP, SPLIT = 0.72, 0.25, 0.65
# NQ_1m spans 2022-12-26 to 2025-12-11; the split is the first 65% of BARS, so the research block
# is roughly two years and the locked block one.
YEARS = {"res": 1.919, "lock": 1.038}
SHIPPED = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0,
               k=3, w=20, ma=-99.0, chop=99.0, psh=0)


# ------------------------------------------------------------------ indicators
def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _chop(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    s = pd.Series(tr).rolling(n).sum().to_numpy()
    rng = (pd.Series(h).rolling(n).max() - pd.Series(l).rolling(n).min()).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * np.log10(s / rng) / np.log10(n)


def _prior_rth_high(ix, h, mod):
    """The last COMPLETED 09:30-16:00 session's high, frozen at the session end. A LEVEL, so it
    must be knowable at the bar that reads it -- `request.security` on a daily bar returns the
    24-hour futures high and is not this."""
    n = len(h)
    key = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    out = np.full(n, np.nan)
    cur, H, last = -1, -np.inf, np.nan
    for i in range(n):
        if key[i] != cur:
            if H > -np.inf:
                last = H
            cur, H = key[i], -np.inf
        if 570 <= mod[i] < 960:
            H = max(H, h[i])
        out[i] = last
    return out


def build(tf, path="data/NQ_1m.csv"):
    import v53abs as A
    import v54cvd as C
    f1 = A.load_1m(path)
    cvd1 = C.cvd_1m(f1)
    g = A.resample(f1, tf)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    vol = g["volume"].to_numpy(float)          # V62 needs it for the Money Flow Index
    n = len(c)
    ix = g.index
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    atr = _atr(h, l, c)
    cv = C.cvd_on(f1, cvd1, tf).reindex(ix).ffill().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()
    with np.errstate(invalid="ignore"):
        d_ma = (c - sma200) / atr
    ch = _chop(h, l, c)
    psh = _prior_rth_high(ix, h, mod)
    # volatility percentile of ATR/price over its own trailing 250 bars, causal
    ap = pd.Series(atr / c)
    vpct = ap.rolling(250).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True).to_numpy()
    ent_hi = {e: pd.Series(h).rolling(e).max().shift(1).to_numpy() for e in ENTS}
    ex_lo = {e: pd.Series(l).rolling(e).min().shift(1).to_numpy() for e in EXITS}
    pats = {k: C.patterns(h, l, cv, k, n) for k in KS}
    return dict(tf=tf, n=n, o=o, h=h, l=l, c=c, v=vol, atr=atr, ix=ix, mod=mod, cv=cv,
                d_ma=d_ma, chop=ch, psh=psh, vpct=vpct, ent_hi=ent_hi, ex_lo=ex_lo,
                pats=pats, cut=int(SPLIT * n))


# ------------------------------------------------------------------ the exit tensor
@njit(cache=True, parallel=True)
def _tensor(o, h, l, c, atr, rows, exlo, calm, g_e, g_shi, g_slo, g_tp, g_hold, cost, slip, m):
    N = len(rows)
    G = len(g_e)
    xb = np.full((N, G), -1, np.int32)
    R = np.full((N, G), np.nan, np.float32)
    pts = np.full((N, G), np.nan, np.float32)
    for kk in prange(N):
        i = rows[kk]
        a = i + 1
        anchor = atr[i]
        if a < 2 or a >= m - 2 or not np.isfinite(anchor) or anchor <= 0:
            continue
        px = o[a] + slip
        for gg in range(G):
            mult = g_shi[gg] if calm[i] else g_slo[gg]
            risk = mult * anchor
            if risk <= 0:
                continue
            fixed = px - risk
            tgt = px + g_tp[gg] * anchor if g_tp[gg] > 0.0 else 1e18
            end = a + g_hold[gg]
            if end > m - 2:
                end = m - 2
            e = g_e[gg]
            out = np.nan
            j = a
            while j <= end:
                lvl = fixed
                ch = exlo[e, j]
                if np.isfinite(ch) and ch > lvl:
                    lvl = ch
                cap = c[j - 1]
                if np.isfinite(cap) and lvl > cap:
                    lvl = cap
                if l[j] <= lvl:
                    out = (lvl if o[j] > lvl else o[j]) - slip
                    break
                if h[j] >= tgt:
                    out = (tgt if o[j] < tgt else o[j]) - slip
                    break
                j += 1
            if not np.isfinite(out):
                j = end
                out = c[j] - slip
            xb[kk, gg] = j
            R[kk, gg] = (out - px - cost) / risk
            pts[kk, gg] = out - px - cost
    return xb, R, pts


# ------------------------------------------------------------------ the sweep
@njit(cache=True, parallel=True)
def _sweep(offs, vals, sig_bar, xb, R, pts, epx, cut, G):
    S = len(offs) - 1
    stat = np.zeros((S, G, 12), np.float32)
    for s in prange(S):
        a0, a1 = offs[s], offs[s + 1]
        for g in range(G):
            free = -1
            for t in range(a0, a1):
                k = vals[t]
                if xb[k, g] < 0 or not np.isfinite(R[k, g]):
                    continue
                if sig_bar[k] <= free:
                    continue
                free = xb[k, g]
                r = R[k, g]
                pc = 100.0 * pts[k, g] / epx[k]
                b = 0 if sig_bar[k] < cut else 6
                stat[s, g, b + 0] += 1.0
                stat[s, g, b + 1] += r
                stat[s, g, b + 2] += pc
                stat[s, g, b + 5] += pc * pc
                if r > 0:
                    stat[s, g, b + 3] += r
                    stat[s, g, b + 4] += 1.0
    return stat


@njit(cache=True, parallel=True)
def _sweep_loss(offs, vals, sig_bar, xb, R, cut, G):
    """Gross loss per block, kept separate so the profit factor is exact."""
    S = len(offs) - 1
    out = np.zeros((S, G, 2), np.float32)
    for s in prange(S):
        a0, a1 = offs[s], offs[s + 1]
        for g in range(G):
            free = -1
            for t in range(a0, a1):
                k = vals[t]
                if xb[k, g] < 0 or not np.isfinite(R[k, g]):
                    continue
                if sig_bar[k] <= free:
                    continue
                free = xb[k, g]
                r = R[k, g]
                if r <= 0:
                    out[s, g, 0 if sig_bar[k] < cut else 1] += -r
    return out


# ------------------------------------------------------------------ assembling one timeframe
def geometry():
    rows = []
    for ei, e in enumerate(EXITS):
        for st in STOPS:
            for tp in TPS:
                for hd in HOLDS:
                    for ad in ADAPT:
                        rows.append(dict(exN=e, ei=ei, stop=st, tp=tp, hold=hd, adapt=ad,
                                         shi=st, slo=(st - 1.0) if ad else st))
    return pd.DataFrame(rows)


def signal_sets(D):
    """Every (ent, cvd, ma200, chop, psh) combination, as a CSR over the candidate rows.

    The candidate rows are the ent=15 breakout bars: a close above the 55-bar high is also above
    the 15-bar high, so the loosest entry channel is the union of all of them.
    """
    h, n = D["h"], D["n"]
    base = np.asarray(h > D["ent_hi"][min(ENTS)], bool).copy()
    base[:1000] = False
    base[-(max(HOLDS) + 5):] = False
    base &= np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(D["vpct"])
    rows = np.flatnonzero(base)
    ent_m = {e: np.asarray(h[rows] > D["ent_hi"][e][rows], bool) for e in ENTS}
    import v53abs as A
    cvd_m = {(0, 0): np.ones(len(rows), bool)}
    for k in KS:
        es = D["pats"][k][0]
        for w in WS:
            cvd_m[(k, w)] = A.recent(es, w)[rows]
    dm, ch, ps, c = D["d_ma"][rows], D["chop"][rows], D["psh"][rows], D["c"][rows]
    offs = [0]
    vals = []
    keys = []
    for ei, e in enumerate(ENTS):
        for ck in cvd_m:
            for ma in MA200:
                for cp in CHOPS:
                    for pg in PSH:
                        m = ent_m[e] & cvd_m[ck]
                        if ma > -50:
                            m = m & np.isfinite(dm) & (dm >= ma)
                        if cp < 90:
                            m = m & np.isfinite(ch) & (ch <= cp)
                        if pg:
                            m = m & np.isfinite(ps) & (c > ps)
                        idx = np.flatnonzero(m)
                        vals.append(idx)
                        offs.append(offs[-1] + len(idx))
                        keys.append(dict(ent=e, k=ck[0], w=ck[1], ma=ma, chop=cp, psh=pg))
    return rows, np.asarray(offs, np.int64), np.concatenate(vals).astype(np.int64), pd.DataFrame(keys)


def run_tf(D):
    Gd = geometry()
    rows, offs, vals, K = signal_sets(D)
    exlo = np.vstack([D["ex_lo"][e] for e in EXITS])
    calm = np.zeros(D["n"], np.bool_)
    v = D["vpct"]
    calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
    xb, R, pts = _tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo,
                         calm, Gd["ei"].to_numpy(np.int64), Gd["shi"].to_numpy(float),
                         Gd["slo"].to_numpy(float), Gd["tp"].to_numpy(float),
                         Gd["hold"].to_numpy(np.int64), COST, SLIP, D["n"])
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    st = _sweep(offs, vals, rows.astype(np.int64), xb, R, pts, epx, D["cut"], len(Gd))
    ls = _sweep_loss(offs, vals, rows.astype(np.int64), xb, R, D["cut"], len(Gd))
    return dict(G=Gd, K=K, stat=st, loss=ls, rows=rows, xb=xb, R=R, pts=pts, epx=epx,
                offs=offs, vals=vals)


def table(res, tf):
    """One row per (signal set x geometry), research and locked columns."""
    K, Gd, st, ls = res["K"], res["G"], res["stat"], res["loss"]
    S, G, _ = st.shape
    ki = np.repeat(np.arange(S), G)
    gi = np.tile(np.arange(G), S)
    f = st.reshape(S * G, 12)
    lo = ls.reshape(S * G, 2)
    d = pd.DataFrame({
        "n_res": f[:, 0], "R_res": np.where(f[:, 0] > 0, f[:, 1] / np.maximum(f[:, 0], 1), np.nan),
        "pct_res": np.where(f[:, 0] > 0, f[:, 2] / np.maximum(f[:, 0], 1), np.nan),
        "pf_res": np.where(lo[:, 0] > 0, f[:, 3] / np.maximum(lo[:, 0], 1e-9), np.nan),
        "win_res": np.where(f[:, 0] > 0, f[:, 4] / np.maximum(f[:, 0], 1), np.nan),
        "sq_res": f[:, 5],
        "n_lock": f[:, 6], "R_lock": np.where(f[:, 6] > 0, f[:, 7] / np.maximum(f[:, 6], 1), np.nan),
        "pct_lock": np.where(f[:, 6] > 0, f[:, 8] / np.maximum(f[:, 6], 1), np.nan),
        "pf_lock": np.where(lo[:, 1] > 0, f[:, 9] / np.maximum(lo[:, 1], 1e-9), np.nan),
        "win_lock": np.where(f[:, 6] > 0, f[:, 10] / np.maximum(f[:, 6], 1), np.nan),
        "sq_lock": f[:, 11],
    })
    for col in K.columns:
        d[col] = K[col].to_numpy()[ki]
    for col in ("exN", "stop", "tp", "hold", "adapt"):
        d[col] = Gd[col].to_numpy()[gi]
    d["tf"] = tf
    d["cvd"] = np.where(d["k"].to_numpy() == 0, "off", "k" + d["k"].astype(str) + "w"
                        + d["w"].astype(str))
    # An annualised trade Sharpe: (mean / sd) x sqrt(trades a year). It balances per-trade edge
    # against trade count, which neither "total percent" nor "percent per trade" does alone.
    for blk in ("res", "lock"):
        n = d[f"n_{blk}"].to_numpy()
        m = np.nan_to_num(d[f"pct_{blk}"].to_numpy())
        v = d[f"sq_{blk}"].to_numpy() / np.maximum(n, 1) - m ** 2
        sd = np.sqrt(np.maximum(v, 1e-12))
        d[f"sh_{blk}"] = np.where(n > 2, m / sd * np.sqrt(np.maximum(n, 1) / YEARS[blk]), np.nan)
    return d
