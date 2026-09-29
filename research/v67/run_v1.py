"""V1 -- what is predictable at all: 8 targets x 4 horizons, against the trivial baseline.

Order matters here. The AUDIT runs before any score, the BASELINE is computed before any model, and
DIRECTION is in the grid as the control that prior work says must fail. A study that reports only
the targets that worked has not measured anything.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v67"); sys.path.insert(0, "research/v22")
import v67core as V
import v22vol as VV

t0 = time.time()
pd.set_option("display.width", 220)
def say(*a): print(*a, flush=True)

say(__doc__)
say(f"[{time.time()-t0:6.1f}s] loading NQ 15m ...")
D = V.load(15)
mR = D["blk"] == 0
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars   research {int(mR.sum()):,}  "
    f"locked {int((~mR).sum()):,}   split {D['cut_day']}")

say(f"[{time.time()-t0:6.1f}s] building the causal volatility features ...")
# v22vol.build returns a DICT of arrays, not a DataFrame -- caught live by the monitor on the
# first run rather than after the fact, which is the whole point of the streaming setup.
X = pd.DataFrame(VV.build(D["o"], D["h"], D["l"], D["c"]))
FEATS = list(X.columns)
say(f"[{time.time()-t0:6.1f}s] features done: {len(FEATS)}")

# ---------------------------------------------------------------- leakage audit
say(f"\n[{time.time()-t0:6.1f}s] LEAKAGE AUDIT -- recompute each feature on history ENDING at the "
    f"probe bar")
rng = np.random.default_rng(11)
probes = rng.choice(np.arange(3000, D["n"] - 200), 12, replace=False)
bad = 0; checked = 0
for i in probes:
    Dt = {k: (v[:i + 1] if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == D["n"] else v)
          for k, v in D.items()}
    Xt = pd.DataFrame(VV.build(Dt["o"], Dt["h"], Dt["l"], Dt["c"]))
    for cnm in FEATS:
        a, b = X[cnm].to_numpy()[i], Xt[cnm].to_numpy()[-1]
        checked += 1
        if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > 1e-8 * max(1, abs(a))):
            bad += 1
say(f"[{time.time()-t0:6.1f}s]   {bad} mismatches over {checked:,} comparisons on "
    f"{len(probes)} probe bars")

# ---------------------------------------------------------------- the grid
say(f"\n[{time.time()-t0:6.1f}s] PART A -- every target against its own trailing realisation")
say(f"{'h':>4} {'target':>7} {'base IC':>8} {'base t':>8} | {'best feat':>22} {'IC':>8} "
    f"{'NW t':>8} {'shuf':>7} | {'beats base':>10}")
rows = []
for h in V.HORIZONS:
    T = V.build_targets(D, h)
    B = V.trailing_baseline(D, h)
    for tg in V.TARGETS:
        y = T[tg]
        yb = B[tg]
        m = mR & np.isfinite(y)
        base_ic = V.ic(yb[m], y[m]) if np.isfinite(yb).any() else np.nan
        _, base_t = V.newey_west_t(yb[m], y[m], h) if np.isfinite(yb).any() else (np.nan, np.nan)
        best = (None, 0.0, np.nan, np.nan)
        for cnm in FEATS:
            x = X[cnm].to_numpy(float)
            v = V.ic(x[m], y[m])
            if np.isfinite(v) and abs(v) > abs(best[1]):
                _, tt = V.newey_west_t(x[m], y[m], h)
                best = (cnm, v, tt, np.nan)
        # shuffled twin: the same feature against a permuted target
        ys = y[m].copy(); rng.shuffle(ys)
        shuf = V.ic(X[best[0]].to_numpy(float)[m], ys) if best[0] else np.nan
        beat = (abs(best[1]) > abs(base_ic)) if np.isfinite(base_ic) else None
        rows.append(dict(h=h, target=tg, base_ic=base_ic, base_t=base_t, feat=best[0],
                         ic=best[1], t=best[2], shuf=shuf, beats=beat))
        say(f"{h:>4} {tg:>7} {base_ic:>8.4f} {base_t:>8.2f} | {str(best[0]):>22} {best[1]:>8.4f} "
            f"{best[2]:>8.2f} {shuf:>7.4f} | {str(beat):>10}")
    say(f"      ... h={h} done  [{time.time()-t0:6.1f}s]")

R = pd.DataFrame(rows)
R.to_csv("results/v67/v1_grid.csv", index=False)
say("")
say(f"  targets whose BEST feature beats the trivial trailing baseline: "
    f"{int((R.beats == True).sum())} of {int(R.beats.notna().sum())}")
for tg in V.TARGETS:
    q = R[R.target == tg]
    say(f"    {tg:>5}  base IC {q.base_ic.mean():+.4f}   best-feature IC {q.ic.abs().mean():+.4f} "
        f"  beats base {int((q.beats == True).sum())}/{int(q.beats.notna().sum())}")
say(f"\n[{time.time()-t0:6.1f}s] done")
