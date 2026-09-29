"""The 110-cell ADX x CHOP grid on the V20 base. Population first, ranking second, locked third."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v21")
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402
import v21regime as V        # noqa: E402


def hdr(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


def sweep(block_name):
    """Every cell, pooled across markets in R. Returns a tidy frame."""
    rows = []
    CT = {k: V.ctx(k) for k in L.MARKETS}
    BL = {k: L.blocks(CT[k]) for k in L.MARKETS}
    for a in V.ADX_GRID:
        for ch in V.CHOP_GRID:
            allr, per, ns = [], {}, 0
            for k in L.MARKETS:
                P = CT[k]
                blk = BL[k][0] if block_name == "research" else BL[k][1]
                O, i = V.run(P, a, ch, blk)
                r = O["R"][i]
                allr.append(r)
                ns += len(i)
                w, lo = r[r > 0], r[r < 0]
                per[k] = float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan
            r, pf = V.pooled(allr)
            kind = ("none" if a == 0 and ch == 100 else
                    "ADX alone" if ch == 100 else
                    "CHOP alone" if a == 0 else "both")
            rows.append(dict(adx=a, chop=ch, kind=kind, n=ns, pf=pf, ev=float(r.mean()),
                             net=float(r.sum()),
                             mkts_pf1=int(sum(1 for v in per.values() if np.isfinite(v) and v > 1)),
                             **{f"pf_{k}": per[k] for k in L.MARKETS}))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    res = sweep("research")
    lock = sweep("locked")
    res.to_csv("results/v21/v21_res.csv", index=False)
    lock.to_csv("results/v21/v21_lock.csv", index=False)
    j = res.merge(lock[["adx", "chop", "pf", "ev", "n", "mkts_pf1"]], on=["adx", "chop"],
                  suffixes=("", "_lk"))

    base = res[(res.adx == 0) & (res.chop == 100)].iloc[0]
    basel = lock[(lock.adx == 0) & (lock.chop == 100)].iloc[0]

    hdr("0. THE POPULATION, BEFORE ANY RANKING")
    print(f"   base with no regime filter at all : research PF {base.pf:.3f} on {int(base.n):,} "
          f"trades, EV {base.ev:+.4f}   |   locked PF {basel.pf:.3f} on {int(basel.n):,}, "
          f"EV {basel.ev:+.4f}")
    print(f"   110 cells. Research: {float((res.pf > 1).mean()):.0%} have PF > 1, median PF "
          f"{res.pf.median():.3f}, median EV {res.ev.median():+.4f}")
    print(f"                Locked: {float((lock.pf > 1).mean()):.0%} have PF > 1, median PF "
          f"{lock.pf.median():.3f}, median EV {lock.ev.median():+.4f}")
    print(f"   correlation between a cell's RESEARCH PF and its LOCKED PF: "
          f"{np.corrcoef(j.pf, j.pf_lk)[0, 1]:+.3f}")
    print("\n   That last number is the one that decides whether any ranking below is worth reading.")

    hdr("1. ADX ALONE -- every floor, no chop filter")
    print(f"   {'ADX floor':>10}{'n':>8}{'PF':>8}{'EV(R)':>9}{'mkts PF>1':>11}"
          f"{'LOCKED n':>10}{'LOCKED PF':>11}{'LOCKED EV':>11}")
    for _, r in res[(res.chop == 100)].sort_values("adx").iterrows():
        lk = j[(j.adx == r.adx) & (j.chop == 100)].iloc[0]
        tag = "  <- none" if r.adx == 0 else ""
        print(f"   {int(r.adx):>10}{int(r.n):>8}{r.pf:>8.3f}{r.ev:>+9.4f}{int(r.mkts_pf1):>8}/5"
              f"{int(lk.n_lk):>10}{lk.pf_lk:>11.3f}{lk.ev_lk:>+11.4f}{tag}")

    hdr("2. CHOP ALONE -- every ceiling, no ADX filter")
    print(f"   {'CHOP ceiling':>13}{'n':>8}{'PF':>8}{'EV(R)':>9}{'mkts PF>1':>11}"
          f"{'LOCKED n':>10}{'LOCKED PF':>11}{'LOCKED EV':>11}")
    for _, r in res[(res.adx == 0)].sort_values("chop", ascending=False).iterrows():
        lk = j[(j.adx == 0) & (j.chop == r.chop)].iloc[0]
        tag = "  <- none" if r.chop == 100 else ""
        print(f"   {int(r.chop):>13}{int(r.n):>8}{r.pf:>8.3f}{r.ev:>+9.4f}{int(r.mkts_pf1):>8}/5"
              f"{int(lk.n_lk):>10}{lk.pf_lk:>11.3f}{lk.ev_lk:>+11.4f}{tag}")

    hdr("3. THE TOP 20 BY PROFIT FACTOR, AS ASKED -- ranked on RESEARCH, read on LOCKED")
    print("   Sorted by research PF. `n` is the trade count, because a profit factor without one is")
    print("   not a number. The last three columns are the SAME cell on the locked block.\n")
    print(f"   {'#':>3}{'kind':<12}{'ADX':>5}{'CHOP':>6}{'n':>7}{'PF':>8}{'EV(R)':>9}"
          f"{'mkts':>6}{'|':>3}{'LOCK n':>8}{'LOCK PF':>9}{'LOCK EV':>10}{'kept?':>8}")
    top = j.sort_values("pf", ascending=False).head(20)
    for rank, (_, r) in enumerate(top.iterrows(), 1):
        kept = "yes" if r.pf_lk > 1 else "NO"
        print(f"   {rank:>3}{r.kind:<12}{int(r.adx):>5}{int(r.chop):>6}{int(r.n):>7}{r.pf:>8.3f}"
              f"{r.ev:>+9.4f}{int(r.mkts_pf1):>4}/5{'|':>3}{int(r.n_lk):>8}{r.pf_lk:>9.3f}"
              f"{r.ev_lk:>+10.4f}{kept:>8}")
    print(f"\n   Of the top 20 on research, {int((top.pf_lk > 1).sum())} still have PF > 1 on locked.")
    print(f"   Of all 110 cells, {int((lock.pf > 1).sum())} do -- so the ranking "
          f"{'beat' if (top.pf_lk > 1).mean() > (lock.pf > 1).mean() else 'did not beat'} "
          f"picking at random ({float((top.pf_lk > 1).mean()):.0%} against "
          f"{float((lock.pf > 1).mean()):.0%}).")

    hdr("4. WHAT THE GRID LOOKS LIKE BY FAMILY -- marginal medians, not the best cell")
    g = j.groupby("kind").agg(cells=("pf", "size"), med_pf=("pf", "median"),
                              med_pf_lk=("pf_lk", "median"), med_ev=("ev", "median"),
                              med_ev_lk=("ev_lk", "median"),
                              pos_lk=("pf_lk", lambda x: float((x > 1).mean())))
    print(f"   {'family':<14}{'cells':>7}{'research PF':>13}{'LOCKED PF':>12}"
          f"{'research EV':>13}{'LOCKED EV':>12}{'% PF>1 locked':>15}")
    for k, r in g.iterrows():
        print(f"   {k:<14}{int(r.cells):>7}{r.med_pf:>13.3f}{r.med_pf_lk:>12.3f}"
              f"{r.med_ev:>+13.4f}{r.med_ev_lk:>+12.4f}{r.pos_lk:>14.0%}")
