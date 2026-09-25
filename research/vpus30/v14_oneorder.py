"""V14's US30 short book re-measured with ONE LIVE ORDER, which is what a script can place.

STUDY_V14_WINDOW_GRID's shipped configuration rests a limit 0.75 x ATR(5) above the signal close
with an 8-BAR EXPIRY. STUDY_V34 established that `limit_entry._walk_limit` frees its position lock
only on EXIT, so an unfilled resting order blocks nothing and the next trigger places its own --
a mean of 2.45 live orders at expiry 2 rising to 15.9 at expiry 18. V14 was never re-measured under
the correction. This does it: an unfilled order HOLDS THE LOCK UNTIL IT EXPIRES.

Config, verbatim from the study: Donchian 30 down-breakout, EMA13 < EMA34, ADX >= 22, resting limit
0.75 x ATR(5) above the signal close with an 8-bar expiry, 2.5 x ATR(14) stop, 2R target, 25-bar
exit channel, one unit, entries 07:00-11:00 New York, exits free.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V  # noqa: E402

RT = 2.29


def adx(f, n=14):
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = 1.0 / n
    atr_ = pd.Series(tr).ewm(alpha=a, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr_ > 0, atr_, np.nan)
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean().to_numpy() / np.where(atr_ > 0, atr_, np.nan)
    dx = 100 * np.abs(pdi - ndi) / np.where(pdi + ndi > 0, pdi + ndi, np.nan)
    return pd.Series(dx).ewm(alpha=a, adjust=False).mean().to_numpy()


@njit(cache=True)
def _walk(o, h, l, c, a14, a5, xhi, trig, expiry, lim_mult, stop_mult, tp_r, cost, one_order):
    """side is SHORT throughout. `one_order` 1 = an unfilled order holds the lock (a script),
    0 = it does not (the engine V14 was measured on)."""
    n = len(c)
    eb = np.full(n, -1, np.int64); out = np.empty(n); hl = np.empty(n, np.int64)
    cnt = 0; free = -1
    for i in range(n - 2):
        if trig[i] == 0 or i <= free:
            continue
        if not np.isfinite(a14[i]) or a14[i] <= 0 or not np.isfinite(a5[i]):
            continue
        lim = c[i] + lim_mult * a5[i]
        fill = -1
        for t in range(i + 1, min(i + 1 + expiry, n)):
            if h[t] >= lim:
                fill = t
                break
        if fill < 0:
            if one_order == 1:
                free = i + expiry
            continue
        ent = lim
        risk = stop_mult * a14[i]
        stop = ent + risk
        targ = ent - tp_r * risk
        x = -1; px = 0.0
        for t in range(fill, n):
            if h[t] >= stop:
                x = t; px = stop
                break
            if l[t] <= targ:
                x = t; px = targ
                break
            if t > fill and not np.isnan(xhi[t]) and c[t] > xhi[t]:
                x = t; px = c[t]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        eb[cnt] = fill
        out[cnt] = (ent - px) - cost
        hl[cnt] = x - fill
        cnt += 1
        free = x
    return eb[:cnt], out[:cnt], hl[:cnt]


def main():
    f = V.load()
    f["atr14"] = V.atr(f, 14)
    f["atr5"] = V.atr(f, 5)
    f["adx"] = adx(f)
    f["e13"] = f["close"].ewm(span=13, adjust=False).mean()
    f["e34"] = f["close"].ewm(span=34, adjust=False).mean()
    mod = f.index.hour * 60 + f.index.minute
    dlo = f["low"].rolling(30).min().shift(1)
    xhi = f["high"].rolling(25).max().shift(1)
    trig = ((f["close"] < dlo) & (f["e13"] < f["e34"]) & (f["adx"] >= 22)
            & (mod >= 420) & (mod < 660)).to_numpy().astype(np.int64)
    print(f"US30 15m  bars {len(f):,}  triggers in 07:00-11:00 {int(trig.sum()):,}")

    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    arr = [f[k].to_numpy() for k in ("open", "high", "low", "close")]

    print(f"\n{'engine':<26}{'expiry':>7}{'blk':<10}{'n':>6}{'pts/trade':>11}"
          f"{'PF':>8}{'total':>10}{'hold':>7}")
    res = {}
    for one, nm in ((0, "V14 as measured (book)"), (1, "ONE LIVE ORDER (script)")):
        for exp in (8,):
            eb, r, hl = _walk(*arr, f["atr14"].to_numpy(), f["atr5"].to_numpy(),
                              xhi.to_numpy(), trig, exp, 0.75, 2.5, 2.0, RT, one)
            ts = f.index[eb]
            for bl, sel in (("research", ts < cut), ("HOLDOUT", ts >= cut)):
                x = r[sel]
                if len(x) < 10:
                    continue
                pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)
                print(f"{nm:<26}{exp:>7}{bl:<10}{len(x):>6}{x.mean():>11.2f}"
                      f"{pf:>8.3f}{x.sum():>10.0f}{np.median(hl[sel]) * 15:>7.0f}")
                res[(one, bl)] = (len(x), x.mean(), pf)

    print("\nTHE SIGNATURE STUDY_V34 NAMES: profit rising with resting time at a flat fill rate")
    print(f"{'expiry':>7}{'engine':>10}{'fills':>7}{'fill rate':>11}{'pts/trade':>11}{'$/signal':>10}")
    nsig = int(trig.sum())
    for exp in (2, 4, 8, 12, 18):
        for one, tag in ((0, "book"), (1, "one")):
            eb, r, hl = _walk(*arr, f["atr14"].to_numpy(), f["atr5"].to_numpy(),
                              xhi.to_numpy(), trig, exp, 0.75, 2.5, 2.0, RT, one)
            print(f"{exp:>7}{tag:>10}{len(r):>7}{len(r)/nsig:>11.3f}"
                  f"{r.mean():>11.2f}{r.sum()/nsig:>10.2f}")


if __name__ == "__main__":
    main()
