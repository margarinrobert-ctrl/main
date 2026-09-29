"""Pick 1R strategies by excess over their OWN geometry's base rate, not by raw win rate.

The raw 60% target is not what it looks like. Base win rates at a 1R target are not 50%: costs
push them down, a wider barrier pushes them back up because the same cost is a smaller fraction
of a bigger move, and the index's drift pushes longs up and shorts down. On 60-minute bars a
long 2.5xATR 1R strategy wins 54.2% of the time on average and 59.9% at the 95th percentile --
so "60% at 1R", long, is roughly a one-in-twenty result by chance, and 156,219 of that exact
geometry were searched.

Judged against its own geometry, a short at 60% (base 45.5%) is a far stronger result than a long
at 60% (base 54.2%). This ranks by that excess, requires it on BOTH blocks, and then reads the
survivors' correlation to each other, because a list of near-duplicates is one strategy.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from oner_pick import load

MIN_RES, MIN_LOK = 60, 25


def geometry_base(Z, live, arr_n, arr_w):
    nvar = len(Z["exits"]) * 2
    v = np.arange(len(arr_n)) % nvar
    wr = np.where(arr_n > 0, 100 * arr_w / np.maximum(arr_n, 1), np.nan)
    base = np.full(nvar, np.nan)
    for vv in range(nvar):
        m = live & (v == vv)
        if m.sum() > 200:
            base[vv] = np.nanmean(wr[m])
    return wr, base[v], v


def select(tf, min_win=60.0):
    Z = load(tf)
    names = list(Z["names"]); combos = Z["combos"]; ex = Z["exits"]; nvar = len(ex) * 2
    rn, rs, rw = Z["r_n"].astype(float), Z["r_sum"].astype(float), Z["r_win"].astype(float)
    ln, ls, lw = Z["l_n"].astype(float), Z["l_sum"].astype(float), Z["l_win"].astype(float)
    live = (rn >= MIN_RES) & (ln >= MIN_LOK)
    wr_r, base_r, v = geometry_base(Z, live, rn, rw)
    wr_l = np.where(ln > 0, 100 * lw / np.maximum(ln, 1), np.nan)
    exc_r = wr_r - base_r
    exc_l = wr_l - base_r
    wr_all = np.where(rn + ln > 0, 100 * (rw + lw) / np.maximum(rn + ln, 1), np.nan)

    # RESEARCH ONLY. An earlier version of this file also required ls > 0 and exc_l > 0, which
    # puts the holdout inside the selection and makes every locked figure downstream a
    # restatement of the fit. The locked block is read once, after the choice is made.
    sel = live & (rs > 0) & (wr_r >= min_win) & (exc_r > 0)
    idx = np.flatnonzero(sel)
    idx = idx[np.argsort(-exc_r[idx])]
    rows = []
    for k in idx:
        r, vv = divmod(int(k), nvar)
        am, tp, fl = ex[vv % len(ex)]
        rows.append(dict(tf=tf, key=int(k), rule=[names[j] for j in combos[r] if j >= 0],
                         side=1 if vv < len(ex) else -1, am=float(am), flat=int(fl),
                         n=int(rn[k] + ln[k]), res=float(rs[k]), lok=float(ls[k]),
                         wr=float(wr_all[k]), wr_r=float(wr_r[k]), wr_l=float(wr_l[k]),
                         base=float(base_r[k]), exc_r=float(exc_r[k]), exc_l=float(exc_l[k])))
    return rows, dict(live=int(live.sum()), passing=int(sel.sum()))


def dedupe(rows, max_shared=1):
    """Two rules sharing two of three conditions are one idea. Keep the strongest of each."""
    keep, sets = [], []
    for r in rows:
        cs = set(r["rule"])
        if any(len(cs & s) > max_shared for s in sets):
            continue
        keep.append(r); sets.append(cs)
    return keep


if __name__ == "__main__":
    allr = []
    for tf in (15, 30, 60):
        rows, st = select(tf)
        print(f"\n{tf}m: {st['passing']:,} of {st['live']:,} clear 60% overall, beat their own "
              f"geometry's base on BOTH blocks, and are profitable on both")
        k = dedupe(rows)
        print(f"      {len(k)} remain after collapsing rules that share 2+ conditions")
        allr += k
        print(f"  {'rule':<52}{'dir':>6}{'stop':>5}{'n':>5}{'win%':>6}{'base':>6}"
              f"{'exc R':>7}{'exc L':>7}{'res $':>9}{'lok $':>9}")
        for x in k[:8]:
            print(f"  {' AND '.join(x['rule'])[:50]:<52}{'long' if x['side']==1 else 'short':>6}"
                  f"{x['am']:>5.1f}{x['n']:>5}{x['wr']:>6.1f}{x['base']:>6.1f}"
                  f"{x['exc_r']:>+7.1f}{x['exc_l']:>+7.1f}{x['res']:>9,.0f}{x['lok']:>9,.0f}")
    allr.sort(key=lambda r: -min(r["exc_r"], r["exc_l"]))
    np.save("results/oner/oner_final.npy", np.array(dedupe(allr), dtype=object), allow_pickle=True)
    print(f"\n{'='*100}\nBEST BY WORST-BLOCK EXCESS (the weakest of the two blocks, so neither can "
          f"carry it)\n{'='*100}")
    print(f"  {'rule':<50}{'tf':>4}{'dir':>6}{'stop':>5}{'n':>5}{'win%':>6}{'base':>6}"
          f"{'exc R':>7}{'exc L':>7}{'net $':>9}")
    for x in dedupe(allr)[:12]:
        print(f"  {' AND '.join(x['rule'])[:48]:<50}{x['tf']:>4}"
              f"{'long' if x['side']==1 else 'short':>6}{x['am']:>5.1f}{x['n']:>5}{x['wr']:>6.1f}"
              f"{x['base']:>6.1f}{x['exc_r']:>+7.1f}{x['exc_l']:>+7.1f}{x['res']+x['lok']:>9,.0f}")
