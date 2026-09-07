"""O2 -- robustness: the two alpha.2 knobs, the four compatibility gates, and the components.

Read by MARGINAL, per block, never by the top row. An axis that is INERT is named as inert rather
than counted as four passing rungs -- STUDY_V33 recorded that a stability score which counts a flat
line reaches 1.000 while measuring nothing.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/ftm")
import numpy as np, pandas as pd
import ftm_sim as FS

R = "results/ftm2/"; os.makedirs(R, exist_ok=True)
OOS = pd.Timestamp("2025-01-01")
print(__doc__); t0 = time.time()
pd.set_option("display.width", 230)

def sc(t):
    t = t.copy(); t["time"] = pd.to_datetime(t.time)
    out = {}
    for tag, s in (("all", t), ("is", t[t.time < OOS]), ("oos", t[t.time >= OOS])):
        u = s.usd.to_numpy()
        out[f"n_{tag}"] = len(s)
        out[f"R_{tag}"] = s.R.mean() if len(s) else np.nan
        out[f"net_{tag}"] = u.sum()
        out[f"pf_{tag}"] = u[u > 0].sum() / max(-u[u < 0].sum(), 1e-9) if len(s) else np.nan
    return out

print("=" * 126)
print("O2.1  THE TWO ALPHA.2 KNOBS, SWEPT -- the only things this version changes")
print("=" * 126)
rows = []
for pb in (1, 2, 3, 4, 5):
    for cap in (0, 1, 2, 3):
        _, t = FS.run(verbose=False, prior_bars=pb, h2_cap=cap)
        rows.append(dict(prior_bars=pb, h2_cap=cap, **sc(t)))
K = pd.DataFrame(rows)
K.to_csv(R + "o2_knobs.csv", index=False)
print(K[["prior_bars", "h2_cap", "n_all", "net_all", "R_all", "R_is", "R_oos",
         "pf_is", "pf_oos"]].round(4).to_string(index=False))
print(f"\n  MARGINAL per axis (mean over the other):")
for ax in ("prior_bars", "h2_cap"):
    m = K.groupby(ax)[["net_all", "R_all", "R_is", "R_oos"]].mean().round(4)
    print(f"\n  --- {ax} ---"); print(m.to_string())
print("\n  RC1 is (2, 0) and alpha.2 is (1, 1). If neither axis has a gradient, the alpha.2 policy")
print("  is not a change worth having an opinion about.")

print("\n" + "=" * 126)
print("O2.2  THE FOUR COMPATIBILITY GATES -- each is a DEVIATION from the NinjaScript")
print("=" * 126)
rows = []
base = dict(prior_bars=1, h2_cap=1)
for lab, kw in (("source values (warm ON, lb 120, strict ON)",
                 dict(require_warm=True, orb_lookback=120, strict_contig=True)),
                ("shipped defaults (warm OFF, lb 40, strict OFF)",
                 dict(require_warm=False, orb_lookback=40, strict_contig=False)),
                ("warm ON only", dict(require_warm=True, orb_lookback=40, strict_contig=False)),
                ("lookback 120 only", dict(require_warm=False, orb_lookback=120, strict_contig=False)),
                ("strict contiguity only", dict(require_warm=False, orb_lookback=40, strict_contig=True)),
                ("lookback 20", dict(require_warm=False, orb_lookback=20, strict_contig=False)),
                ("lookback 60", dict(require_warm=False, orb_lookback=60, strict_contig=False)),
                ("lookback 90", dict(require_warm=False, orb_lookback=90, strict_contig=False))):
    _, t = FS.run(verbose=False, **base, **kw)
    rows.append(dict(config=lab, **sc(t)))
    print(f"  ...{lab} done {time.time()-t0:.0f}s")
G = pd.DataFrame(rows)
G.to_csv(R + "o2_gates.csv", index=False)
print(G[["config", "n_all", "net_all", "R_all", "R_is", "R_oos", "pf_is", "pf_oos"]]
      .round(4).to_string(index=False))

print("\n" + "=" * 126)
print("O2.3  COMPONENT DROP-ONE, PER BLOCK -- what is load-bearing and what is decoration")
print("=" * 126)
rows = []
for lab, kn in (("as shipped", {}),
                ("no profit target", dict(target_on=False)),
                ("no managed stop", dict(managed_on=False)),
                ("no 15:30 conditional exit", dict(cond_exit_on=False)),
                ("no kNN direction model", dict(knn_on=False)),
                ("no prior-day override", dict(prior_override_on=False)),
                ("no entry refinement", dict(refine_on=False)),
                ("no RC1 direct action", dict(direct_on=False)),
                ("no admission geometry", dict(adm_geom_on=False)),
                ("no touch veto", dict(adm_touch_on=False)),
                ("no high-ORB regime", dict(high_orb_regime_on=False)),
                ("first signal only", dict(first_signal_only=True)),
                ("SIDE = coin flip", dict(side_mode="random", side_seed=3)),
                ("SIDE = always long", dict(side_mode="long")),
                ("SIDE = always short", dict(side_mode="short"))):
    _, t = FS.run(verbose=False, **base, knobs=kn)
    rows.append(dict(component=lab, **sc(t)))
D = pd.DataFrame(rows)
D.to_csv(R + "o2_dropone.csv", index=False)
print(D[["component", "n_all", "net_all", "R_all", "R_is", "R_oos", "pf_oos"]]
      .round(4).to_string(index=False))
b = D.iloc[0]
print(f"\n  A component whose removal RAISES R is not earning its place. Baseline "
      f"R_all {b.R_all:+.4f}, R_oos {b.R_oos:+.4f}.")
print(f"  Components that improve R_oos when removed: "
      f"{', '.join(D[D.R_oos > b.R_oos].component.tolist()[:8])}")
print(f"\ntotal {time.time()-t0:.0f}s")
