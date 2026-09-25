"""O1 -- the FTM alpha.2 port: IS/OOS with the control computed SEPARATELY PER BLOCK.

STUDY_TOP5 recorded the error this study exists to avoid: FTM's published +0.1013 R excess at
p 0.004 was computed over ALL 342 trades, which makes it a research-block statistic. Read on the
147 out-of-sample trades alone it is p 0.152. Every control here is computed inside its own block.

The split is 2025-01-01, which is a calendar boundary rather than a fitted one. CAVEAT THAT STAYS
ATTACHED: this is a POST-HOC split of a sample this branch has already read whole, three times
(STUDY_FTM_ORB_BACKTEST, STUDY_FTM_ANATOMY, STUDY_FTM_ALPHA2). The out-of-sample block is not
virgin; it is the least-contaminated slice available, not a clean holdout.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/ftm")
import numpy as np, pandas as pd
import ftm_sim as FS, ftm_backtest as B

R = "results/ftm2/"; os.makedirs(R, exist_ok=True)
OOS = pd.Timestamp("2025-01-01")
print(__doc__); t0 = time.time()
pd.set_option("display.width", 230); pd.set_option("display.max_columns", 40)
f = FS.load_nq()

def stats(t):
    if len(t) < 5:
        return dict(n=len(t))
    u = t.usd.to_numpy(); r = t.R.to_numpy()
    eq = np.cumsum(u); dd = float((eq - np.maximum.accumulate(eq)).min())
    d = pd.to_datetime(t.time).dt.normalize()
    per_day = t.groupby(d).usd.sum()
    span = (d.max() - d.min()).days / 365.25
    us = np.sort(u)[::-1]; k5 = max(1, int(len(u) * .05))
    return dict(n=len(t), per_yr=len(t) / max(span, .01), net=u.sum(), R=r.mean(),
                usd=u.mean(), pf=u[u > 0].sum() / max(-u[u < 0].sum(), 1e-9),
                win=(u > 0).mean(), dd=dd, ret_dd=u.sum() / max(-dd, 1e-9),
                sharpe=per_day.mean() / per_day.std(ddof=1) * np.sqrt(252) if len(per_day) > 2 else np.nan,
                top5=us[:k5].sum() / u.sum() if u.sum() else np.nan)

print("=" * 132)
print("O1.1  ALPHA.2 AND ITS RC1 PARENT, EACH BLOCK ON ITS OWN")
print("=" * 132)
rows = []
runs = {}
for lab, kw in (("RC1 (prior=2, cap=0)", dict(prior_bars=2, h2_cap=0)),
                ("alpha.2 (prior=1, cap=1)", dict(prior_bars=1, h2_cap=1))):
    _, t = FS.run(verbose=False, **kw)
    t["time"] = pd.to_datetime(t.time)
    runs[lab] = t
    for bl, sub in (("ALL", t), ("in-sample", t[t.time < OOS]), ("OUT-OF-SAMPLE", t[t.time >= OOS])):
        rows.append(dict(version=lab, block=bl, **stats(sub)))
A = pd.DataFrame(rows)
A.to_csv(R + "o1_blocks.csv", index=False)
print(A.round(4).to_string(index=False))

print("\n" + "=" * 132)
print("O1.2  THE MATCHED CONTROL, COMPUTED INSIDE EACH BLOCK -- the STUDY_TOP5 correction")
print("=" * 132)
print("  A random quarter-hour entry on the SAME sessions with identical management.")
rows = []
for lab, t in runs.items():
    for bl, sub in (("ALL", t), ("in-sample", t[t.time < OOS]), ("OUT-OF-SAMPLE", t[t.time >= OOS])):
        if len(sub) < 20:
            continue
        v = B.control(f, sub, draws=1500, seed=17)
        rows.append(dict(version=lab, block=bl, n=len(sub), rule_R=sub.R.mean(),
                         ctl_med=np.median(v), ctl_p95=np.percentile(v, 95),
                         excess=sub.R.mean() - np.median(v), p=float((v >= sub.R.mean()).mean())))
        print(f"  ...{lab} {bl} done {time.time()-t0:.0f}s")
C = pd.DataFrame(rows)
C.to_csv(R + "o1_controls.csv", index=False)
print(C.round(4).to_string(index=False))
print("\n  READ THE CONTROL'S OWN LEVEL. A control that loses money makes clearing it a weak")
print("  statement; a control that makes money makes failing it a weak statement.")

print("\n" + "=" * 132)
print("O1.3  BY YEAR, AND WHERE THE MONEY IS")
print("=" * 132)
for lab, t in runs.items():
    t2 = t.copy(); t2["yr"] = t2.time.dt.year
    g = t2.groupby("yr").agg(n=("usd", "size"), net=("usd", "sum"), R=("R", "mean"))
    g["pf"] = t2.groupby("yr").usd.apply(lambda u: u[u > 0].sum() / max(-u[u < 0].sum(), 1e-9))
    g["win"] = t2.groupby("yr").usd.apply(lambda u: (u > 0).mean())
    print(f"\n  {lab}")
    print(g.round(3).to_string())

print("\n" + "=" * 132)
print("O1.4  EXIT MIX -- where the P&L actually comes from, per block")
print("=" * 132)
t = runs["alpha.2 (prior=1, cap=1)"]
for bl, sub in (("in-sample", t[t.time < OOS]), ("OUT-OF-SAMPLE", t[t.time >= OOS])):
    g = sub.groupby("reason").agg(n=("usd", "size"), net=("usd", "sum"), R=("R", "mean"))
    g["share_of_net"] = g.net / sub.usd.sum()
    print(f"\n  {bl}  (total ${sub.usd.sum():,.0f})")
    print(g.round(3).to_string())
print("\n  STUDY_FTM_ORB_BACKTEST recorded that the conditional 15:30 exit alone contributes more")
print("  than the entire net result. If that holds per block, the EXITS carry this strategy.")
for lab, t in runs.items():
    t.to_parquet(R + f"o1_{'rc1' if 'RC1' in lab else 'a2'}.parquet")
print(f"\ntotal {time.time()-t0:.0f}s")
