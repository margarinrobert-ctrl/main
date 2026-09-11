"""V63 stage B -- the four finalists frozen and read ONCE on every block of every market.

US100's later blocks have not been touched. US30 and NQ have had NO part in the search at all, so
they are the test, and `STUDY_V12_DONCHIAN_3020`'s shape applies: watch whether the market that
CHOSE is the one that fails.

Two nulls, because they ask different questions:
  RANDOM ENTRY        same geometry, same block, matched trade count, same position lock. Asks
                      whether the trigger and its filters are worth anything at all.
  SAME-SELECTIVITY    a random subset of the TRIGGER's own bars, of the same size. Asks whether the
  FILTER              VWAP and ATR conditions are worth anything GIVEN the trigger. Degenerate --
                      and reported as such -- for a cell that filters nothing.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V  # noqa: E402
from run_v63 import AXES  # noqa: E402

DRAWS = 1000
_C = {}


def res_for(market, tf):
    k = (market, tf)
    if k not in _C:
        _C[k] = V.run_market(market, tf)
    return _C[k]


def geo_index(Gd, cell):
    m = np.ones(len(Gd), bool)
    for a in ("stop", "trail", "tp"):
        m &= Gd[a].to_numpy() == cell[a]
    return int(np.flatnonzero(m)[0])


def set_rows(res, cell):
    K = res["K"]
    m = np.ones(len(K), bool)
    for a in ("ema", "win", "vwap", "anchor", "weight", "atrg"):
        m &= K[a].to_numpy() == cell[a]
    si = int(np.flatnonzero(m)[0])
    p = ((K["ema"].to_numpy() == cell["ema"]) & (K["win"].to_numpy() == cell["win"])
         & (K["vwap"].to_numpy() == "off") & (K["atrg"].to_numpy() == "off"))
    pi = int(np.flatnonzero(p)[0])
    o = res["offs"]
    return res["vals"][o[si]:o[si + 1]], res["vals"][o[pi]:o[pi + 1]]


def take(idx, sig_bar, xb, pts, epx, g, blk):
    free, out = -1, []
    for k in idx:
        if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or sig_bar[k] <= free:
            continue
        free = xb[k, g]
        out.append((blk[sig_bar[k]], 100.0 * float(pts[k, g]) / epx[k]))
    return out


def stat(tr, bi):
    p = np.array([x[1] for x in tr if x[0] == bi])
    if len(p) < 5:
        return None
    w = p > 0
    eq = np.cumsum(p)
    return dict(n=len(p), pct=float(p.mean()), tot=float(p.sum()),
                pf=float(p[w].sum() / max(1e-9, -p[~w].sum())), win=float(w.mean()),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)), p=p)


def boot(p, draws=4000, seed=6):
    rng = np.random.default_rng(seed)
    return float(np.mean([p[rng.integers(0, len(p), len(p))].mean() for _ in range(draws)]) * 0
                 + np.mean(np.array([p[rng.integers(0, len(p), len(p))].mean()
                                     for _ in range(draws)]) <= 0))


def filter_control(pool, sig_bar, xb, pts, epx, g, blk, nb, rate, draws=DRAWS, seed=63):
    rng = np.random.default_rng(seed)
    out = np.full((draws, nb), np.nan)
    for d in range(draws):
        tr = take(pool[rng.random(len(pool)) < rate], sig_bar, xb, pts, epx, g, blk)
        for bi in range(nb):
            q = [x[1] for x in tr if x[0] == bi]
            out[d, bi] = np.mean(q) if len(q) >= 3 else np.nan
    return out


def entry_control(D, cell, n_target, bi, blk, draws=400, seed=17):
    pool = np.flatnonzero((blk == bi) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    pool = pool[(pool > 300) & (pool < D["n"] - V.HOLD - 5)]
    if len(pool) < 50:
        return np.zeros(0)
    rng = np.random.default_rng(seed)
    out = np.full(draws, np.nan)
    for d in range(draws):
        r = np.sort(rng.choice(pool, size=min(len(pool), n_target * 4), replace=False))
        xb, pt = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], r.astype(np.int64),
                           np.array([cell["stop"]]), np.array([cell["trail"]]),
                           np.array([cell["tp"]]), D["cost"], D["slip"], V.HOLD, D["n"])
        free, p = -1, []
        for j in range(len(r)):
            if xb[j, 0] < 0 or not np.isfinite(pt[j, 0]) or r[j] <= free:
                continue
            free = xb[j, 0]
            p.append(100.0 * float(pt[j, 0]) / D["o"][r[j] + 1])
        if len(p) >= 3:
            out[d] = np.mean(p[:n_target])
    return out[np.isfinite(out)]


def main():
    print(__doc__)
    fin = pd.read_csv("results/v63/finalists.csv")
    print("=" * 122)
    print(f"  {'cell':34s} {'market':7s} {'block':11s} {'n':>5s} {'pct/tr':>8s} {'total':>8s} "
          f"{'PF':>5s} {'win':>6s} {'DD':>6s} {'boot':>6s} | {'filter p':>9s} | {'entry p':>8s}")
    rows = []
    for _, f in fin.iterrows():
        cell = {a: f[a] for a in AXES}
        cell["win"] = int(cell["win"])
        cell["ema"] = str(cell["ema"])
        for market in V.FEEDSORDER:
            res = res_for(market, int(cell["tf"]))
            D, blk, names = res["D"], res["blk"], res["names"]
            g = geo_index(res["G"], cell)
            sel, pool = set_rows(res, cell)
            tr = take(sel, res["rows"], res["xb"], res["pts"], res["epx"], g, blk)
            rate = len(sel) / max(len(pool), 1)
            fc = filter_control(pool, res["rows"], res["xb"], res["pts"], res["epx"], g, blk,
                                len(names), rate)
            for bi, nm in enumerate(names):
                s = stat(tr, bi)
                if s is None:
                    continue
                c = fc[:, bi][np.isfinite(fc[:, bi])]
                pf_p = float(np.mean(c >= s["pct"])) if len(c) and rate < 0.999 else np.nan
                ec = entry_control(D, cell, s["n"], bi, blk)
                pe = float(np.mean(ec >= s["pct"])) if len(ec) else np.nan
                print(f"  {f['name']:34s} {market:7s} {nm:11s} {s['n']:5d} {s['pct']:+8.4f} "
                      f"{s['tot']:+8.2f} {s['pf']:5.2f} {100*s['win']:5.1f}% {s['dd']:6.2f} "
                      f"{boot(s['p']):6.3f} | {pf_p:9.3f} | {pe:8.3f}")
                rows.append(dict(name=f["name"], market=market, block=nm,
                                 **{f"c_{k}": v for k, v in cell.items()}, n=s["n"],
                                 pct=s["pct"], tot=s["tot"], pf=s["pf"], win_rate=s["win"],
                                 dd=s["dd"], filter_p=pf_p, entry_p=pe, keep=rate))
            print(f"     {market}: keeps {100*rate:.1f}% of {len(pool)} trigger bars")
        print()
    pd.DataFrame(rows).to_csv("results/v63/frozen.csv", index=False)


if __name__ == "__main__":
    main()
