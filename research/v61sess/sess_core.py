"""THE V61 SCRIPT AS THE USER IS RUNNING IT -- session window ON, flatten ON, touch ON.

This is NOT the shipped default and the difference matters, so it is stated before any number:

  * The shipped preset has the SESSION OFF. The user's screenshots show entries restricted to
    07:00-11:00 New York with FLATTEN AT THE STOP TIME ON. This branch has thirteen separate
    measurements that a hard flatten costs money (STUDY_V60: 57-69% of the per-trade result on
    three markets; STUDY_V63: -0.1710 %/trade averaged over seven windows). It is not obviously
    wrong here -- it may be trading a lower drawdown for a lower return, which is a real choice --
    but it has to be MEASURED rather than assumed either way.

  * ON A 15-MINUTE CHART THE INCUMBENT PRESET IS A DIFFERENT STRATEGY. The order-flow settings are
    declared in MINUTES and converted by the chart timeframe, so k3/w20 on 30m bars (90 / 600
    minutes) becomes k6/w40 on 15m -- the same TIME reach. But the entry and exit channels are in
    BARS, so 20/20 on 15m is HALF the time reach of 20/20 on 30m. "15m looks better" is therefore a
    comparison between two different rules, not two views of one.

  * THE CVD IS COARSER AT 15m TOO: 15 one-minute sub-bars a bar against 30 at 30m.

THE ORDER MODEL IS THE SCRIPT'S, not the research engine's:
  - entry on a TOUCH of the entry channel (>=), at the next bar's open;
  - ATR frozen at the SIGNAL bar; a fill-relative bracket live from the fill (the V56 fix);
  - then max(fill stop, prior-bar exit channel) capped at the previous close;
  - the flatten uses `strategy.close_all()` on the first bar OUTSIDE the window, which fills at the
    NEXT bar's open -- one bar later than "flat at the 11:00 open". That is what the script does, so
    it is what is modelled; STUDY_V60 records the earlier-submission alternative.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v53", "research/v54", "research/v61"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import v53abs as A       # noqa: E402
import v54cvd as C       # noqa: E402

COST, SLIP, SPLIT = 0.72, 0.25, 0.65


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(tf, path="data/NQ_1m.csv", ent_max=80, ex_max=80):
    f1 = A.load_1m(os.path.join(ROOT, path))
    cvd1 = C.cvd_1m(f1)
    g = A.resample(f1, tf)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = g["volume"].to_numpy(float)
    ix = pd.DatetimeIndex(g.index)
    n = len(c)
    cv = C.cvd_on(f1, cvd1, tf).reindex(ix).ffill().to_numpy()
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    D = dict(tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, cv=cv, atr=_atr(h, l, c),
             day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
    sh, sl = pd.Series(h), pd.Series(l)
    D["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, ent_max + 1)])
    D["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, ex_max + 1)])
    us = np.unique(D["day"])
    D["cut_day"] = int(us[int(SPLIT * len(us))])
    D["blk"] = (D["day"] >= D["cut_day"]).astype(np.int64)     # 0 research, 1 locked
    D["last_bar"] = n - max(200, 20000 // tf)
    return D


def gate(D, piv_min, win_min):
    """EXHAUSTED SELLERS -- price lower low with CVD higher low at a CONFIRMED pivot -- fired within
    the last `win_min` minutes. The two settings are in MINUTES and converted by the timeframe,
    exactly as the script does it."""
    tf = D["tf"]
    k = max(1, int(round(piv_min / tf)))
    w = max(1, int(round(win_min / tf)))
    P = C.patterns(D["h"], D["l"], D["cv"], k, D["n"])
    return (pd.Series(P[0].astype(float)).rolling(w).max().to_numpy() > 0), k, w


@njit(cache=True)
def _walk(o, h, l, c, atr, mod, ent_hi, ex_lo, g, touch, stop_n, tp_n, hold,
          sess_on, s_start, s_stop, flat_on, cost, slip, first, last_bar):
    m = len(c)
    cap = 20000
    sig = np.zeros(cap, np.int64); xb = np.zeros(cap, np.int64)
    pts = np.full(cap, np.nan); pct = np.full(cap, np.nan); R = np.full(cap, np.nan)
    why = np.zeros(cap, np.int64)
    cnt = 0; busy = -1
    for i in range(first, last_bar):
        if i <= busy or not g[i]:
            continue
        if sess_on == 1:
            mi = mod[i]
            inw = (mi >= s_start and mi < s_stop) if s_start <= s_stop else (mi >= s_start or mi < s_stop)
            if not inw:
                continue
        a = i + 1
        anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0 or not np.isfinite(ent_hi[i]):
            continue
        brk = (h[i] >= ent_hi[i]) if touch == 1 else (h[i] > ent_hi[i])
        if not brk:
            continue
        px = o[a] + slip
        risk = stop_n * anchor
        fixed = px - risk
        tgt = px + tp_n * anchor if tp_n > 0.0 else 1e18
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a; w = 3
        while j <= end:
            lvl = fixed
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cp = c[j - 1]
            if np.isfinite(cp) and lvl > cp:
                lvl = cp
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip; w = 0; break
            if h[j] >= tgt:
                out = (tgt if o[j] < tgt else o[j]) - slip; w = 1; break
            if sess_on == 1 and flat_on == 1:
                mj = mod[j]
                inw = (mj >= s_start and mj < s_stop) if s_start <= s_stop else (mj >= s_start or mj < s_stop)
                if not inw:
                    # strategy.close_all() on bar j fills at the OPEN of bar j+1
                    if j + 1 <= m - 1:
                        out = o[j + 1] - slip; j = j + 1; w = 2; break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] - slip; w = 4
        gross = out - px - cost
        if cnt < cap:
            sig[cnt] = i; xb[cnt] = j; pts[cnt] = gross
            pct[cnt] = 100.0 * gross / px; R[cnt] = gross / risk; why[cnt] = w
            cnt += 1
        busy = j
    return sig[:cnt], xb[:cnt], pts[:cnt], pct[:cnt], R[:cnt], why[:cnt]


def run(D, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600,
        touch=True, sess=False, s_start=7 * 60, s_stop=11 * 60, flat=False,
        cost=COST, slip=SLIP, g=None):
    if g is None:
        g, _k, _w = gate(D, piv_min, win_min)
    ei = int(np.clip(ent, 2, D["ent_hi"].shape[0] + 1)) - 2
    xi = int(np.clip(exN, 2, D["ex_lo"].shape[0] + 1)) - 2
    sig, xb, pts, pct, R, why = _walk(
        D["o"], D["h"], D["l"], D["c"], D["atr"], D["mod"], D["ent_hi"][ei], D["ex_lo"][xi],
        g, 1 if touch else 0, float(stop), float(tp), int(hold),
        1 if sess else 0, int(s_start), int(s_stop), 1 if flat else 0,
        float(cost), float(slip), 1000, int(D["last_bar"]))
    return pd.DataFrame(dict(sig=sig, exit_bar=xb, pts=pts, pct=pct, R=R, why=why,
                             blk=D["blk"][sig], day=D["day"][sig], ts=D["ix"][sig]))


def stats(t, pv=2.0):
    """pv = 2.0 is MNQ. Points x point value; the branch's NQ levels are synthetic so DOLLARS are
    inflated early in the sample -- percent of price and R are not (STUDY_US100)."""
    if len(t) == 0:
        return dict(n=0)
    p = t.pts.to_numpy()
    cum = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    wins = p[p > 0].sum()
    loss = -p[p < 0].sum()
    return dict(n=len(t), pts=float(p.sum()), usd=float(p.sum() * pv), pf=float(wins / max(loss, 1e-9)),
                win=float(100 * (p > 0).mean()), dd_pts=dd, dd_usd=float(dd * pv),
                ret_dd=float(p.sum() / max(dd, 1e-9)), pct=float(t.pct.mean()),
                tot_pct=float(t.pct.sum()), R=float(t.R.mean()),
                sharpe=float(p.mean() / p.std() * np.sqrt(252 * 6.5 * 60 / t.attrs.get("tf", 30) / max(len(t), 1)) if p.std() > 0 else 0.0))
