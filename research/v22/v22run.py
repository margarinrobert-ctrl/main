"""Does a volatility state forecast chop, and does it tell you where to put the stop?

PART A is a FORECASTING test, not a backtest. Every feature is scored by its information
coefficient against the forward efficiency ratio, with Newey-West standard errors because the label
overlaps -- consecutive bars share most of their forward window, so a naive t is inflated by roughly
the square root of the horizon. Benjamini-Hochberg is applied across the whole family and the
expected number of chance passes is printed beside the observed one.

PART B does not optimise anything. It asks what the MAE and MFE distribution of real trades looks
like inside each volatility decile, in ATR units. If those quantiles are flat across deciles then an
ATR-sized stop is ALREADY volatility-adaptive and scaling it further by a VIX-like state adds
nothing; if they slope, the slope says by how much.
"""
from __future__ import annotations

import math
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
sys.path.insert(0, "research/v22")
import fastbars               # noqa: E402
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v18diag as G           # noqa: E402
import v22vol as V            # noqa: E402

TFS = (15, 30)
HS = (12, 24, 48)


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


def bh(p, q=0.10):
    p = np.asarray(p, float)
    o = np.argsort(p)
    m = len(p)
    below = p[o] <= q * np.arange(1, m + 1) / m
    out = np.zeros(m, bool)
    if below.any():
        out[o[:np.max(np.flatnonzero(below)) + 1]] = True
    return out


def hdr(t):
    print("\n" + "=" * 120)
    print(t)
    print("=" * 120)


if __name__ == "__main__":
    rows = []
    for tf in TFS:
        b = fastbars.bars(tf)
        F = V.build(b["o"], b["h"], b["l"], b["c"])
        res, lock = blocks(b["sess"])
        for h in HS:
            y = V.forward_er(b["c"], h)
            for name, x in F.items():
                r_r, t_r, n_r = G.nw_corr(x[res], y[res], lag=max(2, h))
                r_l, t_l, n_l = G.nw_corr(x[lock], y[lock], lag=max(2, h))
                if not np.isfinite(r_r):
                    continue
                fam = ("chop ratio" if "_cc" in name and name.startswith(("park", "rs", "gk"))
                       else "term structure" if name.startswith("ts_")
                       else "state" if name.startswith(("pct", "z_"))
                       else "vol of vol" if name.startswith(("vov", "accel"))
                       else "semivariance" if name.startswith("semi")
                       else "level")
                rows.append(dict(tf=tf, h=h, feat=name, family=fam,
                                 ic=r_r, t=t_r, n=n_r, ic_lk=r_l, t_lk=t_l))
    df = pd.DataFrame(rows)
    df["p"] = 2 * (1 - pd.Series(np.abs(df.t)).apply(
        lambda z: 0.5 * (1 + math.erf(z / np.sqrt(2)))))
    df["bh"] = bh(df.p.to_numpy(), 0.10)
    df["same_sign"] = np.sign(df.ic) == np.sign(df.ic_lk)
    df.to_csv("results/v22/v22_ic.csv", index=False)

    hdr("A. DOES A VOLATILITY STATE FORECAST CHOP? -- IC against the forward efficiency ratio")
    print(f"   {len(df)} tests = 71 features x {len(HS)} horizons x {len(TFS)} timeframes.")
    print(f"   At alpha 0.05, {0.05*len(df):.0f} pass by chance. Observed p <= 0.05: "
          f"{int((df.p <= 0.05).sum())}.   Surviving Benjamini-Hochberg at q 0.10: {int(df.bh.sum())}.")
    print(f"   Largest |IC| anywhere: {df.ic.abs().max():.4f}   median |IC|: {df.ic.abs().median():.4f}")
    print(f"   Of the survivors, {float(df[df.bh].same_sign.mean()):.0%} keep their SIGN on the "
          f"locked block (chance is 50%).")
    print(f"   Correlation between a feature's research IC and its locked IC: "
          f"{np.corrcoef(df.ic, df.ic_lk)[0,1]:+.3f}")

    hdr("B. THE TOP 50 BY |IC| -- research rank, locked read attached")
    print("   A positive IC means the feature is HIGH when the next h bars TREND. Negative means")
    print("   high when they CHOP. Both are usable; the sign has to be stable to be usable.\n")
    top = df.reindex(df.ic.abs().sort_values(ascending=False).index).head(50)
    print(f"   {'#':>3} {'feature':<18}{'family':<16}{'tf':>4}{'h':>4}{'IC':>9}{'NW t':>8}"
          f"{'BH':>4}{'|':>3}{'LOCK IC':>10}{'LOCK t':>8}{'sign':>6}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"   {i:>3} {r.feat:<18}{r.family:<16}{r.tf:>3}m{r.h:>4}{r.ic:>+9.4f}{r.t:>+8.2f}"
              f"{('Y' if r.bh else '.'):>4}{'|':>3}{r.ic_lk:>+10.4f}{r.t_lk:>+8.2f}"
              f"{('same' if r.same_sign else 'FLIP'):>6}")
    print(f"\n   Of these 50, {int(top.same_sign.sum())} keep their sign out of sample.")

    hdr("C. BY FAMILY -- median |IC|, never the best member")
    g = df.groupby("family").agg(tests=("ic", "size"), med_abs=("ic", lambda x: float(np.abs(x).median())),
                                 best=("ic", lambda x: float(np.abs(x).max())),
                                 bh=("bh", "sum"), sign=("same_sign", "mean"))
    print(f"   {'family':<18}{'tests':>7}{'median |IC|':>14}{'best |IC|':>12}{'BH':>6}{'sign kept':>12}")
    for k, r in g.sort_values("med_abs", ascending=False).iterrows():
        print(f"   {k:<18}{int(r.tests):>7}{r.med_abs:>14.4f}{r.best:>12.4f}{int(r.bh):>6}"
              f"{r.sign:>11.0%}")
