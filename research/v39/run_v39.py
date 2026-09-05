"""V39 -- the Monte Carlo table: every individual indicator rule, three markets, both blocks.

Usage: python3 research/v39/run_v39.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
import indicators as I       # noqa: E402
import fastbars as FB        # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v39mc as M            # noqa: E402

TF = 30
MARKETS = ("NQ", "US30L", "US100L")


def hdr(t):
    print("\n" + "=" * 132)
    print(t)
    print("=" * 132, flush=True)


def ctx(mkt):
    if mkt == "NQ":
        d = FB.bars(TF)
        P = G.prep(TF, d=d)
        P["v"] = d["v"]
    else:
        d = F.frame(mkt, TF)
        P = G.prep(TF, d=d, pv=F.INSTR[mkt]["pv"])
        P["v"] = None
    P["mkt"] = mkt
    return P


def main():
    t0 = time.perf_counter()
    hdr("V39 -- MONTE CARLO MEAN OF EVERY INDIVIDUAL INDICATOR RULE")
    print("   base: Donchian 30 entry / 20-bar channel exit / 2.0xATR(14) stop / NO take profit /")
    print("         one unit / LONG / market order at the next open / real per-instrument costs.")
    print(f"   {M.DRAWS:,}-draw day-block bootstrap for the EDGE, {M.DRAWS:,} permutations for the")
    print(f"   PATH, and a {M.CTRL}-draw same-selectivity control so restrictiveness alone cannot")
    print("   pass. Each indicator is added to the base ALONE.")

    rows = []
    for mkt in MARKETS:
        P = ctx(mkt)
        ten = G.tensor(P)
        xb, pnl, _w = ten[(M.BASE["exit_n"], M.BASE["stop_n"], M.BASE["tp_r"])]
        brk = P["c"] > I.shift(I.rmax(P["h"], M.BASE["entry_n"]), 1)
        ok = np.isfinite(P["atr"]) & (xb >= 0)
        day = P["day"]
        u = np.unique(day)
        cut = u[int(len(u) * 0.65)]
        blocks = (("research", day < cut), ("LOCKED", day >= cut))
        R = M.rules(P)
        for bname, bm in blocks:
            pool = np.flatnonzero(brk & ok & bm)
            bp, bs = M.gather(P, xb, pnl, pool)
            if len(bp) < 20:
                continue
            bb = M.boot(bp, day[bs])
            rows.append(dict(mkt=mkt, block=bname, rule="(no filter -- the base)", n=len(bp),
                             usd=float(bp.mean()), **bb, **M.perm(bp), p_ctrl=np.nan))
            for rn, rm in R.items():
                sig = np.flatnonzero(brk & ok & bm & np.nan_to_num(rm, nan=False).astype(bool))
                p, sb = M.gather(P, xb, pnl, sig)
                if len(p) < 20:
                    continue
                A = M.control(P, xb, pnl, pool, len(sb))
                rows.append(dict(mkt=mkt, block=bname, rule=rn, n=len(p),
                                 usd=float(p.mean()), **M.boot(p, day[sb]), **M.perm(p),
                                 p_ctrl=float(((A >= p.mean()).sum() + 1) / (len(A) + 1))))
        print(f"   {mkt}: {P['n']:,} bars, {len(R)} rules scored on both blocks "
              f"({time.perf_counter() - t0:.0f}s)")
    T = pd.DataFrame(rows)
    T.to_csv("research/v39/v39_mc.csv", index=False)

    for mkt in MARKETS:
        hdr(f"{mkt} -- bootstrap mean $/trade with a 5th-95th interval, and the control p")
        print(f"   {'rule':<32}{'blk':<9}{'n':>5}{'MC mean':>10}{'5th':>9}{'95th':>9}"
              f"{'P(<=0)':>8}{'ctrl p':>8}   {'blk':<9}{'n':>5}{'MC mean':>10}{'P(<=0)':>8}{'ctrl p':>8}")
        sub = T[T.mkt == mkt]
        r_ = sub[sub.block == "research"].set_index("rule")
        l_ = sub[sub.block == "LOCKED"].set_index("rule")
        order = ["(no filter -- the base)"] + [x for x in r_.index if x != "(no filter -- the base)"]
        for rule in order:
            if rule not in r_.index:
                continue
            a = r_.loc[rule]
            b = l_.loc[rule] if rule in l_.index else None
            s = (f"   {rule:<32}{'research':<9}{a.n:>5.0f}{a.mc_mean:>+10.2f}{a.p5:>+9.2f}"
                 f"{a.p95:>+9.2f}{a.p_le0:>8.3f}"
                 f"{(f'{a.p_ctrl:.3f}' if np.isfinite(a.p_ctrl) else '  --'):>8}")
            if b is not None:
                s += (f"   {'LOCKED':<9}{b.n:>5.0f}{b.mc_mean:>+10.2f}{b.p_le0:>8.3f}"
                      f"{(f'{b.p_ctrl:.3f}' if np.isfinite(b.p_ctrl) else '  --'):>8}")
            print(s)

    hdr("THE SUMMARY THAT MATTERS -- how many rules clear their control, against chance")
    F_ = T[T.rule != "(no filter -- the base)"]
    for mkt in MARKETS:
        for bn in ("research", "LOCKED"):
            g = F_[(F_.mkt == mkt) & (F_.block == bn)]
            if not len(g):
                continue
            print(f"   {mkt:<8}{bn:<10}{int((g.p_ctrl <= 0.05).sum()):>3} of {len(g):>3} rules "
                  f"clear the control at p<=0.05  ({0.05 * len(g):.1f} expected by chance)   "
                  f"mean MC ${g.mc_mean.mean():>+7.2f}   median ${g.mc_mean.median():>+7.2f}")
    hdr("RESEARCH-TO-LOCKED TRANSFER, per market")
    for mkt in MARKETS:
        a = F_[(F_.mkt == mkt) & (F_.block == "research")].set_index("rule").mc_mean
        b = F_[(F_.mkt == mkt) & (F_.block == "LOCKED")].set_index("rule").mc_mean
        j = a.to_frame("r").join(b.to_frame("l"), how="inner")
        sign = float((np.sign(j.r) == np.sign(j.l)).mean())
        print(f"   {mkt:<8} n {len(j):>3}   Pearson {j.r.corr(j.l):>+6.3f}   "
              f"Spearman {j.r.corr(j.l, method='spearman'):>+6.3f}   sign kept {sign:.3f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
