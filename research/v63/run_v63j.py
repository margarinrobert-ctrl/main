"""V63 stage J -- the stop-loss and take-profit optimisation, read the way this branch reads a grid.

Population first, then the MARGINAL AVERAGE PER AXIS, then consistency across blocks, then the
cells. The top row of a 405-cell grid is the maximum of 405 draws and has been read badly here
before.

THE RESERVED BLOCKS HAVE NOW BEEN READ SEVERAL TIMES FOR THIS DESIGN, so nothing below is a fresh
out-of-sample test. It is an optimisation, and the honest criterion is CONSISTENCY ACROSS EIGHT
BLOCKS OF THREE MARKETS rather than a p-value.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V   # noqa: E402
import v63exit as E   # noqa: E402

FLOOR = 40
SHIP = dict(stop=1.5, tp_mode=0, tp_val=0.0, partial=0.0)


def main():
    print(__doc__)
    print(E.__doc__)
    fr = []
    for m in V.FEEDSORDER:
        fr.append(E.table(E.run(m), m))
        print(f"  .. {m} done")
    d = pd.concat(fr, ignore_index=True)
    d.to_csv("results/v63/sltp.csv", index=False)

    # every (market, block) pair, with US100 research flagged as the only block that chose
    cols = [(m, b) for m in V.FEEDSORDER
            for b in (["research", "validation", "test"] if m != "NQ" else ["research", "locked"])]
    oos = [(m, b) for m, b in cols if not (m == "US100" and b == "research")]

    def pick(df, m, b, col):
        s = df[df["market"] == m]
        return s[f"{col}_{b}"].to_numpy(), s[f"n_{b}"].to_numpy()

    # one row per geometry, aggregated over the blocks that chose nothing
    G = d[d["market"] == V.FEEDSORDER[0]][["stop", "tp_mode", "tp_val", "partial"]].reset_index(drop=True)
    tot = np.zeros(len(G)); n = np.zeros(len(G)); pos = np.zeros(len(G)); nb = np.zeros(len(G))
    gp = np.zeros(len(G)); gl = np.zeros(len(G)); wins = np.zeros(len(G))
    amb = np.zeros(len(G)); bars = np.zeros(len(G)); tsh = np.zeros(len(G)); ssh = np.zeros(len(G))
    Rsum = np.zeros(len(G))
    for m, b in oos:
        s = d[d["market"] == m].reset_index(drop=True)
        nn = s[f"n_{b}"].to_numpy()
        pc = np.nan_to_num(s[f"pct_{b}"].to_numpy())
        ok = nn >= 5
        tot += np.where(ok, nn * pc, 0.0)
        n += np.where(ok, nn, 0.0)
        pos += np.where(ok & (pc > 0), 1.0, 0.0)
        nb += ok
        wins += np.where(ok, nn * np.nan_to_num(s[f"win_{b}"].to_numpy()), 0.0)
        amb += np.where(ok, nn * np.nan_to_num(s[f"amb_{b}"].to_numpy()), 0.0)
        bars += np.where(ok, nn * np.nan_to_num(s[f"bars_{b}"].to_numpy()), 0.0)
        tsh += np.where(ok, nn * np.nan_to_num(s[f"tgtsh_{b}"].to_numpy()), 0.0)
        ssh += np.where(ok, nn * np.nan_to_num(s[f"stopsh_{b}"].to_numpy()), 0.0)
        Rsum += np.where(ok, nn * np.nan_to_num(s[f"R_{b}"].to_numpy()), 0.0)
    A = G.copy()
    A["n"] = n; A["blocks"] = nb; A["pos"] = pos
    A["pct"] = np.where(n > 0, tot / np.maximum(n, 1), np.nan)
    A["R"] = np.where(n > 0, Rsum / np.maximum(n, 1), np.nan)
    A["tot"] = tot
    A["win"] = np.where(n > 0, wins / np.maximum(n, 1), np.nan)
    A["amb"] = np.where(n > 0, amb / np.maximum(n, 1), np.nan)
    A["bars"] = np.where(n > 0, bars / np.maximum(n, 1), np.nan)
    A["tgt_share"] = np.where(n > 0, tsh / np.maximum(n, 1), np.nan)
    A["stop_share"] = np.where(n > 0, ssh / np.maximum(n, 1), np.nan)
    A["label"] = [E.label(r) for _, r in A.iterrows()]
    A = A[A["n"] >= FLOOR].copy()
    A.to_csv("results/v63/sltp_pooled.csv", index=False)

    print("\n" + "=" * 118)
    print("J1. THE POPULATION -- 405 cells, pooled over the seven blocks that chose nothing")
    print("=" * 118)
    print(f"  scorable cells {len(A)} of 405   profitable {100*(A['pct']>0).mean():.1f}%   "
          f"median {A['pct'].median():+.4f} %/trade   median win {100*A['win'].median():.1f}%")
    print(f"  cells positive on ALL {int(A['blocks'].max())} blocks: "
          f"{int((A['pos'] == A['blocks']).sum())}")
    sh = A[(A["stop"] == 1.5) & (A["tp_mode"] == 0) & (A["partial"] == 0)].iloc[0]
    print(f"  the shipped 1.5N / no target / no partial: {sh['pct']:+.4f} %/trade, "
          f"{int(sh['pos'])}/{int(sh['blocks'])} blocks, PF-free win {100*sh['win']:.1f}%, "
          f"R {sh['R']:+.3f}")

    print("\n" + "=" * 118)
    print("J2. THE MARGINAL AVERAGE PER AXIS -- percent of price, then the SAME axis in R")
    print("=" * 118)
    for ax, lab in (("stop", "stop, ATR"), ("partial", "partial exit, R")):
        g = A.groupby(ax).agg(pct=("pct", "mean"), R=("R", "mean"), win=("win", "mean"),
                              n=("n", "mean"), cells=("pct", "size"))
        print(f"  {lab}")
        for k, v in g.iterrows():
            print(f"    {k:>6} : {v['pct']:+.4f} %/trade   R {v['R']:+.3f}   win "
                  f"{100*v['win']:5.1f}%   mean trades {v['n']:6.0f}   {int(v['cells']):3d} cells")
    print("  take profit, as a multiple of the STOP")
    g = A[A["tp_mode"] != 2].groupby(["tp_mode", "tp_val"]).agg(
        pct=("pct", "mean"), R=("R", "mean"), win=("win", "mean"), tg=("tgt_share", "mean"),
        n=("n", "mean"))
    for (mo, va), v in g.iterrows():
        nm = "none" if mo == 0 else f"{va:g}R"
        print(f"    {nm:>6} : {v['pct']:+.4f} %/trade   R {v['R']:+.3f}   win {100*v['win']:5.1f}%"
              f"   target hit {100*v['tg']:5.1f}%   mean trades {v['n']:6.0f}")
    print("  take profit, as an absolute multiple of ATR")
    g = A[A["tp_mode"] != 1].groupby(["tp_mode", "tp_val"]).agg(
        pct=("pct", "mean"), R=("R", "mean"), win=("win", "mean"), tg=("tgt_share", "mean"),
        n=("n", "mean"))
    for (mo, va), v in g.iterrows():
        nm = "none" if mo == 0 else f"{va:g}ATR"
        print(f"    {nm:>6} : {v['pct']:+.4f} %/trade   R {v['R']:+.3f}   win {100*v['win']:5.1f}%"
              f"   target hit {100*v['tg']:5.1f}%   mean trades {v['n']:6.0f}")
    st = A.groupby("stop").agg(pct=("pct", "mean"), R=("R", "mean"))
    print(f"\n  THE STOP AXIS IN THE TWO UNITS: percent of price "
          + " ".join(f"{k:g}N {v['pct']:+.3f}" for k, v in st.iterrows()))
    print("                                  R           "
          + " ".join(f"{k:g}N {v['R']:+.3f}" for k, v in st.iterrows()))

    print("\n" + "=" * 118)
    print("J3. THE BREAK-EVEN ARITHMETIC -- a target's win rate has to clear 1/(1+RR) before costs")
    print("=" * 118)
    print(f"  {'target':>8s} {'break-even':>11s} {'actual win':>11s} {'shortfall':>10s} "
          f"{'target hit':>11s}")
    for (mo, va), v in A[A["tp_mode"] == 1].groupby(["tp_mode", "tp_val"]).agg(
            win=("win", "mean"), tg=("tgt_share", "mean")).iterrows():
        be = 1.0 / (1.0 + va)
        print(f"  {va:g}R{'':5s} {100*be:10.1f}% {100*v['win']:10.1f}% "
              f"{100*(v['win']-be):+9.1f}% {100*v['tg']:10.1f}%")
    print("  A target below its break-even is losing money by construction, whatever the backtest")
    print("  says about any single cell.")

    print("\n" + "=" * 118)
    print("J4. CELLS POSITIVE ON EVERY BLOCK, ranked by percent of price")
    print("=" * 118)
    con = A[A["pos"] == A["blocks"]].sort_values("pct", ascending=False)
    print(f"  {len(con)} of {len(A)} cells are positive on all {int(A['blocks'].max())} blocks.")
    print(f"  {'cell':26s} {'n':>5s} {'pct/tr':>9s} {'total':>8s} {'R':>7s} {'win':>6s} "
          f"{'tgt hit':>8s} {'ambig':>7s} {'hold h':>7s}")
    for _, r in con.head(15).iterrows():
        print(f"  {r['label']:26s} {int(r['n']):5d} {r['pct']:+9.4f} {r['tot']:+8.1f} "
              f"{r['R']:+7.3f} {100*r['win']:5.1f}% {100*r['tgt_share']:7.1f}% "
              f"{100*r['amb']:6.1f}% {r['bars']*0.5:7.1f}")
    print("\n  and the ten WORST cells, for the shape of the surface:")
    for _, r in A.sort_values("pct").head(10).iterrows():
        print(f"  {r['label']:26s} {int(r['n']):5d} {r['pct']:+9.4f} {r['tot']:+8.1f} "
              f"{r['R']:+7.3f} {100*r['win']:5.1f}% {100*r['tgt_share']:7.1f}% "
              f"{100*r['amb']:6.1f}% {r['bars']*0.5:7.1f}")

    print("\n" + "=" * 118)
    print("J5. PER-BLOCK DETAIL for the shipped cell and the best consistent cells")
    print("=" * 118)
    want = [SHIP] + [dict(stop=r["stop"], tp_mode=int(r["tp_mode"]), tp_val=r["tp_val"],
                          partial=r["partial"]) for _, r in con.head(3).iterrows()]
    seen = set()
    for cell in want:
        key = tuple(cell.values())
        if key in seen:
            continue
        seen.add(key)
        lab = E.label(cell)
        print(f"\n  {lab}")
        for m, b in cols:
            s = d[(d["market"] == m) & (d["stop"] == cell["stop"])
                  & (d["tp_mode"] == cell["tp_mode"]) & (d["tp_val"] == cell["tp_val"])
                  & (d["partial"] == cell["partial"])]
            if not len(s):
                continue
            r = s.iloc[0]
            if not np.isfinite(r[f"pct_{b}"]) or r[f"n_{b}"] < 5:
                continue
            tag = "IS " if (m == "US100" and b == "research") else "OOS"
            print(f"    {m:7s} {b:11s} {tag} n {int(r[f'n_{b}']):4d}  {r[f'pct_{b}']:+.4f} "
                  f"%/trade  PF {r[f'pf_{b}']:5.2f}  win {100*r[f'win_{b}']:5.1f}%  "
                  f"target hit {100*r[f'tgtsh_{b}']:5.1f}%  ambiguous "
                  f"{100*r[f'amb_{b}']:4.1f}%")


def extra():
    """J6 -- the path risk of a much wider stop, which is what the optimisation is really asking
    you to accept. Day-block bootstrap for the edge, permutation for the drawdown."""
    import v63exit as E2
    cells = {"1.5N / none (shipped)": dict(stop=1.5, tp_mode=0, tp_val=0.0, partial=0.0),
             "2.5N / none": dict(stop=2.5, tp_mode=0, tp_val=0.0, partial=0.0),
             "4N / none": dict(stop=4.0, tp_mode=0, tp_val=0.0, partial=0.0),
             "6N / none": dict(stop=6.0, tp_mode=0, tp_val=0.0, partial=0.0),
             "12N / none (stop cannot bind)": dict(stop=12.0, tp_mode=0, tp_val=0.0, partial=0.0)}
    print("\n" + "=" * 118)
    print("J6. WHAT A WIDER STOP COSTS IN PATH RISK -- pooled over the blocks that chose nothing")
    print("=" * 118)
    print(f"  {'cell':30s} {'n':>5s} {'pct/tr':>9s} {'total':>8s} {'P(<=0)':>7s} "
          f"{'95% CI':>20s} {'realDD':>7s} {'MCp99':>7s} {'pctile':>7s} {'risk%':>6s}")
    runs = {m: E2.run(m) for m in V.FEEDSORDER}
    for lab, cell in cells.items():
        allp, days, risk = [], [], []
        for m, res in runs.items():
            G = res["G"]
            gi = int(np.flatnonzero((G["stop"] == cell["stop"]) & (G["tp_mode"] == cell["tp_mode"])
                                    & (G["tp_val"] == cell["tp_val"])
                                    & (G["partial"] == cell["partial"]))[0])
            D, rows, blk = res["D"], res["rows"], res["blk"]
            names = list(D["blocks"].keys())
            ix = pd.DatetimeIndex(D["ix"])
            key = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
            free = -1
            for k in range(len(rows)):
                if res["xb"][k, gi] < 0 or not np.isfinite(res["pts"][k, gi]) or rows[k] <= free:
                    continue
                free = res["xb"][k, gi]
                b = blk[rows[k]]
                if b < 0 or (m == "US100" and names[b] == "research"):
                    continue
                allp.append(100.0 * float(res["pts"][k, gi]) / res["epx"][k])
                days.append(f"{m}{key[rows[k]]}")
                risk.append(100.0 * cell["stop"] * D["atr"][rows[k]] / D["c"][rows[k]])
        p = np.array(allp)
        g = pd.Series(p).groupby(days).apply(lambda x: x.to_numpy())
        arrs = list(g.values)
        rng = np.random.default_rng(31)
        mb = np.array([np.concatenate([arrs[i] for i in rng.integers(0, len(arrs), len(arrs))]).mean()
                       for _ in range(3000)])
        def dd(x):
            eq = np.cumsum(x)
            return float(np.max(np.maximum.accumulate(eq) - eq))
        pm = np.array([dd(rng.permutation(p)) for _ in range(3000)])
        print(f"  {lab:30s} {len(p):5d} {p.mean():+9.4f} {p.sum():+8.1f} "
              f"{np.mean(mb <= 0):7.4f} [{np.percentile(mb,2.5):+.4f},{np.percentile(mb,97.5):+.4f}]"
              f" {dd(p):7.2f} {np.percentile(pm,99):7.2f} {np.mean(pm <= dd(p)):7.2f} "
              f"{np.mean(risk):6.2f}")
    print("  `risk%` is the stop distance as a percent of the entry price -- what one unit actually")
    print("  puts at risk per trade. It is the number the wider stop is spending.")


if __name__ == "__main__":
    extra()
