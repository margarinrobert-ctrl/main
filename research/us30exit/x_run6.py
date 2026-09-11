"""x_run6 -- THE SAME 80 DECLARED CELLS on two more arms, reported SIDE BY SIDE, not replacing.

A parallel workstream (`research/us30rate/`, STUDY_US30_SCALP_0711 sections 14-15) measured that
the arm x_run1..x_run5 was built on is the WEAKER of the two conditions: over six Donchian channel
rungs x three blocks against a same-selectivity random VETO, `+adx<=20` beats its null in 15 of 18
cells but only 3 of 6 on the RESERVED forward feed (median p 0.617 there), while `+ema align` is
18 of 18 including 6 of 6 forward (median p 0.301). Section 13's "only arm positive on all three
blocks" was true at channel 20 and not of the condition. And the EMA stack decomposes:
`ema34>ema89` alone carries it while `ema13>ema34` alone is a coin flip, so dropping the fast leg
is FREE rather than an improvement.

Nothing is refitted to that. The grid, the policies, the units and the reading order are EXACTLY
those declared in `x_lib`'s docstring; only the arm changes. If the exit marginals agree across
arms that is worth more than any one grid; if they disagree that is the finding.

  arms      +adx<=20 (as run)  |  +ema align (e13>e34>e89)  |  ema34>89 alone
  grid      the same 80 cells: stop {30,50,75,100,150} x target {100,150,200,none}
            x policy {flatten | +chan10 | +be1R | +trail 1.0 ATR}
  = 160 NEW research cells, and the trail ladder repeated on each new arm (+12).

DECLARED NOW, BEFORE THE READ, and read once: the same five cells D0..D4 from `x_run4` on each of
the two new arms, on B_holdout and C_forward. 5 x 2 x 2 = 20 additional reserved cells. They are
declared here so the geometry verdict does not rest on the arm that fails the reserved block.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_lib as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 300)

STOPS = [30, 50, 75, 100, 150]
TGTS = [100, 150, 200, None]
ARMS = ["+adx<=20", "+ema align", "ema34>89"]
DECL = [
    ("D0 50/150 flat", dict(stop=50, tgt=150, policy="flatten")),
    ("D1 50/none flat", dict(stop=50, tgt=None, policy="flatten")),
    ("D2 100/none flat", dict(stop=100, tgt=None, policy="flatten")),
    ("D3 100/150 trail1", dict(stop=100, tgt=150, policy="+trail1atr", tr_mult=1.0)),
    ("D4 150/none trail1", dict(stop=150, tgt=None, policy="+trail1atr", tr_mult=1.0)),
]


def masks(f):
    """`s10lib.build_masks` plus the decomposed slow leg. The published module is not edited."""
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    c = f["close"].to_numpy()
    e34, e89 = X.L.ema(c, 34), X.L.ema(c, 89)
    M["ema34>89"] = e34 > e89
    return M


COND = {"+adx<=20": ["adx<=20"], "+ema align": ["ema align"], "ema34>89": ["ema34>89"]}


def sigs(f, arm, bm, M):
    s2, d2 = S.donchian(f, 20, 1)
    keep = np.isin(s2, np.flatnonzero(bm))
    for c in COND[arm]:
        keep &= M[c][s2]
    return s2[keep], d2[keep]


def cell(f, sig, sd, chlo, elig, nsess, kw, draws=150, seed=71):
    t = X.xwalk(f, sig, sd, chlo=chlo, **kw)
    if len(t) < 15:
        return None
    r = X.stats(t, nsess, kw["stop"], kw["tgt"])
    cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=draws, seed=seed,
                       chlo=chlo, **kw)
    r.update(ctl_pts=float(np.median(cp)), ctl_pf=float(np.median(cf)),
             pf_ratio=r["pf"] / float(np.median(cf)),
             edge=r["pts"] - float(np.median(cp)),
             p_pts=float(np.mean(cp >= r["pts"])), p_pf=float(np.mean(cf >= r["pf"])))
    r["excess_total"] = r["edge"] * r["n"]
    return r


def main():
    f = S.load("US30L")
    res = S.blocks(f, "US30L")["A_research"]
    nsess = f.index[res & S.window(f)].normalize().nunique()
    M = masks(f)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & res

    print("=== 0. the three arms on the research block, unfiltered geometry aside ===")
    for a in ARMS:
        s, _ = sigs(f, a, res, M)
        print(f"  {a:12s} {len(s):5d} signal bars   "
              f"pass rate on all Donchian-20 breakouts "
              f"{len(s)/len(sigs(f,'+adx<=20',res,M)[0]) if a=='+adx<=20' else np.nan:.3f}")
    s_all, _ = S.donchian(f, 20, 1)
    s_all = s_all[np.isin(s_all, np.flatnonzero(res & S.window(f)))]
    for a in ARMS:
        s, _ = sigs(f, a, res, M)
        print(f"  {a:12s} keeps {len(s)/max(len(s_all),1):.1%} of in-window breakout bars")

    grids = {}
    for arm in ARMS:
        sig, sd = sigs(f, arm, res, M)
        rows = []
        for st in STOPS:
            for tg in TGTS:
                for pol in X.POLICIES:
                    kw = dict(stop=st, tgt=tg, policy=pol)
                    r = cell(f, sig, sd, chlo, elig, nsess, kw)
                    if r is None:
                        continue
                    r.update(stop=st, tgt="none" if tg is None else str(tg), policy=pol, arm=arm)
                    rows.append(r)
        grids[arm] = pd.DataFrame(rows)
        print(f"\n  built {arm}: {len(rows)} cells")
    G = pd.concat(grids.values(), ignore_index=True)
    G.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_grid_arms.csv"),
             index=False)

    print("\n=== 1. POPULATION SHAPE per arm, before any ranking ===")
    print(G.groupby("arm").agg(cells=("pf", "size"), pf_gt1=("pf", lambda s: (s > 1).mean()),
                               tot_gt0=("total", lambda s: (s > 0).mean()),
                               outside_mde=("outside_mde", "mean"),
                               med_pf=("pf", "median"), med_total=("total", "median"),
                               med_n=("n", "median"), best_pf=("pf", "max"),
                               best_t=("t", "max")).round(4).to_string())

    print("\n=== 2. THE MARGINALS SIDE BY SIDE -- raw PF, then excess of the arm's own null ===")
    for ax, order in (("policy", X.POLICIES), ("stop", STOPS),
                      ("tgt", [str(t) if t else "none" for t in TGTS])):
        print(f"\n  --- {ax} ---")
        for m, lab in (("pf", "raw PF"), ("ctl_pf", "twin PF"), ("pf_ratio", "PF ratio"),
                       ("pts", "pts/trade"), ("edge", "excess pts/trade"),
                       ("excess_total", "excess TOTAL"), ("total", "total pts"),
                       ("n", "trades"), ("ret_dd", "ret/DD"), ("mde", "MDE")):
            p = G.pivot_table(index=ax, columns="arm", values=m, aggfunc="mean").reindex(order)
            p = p[ARMS]
            print(f"    {lab:18s} " + "  ".join(
                f"{c}: " + " ".join(f"{v:8.3f}" for v in p[c].to_numpy()) for c in ARMS))
        print(f"    {'(axis order)':18s} " + " ".join(f"{str(o):>8s}" for o in order))

    print("\n=== 3. DO THE ARMS AGREE ON THE GEOMETRY? rank correlation across the 80 cells ===")
    key = ["stop", "tgt", "policy"]
    piv = {a: grids[a].set_index(key) for a in ARMS}
    for m in ("pf", "pts", "excess_total", "pf_ratio", "ret_dd"):
        print(f"\n  {m}")
        for i, a in enumerate(ARMS):
            for b in ARMS[i + 1:]:
                j = piv[a][m].align(piv[b][m], join="inner")
                print(f"    {a:12s} vs {b:12s}  Pearson {j[0].corr(j[1]):+.4f}   "
                      f"Spearman {j[0].corr(j[1], method='spearman'):+.4f}")

    print("\n  best cell per arm, by each unit:")
    for m in ("pf", "excess_total", "ret_dd"):
        print(f"    by {m}:")
        for a in ARMS:
            r = grids[a].loc[grids[a][m].idxmax()]
            print(f"      {a:12s} {r.stop:>4}/{r.tgt:<5}{r.policy:12s} "
                  f"PF {r.pf:.3f} twinPF {r.ctl_pf:.3f} ratio {r.pf_ratio:.3f} "
                  f"pts {r.pts:+7.3f} excess_tot {r.excess_total:+8.1f} "
                  f"ret/DD {r.ret_dd:6.2f} n {int(r.n)}")

    print("\n=== 4. THE TRAIL LADDER ON EACH ARM, each rung beside its own twin ===")
    for arm in ARMS:
        sig, sd = sigs(f, arm, res, M)
        print(f"\n  --- {arm} --- (stop 100 / target 150 fixed)")
        rows = []
        for mult in (0.25, 0.5, 1.0, 2.0, None):
            kw = dict(stop=100, tgt=150, policy="flatten" if mult is None else "+trail1atr")
            if mult is not None:
                kw["tr_mult"] = mult
            r = cell(f, sig, sd, chlo, elig, nsess, kw, draws=250, seed=83)
            if r:
                rows.append(dict(trail="none" if mult is None else f"{mult:.2f}", n=r["n"],
                                 pf=r["pf"], twin_pf=r["ctl_pf"], pf_ratio=r["pf_ratio"],
                                 pts=r["pts"], twin_pts=r["ctl_pts"], edge=r["edge"],
                                 excess_total=r["excess_total"], total=r["total"],
                                 ret_dd=r["ret_dd"], win=r["win"], mde=r["mde"],
                                 med_min=r["med_min"], p_pts=r["p_pts"]))
        print(pd.DataFrame(rows).round(4).to_string(index=False))

    print("\n=== 5. tie-break bracket on the two new arms ===")
    for arm in ARMS[1:]:
        sig, sd = sigs(f, arm, res, M)
        amb = []
        for st in STOPS:
            for tg in TGTS:
                for pol in X.POLICIES:
                    a = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tie=0, chlo=chlo)
                    b = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tie=1, chlo=chlo)
                    ra, rb = X.stats(a, nsess, st, tg), X.stats(b, nsess, st, tg)
                    amb.append(dict(amb=ra["amb"], d=rb["pts"] - ra["pts"],
                                    flip=np.sign(ra["pts"]) != np.sign(rb["pts"])))
        A = pd.DataFrame(amb)
        print(f"  {arm:12s} mean ambiguous {A.amb.mean():.4%}  max {A.amb.max():.4%}  "
              f"mean |spread| {A.d.abs().mean():.3f}  max {A.d.abs().max():.3f}  "
              f"sign flips {int(A.flip.sum())} of {len(A)}")

    # -------- ONE READ, declared in the docstring above --------------------------------------
    print("\n=== 6. ONE READ: D0..D4 on the two new arms, B_holdout and C_forward ===")
    out = []
    fI = S.load("US30I")
    for feed, fname, bl, seed in ((f, "US30L", S.blocks(f, "US30L"), 91),
                                  (fI, "US30I", S.blocks(fI, "US30I"), 93)):
        MM = masks(feed)
        ch = X.chan_low(feed, 10, 1)
        for bn, bm in bl.items():
            ns = feed.index[bm & S.window(feed)].normalize().nunique()
            el = S.window(feed) & bm
            for arm in ARMS:
                sg, sdd = sigs(feed, arm, bm, MM)
                for nm, kw in DECL:
                    r = cell(feed, sg, sdd, ch, el, ns, kw, draws=400, seed=seed)
                    if r is None:
                        continue
                    r.update(feed=fname, block=bn, arm=arm, cell=nm)
                    out.append(r)
    O = pd.DataFrame(out)
    for m in ("pts", "pf", "pf_ratio", "edge", "ret_dd", "n"):
        print(f"\n  {m}")
        print(O.pivot_table(index=["arm", "cell"], columns="block", values=m, aggfunc="first")
              .round(3).to_string())
    print("\n  per arm x cell: blocks positive in EXCESS, and outside its MDE")
    for arm in ARMS:
        for nm, _ in DECL:
            s = O[(O.arm == arm) & (O.cell == nm)]
            if not len(s):
                continue
            print(f"    {arm:12s} {nm:20s} pts+ {int((s.pts>0).sum())}/{len(s)}   "
                  f"excess+ {int((s.edge>0).sum())}/{len(s)}   "
                  f"PFratio>1 {int((s.pf_ratio>1).sum())}/{len(s)}   "
                  f"outside MDE {int(s.outside_mde.sum())}/{len(s)}   "
                  f"clears ctl {int((s.p_pts<=0.05).sum())}/{len(s)}")
    O.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_oos_arms.csv"),
             index=False)


if __name__ == "__main__":
    main()
