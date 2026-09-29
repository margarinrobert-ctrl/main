"""V61 stage C -- the second null, the neighbourhood on the locked block, and the live tests.

B measured each cell against a random FILTER of the same selectivity. That is the right null for a
filter and the WRONG null for a cell that filters nothing: F2 keeps 100% of its entry channel, so
its "control" is itself and its p-value is 1.000 by construction. The null a trigger has to beat
is a RANDOM ENTRY with the same geometry (`STUDY_V11`), and it is run here for every candidate.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v56"))
import v61core as V            # noqa: E402
import v56core as K            # noqa: E402
from run_v61 import AXES       # noqa: E402
from run_v61b import tf_data, geo_index, set_rows, take, stats  # noqa: E402

CANDS = ["S  shipped (the incumbent)", "F2 top research total", "F1 marginal consensus",
         "G2 CVD kept: top total", "F3 best neighbourhood mean"]
DRAWS = 1000


def walk_cell(D, cell, rows, cost_mult=1.0):
    exlo = D["ex_lo"][int(cell["exN"])]
    if int(cell["adapt"]) == 0:
        return K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo,
                      float(cell["stop"]), float(cell["tp"]), V.COST * cost_mult,
                      V.SLIP * cost_mult, int(cell["hold"]), 0)
    calm = np.isfinite(D["vpct"]) & (D["vpct"] <= 0.5)
    a = rows[calm[rows]]
    b = rows[~calm[rows]]
    out = [np.full(len(rows), -1, np.int64), np.full(len(rows), np.nan), np.zeros(len(rows), np.int64)]
    for sub, mult in ((a, float(cell["stop"])), (b, float(cell["stop"]) - 1.0)):
        if not len(sub):
            continue
        x, r, w = K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sub.astype(np.int64), exlo,
                         mult, float(cell["tp"]), V.COST * cost_mult, V.SLIP * cost_mult,
                         int(cell["hold"]), 0)
        pos = np.searchsorted(rows, sub)
        out[0][pos], out[1][pos], out[2][pos] = x, r, w
    return out[0], out[1], out[2]


def lock_pct(D, cell, rows, xb, R, blk):
    cut = D["cut"]
    free, p = -1, []
    for j in range(len(rows)):
        if xb[j] < 0 or not np.isfinite(R[j]) or rows[j] <= free:
            continue
        free = xb[j]
        keep = rows[j] < cut if blk == "res" else rows[j] >= cut
        if keep:
            risk = float(cell["stop"]) * D["atr"][rows[j]]
            p.append(100.0 * R[j] * risk / D["o"][rows[j] + 1])
    return np.asarray(p)


def random_entry(D, cell, n_target, blk, draws=DRAWS, seed=11):
    """Random bars in the same block, same geometry, same lock, matched on trade count."""
    cut = D["cut"]
    lo = 1000 if blk == "res" else cut
    hi = cut if blk == "res" else D["n"] - max(V.HOLDS) - 5
    pool = np.arange(lo, hi)
    pool = pool[np.isfinite(D["atr"][pool]) & (D["atr"][pool] > 0)]
    rng = np.random.default_rng(seed)
    out = np.full(draws, np.nan)
    for d in range(draws):
        r = np.sort(rng.choice(pool, size=min(len(pool), int(n_target * 3)), replace=False))
        xb, R, _ = walk_cell(D, cell, r)
        p = lock_pct(D, cell, r, xb, R, blk)
        if len(p) >= 3:
            out[d] = p[:n_target].mean() if len(p) > n_target else p.mean()
    return out[np.isfinite(out)]


def main():
    print(__doc__)
    fin = pd.read_csv("results/v61/finalists.csv").set_index("name")
    grid = pd.read_parquet("results/v61/grid.parquet")

    print("=" * 112)
    print("C1. THE RANDOM-ENTRY CONTROL -- same geometry, same block, same trade count, same lock")
    print("=" * 112)
    print(f"  {'cell':28s} {'block':6s} {'n':>4s} {'rule':>9s} {'random':>9s} {'p':>7s}")
    for name in CANDS:
        f = fin.loc[name]
        cell = {a: f[a] for a in AXES}
        D, res = tf_data(int(cell["tf"]))
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(D, res, cell)
        tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
        for blk in ("res", "lock"):
            s = stats(tr, D["cut"], blk)
            if s is None:
                continue
            c = random_entry(D, cell, s["n"], blk)
            p = float(np.mean(c >= s["pct"])) if len(c) else np.nan
            print(f"  {name:28s} {blk:6s} {s['n']:4d} {s['pct']:+9.4f} "
                  f"{np.median(c):+9.4f} {p:7.3f}")

    print("\n" + "=" * 112)
    print("C2. THE ONE-RUNG NEIGHBOURHOOD, READ ON BOTH BLOCKS")
    print("=" * 112)
    ORD = {"ent": V.ENTS, "exN": V.EXITS, "stop": V.STOPS, "tp": V.TPS, "ma": V.MA200,
           "chop": V.CHOPS}
    for name in CANDS:
        f = fin.loc[name]
        cell = {a: f[a] for a in AXES}
        rows = []
        for a, lev in ORD.items():
            lev = list(lev)
            i = lev.index(cell[a])
            for j in (i - 1, i + 1):
                if not (0 <= j < len(lev)):
                    continue
                m = np.ones(len(grid), bool)
                for b in AXES:
                    m &= grid[b].to_numpy() == (lev[j] if b == a else cell[b])
                s = grid[m]
                if len(s) and s.iloc[0]["n_res"] >= 20 and s.iloc[0]["n_lock"] >= 10:
                    rows.append((a, lev[j], float(s.iloc[0]["pct_res"]), float(s.iloc[0]["pct_lock"])))
        if not rows:
            continue
        r = np.array([[x[2], x[3]] for x in rows])
        print(f"  {name:28s} {len(rows):2d} neighbours   research {100*(r[:,0]>0).mean():3.0f}% "
              f"profitable (mean {r[:,0].mean():+.4f})   locked {100*(r[:,1]>0).mean():3.0f}% "
              f"(mean {r[:,1].mean():+.4f})")

    print("\n" + "=" * 112)
    print("C3. COST STRESS AND C4. SIX CHRONOLOGICAL FOLDS")
    print("=" * 112)
    for name in CANDS[:4]:
        f = fin.loc[name]
        cell = {a: f[a] for a in AXES}
        D, res = tf_data(int(cell["tf"]))
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(D, res, cell)
        line = f"  {name:28s} cost"
        for cm in (0.0, 1.0, 2.0, 4.0):
            xb, R, _ = walk_cell(D, cell, res["rows"][sel], cost_mult=cm)
            p = lock_pct(D, cell, res["rows"][sel], xb, R, "lock")
            line += f"  x{cm:.0f} {p.mean():+.4f}"
        tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
        allp = np.array([t[2] for t in tr])
        bars = np.array([t[0] for t in tr])
        o = np.argsort(bars)
        parts = np.array_split(allp[o], 6)
        line += "   folds " + " ".join(f"{x.mean():+.3f}" for x in parts if len(x))
        print(line)

    print("\n" + "=" * 112)
    print("C5. FUNDED EVALUATION on the LOCKED block -- 60 trading days, +8% / -6% static, a 3%")
    print("    daily loss limit, sampled over EVERY session zero-filled, notional leverage swept")
    print("=" * 112)
    for name in CANDS[:4]:
        f = fin.loc[name]
        cell = {a: f[a] for a in AXES}
        D, res = tf_data(int(cell["tf"]))
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(D, res, cell)
        tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
        s = stats(tr, D["cut"], "lock")
        ix = pd.DatetimeIndex(D["ix"])
        key = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
        nd = len(np.unique(key[D["cut"]:]))
        daily = pd.Series(s["p"]).groupby(key[s["days"]]).sum().to_numpy()
        d = np.zeros(nd)
        d[: len(daily)] = daily
        line = f"  {name:28s}"
        for L in (2, 4, 6, 8):
            x = d * L / 100.0
            rng = np.random.default_rng(7)
            np_, nb = 0, 0
            for _ in range(4000):
                eq, done = 1.0, 0
                for v in x[rng.integers(0, len(x), 60)]:
                    eq *= 1.0 + max(v, -0.03)
                    if eq <= 0.94:
                        done = -1; break
                    if eq >= 1.08:
                        done = 1; break
                np_ += done == 1; nb += done == -1
            line += (f"  x{L}: pass {100*np_/4000:4.1f} bust {100*nb/4000:4.1f} "
                     f"nei {100*(4000-np_-nb)/4000:4.1f}")
        print(line)


if __name__ == "__main__":
    main()
