"""ONE read of everything the screen kept: the locked block, and the two markets that chose nothing.

The multiplicity is stated before the numbers, not after.  Whatever survives here is the maximum of
the screen that produced it, so the expected best-of-noise over that many arms is printed beside the
result -- on this branch that comparison has repeatedly been the difference between a finding and
the luckiest draw of a null search.

The neighbourhood is the real evidence.  `STUDY_V17_FEATURES` shipped a condition that was not the
best cell in its pool: it was the only one whose whole ladder was sign-consistent in both
directions, and that gradient reproduced out of sample.  A p-value on one rung is one draw.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_feat as CF                      # noqa: E402
from run_c3 import prep, masks_for, N_DRAW             # noqa: E402

READ = [("NQ", 240), ("US100L", 240), ("US30L", 240)]


def e_max_normal(n):
    """Bailey/Lopez de Prado's expected maximum of n standard normals -- the noise floor a search
    of this size has to clear before its best cell means anything."""
    from scipy.stats import norm
    g = 0.5772156649015329
    return (1 - g) * norm.ppf(1 - 1.0 / n) + g * norm.ppf(1 - 1.0 / (n * np.e))


def read_arm(mkt, tf, arm, cuts, blocks=("A", "B"), n_draw=N_DRAW):
    feat, pol = arm.rsplit(" [", 1)
    pol = pol.rstrip("]")
    d, atr, C, base, cut = prep(mkt, tf)
    F = CF.build(d, atr)
    v = F[feat]
    u = np.unique(v[np.isfinite(v)])
    if len(u) <= 2 and set(u.tolist()) <= {0.0, 1.0}:
        on = np.nan_to_num(v, nan=0.0) > 0.5
    else:
        on = np.nan_to_num(v, nan=-np.inf) >= cuts[feat]
    if pol == "refuse":
        on = ~on
    cost = T.COST[mkt]
    out = []
    for blk in blocks:
        lo, hi = (0, cut) if blk == "A" else (cut, len(d["c"]))
        m0 = base.copy(); m0[:lo] = False; m0[hi:] = False
        tr0 = T.run(d, C, atr, m0, cost)
        tr = T.run(d, C, atr, m0 & on, cost)
        if len(tr) < 10 or not len(tr0):
            out.append(dict(mkt=mkt, tf=tf, arm=arm, block=blk, n=len(tr),
                            pct=np.nan, base=np.nan, p=np.nan))
            continue
        sig0 = T.signal_bars(d, C, m0, atr)
        keep = float(on[sig0].mean()) if len(sig0) else np.nan
        ctl = T.random_gate(d, C, atr, m0, keep, cost,
                            seed=abs(hash((mkt, blk, arm))) % 9999, n_draw=n_draw)
        p0 = tr0["pnl"].to_numpy(float); p1 = tr["pnl"].to_numpy(float)
        out.append(dict(mkt=mkt, tf=tf, arm=arm, block=blk, n=len(tr), n_base=len(tr0),
                        keep=keep, pct=tr["pct"].mean(), base=tr0["pct"].mean(),
                        pf=p1[p1 > 0].sum() / max(-p1[p1 < 0].sum(), 1e-9),
                        pf_base=p0[p0 > 0].sum() / max(-p0[p0 < 0].sum(), 1e-9),
                        tot=tr["pct"].sum(), tot_base=tr0["pct"].sum(),
                        ctl=float(np.median(ctl)), p=T.pval(tr["pct"].mean(), ctl)))
    return pd.DataFrame(out)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    S = json.load(open("research/tcandle/c3_survivors.json"))
    scr = pd.read_csv("research/tcandle/c3_screen.csv")
    n_arms = int((scr.note == "").sum())
    arms = S["survivors"][:6]
    print(f"screened on {S['mkt']} 240m: {n_arms} scorable arms, "
          f"{len(S['survivors'])} cleared p<=0.05 (expected by chance {0.05*n_arms:.1f}), "
          f"{len(S['bh'])} survived BH q=0.10")
    print(f"E[max |t| | pure noise] over {n_arms} arms: {e_max_normal(max(n_arms,2)):.3f}\n")
    if not arms:
        print("NOTHING CLEARED THE SCREEN -- no locked read taken, the block stays unspent.")
        sys.exit(0)
    rows = [read_arm(m, tf, a, S["cuts"]) for a in arms for m, tf in READ]
    df = pd.concat(rows, ignore_index=True)
    df.to_csv("research/tcandle/c4_read.csv", index=False)
    print("=" * 110)
    print("ONE READ -- survivors on the locked block and on the two markets that chose nothing")
    print("=" * 110)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    for a in arms:
        s = df[df.arm == a].dropna(subset=["pct"])
        better = int((s.pct > s.base).sum())
        print(f"\n{a}:  beats its own unfiltered base in {better} of {len(s)} cells; "
              f"clears p<=0.05 in {int((s.p<=0.05).sum())} of {len(s)}; "
              f"total return better in {int((s.tot>s.tot_base).sum())} of {len(s)}")
