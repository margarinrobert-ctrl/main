"""M6 -- THE ONE AXIS WITH A GRADIENT: the volume multiple, tested properly.

M2's marginals found `vol_mult` monotone toward HIGHER on BOTH feeds and, unusually, on BOTH
BLOCKS -- US100 locked -0.051 -> +0.013 and US30 locked -0.016 -> +0.068 as the multiple rises
from ~1.0 to ~2.4 -- and fANOVA gave it 0.40-0.46 of the objective on US30 and 0.22-0.43 on US100.
On GOLD the same axis was the one component that carried information on research and then INVERTED
(`STUDY_VWAP_EMA_GOLD` section 8: Spearman +1.000 research, -0.900 locked). So it gets the test the
branch requires rather than another marginal:

  * the ladder run on every feed and BOTH blocks, with the rung's own selectivity reported;
  * each rung against a RANDOM FILTER KEEPING THE SAME NUMBER of the un-gated rule's signal bars,
    re-simulated end to end (a veto releases the position lock and admits later signals -- filter
    the TRIGGERS and re-simulate, STUDY_AUCTION);
  * the same ladder on US30_ISO, the reserved forward block;
  * and the obvious confound named and measured: a volume spike is not independent of the bar's
    range, so the ladder is also run with C6 (the range condition) removed.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

RNG = np.random.default_rng(777)
pd.set_option("display.width", 235)
print(__doc__)
MK = ("US100", "US30", "US30_ISO")
DS = {k: M.build(k) for k in MK}
RUNGS = (0.8, 1.0, 1.1, 1.3, 1.6, 2.0, 2.4)
L = lambda s: print("\n" + "=" * 118 + f"\n{s}\n" + "=" * 118)


def sig_of(mk, side, vol_mult, drop_c6=False):
    D = DS[mk]
    p = {**V.PARAMS, "vol_mult": vol_mult}
    if drop_c6:
        p["range_mult"] = 0.0
    s, _ = V.triggers(D, side=side, p=p)
    return s, p


def rnd_filter(mk, base_sig, keep_n, side, p, blk, draws=250):
    """A random filter of the SAME selectivity, applied to the un-gated rule's own signal bars and
    RE-SIMULATED, so the position lock behaves as it does for the real gate."""
    D = DS[mk]
    idx = np.flatnonzero(base_sig)
    if len(idx) == 0 or keep_n <= 0:
        return np.zeros(0)
    rate = min(1.0, keep_n / len(idx))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool)
        g[idx[RNG.random(len(idx)) < rate]] = True
        t = M.run(D, g, side=side, tgt_R=3.0, p=p)
        t = t if blk is None else t[t.blk == blk]
        if len(t) >= 15:
            out.append(t.R.mean())
    return np.array(out)


for drop in (False, True):
    L(f"M6.{1 if not drop else 2}  THE VOLUME LADDER"
      f"{'  (C6 range condition REMOVED -- the confound named)' if drop else ''}")
    rows = []
    for mk in MK:
        D = DS[mk]
        for side, sn in ((1, "LONG"), (-1, "SHORT")):
            base_sig, basep = sig_of(mk, side, 0.0, drop_c6=drop)   # vol_mult 0 => C5 always true
            for vm in RUNGS:
                s, p = sig_of(mk, side, vm, drop_c6=drop)
                t = M.run(D, s, side=side, tgt_R=3.0, p=p)
                blocks = ((None, "whole"),) if mk == "US30_ISO" else ((0, "research"), (1, "LOCKED"))
                for blk, bn in blocks:
                    tb = t if blk is None else t[t.blk == blk]
                    st = V.stats(tb)
                    if st["n"] < 15:
                        continue
                    ctl = rnd_filter(mk, base_sig, st["n"], side, p, blk)
                    keep = 100.0 * s.sum() / max(base_sig.sum(), 1)
                    rows.append(dict(feed=mk, side=sn, block=bn, vol_mult=vm,
                                     keep_pct=round(keep, 1), n=st["n"], R=round(st["R"], 4),
                                     pct=round(st["pct"], 4), pf=round(st["pf"], 3),
                                     ctl_R=round(float(np.median(ctl)), 4) if len(ctl) else np.nan,
                                     p_ctl=round(float((ctl >= st["R"]).mean()), 3) if len(ctl) else np.nan))
    Lad = pd.DataFrame(rows)
    print(Lad.to_string(index=False))
    Lad.to_csv(f"results/vwapema/m6_ladder{'_noc6' if drop else ''}.csv", index=False)
    print("\nSpearman(vol_mult, R) per feed x side x block:")
    for (f2, s2, b2), g in Lad.groupby(["feed", "side", "block"]):
        if len(g) >= 4:
            print(f"  {f2:9s} {s2:5s} {b2:8s}  rho {g.vol_mult.corr(g.R, method='spearman'):+.3f}"
                  f"   n rungs {len(g)}  R {g.R.min():+.3f}..{g.R.max():+.3f}")
