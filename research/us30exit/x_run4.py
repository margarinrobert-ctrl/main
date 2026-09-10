"""x_run4 -- ONE read of B_holdout and ONE of C_forward, on cells declared before looking.

DECLARED HERE, and this is the entire out-of-sample grid:
  D0  50/150  flatten        the section-12 incumbent -- the reference, not a candidate
  D1  50/none flatten        no take profit on the incumbent's own stop: the smallest possible
                             change, and the branch's 25-times finding applied literally
  D2  100/none flatten       the best flatten cell on TOTAL points and per-trade in x_run1
  D3  100/150 trail 1.0 ATR  the marginal consensus -- the trail led every unit at once
  D4  150/none trail 1.0 ATR THE TOP ROW of 80, carried so it can be seen to be the top row
Each is read on both reserved blocks and each is scored against a MATCHED RANDOM ENTRY carrying
its own identical exit machinery (400 draws), because a trail flatters any entry it is attached to.

AND ONE MECHANISM PREDICTION, made before the read and not a selection: `x_run3` measured that a
COIN FLIP with a 0.25 ATR trail earns PF 2.44 on the research block. If the trail is geometry
rather than signal, the CONTROL's PF ladder must rise the same way on both reserved blocks. That
is a prediction about the null, so it costs no selection.

C_forward is `US30_ISO_15m` after 2025-07-16 -- a DIFFERENT PROVIDER over a span no search on this
branch has touched. B_holdout is US30L from 2023-01-01 and has been read by six studies, so a
p-value there is descriptive.
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
ARM = "+adx<=20"

DECL = [
    ("D0 incumbent 50/150 flat", dict(stop=50, tgt=150, policy="flatten")),
    ("D1 no-target 50/none flat", dict(stop=50, tgt=None, policy="flatten")),
    ("D2 no-target 100/none flat", dict(stop=100, tgt=None, policy="flatten")),
    ("D3 marginal 100/150 trail1", dict(stop=100, tgt=150, policy="+trail1atr", tr_mult=1.0)),
    ("D4 top row 150/none trail1", dict(stop=150, tgt=None, policy="+trail1atr", tr_mult=1.0)),
]


def block_read(f, bm, fname, bname, seed):
    nsess = f.index[bm & S.window(f)].normalize().nunique()
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    sig, sd = X.signals(f, ARM, bm, M)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & bm
    rows = []
    for nm, kw in DECL:
        kk = dict(kw); kk["chlo"] = chlo
        t = X.xwalk(f, sig, sd, **kk)
        if len(t) < 15:
            rows.append(dict(feed=fname, block=bname, cell=nm, n=len(t)))
            continue
        r = X.stats(t, nsess, kw["stop"], kw["tgt"])
        cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=400, seed=seed, **kk)
        r.update(feed=fname, block=bname, cell=nm,
                 ctl_pts=float(np.median(cp)), edge=r["pts"] - float(np.median(cp)),
                 p_pts=float(np.mean(cp >= r["pts"])),
                 ctl_pf=float(np.median(cf)), pf_ratio=r["pf"] / float(np.median(cf)),
                 p_pf=float(np.mean(cf >= r["pf"])))
        rows.append(r)
    return pd.DataFrame(rows), (f, sig, sd, chlo, elig, nsess)


def ladder(f, sig, sd, chlo, elig, nsess, seed):
    out = []
    for mult in (None, 1.0, 0.5, 0.25):
        kw = dict(stop=100, tgt=150, chlo=chlo,
                  policy="flatten" if mult is None else "+trail1atr")
        if mult is not None:
            kw["tr_mult"] = mult
        t = X.xwalk(f, sig, sd, **kw)
        if len(t) < 15:
            continue
        r = X.stats(t, nsess, 100, 150)
        cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=300, seed=seed, **kw)
        out.append(dict(trail="none" if mult is None else f"{mult:.2f}", n=r["n"], pf=r["pf"],
                        ctl_pf=float(np.median(cf)), pf_ratio=r["pf"] / float(np.median(cf)),
                        pts=r["pts"], ctl_pts=float(np.median(cp)),
                        edge=r["pts"] - float(np.median(cp)),
                        excess_total=(r["pts"] - float(np.median(cp))) * r["n"],
                        total=r["total"], ret_dd=r["ret_dd"], win=r["win"], mde=r["mde"],
                        med_min=r["med_min"]))
    return pd.DataFrame(out)


def main():
    fL = S.load("US30L")
    blL = S.blocks(fL, "US30L")
    fI = S.load("US30I")
    blI = S.blocks(fI, "US30I")

    frames, ctx = [], {}
    for f, fname, bl, seed in ((fL, "US30L", blL, 41), (fI, "US30I", blI, 43)):
        for bn, bm in bl.items():
            df, c = block_read(f, bm, fname, bn, seed)
            frames.append(df)
            ctx[bn] = c
    A = pd.concat(frames, ignore_index=True)
    cols = ["feed", "block", "cell", "n", "pts", "total", "pf", "ret_dd", "dd", "win", "be",
            "mde", "outside_mde", "med_min", "ctl_pts", "edge", "p_pts", "ctl_pf", "pf_ratio",
            "p_pf", "sh_stop", "sh_target", "sh_flat"]
    print("=== 1. ALL THREE BLOCKS, the five declared cells ===")
    print(A[cols].round(4).to_string(index=False))

    print("\n=== 2. per cell across the three blocks -- points a trade, PF, and the excess ===")
    for m in ("pts", "pf", "edge", "ret_dd", "total", "n"):
        print(f"\n  {m}")
        print(A.pivot_table(index="cell", columns="block", values=m, aggfunc="first")
              .round(3).to_string())

    print("\n=== 3. the verdict per cell ===")
    for nm, _ in DECL:
        s = A[A.cell == nm].dropna(subset=["pts"])
        print(f"  {nm:28s} {int((s.pts > 0).sum())}/{len(s)} blocks positive   "
              f"mean pts {s.pts.mean():+7.3f}   mean PF {s.pf.mean():.3f}   "
              f"clears its control {int((s.p_pts <= 0.05).sum())}/{len(s)}   "
              f"outside its MDE {int(s.outside_mde.sum())}/{len(s)}")

    print("\n=== 4. THE MECHANISM PREDICTION: does the CONTROL's PF ladder reproduce? ===")
    print("    research had ctl_pf  0.970 (no trail) -> 1.043 (1.0) -> 1.530 (0.5) -> 2.444 (0.25)\n")
    for bn in ("A_research", "B_holdout", "C_forward"):
        if bn not in ctx:
            continue
        f, sig, sd, chlo, elig, nsess = ctx[bn]
        print(f"  --- {bn} ---")
        print(ladder(f, sig, sd, chlo, elig, nsess, seed=47).round(4).to_string(index=False))

    print("\n=== 5. what the PF gain is worth in money, out of sample ===")
    ref = A[A.cell == "D0 incumbent 50/150 flat"].set_index("block")
    for nm, _ in DECL:
        if nm.startswith("D0"):
            continue
        s = A[A.cell == nm].set_index("block")
        for b in s.index:
            if b not in ref.index or not np.isfinite(s.loc[b, "pts"]):
                continue
            d = s.loc[b, "pts"] - ref.loc[b, "pts"]
            dt = s.loc[b, "total"] - ref.loc[b, "total"]
            print(f"  {nm:28s} {b:11s} dPF {s.loc[b,'pf']-ref.loc[b,'pf']:+6.3f}  "
                  f"dpts {d:+7.3f}  dtotal {dt:+8.1f}  "
                  f"dret/DD {s.loc[b,'ret_dd']-ref.loc[b,'ret_dd']:+6.2f}  "
                  f"MDE {s.loc[b,'mde']:5.2f}  "
                  f"{'OUTSIDE' if abs(d) > s.loc[b,'mde'] else 'inside'}")


if __name__ == "__main__":
    main()
