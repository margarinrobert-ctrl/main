"""D8 -- the COUNT gate against a RANDOM gate of the same selectivity, re-simulated end to end.

This is the one thing D7 left open. The count form (how many of the seven volatility features sit
above their own research median) improved every locked rung, which is the only filter result in the
study that did. But it was never scored against the right null.

A filter in a script is a VETO, not a subset: refusing a signal RELEASES the position lock and
admits a later breakout the unfiltered run never saw. So the control has to be a random gate over
BARS, re-simulated through the same walker -- `STUDY_AUCTION`'s rule, and `STUDY_XAU_CVD_FEATURES`
measured that the two framings give different answers.

Every print flushes, so this streams.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v66"); sys.path.insert(0, "research/v61sess")
sys.path.insert(0, "research/v61feat")
import v66core as V
import v66_parity as P

t0 = time.time()
pd.set_option("display.width", 200)
def say(*a):
    print(*a, flush=True)

say(__doc__)
say(f"[{time.time()-t0:6.1f}s] loading 15m bars ...")
D = V.load(15)
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars, split day {D['cut_day']}")

say(f"[{time.time()-t0:6.1f}s] building the seven features ...")
F = P.features(D)
MED = P.MED
cnt = (F > MED).sum(axis=1).astype(float)
cnt[~np.isfinite(F).all(axis=1)] = np.nan
say(f"[{time.time()-t0:6.1f}s] features done; count distribution over all bars "
    f"{np.bincount(cnt[np.isfinite(cnt)].astype(int), minlength=8)}")

say(f"[{time.time()-t0:6.1f}s] base run (no gate) ...")
base = P.script_walk(D)
for blk, nm in ((0, "research"), (1, "LOCKED")):
    x = base[base.blk == blk].pct.to_numpy()
    pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
    say(f"           base {nm:>8}: n {len(x):>4}  {x.mean():+.5f} %/ev  PF {pf:.3f}")

DRAWS = 400
rng = np.random.default_rng(88)
rows = []
say(f"\n[{time.time()-t0:6.1f}s] the count gate vs a random gate of the SAME selectivity, "
    f"{DRAWS} draws a rung")
say(f"{'T>=':>4} {'block':>9} {'rate':>6} {'n':>5} {'rule':>9} {'PF':>7} {'ctl med':>9} "
    f"{'excess':>9} {'p':>6}")
for T in (3, 4, 5, 6, 7):
    g = np.isfinite(cnt) & (cnt >= T)
    rate = float(np.nanmean(g[np.isfinite(cnt)]))
    t = P.script_walk(D, gate=g)
    ctl = {0: [], 1: []}
    for j in range(DRAWS):
        rg = np.zeros(D["n"], bool)
        ok = np.flatnonzero(np.isfinite(cnt))
        rg[rng.choice(ok, int(round(rate * len(ok))), replace=False)] = True
        q = P.script_walk(D, gate=rg)
        for blk in (0, 1):
            v = q[q.blk == blk].pct.to_numpy()
            if len(v) >= 10:
                ctl[blk].append(v.mean())
        if (j + 1) % 100 == 0:
            say(f"      ... T>={T} draw {j+1}/{DRAWS}  [{time.time()-t0:6.1f}s]")
    for blk, nm in ((0, "research"), (1, "LOCKED")):
        x = t[t.blk == blk].pct.to_numpy()
        if len(x) < 15:
            say(f"{T:>4} {nm:>9} {rate:>6.3f} {len(x):>5}  -- too few --")
            continue
        c = np.array(ctl[blk])
        pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        p = float((c >= x.mean()).mean())
        rows.append(dict(T=T, block=nm, rate=rate, n=len(x), rule=x.mean(), pf=pf,
                         ctl=np.median(c), excess=x.mean() - np.median(c), p=p))
        say(f"{T:>4} {nm:>9} {rate:>6.3f} {len(x):>5} {x.mean():>+9.5f} {pf:>7.3f} "
            f"{np.median(c):>+9.5f} {x.mean()-np.median(c):>+9.5f} {p:>6.3f}")

R = pd.DataFrame(rows)
os.makedirs("results/v66", exist_ok=True)
R.to_csv("results/v66/d8_count_control.csv", index=False)
say("")
for nm in ("research", "LOCKED"):
    q = R[R.block == nm]
    say(f"  {nm}: cells clearing the random gate at p<=0.05: {int((q.p <= 0.05).sum())} of {len(q)}"
        f"   best p {q.p.min():.3f}")
both = R.pivot(index="T", columns="block", values="p")
say(f"\n  rungs clearing on BOTH blocks: "
    f"{int(((both['research'] <= 0.05) & (both['LOCKED'] <= 0.05)).sum())} of {len(both)}")
say(f"\n[{time.time()-t0:6.1f}s] done")
