"""V62 stage C -- the drop-one at the winning cell, and whether it is a spike.

A cell that contains an MFI condition and an EMA condition is not evidence that either does
anything: it is the top of 2,055,874 draws, and the population table in B3 says the top 100 of
those land at -0.0300 on the locked block. The test that settles it is the DROP-ONE at that exact
geometry -- remove the MFI, remove the EMA, remove both -- plus the one-rung neighbourhood.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v62core as V                                              # noqa: E402
from run_v62 import FLOOR, AXES, matched_pairs                   # noqa: E402
from run_v62b import tf_data, geo_index, set_rows, take, block, control, boot, random_entry  # noqa: E402

BEST = dict(tf=30, ent=15, exN=10, stop=3.0, tp=3.0, adapt=1, cvd="k3w20", psh=0,
            mfi="mfi>=60", mfi_n=14, ema="spread momentum>=0.02 ATR", ema_f=21, ema_s=55)
SHIP = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, adapt=0, cvd="k3w20", psh=0,
            mfi="off", mfi_n=0, ema="off", ema_f=0, ema_s=0)


def score(cell, with_controls=True):
    D, res = tf_data(int(cell["tf"]))
    g = geo_index(res["G"], cell)
    sel, pool = set_rows(res, cell)
    tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
    rate = len(sel) / max(len(pool), 1)
    ctl = control(pool, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g, D["cut"],
                  rate) if with_controls else None
    out = {}
    for blk in ("res", "lock"):
        p = block(tr, D["cut"], blk)
        if len(p) < 5:
            out[blk] = None
            continue
        w = p > 0
        r = dict(n=len(p), pct=float(p.mean()), tot=float(p.sum()),
                 pf=float(p[w].sum() / max(1e-9, -p[~w].sum())))
        if with_controls:
            c = ctl[blk][np.isfinite(ctl[blk])]
            r["ctl"] = float(np.median(c)) if len(c) else np.nan
            r["p"] = float(np.mean(c >= p.mean())) if len(c) and rate < 0.999 else np.nan
            re = random_entry(D, cell, len(p), blk)
            r["pe"] = float(np.mean(re >= p.mean())) if len(re) else np.nan
            r["boot"] = boot(p)
        out[blk] = r
    return out


def line(label, s):
    o = f"  {label:44s}"
    for blk in ("res", "lock"):
        r = s[blk]
        if r is None:
            o += f" | {blk} --"
            continue
        o += (f" | {blk} n {r['n']:4d} {r['pct']:+.4f} PF {r['pf']:5.2f}")
        if "p" in r:
            o += f" ctl p {r['p']:.3f} ent p {r['pe']:.3f} boot {r['boot']:.3f}"
    return o


def main():
    print(__doc__)
    grid = pd.read_parquet("results/v62/grid.parquet")
    ok = grid[grid["n_res"] >= FLOOR]

    print("=" * 118)
    print("C1. DOES THE RESEARCH RANKING OF A CONFIRMATION SURVIVE? -- Spearman between the share")
    print("    of matched pairs a condition helps on research and the share it helps on locked")
    print("=" * 118)
    for fam in ("mfi", "ema"):
        r = matched_pairs(ok, fam, "res").set_index("condition")
        l = matched_pairs(ok, fam, "lock").set_index("condition")
        j = r.join(l, lsuffix="_r", rsuffix="_l").dropna()
        rho = j["helps_r"].corr(j["helps_l"], method="spearman")
        pe = j["helps_r"].corr(j["helps_l"])
        print(f"  {fam.upper():4s} {len(j)} conditions   Spearman {rho:+.3f}   Pearson {pe:+.3f}"
              f"   research mean {100*j['helps_r'].mean():.1f}%  locked mean "
              f"{100*j['helps_l'].mean():.1f}%")

    print("\n" + "=" * 118)
    print("C2. DROP-ONE AT THE WINNING CELL -- the only test that says whether its two")
    print("    confirmations are doing anything, rather than being carried by the geometry")
    print("=" * 118)
    variants = {
        "best cell as found (MFI + EMA)": dict(BEST),
        "  drop the MFI": dict(BEST, mfi="off", mfi_n=0),
        "  drop the EMA momentum": dict(BEST, ema="off", ema_f=0, ema_s=0),
        "  drop BOTH (geometry + CVD only)": dict(BEST, mfi="off", mfi_n=0, ema="off", ema_f=0,
                                                  ema_s=0),
        "  drop the CVD gate too": dict(BEST, mfi="off", mfi_n=0, ema="off", ema_f=0, ema_s=0,
                                        cvd="off"),
        "V61 incumbent": dict(SHIP),
    }
    for lab, cell in variants.items():
        print(line(lab, score(cell)))

    print("\n" + "=" * 118)
    print("C3. IS IT A SPIKE? -- one rung on every ordered axis, both blocks")
    print("=" * 118)
    ORD = {"ent": V.ENTS, "exN": V.EXITS, "stop": V.STOPS, "tp": V.TPS,
           "mfi_n": (0,) + V.MFI_LENS}
    rows = []
    for a, lev in ORD.items():
        lev = list(lev)
        if BEST[a] not in lev:
            continue
        i = lev.index(BEST[a])
        for j in (i - 1, i + 1):
            if not (0 <= j < len(lev)):
                continue
            cell = dict(BEST)
            cell[a] = lev[j]
            if a == "mfi_n" and lev[j] == 0:
                cell["mfi"] = "off"
            m = np.ones(len(grid), bool)
            for b in AXES:
                m &= grid[b].to_numpy() == cell[b]
            s = grid[m]
            if len(s) and s.iloc[0]["n_res"] >= 20 and s.iloc[0]["n_lock"] >= 10:
                rows.append((f"{a}={lev[j]}", float(s.iloc[0]["pct_res"]),
                             float(s.iloc[0]["pct_lock"])))
    for lab, a, b in rows:
        print(f"    {lab:16s} research {a:+.4f}   locked {b:+.4f}")
    arr = np.array([[a, b] for _, a, b in rows])
    print(f"  {len(rows)} neighbours: research {100*(arr[:,0]>0).mean():.0f}% profitable "
          f"(mean {arr[:,0].mean():+.4f}), locked {100*(arr[:,1]>0).mean():.0f}% "
          f"(mean {arr[:,1].mean():+.4f})   the cell itself: research +0.1371 locked +0.1203")


if __name__ == "__main__":
    main()
