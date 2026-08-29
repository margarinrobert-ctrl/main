"""Runs the VIX study. Four questions, in the order that decides whether the later ones matter."""
from __future__ import annotations

import math
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v18")
sys.path.insert(0, "research/v22")
import v18diag as G           # noqa: E402
import v22vix as X            # noqa: E402

HS = (5, 10, 20)
RUNGS = (10, 20, 30, 40, 50, 60, 70, 80, 90)


def norm_p(t):
    return 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))


def fam(n):
    return ("volatility risk premium" if n.startswith(("vrp",))
            else "realised vol" if n.startswith("rv")
            else "term structure proxy" if n.startswith("vixts")
            else "change" if n.startswith("vix_d") or n == "vix_accel"
            else "vol of vol" if n.startswith("vov")
            else "bar shape" if n in ("vix_range", "vix_barpos", "vix_gap")
            else "level and state")


if __name__ == "__main__":
    d = X.load()
    F = X.features(d)
    c = d.c.to_numpy()
    res, lk = X.blocks(len(d))
    print(f"SPX x VIX daily, {len(d)} sessions {d.Date.min().date()} -> {d.Date.max().date()}")
    print(f"   research {int(res.sum())} sessions to {d.Date[int(res.sum())-1].date()}"
          f"   |  locked {int(lk.sum())} sessions from {d.Date[int(res.sum())].date()}"
          f"  -- CONTAINS THE COVID SHOCK")

    # ---------------------------------------------------------------- A, and its positive control
    rows = []
    for h in HS:
        y_er = X.forward_er(c, h)
        y_vol = X.forward_vol(c, h)
        for name, x in F.items():
            for lab, y in (("chop (forward ER)", y_er), ("forward realised vol", y_vol)):
                g = np.isfinite(x) & np.isfinite(y)
                r_r, t_r, n_r = G.nw_corr(x[g & res], y[g & res], lag=max(2, h))
                r_l, t_l, _ = G.nw_corr(x[g & lk], y[g & lk], lag=max(2, h))
                if not np.isfinite(r_r):
                    continue
                rows.append(dict(target=lab, h=h, feat=name, family=fam(name), ic=r_r, t=t_r,
                                 n=n_r, ic_lk=r_l, t_lk=t_l, p=norm_p(t_r)))
    df = pd.DataFrame(rows)
    df["same_sign"] = np.sign(df.ic) == np.sign(df.ic_lk)
    for lab in df.target.unique():
        df.loc[df.target == lab, "bh"] = X.bh(df[df.target == lab].p.to_numpy(), 0.10)
    df.to_csv("results/v22/v22_vix_ic.csv", index=False)

    X.hdr("A0. THE POSITIVE CONTROL -- does the VIX forecast FORWARD REALISED VOLATILITY?")
    print("   It must. If this table is null the harness is broken and nothing below is readable.\n")
    a0 = df[df.target == "forward realised vol"]
    print(f"   {len(a0)} tests.  p <= 0.05: {int((a0.p<=0.05).sum())} (chance {0.05*len(a0):.0f})."
          f"  BH at q 0.10: {int(a0.bh.sum())}.  Largest |IC| {a0.ic.abs().max():.4f}")
    print(f"   Sign kept on the locked block: {a0[a0.bh].same_sign.mean():.0%}\n")
    top = a0.reindex(a0.ic.abs().sort_values(ascending=False).index).head(8)
    for _, r in top.iterrows():
        print(f"      {r.feat:<16}h={r.h:<4}IC {r.ic:>+7.4f}  t {r.t:>+7.2f}   locked"
              f" {r.ic_lk:>+7.4f}")

    X.hdr("A. DOES THE VIX FORECAST CHOP? -- IC against the forward efficiency ratio on SPX")
    print("   Positive IC = the reading is HIGH before the index TRENDS. Negative = high before it")
    print("   CHOPS. Either is usable; the sign has to survive the locked block to be usable.\n")
    a = df[df.target == "chop (forward ER)"]
    print(f"   {len(a)} tests = 39 features x {len(HS)} horizons x 1 target."
          f"  p <= 0.05: {int((a.p<=0.05).sum())} (chance {0.05*len(a):.0f})."
          f"  BH at q 0.10: {int(a.bh.sum())}")
    print(f"   Largest |IC| anywhere {a.ic.abs().max():.4f}   median |IC| {a.ic.abs().median():.4f}")
    print(f"   Research IC vs locked IC, correlation over all {len(a)} tests:"
          f" {np.corrcoef(a.ic, a.ic_lk)[0,1]:+.3f}")
    print(f"   Of the BH survivors, {a[a.bh].same_sign.mean():.0%} keep their sign out of sample"
          f" (chance is 50%).")

    X.hdr("B. THE TOP 50 READINGS BY |IC| ON RESEARCH -- locked attached, never selected on")
    t50 = a.reindex(a.ic.abs().sort_values(ascending=False).index).head(50)
    print(f"   {'#':>3} {'feature':<16}{'family':<26}{'h':>4}{'IC':>9}{'NW t':>8}{'BH':>4}"
          f"{'|':>3}{'LOCK IC':>10}{'LOCK t':>8}{'sign':>7}")
    for i, (_, r) in enumerate(t50.iterrows(), 1):
        print(f"   {i:>3} {r.feat:<16}{r.family:<26}{r.h:>4}{r.ic:>+9.4f}{r.t:>+8.2f}"
              f"{('Y' if r.bh else '.'):>4}{'|':>3}{r.ic_lk:>+10.4f}{r.t_lk:>+8.2f}"
              f"{('same' if r.same_sign else 'FLIP'):>7}")
    print(f"\n   Of these 50, {int(t50.same_sign.sum())} keep their sign out of sample.")

    X.hdr("C. BY FAMILY -- the marginal average, never the best member")
    g = a.groupby("family").agg(tests=("ic", "size"),
                                med=("ic", lambda x: float(np.abs(x).median())),
                                best=("ic", lambda x: float(np.abs(x).max())),
                                bh=("bh", "sum"), sign=("same_sign", "mean"))
    print(f"   {'family':<26}{'tests':>7}{'median |IC|':>14}{'best |IC|':>12}{'BH':>6}{'sign kept':>12}")
    for k, r in g.sort_values("med", ascending=False).iterrows():
        print(f"   {k:<26}{int(r.tests):>7}{r.med:>14.4f}{r.best:>12.4f}{int(r.bh):>6}{r.sign:>11.0%}")
