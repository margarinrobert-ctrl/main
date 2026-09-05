"""V50 gate 2 and the post-mortem. Reads results/v50/v50_selection.csv, computes nothing new."""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy import stats

RHO_REQ, P_REQ, ABANDON = -0.50, 0.05, -0.30

D = pd.read_csv("results/v50/v50_selection.csv")
tot = len(D)
D = D.dropna(subset=["sel_res", "immed_res", "fill_res"])
inband = D[(D.fill_res >= 0.35 - 0.03) & (D.fill_res <= 0.35 + 0.03)].copy()

print("=" * 100)
print("  THE FILL-RATE CONTROL -- the design fix this round exists to apply")
print("=" * 100)
print(f"  {tot} family-side cells; {len(D)} scorable; {len(inband)} inside the declared 0.35 +/- 0.03 band")
print(f"  achieved fill rate  min {D.fill_res.min():.3f}  max {D.fill_res.max():.3f}  "
      f"sd {D.fill_res.std():.4f}   (V49 left it to fall out at a single 5-min expiry: 0.173)")
print(f"  calibrated expiry   min {int(D.expiry.min())} min  median {int(D.expiry.median())}  "
      f"max {int(D.expiry.max())}")

r = inband
print("\n" + "=" * 100)
print("  RANGE CHECK -- did the independent variable actually vary? (V49's second design fault)")
print("=" * 100)
print(f"  immediacy spans {r.immed_res.min():+.4f} to {r.immed_res.max():+.4f}; "
      f"{int((r.immed_res > 0).sum())} of {len(r)} cells positive   (V49: -0.119..+0.034, 2 of 44)")

def blk(df, x, y, label, seed=3, n=5000):
    a, b = df[x].to_numpy(), df[y].to_numpy()
    rho = stats.spearmanr(a, b).statistic
    rng = np.random.default_rng(seed)
    dr = np.array([stats.spearmanr(rng.permutation(a), b).statistic for _ in range(n)])
    p = float(np.mean(dr <= rho))
    print(f"  {label:<46} rho {rho:+.4f}   permutation p {p:.4f}   n {len(a)}")
    return rho, p

print("\n" + "=" * 100)
print("  GATE 2 -- THE GRADIENT, at matched fill rate, research block")
print("=" * 100)
rho, p = blk(r, "immed_res", "sel_res", "rho(immediacy, SELECTION)")
blk(r, "immed_res", "gap_res", "rho(immediacy, fill-minus-nofill gap)")
blk(r, "fill_res", "sel_res", "rho(fill rate, SELECTION)  [confound check]")
ok = (rho <= RHO_REQ) and (p <= P_REQ)
print(f"\n  pre-registered threshold: rho <= {RHO_REQ} and p <= {P_REQ}  ->  {'PASS' if ok else 'FAIL'}")
print(f"  abandonment condition rho > {ABANDON}  ->  {'TRIGGERED' if rho > ABANDON else 'not triggered'}")

print("\n  WITHIN SIDE -- required, or the gradient is this sample's 89% up-drift")
for s in ("L", "S"):
    sub = r[r.side == s]
    if len(sub) >= 10:
        blk(sub, "immed_res", "sel_res", f"    side {s}")

print("\n  QUINTILES of immediacy (the monotonicity check)")
q = r.assign(qq=pd.qcut(r.immed_res, 5, labels=False, duplicates="drop"))
g = q.groupby("qq").agg(n=("family", "size"), immed=("immed_res", "mean"),
                        sel=("sel_res", "mean"), gap=("gap_res", "mean"),
                        fill=("fill_res", "mean"))
for k, row in g.iterrows():
    print(f"    Q{int(k)+1}  cells {int(row.n):>3}  immediacy {row.immed:+.4f}   "
          f"SELECTION {row.sel:+.4f}   gap {row.gap:+.4f}   fill {row.fill:.3f}")

print("\n" + "=" * 100)
print("  POST-MORTEM -- decomposition of SELECTION itself")
print("=" * 100)
print(f"  SELECTION  mean {r.sel_res.mean():+.4f}  median {r.sel_res.median():+.4f}  "
      f"<0 in {int((r.sel_res < 0).sum())}/{len(r)}")
print(f"  gap        mean {r.gap_res.mean():+.4f}  median {r.gap_res.median():+.4f}  "
      f"<0 in {int((r.gap_res < 0).sum())}/{len(r)}")
print(f"  identity check: SELECTION vs (1-fill)*gap  max abs diff "
      f"{np.abs(r.sel_res - (1 - r.fill_res) * r.gap_res).max():.6f}")
print(f"  market R   mean {r.mkt_res_R.mean():+.4f}   SELECTION as a share of |market R|: "
      f"{r.sel_res.abs().mean() / max(r.mkt_res_R.abs().mean(), 1e-9):.2f}x")

lk = r.dropna(subset=["sel_lk", "immed_lk"])
lk = lk[lk.nf_lk >= 100]
print("\n  LOCKED -- read once, for SIGN only")
if len(lk) >= 10:
    rl = stats.spearmanr(lk.immed_lk, lk.sel_lk).statistic
    print(f"    rho(immediacy, SELECTION) on locked = {rl:+.4f} over {len(lk)} cells   "
          f"sign {'HELD' if np.sign(rl) == np.sign(rho) else 'FLIPPED'}")
    print(f"    SELECTION on locked  mean {lk.sel_lk.mean():+.4f}  "
          f"<0 in {int((lk.sel_lk < 0).sum())}/{len(lk)}")
else:
    print(f"    only {len(lk)} cells clear the locked trade floor -- not read")

print("\n  EXTREMES (immediacy, SELECTION, market R, fill)")
sh = r.sort_values("immed_res")
for _, x in pd.concat([sh.head(4), sh.tail(4)]).iterrows():
    print(f"    {x.family:<18} immed {x.immed_res:+.4f}  SEL {x.sel_res:+.4f}  "
          f"mktR {x.mkt_res_R:+.4f}  fill {x.fill_res:.3f}  expiry {int(x.expiry)}")
