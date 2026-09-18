"""N3 -- Gate 2: does the meta layer add anything a random filter of the same size does not?

Two nulls, both on RESEARCH only. (a) a day-block bootstrap of the kept set's own returns, which
asks whether the uplift separates from zero; (b) a SAME-SELECTIVITY RANDOM FILTER, which asks
whether it separates from keeping that many events at random. This branch has recorded that (a)
alone passes on rules a random subset matches, so (b) is the gate.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s3nn")
import numpy as np, pandas as pd
import nn_model as M

R = "results/s3nn/"
print(__doc__)
t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
rng = np.random.default_rng(11)

tr = pd.read_parquet(R + "n2_rows.parquet")
mods = pd.read_csv(R + "model_names.csv", header=None)[0].tolist()
OOF = np.load(R + "oof_real.npy")
y = tr.R.to_numpy(); pts = tr.pts.to_numpy(); day = tr.day.to_numpy()
uday = np.unique(day)

def boot_p(vals, days, n=2000):
    """Day-block bootstrap: resample whole DAYS with their events attached."""
    idx = {d: np.flatnonzero(days == d) for d in np.unique(days)}
    keys = list(idx)
    out = np.empty(n)
    for b in range(n):
        pick = rng.choice(len(keys), len(keys))
        sel = np.concatenate([idx[keys[j]] for j in pick])
        out[b] = vals[sel].mean()
    return (out <= 0).mean(), np.percentile(out, [2.5, 97.5])

def rand_filter_p(score, frac, n=2000):
    """Keep the SAME NUMBER of events at random, 2000 times."""
    k = max(int(round(frac * len(y))), 5)
    real = y[np.argsort(-score)[:k]].mean()
    ctl = np.array([y[rng.choice(len(y), k, replace=False)].mean() for _ in range(n)])
    return real, ctl, (ctl >= real).mean()

print("=" * 118)
print("N3.1  GATE 2 -- uplift on UNSIZED returns, against both nulls")
print("=" * 118)
b_mean = y.mean()
b_pf = y[y > 0].sum() / -y[y < 0].sum()
b_p90 = np.percentile(y, 90)
print(f"  Gate 1 baseline (all {len(y)} research events): R {b_mean:+.4f}  PF {b_pf:.3f}  "
      f"p90 {b_p90:.3f}")
rows = []
for j, nm in enumerate(mods):
    for f in (0.3, 0.5, 0.7):
        s = M.keep_stats(y, OOF[:, j], f)
        k = s["kept"]
        idx = np.argsort(-OOF[:, j])[:k]
        pb, ci = boot_p(y[idx], day[idx], 1000)
        _, ctl, pc = rand_filter_p(OOF[:, j], f, 1000)
        rows.append(dict(model=nm, keep=f, n=k, R=s["mean"], uplift=s["mean"] - b_mean,
                         pf=s["pf"], p90=s["p90"], ctl_R=ctl.mean(),
                         p_boot=pb, p_ctl=pc))
G = pd.DataFrame(rows)
G.to_csv(R + "n3_gate2.csv", index=False)
print(G.round(4).to_string(index=False))

pass_both = G[(G.p_boot <= 0.05) & (G.p_ctl <= 0.05)]
print(f"\n  cells clearing BOTH nulls at p<=0.05: {len(pass_both)} of {len(G)} "
      f"(chance on the control alone is {0.05*len(G):.1f})")
print(f"  cells clearing the bootstrap alone: {(G.p_boot<=0.05).sum()}  "
      f"-- the difference is the whole reason (b) exists")
print(f"  best control p anywhere: {G.p_ctl.min():.3f}")
print(f"  p90 of R falls below the {b_p90:.3f} baseline in "
      f"{(G.p90 < b_p90).sum()} of {len(G)} cells -- a filter that trims the tail is a "
      f"win-rate fit whatever its objective said")

print("\n" + "=" * 118)
print("N3.2  THE ENSEMBLE, AND THE ONE CELL WORTH A LOCKED READ")
print("=" * 118)
z = (OOF - np.nanmean(OOF, 0)) / (np.nanstd(OOF, 0) + 1e-9)
ens_mlp = z[:, [mods.index(m) for m in mods if m.startswith("mlp")]].mean(1)
ens_all = z.mean(1)
for nm, sc in (("mlp ensemble", ens_mlp), ("full ensemble", ens_all)):
    for f in (0.3, 0.5, 0.7):
        s = M.keep_stats(y, sc, f)
        _, ctl, pc = rand_filter_p(sc, f, 1000)
        print(f"  {nm:14s} keep {f:.0%}: R {s['mean']:+.4f}  PF {s['pf']:.3f}  "
              f"p90 {s['p90']:.3f}  ctl {ctl.mean():+.4f}  p {pc:.3f}")

best = G.sort_values("p_ctl").iloc[0]
print(f"\n  best research cell: {best.model} keep {best.keep:.0%}  "
      f"uplift {best.uplift:+.4f} R  control p {best.p_ctl:.3f}")
print(f"\n  TRIALS COUNTED SO FAR: 5 primary cells (N1) + 8 models x 3 rungs x 2 label sets (N2) "
      f"+ 24 gate cells + 6 ensemble cells = 83")
print(f"\ntotal {time.time()-t0:.0f}s")
