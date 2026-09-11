"""THE MONTE CARLO, in full, on the locked block -- four separate questions, four separate methods.

`STUDY_V31`: a Monte Carlo that REORDERS the realised sequence cannot change the endpoint, so it
answers a DRAWDOWN question only. Bootstrap WITH REPLACEMENT for the edge, permute for the path.
And `STUDY_ATME_LIVE`: a perturbation prices execution and data noise ON THE TRADES YOU SELECTED
and can never price the SELECTION.

  1. DAY-BLOCK BOOTSTRAP -- resample whole DAYS with their trades attached (trades cluster inside a
     session, so a trade-wise bootstrap overstates the sample size).
  2. PERMUTATION -- reorder the realised trades; the endpoint is fixed, the drawdown is not.
  3. PARAMETER PERTURBATION -- every free number jittered +-10%.
  4. PRICE JITTER -- every bar's OHLC jittered, the bar repaired, and EVERY INDICATOR RECOMPUTED
     from the jittered bars, which is the only perturbation that moves the signal set itself.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(8080)
DS = {sm: V.build(sess=sm) for sm in ("ny", "utc")}
FIN = json.load(open("results/vwapema/optuna_finalists.json"))
FIN["as published"] = dict(cfg=dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False))
NB = 4000


def trades(cfg, blk=1, D=None):
    D = DS[cfg["sess"]] if D is None else D
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = V.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t[t.blk == blk].reset_index(drop=True)


def jitter_bars(D, ticks, seed):
    """Jitter OHLC, repair the bar, and recompute ATR and all three EMAs from the jittered close."""
    g = np.random.default_rng(seed)
    n = D["n"]; s = 0.01 * ticks
    o = D["o"] + g.normal(0, s, n); h = D["h"] + g.normal(0, s, n)
    l = D["l"] + g.normal(0, s, n); c = D["c"] + g.normal(0, s, n)
    hi = np.maximum.reduce([o, h, l, c]); lo = np.minimum.reduce([o, h, l, c])
    D2 = dict(D); D2["o"], D2["h"], D2["l"], D2["c"] = o, hi, lo, c
    D2["atr"] = V._atr(hi, lo, c, V.PARAMS["atr_len"])
    D2["e200"] = V._ema(c, V.PARAMS["ema_slow"]); D2["e50"] = V._ema(c, V.PARAMS["ema_pull"])
    D2["e20"] = V._ema(c, V.PARAMS["ema_tight"])
    D2["body"] = np.abs(c - o); D2["lw"] = np.minimum(o, c) - lo; D2["uw"] = hi - np.maximum(o, c)
    tp = (hi + lo + c) / 3.0
    df = pd.DataFrame({"pv": np.where(D["rth"], tp * D["v"], 0.0), "vv": np.where(D["rth"], D["v"], 0.0),
                       "tp": np.where(D["rth"], tp, 0.0), "one": np.where(D["rth"], 1.0, 0.0), "s": D["day"]})
    gg = df.groupby("s", sort=False)
    vw = (gg["pv"].cumsum() / gg["vv"].cumsum().replace(0, np.nan)).to_numpy()
    uw = (gg["tp"].cumsum() / gg["one"].cumsum().replace(0, np.nan)).to_numpy()
    vw[~D["rth"]] = np.nan; uw[~D["rth"]] = np.nan
    D2["vwap"], D2["vwap_uw"] = vw, uw
    return D2


print(__doc__)
OUT = {}
for nm, spec in FIN.items():
    cfg = spec["cfg"]
    t = trades(cfg, 1)
    if len(t) < 30:
        continue
    r = t.R.to_numpy(); days = t.date.to_numpy(); ud = np.unique(days)
    by = {d: r[days == d] for d in ud}
    # 1 day-block bootstrap: means AND equity paths
    bs, paths = [], []
    for _ in range(NB):
        pick = RNG.choice(ud, size=len(ud), replace=True)
        v = np.concatenate([by[d] for d in pick])
        bs.append(v.mean())
        if len(paths) < 400:
            paths.append(np.cumsum(v))
    bs = np.array(bs)
    # 2 permutation -> drawdown
    cum = np.cumsum(r); real_dd = float(np.max(np.maximum.accumulate(cum) - cum))
    dds = []
    for _ in range(NB):
        s = RNG.permutation(r); c2 = np.cumsum(s)
        dds.append(float(np.max(np.maximum.accumulate(c2) - c2)))
    dds = np.array(dds)
    # 3 parameter perturbation
    par = []
    for _ in range(120):
        p2 = {k: (max(2, int(round(v * RNG.uniform(0.9, 1.1)))) if isinstance(v, (int, np.integer))
                  else float(v) * RNG.uniform(0.9, 1.1)) for k, v in cfg["p"].items()}
        tt = trades(dict(cfg, p=p2), 1)
        if len(tt) >= 20:
            par.append(tt.R.mean())
    par = np.array(par)
    # 4 price jitter with indicators recomputed
    pj = []
    for k in range(60):
        D2 = jitter_bars(DS[cfg["sess"]], ticks=RNG.choice([1, 2, 4]), seed=1000 + k)
        tt = trades(cfg, 1, D=D2)
        if len(tt) >= 20:
            pj.append(tt.R.mean())
    pj = np.array(pj)
    OUT[nm] = dict(n=len(t), real_mean=float(r.mean()), real_dd=real_dd,
                   bs=bs, dds=dds, par=par, pj=pj,
                   paths=np.array([p[:min(len(x) for x in paths)] for p in paths]),
                   real_path=cum)
    print(f"  {nm:14s} n {len(t):4d}  mean {r.mean():+.4f}  P(mean<=0) {float((bs<=0).mean()):.4f}  "
          f"DD real {real_dd:.1f} p99 {np.percentile(dds,99):.1f}  "
          f"param p5 {np.percentile(par,5):+.3f}  price-jitter p5 {np.percentile(pj,5):+.3f}  "
          f"sign kept {float((pj>0).mean()):.3f}")
np.savez_compressed("results/vwapema/mc_full.npz",
                    **{f"{k}__{f}": v[f] for k, v in OUT.items()
                       for f in ("bs", "dds", "par", "pj", "paths", "real_path")},
                    meta=json.dumps({k: dict(n=v["n"], real_mean=v["real_mean"], real_dd=v["real_dd"])
                                     for k, v in OUT.items()}))
print("\n  saved results/vwapema/mc_full.npz")
