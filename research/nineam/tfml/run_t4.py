"""T4  GATE 2 PER TIMEFRAME, RESEARCH HALF: the pre-declared model's OOF score as a VETO on the
gated primary's signal bars, RE-SIMULATED END TO END with the position lock (`c._walk_sig`), keep in
{0.7, 0.5}, against (i) a PAIRED day-block bootstrap of the uplift and (ii) a same-selectivity
random gate, 400 draws, also re-simulated. The same veto built from the SHUFFLED-TWIN score is
printed beside every cell as the reference a real score has to beat.

PRE-DECLARED here, before the table prints: the single cell read once on the holdout (T5) is the
(timeframe, keep) with the LOWEST random-gate p on research, ties broken by the larger uplift.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import tfmodels as M  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

pd.set_option("display.width", 230)
t0 = time.time()
P = C.P
Rp = pd.read_pickle(os.path.join(HERE, "t3_oof.pkl"))
BEST = pd.read_csv(os.path.join(HERE, "t3_best.csv"), index_col=0).iloc[0, 0]
KEEP = pd.read_csv(os.path.join(HERE, "t2_keep.csv")).iloc[:, 0].tolist()
print(f"Gate-2 score = pooled OOF of {BEST}")

# the shuffled-twin score for the same model: labels permuted, same folds, same weights
X = Rp[KEEP].to_numpy(float); y = Rp["pct"].to_numpy(); w = M.weights(Rp); d = Rp["day"].to_numpy()
ys = np.random.default_rng(4242).permutation(y)
Rp["twin"] = M.oof(BEST, X, ys, w, d, seed=0)
Rp["score"] = Rp[f"oof_{BEST}"]


def walk(c, sig, sd):
    o = np.argsort(sig, kind="stable")
    return c._walk_sig(P, c.atr_frame(P["atr_n"]), np.asarray(sig)[o], np.asarray(sd)[o])


def stats(t):
    if t is None or len(t) == 0:
        return dict(n=0, pct=np.nan, pf=np.nan, win=np.nan, hit=np.nan)
    r = t["pct"].to_numpy()
    return dict(n=len(r), pct=r.mean(), pf=C.pf(r), win=(r > 0).mean(), hit=(t["why"] == 2).mean())


rows = []
for tf in C.TFS:
    c = C.ctx(tf)
    g = Rp[(Rp.tf == tf) & (Rp.gated == 1)].sort_values("sig")
    sig = g["sig"].to_numpy(); sd = g["side"].to_numpy()
    base = walk(c, sig, sd)
    bst = stats(base)
    for k in (0.7, 0.5):
        for src in ("score", "twin"):
            sc = g[src].to_numpy()
            nk = max(1, int(round(k * len(sc))))
            thr = np.sort(sc)[::-1][nk - 1]
            keep = sc >= thr
            kt = walk(c, sig[keep], sd[keep])
            kst = stats(kt)
            up = kst["pct"] - bst["pct"]
            row = dict(tf=tf, keep=k, src=src, n_sig=len(sig), base_n=bst["n"], base_pct=bst["pct"],
                       base_pf=bst["pf"], base_hit=bst["hit"], base_win=bst["win"],
                       kept_n=kst["n"], kept_pct=kst["pct"], kept_pf=kst["pf"], kept_hit=kst["hit"],
                       kept_win=kst["win"], uplift=up, thr=thr,
                       kept_sd=float(kt["pct"].std(ddof=1)) if kst["n"] > 1 else np.nan)
            if src == "score":
                gg = np.random.default_rng(int(tf * 100) + int(k * 10))
                nul = np.full(400, np.nan)
                for q in range(400):
                    m = np.zeros(len(sig), bool); m[gg.choice(len(sig), nk, replace=False)] = True
                    tt = walk(c, sig[m], sd[m])
                    if tt is not None and len(tt):
                        nul[q] = tt["pct"].mean() - bst["pct"]
                v = nul[np.isfinite(nul)]
                bo = C.day_boot_uplift(base, kt, 2000, seed=int(tf * 10)) if kst["n"] > 1 else np.array([np.nan])
                row.update(p_gate=float((v >= up).mean()), null_sd=float(v.std(ddof=1)),
                           mde_uplift=2.802 * float(v.std(ddof=1)),
                           mde_kept=float(C.N.mde(row["kept_sd"], kst["n"])),
                           p_boot=float((bo <= 0).mean()) if kst["n"] > 1 else np.nan)
            rows.append(row)
            print(f"  tf {tf:>4} keep {k} {src:5s} base n{bst['n']:>3} PF {bst['pf']:.3f} "
                  f"-> kept n{kst['n']:>3} PF {kst['pf']:.3f} uplift {up:+.4f}"
                  + (f"  p_gate {row['p_gate']:.3f} p_boot {row['p_boot']:.3f} "
                     f"MDE_up {row['mde_uplift']:.4f}" if src == "score" else ""), flush=True)
G = pd.DataFrame(rows)
G.to_csv(os.path.join(HERE, "t4_gate2.csv"), index=False)
S = G[G.src == "score"].copy()
T = G[G.src == "twin"][["tf", "keep", "uplift", "kept_pf"]].rename(
    columns={"uplift": "twin_uplift", "kept_pf": "twin_pf"})
S = S.merge(T, on=["tf", "keep"])
print()
print(S[["tf", "keep", "base_n", "base_pf", "base_hit", "kept_n", "kept_pf", "kept_hit", "uplift",
         "p_gate", "p_boot", "mde_uplift", "twin_uplift", "twin_pf"]]
      .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print(f"\n  cells clearing BOTH nulls at 0.05: {int(((S.p_gate <= 0.05) & (S.p_boot <= 0.05)).sum())} of {len(S)}"
      f"; uplift outside its own MDE: {int((S.uplift > S.mde_uplift).sum())}; "
      f"score beats its twin: {int((S.uplift > S.twin_uplift).sum())} of {len(S)}")
S = S.sort_values(["p_gate", "uplift"], ascending=[True, False])
ch = S.iloc[0]
print(f"\n  PRE-DECLARED holdout cell: tf {ch.tf} keep {ch.keep} (research p_gate {ch.p_gate:.3f}, "
      f"uplift {ch.uplift:+.4f}, PF {ch.base_pf:.3f} -> {ch.kept_pf:.3f})")
pd.Series(dict(tf=ch.tf, keep=ch.keep, thr_q=ch.keep)).to_csv(os.path.join(HERE, "t4_chosen.csv"))
S.to_csv(os.path.join(HERE, "t4_gate2_scored.csv"), index=False)
print(f"done in {time.time()-t0:.0f}s")
