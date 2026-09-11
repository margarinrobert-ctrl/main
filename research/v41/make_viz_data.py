"""Emit one JSON bundle of everything the visual report plots. Real numbers only."""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
sys.path.insert(0, "research/v41")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v39mc as MC           # noqa: E402
import v41seq as S           # noqa: E402
from run_v41 import blocks                                  # noqa: E402
from run_v41b import trades, tensors, KEYS                  # noqa: E402
from run_v41c import market_prep                            # noqa: E402

OUT = {}


def hist(x, bins=40, lo=None, hi=None):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    lo = float(np.percentile(x, 0.5)) if lo is None else lo
    hi = float(np.percentile(x, 99.5)) if hi is None else hi
    c, e = np.histogram(x, bins=bins, range=(lo, hi))
    return dict(counts=c.tolist(), edges=[round(v, 4) for v in e.tolist()])


# ---------------------------------------------------------------- V41 grid shape and transfer
T = pd.read_pickle("research/v41/v41_grid.pkl")
E = T[~T.inert].dropna(subset=["l_pf"])
OUT["grid"] = dict(
    n_nominal=int(S.N_NOMINAL), n_effective=int(S.N_EFFECTIVE), n_scored=int(len(E)),
    res_pf=hist(E.r_pf, 44, 0.2, 3.0), lock_pf=hist(E.l_pf, 44, 0.2, 3.0),
    pearson=float(E.r_pf.corr(E.l_pf)), spearman=float(E.r_pf.corr(E.l_pf, method="spearman")),
    share_res_gt1=float((E.r_pf > 1).mean()), share_lock_gt1=float((E.l_pf > 1).mean()))
sub = E.sample(min(4000, len(E)), random_state=3)
OUT["scatter"] = dict(
    r=[round(v, 3) for v in sub.r_pf.clip(0, 4).tolist()],
    l=[round(v, 3) for v in sub.l_pf.clip(0, 4).tolist()],
    tf=[int(v) for v in sub.tf.tolist()])
top = E.sort_values("r_pf", ascending=False).head(100)
OUT["top100"] = dict(res=float(top.r_pf.mean()), lock=float(top.dropna(subset=["l_pf"]).l_pf.mean()))

# marginal by timeframe, both blocks
OUT["marginal_tf"] = [dict(tf=int(v), res=float(g.r_pf.mean()), lock=float(g.l_pf.mean()),
                           n=int(len(g))) for v, g in E.groupby("tf")]

# ---------------------------------------------------------------- ablation
A = pd.read_csv("research/v41/v41_ablation.csv")
OUT["ablation"] = dict(
    n=int(len(A)),
    res=hist(A.d_r, 40, -60, 60), lock=hist(A.d_l, 40, -60, 60),
    help_res=float((A.d_r > 0).mean()), help_lock=float((A.d_l > 0).mean()),
    by_mode=[dict(mode=m, res=float((g.d_r > 0).mean()), lock=float((g.d_l > 0).mean()),
                  res_mean=float(g.d_r.mean()), lock_mean=float(g.d_l.mean()))
             for m, g in A.groupby("mode")],
    by_win=[dict(win=int(w), res=float((g.d_r > 0).mean()), lock=float((g.d_l > 0).mean()),
                 n=float(g.r_n.mean()))
            for w, g in A[A["mode"] == "cross"].groupby("win")])

# ---------------------------------------------------------------- signal overlap
P15 = S.prep(15)
res15, _ = blocks(P15)
brk = P15["brk"][20] & res15
rows = []
since, up = P15["since"][(13, 48)]
for nm, m in (("EMA13 > EMA48", up), ("cross <= 5 bars", (since >= 0) & (since <= 5)),
              ("cross <= 10 bars", (since >= 0) & (since <= 10)),
              ("cross <= 40 bars", (since >= 0) & (since <= 40))):
    rows.append(dict(name=nm, all_bars=float((m & res15).mean()),
                     on_breakout=float((m & brk).sum() / max(brk.sum(), 1))))
OUT["overlap"] = rows

# ---------------------------------------------------------------- the three candidates
CANDS = {
    "TOP": dict(tf=60, ema_f=21, ema_s=48, mode="cross", win=5, don_e=30, don_x=10,
                stop=2.5, tp=0.0, gate="adx>=20"),
    "CONSENSUS": dict(tf=60, ema_f=21, ema_s=48, mode="cross", win=10, don_e=30, don_x=10,
                      stop=2.5, tp=0.0, gate="adx>=20"),
    "BRIEF 13/48": dict(tf=60, ema_f=13, ema_s=48, mode="cross", win=40, don_e=55, don_x=20,
                        stop=1.5, tp=0.0, gate="chop<=45"),
}
OUT["cands"] = {}
for nm, c in CANDS.items():
    P = S.prep(int(c["tf"]))
    ten = tensors(P)
    res, lock = blocks(P)
    p, sb = trades(P, ten, c)
    d = P["day"][sb]
    rec = dict(cfg={k: (float(c[k]) if isinstance(c[k], float) else c[k]) for k in KEYS})
    # equity, marked at the research/locked boundary
    cut = np.unique(P["day"])[int(len(np.unique(P["day"])) * 0.65)]
    rec["equity"] = dict(x=list(range(1, len(p) + 1)),
                         y=[round(v, 1) for v in np.cumsum(p).tolist()],
                         split=int((d < cut).sum()))
    pl = p[d >= cut]
    if len(pl) >= 10:
        b = MC.boot(pl, d[d >= cut])
        rng = np.random.default_rng(11)
        days = np.unique(d[d >= cut])
        grp = [pl[d[d >= cut] == u] for u in days]
        draws = np.array([np.concatenate([grp[j] for j in rng.integers(0, len(grp), len(grp))]).mean()
                          for _ in range(1000)])
        pm = MC.perm(pl)
        rng2 = np.random.default_rng(13)
        dd = np.array([float(np.max(np.maximum.accumulate(np.cumsum(rng2.permutation(pl)))
                                    - np.cumsum(rng2.permutation(pl) * 0 + 0)
                                    if False else
                                    np.maximum.accumulate(np.cumsum(x := rng2.permutation(pl))) - np.cumsum(x)))
                       for _ in range(1000)])
        rec["mc"] = dict(hist=hist(draws, 36), mean=float(draws.mean()),
                         p5=float(np.percentile(draws, 5)), p95=float(np.percentile(draws, 95)),
                         p_le0=float((draws <= 0).mean()), n=int(len(pl)))
        rec["dd"] = dict(hist=hist(dd, 32), real=float(pm["dd_real"]),
                         p50=float(pm["dd50"]), p95=float(pm["dd95"]), p99=float(pm["dd99"]))
    # walk-forward
    edges = np.quantile(np.unique(P["day"]), np.linspace(0, 1, 7))
    folds = []
    for i in range(6):
        m = (d >= edges[i]) & (d < edges[i + 1]) if i < 5 else (d >= edges[i])
        if m.sum() < 3:
            continue
        w, lo = p[m][p[m] > 0], p[m][p[m] < 0]
        folds.append(dict(fold=i + 1, n=int(m.sum()), net=float(p[m].sum()),
                          pf=float(w.sum() / abs(lo.sum())) if len(lo) else None))
    rec["folds"] = folds
    OUT["cands"][nm] = rec

# ---------------------------------------------------------------- strategy-return correlation
T12 = E.sort_values("r_pf", ascending=False).head(12)
ser = {}
for i, (_ix, r) in enumerate(T12.iterrows()):
    c = {k: r[k] for k in KEYS}
    P = S.prep(int(c["tf"]))
    ten = tensors(P)
    p, sb = trades(P, ten, c)
    ser[f"#{i + 1}"] = pd.Series(p).groupby(P["day"][sb]).sum()
D = pd.DataFrame(ser).fillna(0.0)
C = D.corr()
OUT["corr_strategy"] = dict(labels=list(C.columns),
                            m=[[round(float(C.iloc[i, j]), 3) for j in range(len(C))]
                               for i in range(len(C))])

# ---------------------------------------------------------------- V40 feature matrix
sys.path.insert(0, "research/v40")
import v40feat as V40       # noqa: E402
P30 = G.prep(30)
P30["mod"] = __import__("fastbars").bars(30)["mod"]
P30["v"] = __import__("fastbars").bars(30)["v"]
Fs = V40.features(P30)
base = V40.signal_bars(P30) & (P30["c"] > I.sma(P30["c"], 200))
u = np.unique(P30["day"])
cutd = u[int(len(u) * 0.65)]
C2, _D2 = V40.corr_matrix(Fs, base & (P30["day"] < cutd))
OUT["corr_feature"] = dict(labels=list(C2.columns),
                           fam=[Fs[k][0] for k in C2.columns],
                           m=[[round(float(C2.iloc[i, j]), 3) for j in range(len(C2))]
                              for i in range(len(C2))])

# ---------------------------------------------------------------- V39 per-rule MC
V = pd.read_csv("research/v39/v39_mc.csv")
Fr = V[V.rule != "(no filter -- the base)"]
r_ = Fr[Fr.block == "research"].groupby("rule").mc_mean.mean()
l_ = Fr[Fr.block == "LOCKED"].groupby("rule").agg(mc=("mc_mean", "mean"), p=("p_ctrl", "mean"))
J = r_.to_frame("res").join(l_)
OUT["v39"] = dict(
    rules=[dict(name=i, res=round(float(r.res), 2), lock=round(float(r.mc), 2),
                p=round(float(r.p), 3)) for i, r in J.iterrows()],
    clears=int((Fr.p_ctrl <= 0.05).sum()), total=int(len(Fr)),
    expected=round(0.05 * len(Fr), 1),
    base=[dict(mkt=r.mkt, block=r.block, mc=round(float(r.mc_mean), 2),
               p_le0=round(float(r.p_le0), 3), dd_real=round(float(r.dd_real)),
               dd99=round(float(r.dd99)))
          for _i, r in V[V.rule == "(no filter -- the base)"].iterrows()])

# ---------------------------------------------------------------- cross-market controls
X = pd.read_csv("research/v41/v41_xmkt_controls.csv")
OUT["xmkt"] = [dict(mkt=r.mkt, cand=r.cand, n=int(r.n), pf=round(float(r.pf), 3),
                    usd=round(float(r.usd), 2), abl_pf=round(float(r.abl_pf), 3),
                    abl_usd=round(float(r.abl_usd), 2), p=round(float(r.p_ctrl), 3))
               for _i, r in X.iterrows()]

with open("docs/ib/v41_viz_data.json", "w") as fh:
    json.dump(OUT, fh, separators=(",", ":"))
print("wrote docs/ib/v41_viz_data.json",
      round(len(json.dumps(OUT)) / 1024, 1), "KB")
