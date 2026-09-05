"""V42 part 3 -- freeze, read the held-back markets ONCE, and run the control that decides it.

`STUDY_TURTLE` measured this system's ENTRY against a risk-matched random-entry control on US100
240m and found +0.595 against +0.601, excess -0.005 at p 0.475. So the control is not a formality
here: it is the specific finding any winner of this search has to overturn.

FOUR configurations are carried, so the selection method is visible rather than hidden:
    TOP-MEDIAN     the single best median-of-folds cell
    SURROGATE      the modal setting of the 2,000 highest-PREDICTED cells, per axis
    NEIGHBOURHOOD  best by the median of its own +/-1 neighbourhood on every ordered axis
    SPEC           the script's own preset T1, which the search never chose -- the reference

US30 and NQ have not been touched until this file runs.
"""
from __future__ import annotations

import sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v38"); sys.path.insert(0, "research/v42")
import indicators as I       # noqa: E402
import core                  # noqa: E402
import data as TD            # noqa: E402
import v38feeds as F         # noqa: E402
import v42grid as G          # noqa: E402
import v42surro as S         # noqa: E402

OUT = "results/v42"
# cost in POINTS per unit, per instrument. US100/NQ are turtle/data.py's own recorded stack;
# US30 uses v38feeds' 2-tick assumed spread at a 1.0-point tick. All three are ASSUMPTIONS --
# no feed here carries bid/ask.
COSTS = {"US100": dict(cost_pts=1.00, slip_pts=0.25),
         "NQ": dict(cost_pts=0.72, slip_pts=0.25),
         "US30": dict(cost_pts=2.00, slip_pts=0.25)}


def prep_any(inst, tf):
    if inst in ("US100", "NQ"):
        P = G.prep(inst, tf)
        P["cost"] = COSTS[inst]
        return P
    d = F.frame("US30L", 15)
    df = pd.DataFrame({k: d[k] for k in ("o", "h", "l", "c")},
                      index=pd.to_datetime(d["ts"]))
    r = df.resample(f"{tf}min").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    o, h, l, c = (r[k].to_numpy(float) for k in ("o", "h", "l", "c"))
    atr = I.rma(I.true_range(h, l, c), 20)
    adx, _p, _m = I.adx_di(h, l, c, 14)
    ema100 = I.ema(c, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        ext = np.where(atr > 0, (c - ema100) / atr, 0.0)
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), inst=inst, tf=tf,
             idx=r.index.values.astype("datetime64[ns]").astype("int64"), cost=COSTS["US30"])
    P["hi"] = {k: I.shift(I.rmax(h, k), 1) for k in set(G.ENTRY1) | set(G.ENTRY2)}
    P["lo"] = {k: I.shift(I.rmin(l, k), 1) for k in set(G.EXIT1) | set(G.EXIT2)}
    P["gate"] = {}
    for a in G.ADX_GATE:
        ga = (np.ones(len(c), np.bool_) if a == "off" else adx < 22.0 if a == "adx<22"
              else adx >= 20.0 if a == "adx>=20" else adx >= 25.0)
        for e in G.EXT_GATE:
            ge = (np.ones(len(c), np.bool_) if e == "off" else ext < 3.193 if e == "ext<3.193"
                  else ext < 3.964 if e == "ext<3.964" else ext >= 3.0)
            P["gate"][(a, e)] = np.ascontiguousarray(ga & ge & np.isfinite(atr) & (atr > 0))
    P["fold"] = np.searchsorted(np.quantile(P["idx"], np.linspace(0, 1, G.N_FOLDS + 1)[1:-1]),
                                P["idx"])
    return P


def score(P, cfg):
    pnl, risk, tin = G.run_cell(P, cfg)
    if len(pnl) < 20:
        return None, None
    R = pnl / np.maximum(risk, 1e-9)
    f = P["fold"][tin]
    per = np.array([R[f == k].mean() if (f == k).sum() >= G.MIN_TRADES_PER_FOLD else np.nan
                    for k in range(G.N_FOLDS)])
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    return dict(n=len(pnl), med=float(np.nanmedian(per)), aggR=float(R.mean()),
                pf=float(w.sum() / abs(lo.sum())) if len(lo) else np.nan,
                folds_pos=int(np.nansum(per > 0)), folds=int(np.isfinite(per).sum()),
                pts=float(pnl.mean())), R


def control(P, cfg, n_target, draws=200, seed=101):
    """The random-entry control, matched the way `core.control` matches it.

    THE ENTRY RATE IS n_target / ELIGIBLE BARS, not n_target / all bars, and eligibility is the
    configuration's OWN gate -- so the coin flip draws from exactly the population the rule draws
    from. A first version of this function used n_target / n * 2.0, which is double the rate: it
    produced more clustered random entries, degraded the control, and made every rule look like it
    cleared at p 0.005. `STUDY_TURTLE` measured the spec on this same market and timeframe at
    p 0.475, and that disagreement is what exposed the error. A control that flatters the thing it
    tests is the one to distrust most.
    """
    g = P["gate"][(cfg["adx"], cfg["ext"])]
    start = max(cfg["entry1"], cfg["entry2"], cfg["exit1"], cfg["exit2"], 20) + 1
    elig = int(g[start:].sum())
    if elig < 50 or n_target < 5:
        return np.array([])
    p_enter = min(0.95, max(1e-5, n_target / float(elig)))
    out = []
    for s in range(draws):
        pnl, risk, _u, bi = core.run_random(
            P["o"], P["h"], P["l"], P["c"], P["lo"][cfg["exit1"]], P["lo"][cfg["exit2"]],
            P["atr"], start, float(cfg["atr_mult"]), float(cfg["pyr"]), int(cfg["units"]),
            float(p_enter), 2, P["cost"]["cost_pts"], P["cost"]["slip_pts"], seed + s)
        if len(pnl) == 0:
            continue
        sel = g[bi]
        if sel.sum() < 5:
            continue
        out.append(float((pnl[sel] / np.maximum(risk[sel], 1e-9)).mean()))
    return np.array(out)


def hdr(t):
    print("\n" + "=" * 124); print(t); print("=" * 124, flush=True)


def main():
    t0 = time.perf_counter()
    T = pd.read_parquet(f"{OUT}/v42_us100_grid.parquet")
    ORD = ["entry1", "entry2", "exit1", "exit2", "atr_mult", "pyr", "units"]
    KEYS = ORD + ["tf", "adx", "ext", "skip"]

    top = T.loc[T.median_fold.idxmax()]
    pred = pd.read_csv(f"{OUT}/v42_top_predicted.csv").nlargest(2000, "pred")
    sur = {k: (pred[k].mode().iloc[0]) for k in KEYS}
    # neighbourhood: mean median_fold over +/-1 on every ordered axis, computed on a slice
    idx = {a: {v: i for i, v in enumerate(sorted(T[a].unique()))} for a in ORD}
    key = T[KEYS].copy()
    for a in ORD:
        key[a] = key[a].map(idx[a])
    lut = dict(zip(map(tuple, key.to_numpy().tolist()), T.median_fold.to_numpy()))
    cand = T.nlargest(4000, "median_fold")
    best, bestv = None, -9e9
    for _i, r in cand.iterrows():
        k = [idx[a][r[a]] if a in ORD else r[a] for a in KEYS]
        vals = [lut[tuple(k)]]
        for a in ORD:
            j = KEYS.index(a)
            for d in (-1, 1):
                q = list(k); q[j] += d
                v = lut.get(tuple(q))
                if v is not None:
                    vals.append(v)
        mv = float(np.mean(vals))
        if mv > bestv:
            best, bestv = r, mv
    spec = dict(tf=240, entry1=20, entry2=55, exit1=10, exit2=20, atr_mult=2.0,
                pyr=0.5, units=4, adx="adx<22", ext="ext<3.964", skip=True)

    CAND = {
        "TOP-MEDIAN": {k: top[k] for k in KEYS},
        "SURROGATE": sur,
        "NEIGHBOURHOOD": {k: best[k] for k in KEYS},
        "SPEC (preset T1)": spec,
    }
    for c in CAND.values():
        for k in ("tf", "entry1", "entry2", "exit1", "exit2", "units"):
            c[k] = int(c[k])
        for k in ("atr_mult", "pyr"):
            c[k] = float(c[k])
        c["skip"] = bool(c["skip"])

    hdr("6. THE FOUR FROZEN CONFIGURATIONS")
    for nm, c in CAND.items():
        print(f"   {nm:<18} " + "  ".join(f"{k}={c[k]}" for k in KEYS))
    print(f"\n   NEIGHBOURHOOD's own median-fold {best.median_fold:+.4f}, "
          f"neighbourhood mean {bestv:+.4f}")
    print(f"   TOP-MEDIAN's own median-fold {top.median_fold:+.4f}")

    rows = []
    for mkt in ("US100", "US30", "NQ"):
        hdr(f"7. {mkt}" + ("   (the search block)" if mkt == "US100" else "   (HELD BACK -- read once, here)"))
        print(f"   {'config':<18}{'n':>6}{'median fold':>13}{'agg R':>9}{'PF':>8}"
              f"{'folds +':>9}{'control mean':>14}{'p':>8}")
        for nm, c in CAND.items():
            P = prep_any(mkt, c["tf"])
            s, _R = score(P, c)
            if s is None:
                print(f"   {nm:<18}   fewer than 20 trades"); continue
            A = control(P, c, s["n"])
            p = float(((A >= s["aggR"]).sum() + 1) / (len(A) + 1)) if len(A) else np.nan
            print(f"   {nm:<18}{s['n']:>6}{s['med']:>+13.4f}{s['aggR']:>+9.4f}{s['pf']:>8.3f}"
                  f"{s['folds_pos']:>4}/{s['folds']:<4}{np.nanmean(A):>+14.4f}{p:>8.3f}")
            rows.append(dict(mkt=mkt, cand=nm, **s, ctrl=float(np.nanmean(A)), p=p))
    pd.DataFrame(rows).to_csv(f"{OUT}/v42_frozen_readout.csv", index=False)

    R = pd.DataFrame(rows)
    hdr("8. THE CONTROL, SUMMARISED")
    held = R[R.mkt != "US100"]
    print(f"   held-back cells beating their random-entry control at p<=0.05: "
          f"{int((held.p<=0.05).sum())} of {len(held)}")
    print(f"   held-back cells with a POSITIVE excess over the control: "
          f"{int((held.aggR>held.ctrl).sum())} of {len(held)}  (chance {len(held)/2:.1f})")
    print(f"   mean excess over control, held-back markets: "
          f"{float((held.aggR-held.ctrl).mean()):+.4f} R/trade")
    print(f"\n   elapsed {time.perf_counter()-t0:.0f}s")


if __name__ == "__main__":
    main()
