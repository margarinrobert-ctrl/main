"""Re-run the sweep's top configuration on the TRUE INTRADAY PATH before shipping it.

The sweep resolves barriers on chart bars, which is fast enough for 110,250 configurations and is
exactly the resolution `STUDY_ATME_LIVE.md` showed can overstate a barrier system fivefold. This
walks the same configuration bar by bar on the finest series each feed provides, so the entry stop,
the channel stop and the 5R target are ordered by SEQUENCE rather than by rule. Same-bar
stop-and-target is resolved stop-first and counted.

THE CONFIGURATION (top of the sweep by in-sample expectancy):
  1H chart, LONG ONLY
  entry   55-bar Donchian high, stop order
  stop    20-bar Donchian low, FIXED at entry
  target  entry + 5.0 x risk
  filter  close of the prior bar above the 4H 50->100 EMA (EMA period 100)
  avoid   at least 1.0R of clearance to the nearest prior daily/weekly/monthly high
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
sys.path.insert(0, "research/vbt")
import ytdata, ytfilters as Y, original as O
from run_yt import COST_BP, SLIP_BP

CHART, ENT_LEN, STOP_LEN, EMA_P, TP_R, TOL_R = 60, 55, 20, 100, 5.0, 1.0


@njit(cache=True)
def walk(o, h, l, c, start, end, io, ih, il, ic, hi_e, lo_s, ema, res_hi, cost, slip, tol, tp):
    n = len(c); cap = n // 3 + 16
    R = np.zeros(cap); why = np.zeros(cap, np.int64); amb = np.zeros(cap, np.int64)
    bar = np.zeros(cap, np.int64); k = 0
    state = 0; entry = 0.0; stop = 0.0; risk = 0.0
    cf = cost / 1e4; sf = slip / 1e4
    for i in range(n):
        if not (hi_e[i] == hi_e[i]) or not (lo_s[i] == lo_s[i]) or not (ema[i] == ema[i]):
            continue
        s, e = start[i], end[i]
        if e <= s:
            continue
        for j in range(s, e):
            if state == 0:
                if not (c[i - 1] > ema[i]):
                    continue
                if ih[j] < hi_e[i]:
                    continue
                lvl = hi_e[i]
                px = (io[j] if io[j] > lvl else lvl) * (1.0 + cf + sf)
                st = lo_s[i]
                if st >= px:
                    continue
                rk = px - st
                room = res_hi[i] - px
                if room == room and room < tol * rk:
                    continue
                state = 1; entry = px; stop = st; risk = rk
                bar[k] = i
                continue
            tgt = entry + tp * risk
            hs = il[j] <= stop; ht = ih[j] >= tgt
            if hs and ht:
                amb[k] = 1
            if hs:
                px = (io[j] if io[j] < stop else stop) * (1.0 - cf - sf)
                R[k] = (px - entry) / risk; why[k] = 1; k += 1; state = 0
                continue
            if ht:
                px = tgt * (1.0 - cf)
                R[k] = (px - entry) / risk; why[k] = 2; k += 1; state = 0
    if state != 0:
        R[k] = (c[n - 1] * (1.0 - cf - sf) - entry) / risk; why[k] = 3; k += 1
    return R[:k], why[:k], amb[:k], bar[:k]


def prep(market):
    b = ytdata.load(market, CHART)
    if b is None:
        return None
    hi_e = np.roll(O._roll_max(b["h"], ENT_LEN), 1); hi_e[:ENT_LEN + 1] = np.nan
    lo_s = np.roll(O._roll_min(b["l"], STOP_LEN), 1); lo_s[:STOP_LEN + 1] = np.nan
    ema = Y.htf_ema(b["idx"], b["c"], "4H", EMA_P, "closed")
    hi, _lo = Y.major_levels(b["idx"], b["h"], b["l"])
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res_hi = np.nanmin(np.where(hi > b["c"][None, :], hi, np.nan), axis=0)
    return dict(b, hi_e=hi_e, lo_s=lo_s, ema=ema, res_hi=res_hi)


def go(market, block, cost_mult=1.0):
    b = prep(market)
    if b is None:
        return None
    cut, _ = ytdata.split(b)
    sl = slice(0, cut) if block == "is" else slice(cut, b["n"])
    return walk(b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl], b["start"][sl], b["end"][sl],
                b["io"], b["ih"], b["il"], b["ic"], b["hi_e"][sl], b["lo_s"][sl],
                b["ema"][sl], b["res_hi"][sl],
                COST_BP[market] * cost_mult, SLIP_BP[market] * cost_mult, TOL_R, TP_R)


if __name__ == "__main__":
    print("TOP SWEEP CONFIGURATION on the TRUE INTRADAY PATH")
    print(f"  {'':<26}{'n':>7}{'win%':>8}{'E[R]':>9}{'PF':>7}{'totR':>9}{'amb%':>7}")
    for blk in ("is", "oos"):
        Rs = []; As = []
        for m in ytdata.BASE:
            r = go(m, blk)
            if r is None or not len(r[0]):
                continue
            Rs.append(r[0]); As.append(r[2])
        R = np.concatenate(Rs); A = np.concatenate(As)
        gp = R[R > 0].sum(); gl = -R[R <= 0].sum()
        t = "in-sample" if blk == "is" else "OUT-OF-SAMPLE"
        print(f"  pooled, {t:<18}{len(R):>7}{100*(R>0).mean():>8.2f}{R.mean():>+9.3f}"
              f"{gp/gl if gl>0 else 9.99:>7.2f}{R.sum():>9.1f}{100*A.mean():>7.2f}")
    print("\n  per market, OUT-OF-SAMPLE")
    for m in ytdata.BASE:
        r = go(m, "oos")
        if r is None or len(r[0]) < 10:
            continue
        R = r[0]; gp = R[R > 0].sum(); gl = -R[R <= 0].sum()
        print(f"  {m:<26}{len(R):>7}{100*(R>0).mean():>8.2f}{R.mean():>+9.3f}"
              f"{gp/gl if gl>0 else 9.99:>7.2f}{R.sum():>9.1f}{100*r[2].mean():>7.2f}")
