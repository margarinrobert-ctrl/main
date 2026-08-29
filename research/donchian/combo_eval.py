"""The combined strategy, selected on RESEARCH and evaluated on LOCKED.

Selection criterion, applied to research-block numbers only:
  qualify on MC mean > 0 AND MC PF > 1, then take the highest-mean legs that are
  least correlated with each other.

  NAS|B   MC mean +2.37  PF 1.212   } pairwise research correlation 0.089
  US30|D  MC mean +2.52  PF 1.100   } - the two best legs, nearly uncorrelated

PORTFOLIO-2 = NAS|B + US30|D            (max pair r 0.089)
PORTFOLIO-3 = NAS|B + NAS|E + US30|D    (max pair r 0.233, best research Sharpe)

WARNING, recorded before the numbers: this is a SECOND look at the locked block.
The first was the pre-registered 8-comparison reveal. Multiplicity is now higher
than that reveal declared, and these portfolios were assembled AFTER seeing which
legs looked best on research. Treat the locked column as confirmatory only.
"""
import numpy as np, pandas as pd
import lab
from combine import legs, daily, mc_stats

NDRAW = 10000
P2 = ["NAS|B", "US30|D"]
P3 = ["NAS|B", "NAS|E", "US30|D"]

L = legs()
res = daily(L, "res"); lok = daily(L, "lok")

def report(name, cols, M, blk):
    d = M[cols].sum(axis=1)
    net = d.values
    sd = net.std(ddof=1)
    sh = net.mean()/sd*np.sqrt(252) if sd > 0 else 0
    eq = np.cumsum(net); mdd = float((np.maximum.accumulate(eq)-eq).max())
    wn = net[net > 0].sum(); ls = -net[net < 0].sum()
    pf = wn/ls if ls > 0 else np.inf
    r = np.random.default_rng(7)
    bm = net[r.integers(0, len(net), size=(NDRAW, len(net)))].mean(1)
    lo, hi = np.percentile(bm, [2.5, 97.5])
    # trade-level count
    ntr = sum(len(L[c][ "res" if blk=="RESEARCH" else "lok"]) for c in cols)
    print(f"  {name:<12} {blk:<9} days={len(net):>5} trades={ntr:>5} "
          f"mean/day={net.mean():>+7.3f} total={net.sum():>+8.0f} PF={pf:>6.3f} "
          f"Sharpe={sh:>6.2f} MDD={mdd:>7.0f}  boot CI [{lo:>+6.3f},{hi:>+6.3f}] P(>0)={(bm>0).mean():.3f}")
    return dict(name=name, block=blk, days=len(net), trades=ntr, mean=net.mean(),
                total=net.sum(), pf=pf, sharpe=sh, mdd=mdd, lo=lo, hi=hi, ppos=(bm>0).mean())

print("="*126)
print("THE COMBINED STRATEGY - selected on research, then evaluated on the locked block")
print("="*126)
print("  Legs selected on RESEARCH-block Monte Carlo only (mean>0, PF>1), then chosen")
print("  for lowest pairwise correlation among the highest-mean survivors.")
print("    PORTFOLIO-2 = NAS|B + US30|D          research corr 0.089")
print("    PORTFOLIO-3 = NAS|B + NAS|E + US30|D  research max pair corr 0.233")
print("  Equal weight, one contract per leg, aggregated daily. Costs already in each leg.\n")
rows = []
for nm, cols in (("PORTFOLIO-2", P2), ("PORTFOLIO-3", P3)):
    rows.append(report(nm, cols, res, "RESEARCH"))
    rows.append(report(nm, cols, lok, "LOCKED"))
    print()
# single best leg for reference
rows.append(report("NAS|B alone", ["NAS|B"], res, "RESEARCH"))
rows.append(report("NAS|B alone", ["NAS|B"], lok, "LOCKED"))
pd.DataFrame(rows).to_csv("/home/user/main/docs/donchian/combo_eval.csv", index=False)

print("\n" + "="*126)
print("LOCKED-BLOCK CORRELATION of the chosen legs (did the decorrelation hold?)")
print("="*126)
for nm, cols in (("PORTFOLIO-2", P2), ("PORTFOLIO-3", P3)):
    cr = res[cols].corr(); cl = lok[cols].corr()
    m = ~np.eye(len(cols), dtype=bool)
    print(f"  {nm:<12} research max pair r = {cr.values[m].max():.3f}   "
          f"locked max pair r = {cl.values[m].max():.3f}")
print("\n  written: docs/donchian/combo_eval.csv")
