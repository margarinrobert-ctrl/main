"""T1  GATE 1 PER TIMEFRAME: the primary against a MATCHED RANDOM ENTRY (same session, same side,
same entry window, same geometry and exits, same position lock; drawn bars SORTED before the walk),
400 draws, the MDE printed beside it. Read on all 92 sessions and on the research half.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

pd.set_option("display.width", 220)
N = C.N
P = C.P
sp = np.load(os.path.join(HERE, "split_days.npy"))
k_is = int(sp[0]); DAYS = sp[1:]; IS_D = DAYS[:k_is]; OOS_D = DAYS[k_is:]


def control(c, sig_g, sd_g, n_draw=400, seed=0):
    rhi, rlo, _ = c.ranges(P["range_end"])
    ok = (c.mod >= P["open_m"]) & (c.mod < P["end_m"]) & np.isfinite(rhi) & np.isfinite(rlo)
    elig = np.flatnonzero(ok)
    eday = c.day[elig]
    pool = {d: elig[eday == d] for d in np.unique(c.day[sig_g])}
    atrf = c.atr_frame(P["atr_n"])
    g = np.random.default_rng(seed)
    out = np.full(n_draw, np.nan)
    for q in range(n_draw):
        bb, ss = [], []
        for i, b in enumerate(sig_g):
            cand = pool.get(c.day[b])
            if cand is None or not len(cand):
                continue
            bb.append(g.choice(cand)); ss.append(sd_g[i])
        o = np.argsort(np.asarray(bb), kind="stable")
        t = c._walk_sig(P, atrf, np.asarray(bb)[o], np.asarray(ss)[o])
        if t is not None and len(t):
            out[q] = t["pct"].mean()
    return out


rows = []
for tf in C.TFS:
    c = C.ctx(tf)
    sig, sd = c.sigs(P)
    for blk, dd in (("ALL", DAYS), ("research", IS_D), ("holdout", OOS_D)):
        m = np.isin(c.day[sig], dd)
        s_, d_ = sig[m], sd[m]
        t = c._walk_sig(P, c.atr_frame(P["atr_n"]), s_, d_)
        if t is None or len(t) < 3:
            rows.append(dict(tf=tf, block=blk, n=0 if t is None else len(t)))
            continue
        r = t["pct"].to_numpy()
        nul = control(c, s_, d_, 400, seed=int(tf * 10) + len(blk))
        v = nul[np.isfinite(nul)]
        mde = N.mde(r.std(ddof=1), len(r))
        bo = N.boot_edge(t.assign(_day=t["eday"]), 4000, 7, col="pct")
        rows.append(dict(tf=tf, block=blk, n=len(r), pct=r.mean(), pf=C.pf(r), win=(r > 0).mean(),
                         hit=(t["why"] == 2).mean(), null_med=np.median(v), null_sd=v.std(ddof=1),
                         p_entry=float((v >= r.mean()).mean()), mde=mde, per_mde=r.mean() / mde,
                         boot_p=float((bo <= 0).mean())))
        print(f"  tf {tf:>4} {blk:9s} n {len(r):>3} {r.mean():+.4f} PF {C.pf(r):.3f} "
              f"null {np.median(v):+.4f} p {rows[-1]['p_entry']:.3f} MDE {mde:.4f} "
              f"({r.mean()/mde:+.2f}x) boot {rows[-1]['boot_p']:.3f}", flush=True)
G = pd.DataFrame(rows)
G.to_csv(os.path.join(HERE, "t1_gate1.csv"), index=False)
print()
print(G.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("\n  Gate 1 PASS requires p_entry <= 0.05 on the research half. A pass inside its own MDE")
print("  is a consistent direction, not a resolved effect.")
