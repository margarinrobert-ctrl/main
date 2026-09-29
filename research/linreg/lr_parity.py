"""The shipped Pine's own order model and its regression maths, diffed against the engine.

Two things are checked separately, because they fail differently:
  1. THE MATHS. Pine has no residual-sd built-in, so the script writes the loop out using
     `ta.linreg(close, n, k)` == the same fit evaluated k bars back == value - slope*k. This
     reproduces that identity in Python and diffs it against the engine's rolling OLS.
  2. THE ORDER MODEL. The opposite-reading exit fires at the bar's CLOSE in the engine and at the
     NEXT bar's OPEN in a script, which no script can avoid.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from linreg import lrcore as L  # noqa: E402

TF, LN, K, STOP, TP = 60, 50, 2.0, 2.5, 0.0


@njit(cache=True)
def _script(o, h, l, c, at, eu, ed, xu, xd, stop_mult, tp_r, cost):
    n = len(c)
    eb = np.full(n, -1, np.int64); out = np.empty(n)
    cnt = 0; last = -1
    for i in range(1, n - 2):
        if i <= last or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        s = 1 if eu[i] == 1 else (-1 if ed[i] == 1 else 0)
        if s == 0:
            continue
        j = i + 1
        ent = o[j]; risk = stop_mult * at[i]
        stop = ent - s * risk
        targ = ent + s * tp_r * risk if tp_r > 0 else 0.0
        x = -1; px = 0.0
        for t in range(j, n - 1):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if tp_r > 0 and (((h[t] >= targ) if s > 0 else (l[t] <= targ))):
                x = t; px = targ
                break
            if t > j and ((s > 0 and xu[t] == 1) or (s < 0 and xd[t] == 1)):
                x = t + 1; px = o[t + 1]        # the script fills the flip at the NEXT open
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        eb[cnt] = j
        out[cnt] = 100.0 * (s * (px - ent) - cost) / ent
        cnt += 1
        last = x
    return eb[:cnt], out[:cnt]


def main():
    for mk in ("US30L", "US100L", "NQ"):
        f = L.load(mk, TF)
        c = f["close"].to_numpy()
        val, slp, sig = L.ols(c, LN)

        # 1. the script's residual-sd loop, using value - slope*k as the fit k bars back
        sig_s = np.full(len(c), np.nan)
        for i in range(LN - 1, len(c)):
            k = np.arange(LN)
            e = c[i - k] - (val[i] - slp[i] * k)
            sig_s[i] = np.sqrt((e * e).sum() / LN)
        ok = np.isfinite(sig) & np.isfinite(sig_s)
        print(f"{mk:<8} residual sd: max |diff| {np.abs(sig_s[ok]-sig[ok]).max():.3e}   "
              f"corr {np.corrcoef(sig_s[ok], sig[ok])[0,1]:.10f}")

        # 2. the order model
        o, h, l = (f[x].to_numpy() for x in ("open", "high", "low"))
        at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
        rd, _, _, _ = L.readings(f, LN, K, False)
        eu, ed, xu, xd = rd["B channel break"]
        cost = L.COST[mk]
        eb_e, r_e, _, _, _ = L._walk(o, h, l, c, at, mod, eu, ed, xu, xd, 0, STOP, TP, 0, -1, -1, cost)
        eb_s, r_s = _script(o, h, l, c, at, eu, ed, xu, xd, STOP, TP, cost)
        s = np.unique(f.index.normalize())
        cut = pd.Timestamp(s[int(0.75 * len(s))])
        te, ts_ = f.index[eb_e], f.index[eb_s]
        m = pd.DataFrame(dict(b=eb_e, r=r_e)).merge(pd.DataFrame(dict(b=eb_s, rs=r_s)), on="b")
        print(f"{'':8} order model: engine {len(r_e)} script {len(r_s)} "
              f"ratio {len(r_s)/len(r_e):.3f}  shared {len(m)}  corr {m.r.corr(m.rs):.4f}")
        for bl, a, b in (("research", r_e[np.asarray(te < cut)], r_s[np.asarray(ts_ < cut)]),
                         ("HOLDOUT", r_e[np.asarray(te >= cut)], r_s[np.asarray(ts_ >= cut)])):
            gap = (b.sum() - a.sum()) / max(abs(a.sum()), 1e-9) * 100
            print(f"{'':8}   {bl:<9} engine {a.sum():+8.2f}%  script {b.sum():+8.2f}%  gap {gap:+.1f}%")


if __name__ == "__main__":
    main()
