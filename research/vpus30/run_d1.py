"""GATE 1 on the declared Donchian+ATR primary grid, US30 15m. No features exist yet.

8 declared cells: entry channel {20,55} x stop {2.0,3.0} ATR x side {long-only, both}.
Exit = opposite 20-bar channel or the stop. No target. Entries RTH only, exits on the full frame.

Scored in PERCENT OF ENTRY PRICE (the stop varies, so R is a denominator trap), gross beside net,
with cost/risk printed. The null is a RISK-MATCHED RANDOM ENTRY: the same number of entries drawn
from eligible RTH bars, the same side mix, re-simulated end to end through the same walker so the
position lock, the channel exit and the ATR stop are identical and only the entry bar moves.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V, vpdon as D  # noqa: E402

RNG = np.random.default_rng(20260909)
NDRAW = 400


def control(g, elig, n, side_mix, ex_n, sl, nd=NDRAW):
    """n random eligible RTH bars, same long/short proportion, re-simulated."""
    out = np.empty(nd)
    for d in range(nd):
        pick = RNG.choice(elig, size=min(n, len(elig)), replace=False)
        sd = np.where(RNG.random(len(pick)) < side_mix, 1, -1)
        r, _ = D.walk_at(g, pick, sd, ex_n=ex_n, sl=sl)
        out[d] = np.nanmean(r) if np.isfinite(r).sum() >= 5 else np.nan
    return out


def main():
    f = V.load()
    g = D.frame(f)
    sess = np.unique(g.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    print(f"US30 15m  bars {len(g):,}  RTH {int(g.is_rth.sum()):,}  split {str(cut)[:10]}")

    ok = g.is_rth.to_numpy().astype(bool) & np.isfinite(g["atr"].to_numpy()) & (g["atr"].to_numpy() > 0)
    elig_all = np.flatnonzero(ok)
    elig_all = elig_all[elig_all < len(g) - 400]

    print("\nGATE 1 -- the raw primary, 8 declared cells, percent of entry price")
    print(f"{'cell':<22}{'blk':<10}{'n':>6}{'net%':>9}{'gross%':>9}{'PF':>7}"
          f"{'c/risk':>8}{'ctl':>9}{'p':>7}")
    rows = []
    for ent_n in (20, 55):
        for sl in (2.0, 3.0):
            for side in (1, 0):
                t = D.walk(g, ent_n=ent_n, ex_n=20, sl=sl, side=side)
                ts = pd.DatetimeIndex(t.ts)
                nm = f"don{ent_n} {sl:.1f}N {'long' if side else 'both'}"
                for bl, sel, gsel in (("research", ts < cut, g.index < cut),
                                      ("HOLDOUT", ts >= cut, g.index >= cut)):
                    s = t[sel]
                    if len(s) < 30:
                        continue
                    gb = g[gsel]
                    e = elig_all[np.isin(elig_all, np.flatnonzero(gsel))]
                    # map global bar indices into the block frame for the control walker
                    off = int(np.flatnonzero(gsel)[0])
                    ctl = control(gb, e - off, len(s), float((s.side > 0).mean()), 20, sl)
                    mu = s.pct.mean()
                    p = float(np.nanmean(ctl >= mu))
                    print(f"{nm:<22}{bl:<10}{len(s):>6}{mu:>9.4f}{s.gross_pct.mean():>9.4f}"
                          f"{D.pf(s.pct):>7.3f}{s.cost_frac.median():>8.3f}"
                          f"{np.nanmedian(ctl):>9.4f}{p:>7.3f}")
                    rows.append(dict(cell=nm, blk=bl, n=len(s), net=mu, pf=D.pf(s.pct), p=p))
    r = pd.DataFrame(rows)
    r.to_csv("/home/user/main/research/vpus30/gate1_don.csv", index=False)
    res = r[r.blk == "research"]
    print(f"\nresearch cells clearing p<=0.05: {int((res.p <= 0.05).sum())} of {len(res)}"
          f"   (0.05*{len(res)} = {0.05*len(res):.1f} expected)")
    print(f"best research p {res.p.min():.3f} at {res.loc[res.p.idxmin(),'cell']}")
    print("trials counted this run: 8 primary cells")


if __name__ == "__main__":
    main()
