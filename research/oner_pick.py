"""Which 1R strategies clear 60%, and how many of them are luck.

Search width is the whole problem here. Four million 1R strategies contain plenty that beat 60%
on a research block by accident, so every number below is quoted against what chance alone would
produce, and the survivors are read once on a locked block they were not selected on.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")

BOUND = 50.0          # a driftless path wins 1/(1+R) = 50% at a 1R target


def load(tf):
    Z = np.load(f"results/oner/oner_{tf}m.npz", allow_pickle=True)
    return {k: Z[k] for k in Z.files}


def table(tf, min_res=60, min_lok=25, target_win=60.0):
    Z = load(tf)
    names = list(Z["names"]); combos = Z["combos"]; ex = Z["exits"]
    nvar = len(ex) * 2
    rn, rs, rw = Z["r_n"].astype(float), Z["r_sum"].astype(float), Z["r_win"].astype(float)
    ln, ls, lw = Z["l_n"].astype(float), Z["l_sum"].astype(float), Z["l_win"].astype(float)
    live = (rn >= min_res) & (ln >= min_lok)
    wr_r = np.where(rn > 0, 100 * rw / np.maximum(rn, 1), 0.0)
    wr_l = np.where(ln > 0, 100 * lw / np.maximum(ln, 1), 0.0)
    wr_a = np.where(rn + ln > 0, 100 * (rw + lw) / np.maximum(rn + ln, 1), 0.0)
    prof = (rs > 0) & (ls > 0)

    print(f"\n{'='*96}\n{tf}-MINUTE BARS\n{'='*96}")
    print(f"  {live.sum():,} of {len(rn):,} 1R strategies have {min_res}+ research and "
          f"{min_lok}+ locked trades")
    print(f"  profitable on BOTH blocks: {prof[live].sum():,} ({100*prof[live].mean():.1f}%)")
    print(f"  mean research win rate across all live 1R strategies: {wr_r[live].mean():.2f}% "
          f"(the driftless bound is {BOUND:.0f}%)")
    for thr in (55, 58, 60, 62, 65):
        a = (wr_r >= thr) & live
        b = a & (wr_l >= thr)
        print(f"    research win >= {thr}%: {a.sum():>7,}   "
              f"of those, locked win >= {thr}% too: {b.sum():>6,} "
              f"({100*b.sum()/max(a.sum(),1):>5.1f}%)")

    sel = live & prof & (wr_r >= target_win) & (wr_l >= target_win)
    print(f"\n  CLEARING {target_win:.0f}% ON BOTH BLOCKS AND PROFITABLE ON BOTH: {sel.sum():,}")
    if sel.sum() == 0:
        return []
    idx = np.flatnonzero(sel)
    idx = idx[np.argsort(-(rs[idx] + ls[idx]))]
    out = []
    for k in idx[:25]:
        r, vv = divmod(int(k), nvar)
        side = 1 if vv < len(ex) else -1
        am, tp, fl = ex[vv % len(ex)]
        rule = [names[j] for j in combos[r] if j >= 0]
        out.append(dict(tf=tf, rule=rule, side=side, am=float(am), tp=float(tp), flat=int(fl),
                        n=int(rn[k] + ln[k]), res=float(rs[k]), lok=float(ls[k]),
                        wr_r=float(wr_r[k]), wr_l=float(wr_l[k]), wr=float(wr_a[k])))
    return out


if __name__ == "__main__":
    tfs = [int(x) for x in sys.argv[1:]] or [30, 15, 60]
    allrows = []
    for tf in tfs:
        rows = table(tf)
        allrows += rows
        if rows:
            print(f"  {'rule':<58}{'dir':>5}{'stop':>6}{'n':>6}{'win%':>7}"
                  f"{'res win%':>10}{'lok win%':>10}{'research $':>12}{'locked $':>11}")
            for x in rows[:12]:
                print(f"  {' AND '.join(x['rule'])[:56]:<58}"
                      f"{'long' if x['side']==1 else 'short':>5}{x['am']:>6.1f}{x['n']:>6}"
                      f"{x['wr']:>7.1f}{x['wr_r']:>10.1f}{x['wr_l']:>10.1f}"
                      f"{x['res']:>12,.0f}{x['lok']:>11,.0f}")
    np.save("results/oner/oner_survivors.npy", np.array(allrows, dtype=object), allow_pickle=True)
    print(f"\n{len(allrows)} survivors saved")
