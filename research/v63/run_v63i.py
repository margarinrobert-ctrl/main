"""V63 stage I -- Monte Carlo, robustness, and a walk-forward that RE-CHOOSES the session.

THE WALK-FORWARD IS THE POINT. The question the user asked -- add a start time, a stop time and a
flatten -- is a question about three parameters, and the honest way to price a parameter is to let
an optimiser pick it inside each training fold and then read the fold it has never seen. This
branch has run that test four times (`STUDY_IBS_SESSION`, `STUDY_APM_VWAP`, `STUDY_TRENDDAY_EMA`,
`STUDY_V60`) and the re-optimiser lost to the author's fixed constants every time. Fifth run.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V         # noqa: E402
import v63sess as S         # noqa: E402
from run_v63d import FINAL  # noqa: E402

STOPS = (1.5, 2.0, 2.5, 3.0)
FOLDS = 8
CACHE = {}


def prep(market, cost_mult=1.0):
    key = (market, round(cost_mult, 3))
    if key in CACHE:
        return CACHE[key]
    D, rows = S.base_rows(market)
    flats = [-1] + sorted({w[1] for w in S.WINDOWS.values() if w})
    geo = [(s, f) for s in STOPS for f in flats]
    xb, pts, why = S.walk(D, rows, [g[0] for g in geo], [g[1] for g in geo], cost_mult)
    mod = S.mod_of(D)
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    CACHE[key] = (D, rows, xb, pts, why, epx, mod, geo, flats)
    return CACHE[key]


def cell_trades(market, window, flat, stop, cost_mult=1.0):
    D, rows, xb, pts, why, epx, mod, geo, flats = prep(market, cost_mult)
    w = S.WINDOWS[window]
    keep = (np.arange(len(rows)) if w is None
            else np.flatnonzero((mod[rows] >= w[0]) & (mod[rows] < w[1])))
    g = geo.index((stop, w[1] if flat else -1))
    return D, S.lock(rows, keep, xb, pts, why, epx, g)


def grid_cells():
    out = []
    for wname, w in S.WINDOWS.items():
        for fl in (False, True):
            if fl and w is None:
                continue
            for st in STOPS:
                out.append((wname, fl, st))
    return out


SHIP = (FINAL["ema"], "all hours", False, float(FINAL["stop"]))


def main():
    print(__doc__)
    variants = {
        "SHIPPED  all hours, no flatten": ("all hours", False, 1.5),
        "window 09:30-12:00, no flatten": ("09:30-12:00", False, 1.5),
        "window 09:30-16:00 + FLATTEN":   ("09:30-16:00", True, 1.5),
        "window 13:00-16:00 + FLATTEN":   ("13:00-16:00", True, 1.5),
    }

    print("=" * 118)
    print("I1. MONTE CARLO on the pooled out-of-sample trades -- day-block bootstrap for the EDGE,")
    print("    permutation for the PATH. Blocks from three markets over overlapping calendars are")
    print("    not independent, so the interval is optimistic; the comparison between rows is not.")
    print("=" * 118)
    print(f"  {'variant':34s} {'n':>5s} {'pct/tr':>9s} {'P(mean<=0)':>11s} {'95% CI':>20s} "
          f"{'realDD':>7s} {'MCp99':>7s} {'pctile':>7s}")
    store = {}
    for lab, (wn, fl, st) in variants.items():
        allp, days = [], []
        for m in V.FEEDSORDER:
            D, tr = cell_trades(m, wn, fl, st)
            blk = D["blocks"]
            names = list(blk.keys())
            ix = pd.DatetimeIndex(D["ix"])
            key = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
            for t in tr:
                bi = next((i for i, nm in enumerate(names)
                           if np.asarray(blk[nm], bool)[t[0]]), -1)
                if bi < 0 or (m == "US100" and names[bi] == "research"):
                    continue
                allp.append(t[1])
                days.append(f"{m}{key[t[0]]}")
        p = np.array(allp)
        store[lab] = (p, np.array(days))
        g = pd.Series(p).groupby(days).apply(lambda x: x.to_numpy())
        arrs = list(g.values)
        rng = np.random.default_rng(21)
        mb = np.array([np.concatenate([arrs[i] for i in rng.integers(0, len(arrs), len(arrs))]).mean()
                       for _ in range(4000)])
        def dd(x):
            eq = np.cumsum(x)
            return float(np.max(np.maximum.accumulate(eq) - eq))
        pm = np.array([dd(rng.permutation(p)) for _ in range(4000)])
        print(f"  {lab:34s} {len(p):5d} {p.mean():+9.4f} {np.mean(mb <= 0):11.4f} "
              f"[{np.percentile(mb,2.5):+.4f},{np.percentile(mb,97.5):+.4f}] {dd(p):7.2f} "
              f"{np.percentile(pm,99):7.2f} {np.mean(pm <= dd(p)):7.2f}")

    print("\n" + "=" * 118)
    print("I2. ROBUSTNESS -- cost stress, and the stop ladder, pooled over the same blocks")
    print("=" * 118)
    for lab, (wn, fl, st) in variants.items():
        line = f"  {lab:34s} cost"
        for cm in (0.0, 1.0, 2.0, 4.0):
            tot = n = 0.0
            for m in V.FEEDSORDER:
                D, tr = cell_trades(m, wn, fl, st, cost_mult=cm)
                names = list(D["blocks"].keys())
                for t in tr:
                    bi = next((i for i, nm in enumerate(names)
                               if np.asarray(D["blocks"][nm], bool)[t[0]]), -1)
                    if bi < 0 or (m == "US100" and names[bi] == "research"):
                        continue
                    tot += t[1]; n += 1
            line += f"  x{cm:.0f} {tot/max(n,1):+.4f}"
        line += "   stops"
        for s2 in STOPS:
            tot = n = 0.0
            for m in V.FEEDSORDER:
                D, tr = cell_trades(m, wn, fl, s2)
                names = list(D["blocks"].keys())
                for t in tr:
                    bi = next((i for i, nm in enumerate(names)
                               if np.asarray(D["blocks"][nm], bool)[t[0]]), -1)
                    if bi < 0 or (m == "US100" and names[bi] == "research"):
                        continue
                    tot += t[1]; n += 1
            line += f"  {s2}N {tot/max(n,1):+.4f}"
        print(line)

    print("\n" + "=" * 118)
    print("I3. WALK-FORWARD OPTIMISATION -- the session and the stop re-chosen inside every")
    print(f"    training fold from {len(grid_cells())} declared cells, then applied to the fold it")
    print("    has never seen. Both an EXPANDING and a ROLLING training window.")
    print("=" * 118)
    cells = grid_cells()
    for m in V.FEEDSORDER:
        D, _ = cell_trades(m, "all hours", False, 1.5)
        n = D["n"]
        edges = np.linspace(300, n - V.HOLD - 6, FOLDS + 1).astype(int)
        # every cell's trades once, indexed by signal bar
        tr = {}
        for c in cells:
            _, t = cell_trades(m, c[0], c[1], c[2])
            tr[c] = (np.array([x[0] for x in t]), np.array([x[1] for x in t]))
        def score(c, lo, hi):
            b, p = tr[c]
            k = (b >= lo) & (b < hi)
            return (float(p[k].sum()), int(k.sum()))
        for mode in ("expanding", "rolling 2 folds"):
            picks, wf, fixed = [], [], []
            for i in range(2, FOLDS):
                lo = edges[0] if mode == "expanding" else edges[i - 2]
                trainlo, trainhi = lo, edges[i]
                testlo, testhi = edges[i], edges[i + 1]
                best, bs = None, -1e18
                for c in cells:
                    s, k = score(c, trainlo, trainhi)
                    if k < 20:
                        continue
                    if s > bs:
                        bs, best = s, c
                if best is None:
                    continue
                picks.append(best)
                wf.append(score(best, testlo, testhi))
                fixed.append(score(SHIP[1:], testlo, testhi))
            wn = sum(x[1] for x in wf); wt = sum(x[0] for x in wf)
            fn = sum(x[1] for x in fixed); ft = sum(x[0] for x in fixed)
            pos_w = sum(1 for x in wf if x[0] > 0)
            pos_f = sum(1 for x in fixed if x[0] > 0)
            print(f"  {m:7s} {mode:16s} re-chosen: n {wn:4d} {wt/max(wn,1):+.4f} %/trade "
                  f"({pos_w}/{len(wf)} folds +)   fixed: n {fn:4d} {ft/max(fn,1):+.4f} "
                  f"({pos_f}/{len(fixed)} folds +)   WFE "
                  f"{(wt/max(wn,1))/max(ft/max(fn,1),1e-9):5.2f}")
            cnt = pd.Series([f"{p[0]}{' +flat' if p[1] else ''} {p[2]}N" for p in picks])
            print(f"  {'':7s} {'':16s} chose: " + ", ".join(cnt.value_counts().index[:4])
                  + f"   flatten chosen in {sum(1 for p in picks if p[1])}/{len(picks)} folds")


if __name__ == "__main__":
    main()
