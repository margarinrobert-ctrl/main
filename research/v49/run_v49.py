"""V49 -- the gradient: does the limit entry's advantage fall as a signal's immediacy rises?

Every parameter is DECLARED here and none is searched: limit 1.0 x ATR, order live 5 minutes,
stop 2.0N, NO target, max hold 480 minutes, immediacy marked at +30 minutes. Research block is the
first 65% of bars; locked is read once at the end.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v49")
import data as TD           # noqa: E402
import v49mech as M         # noqa: E402

LIM_MULT, EXPIRY_MIN = 1.0, 5
STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN = 2.0, 0.0, 480, 30
SPLIT = 0.65
TF = 5


def load():
    d = TD.bars("NQ", TF)
    d1 = TD.bars("NQ", 1)
    t = pd.to_datetime(pd.Series(d["idx"])); t1 = pd.to_datetime(pd.Series(d1["idx"]))
    m1 = pd.Series(np.arange(len(t1)), index=t1.values).reindex(t.values).to_numpy()
    P = dict(o=d["o"], h=d["h"], l=d["l"], c=d["c"], atr=d["atr"], n=len(d["c"]))
    return P, d1, m1


def run_family(P, d1, m1, idx, lim):
    ent1 = m1[idx + 1]
    ok = np.isfinite(ent1)
    idx, ent1 = idx[ok], ent1[ok].astype(np.int64)
    f, R, Rk, held = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], ent1,
                            P["c"][idx], P["atr"][idx], float(lim), EXPIRY_MIN,
                            STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN,
                            M.COST_PTS, M.SLIP_PTS)
    return idx, f.astype(bool), R, Rk, held


def main():
    P, d1, m1 = load()
    S = M.signals(P)
    cut = int(P["n"] * SPLIT)
    rows = []
    for name, idx in sorted(S.items()):
        rec = {"family": name}
        for lab, lim in (("mkt", 0.0), ("lim", LIM_MULT)):
            i2, f, R, Rk, held = run_family(P, d1, m1, idx, lim)
            for bn, blk in (("res", i2 < cut), ("lk", i2 >= cut)):
                sel = blk & f
                if sel.sum() < 60:
                    rec[f"{lab}_{bn}_n"] = int(sel.sum())
                    continue
                r = R[sel]; r = r[np.isfinite(r)]
                rk = Rk[sel]; rk = rk[np.isfinite(rk)]
                rec[f"{lab}_{bn}_n"] = len(r)
                rec[f"{lab}_{bn}_R"] = float(r.mean())
                rec[f"{lab}_{bn}_Rk"] = float(rk.mean()) if len(rk) else np.nan
                rec[f"{lab}_{bn}_hold"] = float(held[sel].mean())
                rec[f"{lab}_{bn}_fill"] = float(f[blk].mean())
        rows.append(rec)
    D = pd.DataFrame(rows)
    for bn in ("res", "lk"):
        D[f"delta_{bn}"] = D.get(f"lim_{bn}_R") - D.get(f"mkt_{bn}_R")
        D[f"immed_{bn}"] = D.get(f"mkt_{bn}_Rk")
    D.to_csv("results/v49/v49_gradient.csv", index=False)

    r = D.dropna(subset=["immed_res", "delta_res"])
    r = r[(r.mkt_res_n >= 100) & (r.lim_res_n >= 100)]
    rho = stats.spearmanr(r.immed_res, r.delta_res)
    print("=" * 100)
    print("  GATE 2 -- THE GRADIENT ON RESEARCH, and the permutation null")
    print("=" * 100)
    print(f"  {len(r)} families with >=100 filled trades on both mechanics")
    print(f"  Spearman rho(immediacy, limit-minus-market) = {rho.statistic:+.4f}")
    rng = np.random.default_rng(3)
    a = r.immed_res.to_numpy(); b = r.delta_res.to_numpy()
    draws = np.array([stats.spearmanr(rng.permutation(a), b).statistic for _ in range(5000)])
    p = float(np.mean(draws <= rho.statistic))
    print(f"  permutation p (5,000 label shuffles)      = {p:.4f}")
    print(f"  pre-registered threshold: rho <= -0.50 and p <= 0.05  -> "
          f"{'PASS' if (rho.statistic <= -0.50 and p <= 0.05) else 'FAIL'}")

    print("\n  MONOTONICITY across immediacy quintiles (the abandonment check)")
    r = r.assign(q=pd.qcut(r.immed_res, 5, labels=False, duplicates="drop"))
    g = r.groupby("q").agg(n=("family", "size"), immed=("immed_res", "mean"),
                           delta=("delta_res", "mean"))
    for q, row in g.iterrows():
        print(f"    Q{int(q)+1}  families {int(row.n):>3}  mean immediacy {row.immed:+.4f}"
              f"   mean delta {row.delta:+.4f}")
    return D, r, rho.statistic, p


if __name__ == "__main__":
    main()
