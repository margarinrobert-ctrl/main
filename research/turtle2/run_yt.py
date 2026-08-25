"""The YouTube Turtle variant: frozen, both take-profit options, in-sample and untouched OOS.

NO PARAMETER IS SEARCHED. Every number is from the video: 20-bar entry, 10-bar stop, 4H 50 EMA,
daily/weekly/monthly majors, targets at 1R/2R/3R.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
import ytdata, ytfilters as Y, original as O

COST_BP = {"XAUUSD": 0.9, "EURUSD": 0.7, "BTC": 11.0, "US30": 0.35, "US100": 0.45, "NQ": 0.4}
SLIP_BP = {"XAUUSD": 1.0, "EURUSD": 0.7, "BTC": 3.0, "US30": 0.5, "US100": 0.6, "NQ": 0.5}


def prep(market, chart):
    b = ytdata.load(market, chart)
    if b is None:
        return None
    h, l, c = b["h"], b["l"], b["c"]
    hi20 = np.roll(O._roll_max(h, 20), 1); hi20[:21] = np.nan
    lo20 = np.roll(O._roll_min(l, 20), 1); lo20[:21] = np.nan
    hi10 = np.roll(O._roll_max(h, 10), 1); hi10[:11] = np.nan
    lo10 = np.roll(O._roll_min(l, 10), 1); lo10[:11] = np.nan
    ema = Y.htf_ema(b["idx"], c, "4H", 50, "closed")
    hi, lo = Y.major_levels(b["idx"], h, l)
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        res_hi = np.nanmin(np.where(hi > c[None, :], hi, np.nan), axis=0)
        res_lo = np.nanmax(np.where(lo < c[None, :], lo, np.nan), axis=0)
    b = dict(b, hi20=hi20, lo20=lo20, hi10=hi10, lo10=lo10, ema=ema,
             res_hi=res_hi, res_lo=res_lo)
    return b


def go(market, chart, mode, block="is", cost_mult=1.0, tol_r=1.0):
    b = prep(market, chart)
    if b is None:
        return None
    cut, _ = ytdata.split(b)
    sl = slice(0, cut) if block == "is" else slice(cut, b["n"])
    import ytturtle as T
    return T.run(b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl],
                 b["start"][sl], b["end"][sl], b["io"], b["ih"], b["il"], b["ic"],
                 b["hi20"][sl], b["lo20"][sl], b["hi10"][sl], b["lo10"][sl],
                 b["ema"][sl], b["res_hi"][sl], b["res_lo"][sl],
                 True, True, mode, COST_BP[market] * cost_mult,
                 SLIP_BP[market] * cost_mult, tol_r)


def stats(R, dirs, why, rr, amb):
    if R is None or len(R) < 20:
        return None
    w = R > 0
    gw = R[w].sum(); gl = -R[~w].sum()
    eq = np.cumsum(R)
    dd = np.maximum.accumulate(eq) - eq
    lg, sh = dirs == 1, dirs == -1
    order = np.sort(R)[::-1]
    top5 = order[:max(1, len(R) // 20)].sum()
    return dict(n=len(R), win=100 * w.mean(), expR=R.mean(), pf=gw / gl if gl > 0 else np.inf,
                totalR=R.sum(), maxdd=dd.max() if len(dd) else 0.0,
                sharpe=R.mean() / R.std(ddof=1) * np.sqrt(len(R)) if R.std(ddof=1) > 0 else np.nan,
                long_expR=R[lg].mean() if lg.any() else np.nan,
                short_expR=R[sh].mean() if sh.any() else np.nan,
                mean_rr=rr.mean(), amb=100 * amb.mean(),
                top5=top5 / gw if gw > 0 else np.nan)


HDR = (f"  {'':<22}{'n':>7}{'win%':>7}{'E[R]':>9}{'PF':>7}{'totR':>9}{'maxDD':>8}"
       f"{'longR':>8}{'shortR':>8}{'avgRR':>7}{'amb%':>7}")


def line(tag, s):
    if s is None:
        print(f"  {tag:<22}   too few trades"); return
    print(f"  {tag:<22}{s['n']:>7}{s['win']:>7.1f}{s['expR']:>+9.3f}{s['pf']:>7.2f}"
          f"{s['totalR']:>9.1f}{s['maxdd']:>8.1f}{s['long_expR']:>+8.3f}"
          f"{s['short_expR']:>+8.3f}{s['mean_rr']:>7.2f}{s['amb']:>7.2f}")


def pooled(chart, mode, block, cost_mult=1.0):
    R = []; D = []; W = []; RR = []; A = []
    for m in ytdata.BASE:
        r = go(m, chart, mode, block, cost_mult)
        if r is None:
            continue
        R.append(r[0]); D.append(r[1]); W.append(r[2]); RR.append(r[3]); A.append(r[4])
    if not R:
        return None
    return stats(np.concatenate(R), np.concatenate(D), np.concatenate(W),
                 np.concatenate(RR), np.concatenate(A))


if __name__ == "__main__":
    print("=" * 100)
    print("YOUTUBE TURTLE -- frozen, nothing optimised")
    print("=" * 100)
    for chart in (15, 60):
        for mode, mname in ((1, "Option 1: fixed R:R by resistance"),
                            (2, "Option 2: scale out thirds 1R/2R/3R")):
            print(f"\n{chart}m chart -- {mname}")
            print(HDR)
            for blk in ("is", "oos"):
                t = "in-sample" if blk == "is" else "OUT-OF-SAMPLE"
                line(f"pooled, {t}", pooled(chart, mode, blk))
            for m in ytdata.BASE:
                r = go(m, chart, mode, "oos")
                if r is None:
                    continue
                line(f"  {m}, OOS", stats(*r[:5]))


# --------------------------------------------------------------------- controls
def random_entry(market, chart, mode, block="is", seed=0, cost_mult=1.0):
    """The same trade management with a RANDOM entry bar, filters kept.

    `STUDY_TURTLE.md` established the decisive test for a breakout system on this branch: a
    coin-flip entry with the same exits scored +0.601 against the breakout's +0.595. The control
    keeps the 4H EMA filter, the avoid-resistance rule, the 10-bar stop and the R:R ladder, and
    replaces ONLY the channel trigger -- so what it isolates is the breakout itself.

    Implemented by rewriting the trigger levels: a chosen long bar gets an unreachable-low `hi20`
    so the entry condition is satisfied there and nowhere else.

    !! THIS CONTROL IS NOT VALID AS WRITTEN AND ITS OUTPUT MUST NOT BE REPORTED. !!

    Measured on US30 60m: the 10-bar-channel stop sits a median 0.693% of price away at a BREAKOUT
    bar and only 0.372% at a RANDOM bar, and 6.8% of random bars have less than a TENTH of the
    breakout median. A near-zero risk denominator turns any adverse move into an enormous
    R-multiple, which is why this printed control means of -0.97 to -2.08 R -- arithmetically
    impossible for a stop-loss system and a clear sign the control, not the market, produced them.

    A breakout bar is BY CONSTRUCTION at the top of its recent range, so the channel stop is far;
    a random bar is not. The control therefore compares two different geometries and measures the
    stop placement rather than the entry.

    THE FIX, not yet applied: match the RISK DISTRIBUTION, not just the exits -- either draw random
    entries only from bars whose channel risk falls inside the rule's own observed range, or give
    both the rule and the control an ATR-based stop so the denominator cannot collapse. Until then
    the breakout remains UNTESTED against a random entry on this variant.
    """
    b = prep(market, chart)
    if b is None:
        return None
    cut, _ = ytdata.split(b)
    sl = slice(0, cut) if block == "is" else slice(cut, b["n"])
    n = len(b["c"][sl])
    real = go(market, chart, mode, block, cost_mult)
    if real is None or len(real[0]) < 20:
        return None
    want = len(real[0])
    frac_long = float((real[1] == 1).mean())
    rng = np.random.default_rng(seed)
    pick = rng.choice(np.arange(30, n - 2), size=min(want * 3, n - 40), replace=False)
    side = np.where(rng.random(len(pick)) < frac_long, 1, -1)
    hi20 = np.full(n, np.inf); lo20 = np.full(n, -np.inf)
    hi20[pick[side == 1]] = -1e18
    lo20[pick[side == 1]] = -1e18
    lo20[pick[side == -1]] = 1e18
    hi20[pick[side == -1]] = 1e18
    import ytturtle as T
    return T.run(b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl],
                 b["start"][sl], b["end"][sl], b["io"], b["ih"], b["il"], b["ic"],
                 hi20, lo20, b["hi10"][sl], b["lo10"][sl],
                 b["ema"][sl], b["res_hi"][sl], b["res_lo"][sl],
                 True, True, mode, COST_BP[market] * cost_mult,
                 SLIP_BP[market] * cost_mult, 1.0)


def control_pooled(chart, mode, block, draws=8):
    out = []
    for s in range(draws):
        R = []
        for m in ytdata.BASE:
            r = random_entry(m, chart, mode, block, seed=s)
            if r is not None and len(r[0]):
                R.append(r[0])
        if R:
            out.append(np.concatenate(R).mean())
    return np.array(out)
