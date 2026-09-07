"""Robustness of the SMC failure, and a direct anomaly hunt on the events themselves.

Two things the model run could not tell us:

  ROBUSTNESS   the failure rested on ONE barrier (+/-1xATR, 60 bars). Cost was 8.4% of risk there.
               A wider barrier cuts the cost fraction proportionally, so the honest question is
               whether the result is a property of SMC or a property of that one geometry.

  ANOMALIES    a gradient booster reported that volatility and time-of-day mattered more than any
               SMC concept, but it cannot say WHICH events pay. This tests each event directly:
               given a BOS / CHoCH / sweep / FVG / order-block touch, what happens next, in dollars,
               with Newey-West t-statistics and Benjamini-Hochberg control across every test.

Usage: python3 research/smc_events.py
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from scipy import stats as st

sys.path.insert(0, "research")
import smc
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice
from smc_ml import ROUND_TURN_PTS, POINT_VALUE, triple_barrier

RTH_START, RTH_END = 570, 960


def newey_west_t(x: np.ndarray, lag: int | None = None) -> float:
    x = np.asarray(x, float)
    n = len(x)
    if n < 10:
        return np.nan
    if lag is None:
        lag = max(1, int(round(4 * (n / 100) ** (2 / 9))))
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


def bh(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * m / (rank + 1))
        q[i] = prev
    return q


def hac_ols_diff(y: np.ndarray, dummy: np.ndarray, lag: int) -> tuple[float, float]:
    """Difference in means (event minus non-event) with a Newey-West HAC standard error.

    This is the test Part B does NOT do. Part B asks "is the event's dollar mean different from
    zero", and the answer is always no-because-of-costs: the round turn is charged to every arm
    equally, so a coin flip with a spread reports a huge negative t at this sample size and says
    nothing about the event. Regressing the outcome on an event dummy differences the cost out and
    asks the only question that matters -- does the event pay MORE than not-the-event.

    The barrier horizon makes neighbouring observations overlap for up to `max_bars` bars, so the
    HAC lag has to cover that overlap or the standard error is a fiction.
    """
    X = np.column_stack([np.ones(len(y)), dummy.astype(float)])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    u = y - X @ beta
    ux = X * u[:, None]
    S = ux.T @ ux
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        G = ux[k:].T @ ux[:-k]
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(max(V[1, 1], 0.0))
    return float(beta[1]), float(beta[1] / se) if se > 0 else np.nan


def load(pivot_k=3, atr_len=30):
    seg = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    mso = minutes_since_open(minute_of_day(seg.index), RTH_START).astype(np.int64)
    atr = smc.atr_series(h, l, c, atr_len)
    ph, pl, phi, pli = smc.swing_pivots(h, l, pivot_k)
    bos, choch, bias, sbos, schoch = smc.structure(c, ph, pl)
    dup, sup, ddn, sdn = smc.fair_value_gaps(h, l, atr)
    sweep, ssweep = smc.liquidity_sweeps(h, l, c, ph, pl)
    pos = smc.dealing_range(c, ph, pl)
    obd = smc.order_block_distance(o, c, h, l, bos, atr)
    return dict(seg=seg, o=o, h=h, l=l, c=c, sess=sess, mso=mso, atr=atr,
                bos=bos, choch=choch, bias=bias, sweep=sweep, pos=pos, obd=obd,
                dup=dup, ddn=ddn, sbos=sbos, schoch=schoch, ssweep=ssweep)


def outcomes(d, mult, max_bars):
    """Signed dollar outcome of taking each bar LONG and each bar SHORT under the barrier."""
    lab, rr, xb = triple_barrier(d["h"], d["l"], d["c"], d["sess"], d["atr"], mult, max_bars)
    risk = mult * d["atr"]
    long_d = rr * risk * POINT_VALUE - ROUND_TURN_PTS * POINT_VALUE
    short_d = -rr * risk * POINT_VALUE - ROUND_TURN_PTS * POINT_VALUE
    valid = np.isfinite(rr) & (xb > 0) & np.isfinite(risk) & (risk > 0)
    return long_d, short_d, valid, risk, xb


def main() -> None:
    d = load()
    n = len(d["c"])
    cut = int(n * 0.8)

    # ---------------------------------------------------------------------------------------
    print("=" * 104)
    print("A. ROBUSTNESS — is the failure a property of SMC, or of one barrier geometry?")
    print("=" * 104)
    print("\n  A symmetric barrier is a coin by construction; what changes with width is only how")
    print("  much of the move the round turn eats. If no width helps, cost is not the binding issue.\n")
    print(f"  {'barrier':>10}{'bars':>7}{'n':>10}{'up first':>10}{'median risk':>13}{'cost/risk':>11}"
          f"{'long $/trade':>14}{'short $/trade':>15}")
    for mult in (0.5, 1.0, 2.0, 3.0):
        for mb in (60, 240):
            ld, sd, ok, risk, xb = outcomes(d, mult, mb)
            lab, rr, _ = triple_barrier(d["h"], d["l"], d["c"], d["sess"], d["atr"], mult, mb)
            up = (rr[ok] > 0).mean()
            mr = np.median(risk[ok]) * POINT_VALUE
            print(f"  {f'+/-{mult}xATR':>10}{mb:>7}{ok.sum():>10,}{100*up:>9.2f}%{mr:>12,.0f}"
                  f"{100*ROUND_TURN_PTS*POINT_VALUE/mr:>10.1f}%{ld[ok].mean():>14.2f}{sd[ok].mean():>15.2f}")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 104)
    print("B. ANOMALY HUNT — which SMC events actually predict anything?")
    print("=" * 104)
    MULT, MAXB = 2.0, 120     # widest sensible barrier: lowest cost drag of those tested
    ld, sd, ok, risk, xb = outcomes(d, MULT, MAXB)
    print(f"\n  barrier +/-{MULT}xATR, {MAXB} bars. Every event tested LONG and SHORT separately;")
    print(f"  Benjamini-Hochberg applied across all tests; research = first 80%, holdout = last 20%.\n")

    ev = {}
    ev["BOS up"] = d["bos"] == 1
    ev["BOS down"] = d["bos"] == -1
    ev["CHoCH up"] = d["choch"] == 1
    ev["CHoCH down"] = d["choch"] == -1
    ev["sweep bullish (lows taken)"] = d["sweep"] == 1
    ev["sweep bearish (highs taken)"] = d["sweep"] == -1
    ev["BOS up, fresh (<10 bars)"] = (d["bias"] == 1) & (d["sbos"] < 10)
    ev["BOS down, fresh (<10 bars)"] = (d["bias"] == -1) & (d["sbos"] < 10)
    ev["discount (<0.25 of range)"] = d["pos"] < 0.25
    ev["premium (>0.75 of range)"] = d["pos"] > 0.75
    ev["at order block (<0.25 ATR)"] = np.abs(d["obd"]) < 0.25
    ev["bull FVG just below (<0.5 ATR)"] = d["dup"] < 0.5
    ev["bear FVG just above (<0.5 ATR)"] = d["ddn"] < 0.5
    ev["sweep + CHoCH agree (bull)"] = (d["ssweep"] < 20) & (d["sweep"] == 1) & (d["choch"] == 1)
    ev["sweep + CHoCH agree (bear)"] = (d["ssweep"] < 20) & (d["sweep"] == -1) & (d["choch"] == -1)
    ev["discount + bull BOS"] = (d["pos"] < 0.35) & (d["bias"] == 1)
    ev["premium + bear BOS"] = (d["pos"] > 0.65) & (d["bias"] == -1)

    rows = []
    for name, mask in ev.items():
        for side, pnl in (("long", ld), ("short", sd)):
            m = mask & ok & np.isfinite(pnl)
            if m.sum() < 200:
                continue
            idx = np.where(m)[0]
            x = pnl[idx]
            t = newey_west_t(x, lag=MAXB)
            if not np.isfinite(t):
                continue
            r_m = idx < cut
            rows.append(dict(event=name, side=side, n=int(m.sum()), mean=x.mean(),
                             t=t, p=2 * (1 - st.norm.cdf(abs(t))),
                             res=x[r_m].mean() if r_m.sum() > 50 else np.nan,
                             hold=x[~r_m].mean() if (~r_m).sum() > 50 else np.nan))
    df = pd.DataFrame(rows)
    df["q"] = bh(df.p.to_numpy())
    df = df.sort_values("p")
    print(f"  {'event':<34}{'side':>6}{'n':>8}{'$/trade':>10}{'t':>8}{'p':>8}{'q':>8}{'research':>11}{'holdout':>10}")
    for _, r in df.iterrows():
        star = "  *" if r.q < 0.10 else ""
        print(f"  {r.event:<34}{r.side:>6}{int(r.n):>8,}{r['mean']:>10.2f}{r.t:>8.2f}{r.p:>8.3f}{r.q:>8.3f}"
              f"{r.res:>11.2f}{r.hold:>10.2f}{star}")

    surv = df[df.q < 0.10]
    print(f"\n  {len(surv)} of {len(df)} tests survive FDR at q < 0.10")
    if len(surv):
        both = surv[(surv.res * surv.hold > 0) & (surv["mean"] > 0)]
        print(f"  of those, {len(both)} are POSITIVE and hold the same sign in both halves")
        for _, r in both.iterrows():
            print(f"    {r.event} ({r.side}): ${r['mean']:.2f}/trade, research ${r.res:.2f} / holdout ${r.hold:.2f}")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 104)
    print("C. THE TEST THAT ACTUALLY ASKS THE QUESTION — event versus NOT-event")
    print("=" * 104)
    print("\n  Part B charges every arm the same round turn, so at n=100k a costed coin reports t=-5")
    print("  and means nothing. Differencing against the non-event bars removes the cost and leaves")
    print(f"  the lift. HAC lag {MAXB} bars, matching the barrier horizon that makes them overlap.\n")
    base_l, base_s = ld[ok].mean(), sd[ok].mean()
    print(f"  unconditional baseline at this barrier:  long ${base_l:.2f}   short ${base_s:.2f}\n")

    lrows = []
    for name, mask in ev.items():
        for side, pnl in (("long", ld), ("short", sd)):
            m = ok & np.isfinite(pnl)
            if (mask & m).sum() < 200:
                continue
            idx = np.where(m)[0]
            y = pnl[idx]
            dmy = mask[idx]
            lift, t = hac_ols_diff(y, dmy, MAXB)
            if not np.isfinite(t):
                continue
            r = idx < cut
            lr, _ = hac_ols_diff(y[r], dmy[r], MAXB) if r.sum() > 500 else (np.nan, np.nan)
            hr, _ = hac_ols_diff(y[~r], dmy[~r], MAXB) if (~r).sum() > 500 else (np.nan, np.nan)
            lrows.append(dict(event=name, side=side, n=int((mask & m).sum()), lift=lift, t=t,
                              p=2 * (1 - st.norm.cdf(abs(t))), res=lr, hold=hr,
                              net=(base_l if side == "long" else base_s) + lift))
    lf = pd.DataFrame(lrows)
    lf["q"] = bh(lf.p.to_numpy())
    lf = lf.sort_values("t", ascending=False)
    print(f"  {'event':<34}{'side':>6}{'n':>8}{'lift $':>9}{'t':>7}{'q':>7}{'research':>10}{'holdout':>9}{'net $':>9}")
    for _, r in lf.iterrows():
        star = "  *" if r.q < 0.10 else ""
        print(f"  {r.event:<34}{r.side:>6}{int(r.n):>8,}{r.lift:>9.2f}{r.t:>7.2f}{r.q:>7.3f}"
              f"{r.res:>10.2f}{r.hold:>9.2f}{r.net:>9.2f}{star}")

    sv = lf[lf.q < 0.10]
    print(f"\n  {len(sv)} of {len(lf)} lift tests survive FDR at q < 0.10")
    pos = sv[(sv.lift > 0) & (sv.res > 0) & (sv.hold > 0)]
    print(f"  positive lift, same sign in BOTH halves: {len(pos)}")
    for _, r in pos.iterrows():
        print(f"    {r.event} ({r.side}): +${r.lift:.2f} lift, research +${r.res:.2f} / holdout +${r.hold:.2f}"
              f"  -> net ${r.net:.2f}/trade")
    prof = pos[pos.net > 0]
    print(f"  of those, {len(prof)} clear costs (net > 0)")


if __name__ == "__main__":
    main()
