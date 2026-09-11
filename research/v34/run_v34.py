"""The declared V34 grid. Research first, controls as a gate, then ONE read of locked.

32 limit cells (2 signal sets x 2 timeframes x 4 depths x 2 sides) and their 8 market-order twins.
Declared in `v34mech.py` before the first run. Nothing here is swept.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v34")
import v34mech as M           # noqa: E402

OUT = "research/v34"


def hdr(t):
    print("\n" + "=" * 132)
    print(t)
    print("=" * 132, flush=True)


def grid(intraday=True, through=0.0, cost=M.COST_MULT, label=""):
    rows = []
    for sig in M.SIGNALS:
        for tf in M.TFS:
            res, lok, _s = M.blocks(tf)
            for side in M.SIDES:
                t, mod = M.signals(sig, tf, side, intraday=intraday)
                for blk, bname in ((res, "research"), (lok, "locked")):
                    tb = t[blk[t]]
                    if len(tb) < 50:
                        continue
                    mk = M.stat(M.run_market(tf, tb, side, cost=cost, intraday=intraday), len(tb))
                    for depth in M.DEPTHS:
                        lm = M.stat(M.run_limit(tf, tb, side, depth, through=through, cost=cost,
                                                intraday=intraday), len(tb))
                        if lm is None or mk is None:
                            continue
                        rows.append(dict(
                            variant=label, sig=sig, tf=tf, side=side, depth=depth, block=bname,
                            signals=len(tb), fill=lm["fill"], n=lm["n"],
                            lim_sig=lm["per_signal"], lim_trd=lm["per_trade"], lim_pf=lm["pf"],
                            mkt_sig=mk["per_signal"], mkt_trd=mk["per_trade"], mkt_pf=mk["pf"],
                            edge_sig=lm["per_signal"] - mk["per_signal"],
                            edge_trd=lm["per_trade"] - mk["per_trade"]))
    return pd.DataFrame(rows)


def show(df, block, tag):
    d = df[df.block == block]
    print(f"\n   {tag}  --  {block.upper()}   ($ per SIGNAL is the honest column; "
          f"$ per trade is beside it, never instead of it)")
    print(f"      {'sig':<9}{'tf':>4}{'side':>6}{'depth':>7}{'signals':>9}{'fill':>7}{'n':>6}"
          f"{'LIMIT $/sig':>13}{'MKT $/sig':>11}{'edge':>9}{'  ':>2}{'LIM $/trd':>11}"
          f"{'MKT $/trd':>11}{'LIM PF':>8}{'MKT PF':>8}")
    for r in d.itertuples():
        print(f"      {r.sig:<9}{r.tf:>4}{r.side:>+6}{r.depth:>7.2f}{r.signals:>9}{r.fill:>7.3f}"
              f"{r.n:>6}{r.lim_sig:>+13.4f}{r.mkt_sig:>+11.4f}{r.edge_sig:>+9.4f}{'  ':>2}"
              f"{r.lim_trd:>+11.3f}{r.mkt_trd:>+11.3f}{r.lim_pf:>8.3f}{r.mkt_pf:>8.3f}")


def hypotheses(df):
    hdr("THE FIVE DECLARED HYPOTHESES, SCORED")
    r = df[df.block == "research"]
    l = df[df.block == "locked"]

    print(f"\n   H1  a resting limit beats a market order on the same signals, per SIGNAL")
    for name, d in (("research", r), ("locked", l)):
        print(f"      {name:<9} limit wins in {int((d.edge_sig > 0).sum()):>3} of {len(d):<3} cells"
              f"   ({float((d.edge_sig > 0).mean()):.0%})   mean edge {d.edge_sig.mean():>+8.4f} "
              f"$/signal   median {d.edge_sig.median():>+8.4f}")

    print(f"\n   H2  the advantage is MONOTONE in depth")
    for name, d in (("research", r), ("locked", l)):
        g = d.groupby("depth").edge_sig.mean()
        mono = all(g.iloc[i] <= g.iloc[i + 1] for i in range(len(g) - 1))
        print(f"      {name:<9} " + "   ".join(f"{k:.2f}: {v:+.4f}" for k, v in g.items())
              + f"    monotone increasing: {'YES' if mono else 'no'}")

    print(f"\n   H3  present on BOTH SIDES -- if it is long only it is drift, not a mechanic")
    for name, d in (("research", r), ("locked", l)):
        g = d.groupby("side").edge_sig.agg(["mean", lambda x: (x > 0).mean()])
        for s, row in g.iterrows():
            print(f"      {name:<9} side {s:>+2}   mean edge {row['mean']:>+8.4f} $/signal   "
                  f"positive in {row['<lambda_0>']:.0%} of cells")

    print(f"\n   H5a the sign holds from research to locked, cell by cell")
    j = r.merge(l, on=["sig", "tf", "side", "depth"], suffixes=("_r", "_l"))
    if len(j):
        same = ((j.edge_sig_r > 0) == (j.edge_sig_l > 0)).mean()
        print(f"      {len(j)} paired cells   sign kept {same:.0%}   "
              f"rank correlation (Spearman) "
              f"{j.edge_sig_r.corr(j.edge_sig_l, method='spearman'):+.3f}")
    return j


if __name__ == "__main__":
    t0 = time.perf_counter()
    hdr("V34  THE ENTRY MECHANIC, PRE-REGISTERED, TRUE 1-MINUTE PATH")
    print(f"   declared cells: {len(M.SIGNALS)} signal sets x {len(M.TFS)} timeframes x "
          f"{len(M.DEPTHS)} depths x {len(M.SIDES)} sides = "
          f"{len(M.SIGNALS) * len(M.TFS) * len(M.DEPTHS) * len(M.SIDES)} limit cells, "
          f"plus {len(M.SIGNALS) * len(M.TFS) * len(M.SIDES)} market twins, per block")
    print(f"   geometry FIXED, not swept: stop {M.STOP_MULT}N, target {M.TP_R * M.STOP_MULT}N, "
          f"entries {M.WIN_START // 60:02d}:{M.WIN_START % 60:02d}-{M.WIN_END // 60:02d}:"
          f"{M.WIN_END % 60:02d} NY, order cancelled {M.CANCEL_MOD // 60:02d}:"
          f"{M.CANCEL_MOD % 60:02d}, position flat {M.FLAT_MIN // 60:02d}:{M.FLAT_MIN % 60:02d}, "
          f"costs x{M.COST_MULT}")

    df = grid(intraday=True, label="intraday")
    df.to_csv(f"{OUT}/v34_grid.csv", index=False)
    show(df, "research", "INTRADAY ONLY, hard flatten (as specified)")
    j = hypotheses(df)
    show(df, "locked", "INTRADAY ONLY, hard flatten (as specified)")

    hdr("WHAT THE INTRADAY CONSTRAINT COSTS -- the same 32 cells with no window and no flatten")
    du = grid(intraday=False, label="unconstrained")
    du.to_csv(f"{OUT}/v34_grid_unconstrained.csv", index=False)
    for blk in ("research", "locked"):
        a = df[df.block == blk]
        b = du[du.block == blk]
        print(f"   {blk:<9} intraday: mean limit {a.lim_sig.mean():>+8.4f} $/signal, "
              f"PF {a.lim_pf.mean():.3f}   |   unconstrained: {b.lim_sig.mean():>+8.4f}, "
              f"PF {b.lim_pf.mean():.3f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
