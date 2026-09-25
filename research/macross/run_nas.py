"""The MA_CROSS_SELECT script's order model on the US100 (NAS100 CFD) 15-minute feed, 2016-2025.

A MECHANICS-AND-SHAPE read, not a test: no matched control is run here, so nothing below says the
rule beats a random entry. What it does say is what each option does to trade count and P&L on
nine years of Nasdaq, split at 2022-12-26 (everything before is unseen by any NQ study here).

Feed: `US100_LONG_15m` (registry sha256 c449dddfbc06a943), New York + 7, re-derived below.
Cost: 1.215 points a round turn -- the figure every US100 study on this branch uses.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mx_sim as M  # noqa: E402

M.COST = 1.215
ROOT = os.path.dirname(os.path.dirname(HERE))


def load(tf=15):
    d = pd.read_csv(os.path.join(ROOT, "data", "US100_LONG_15m.csv"), sep="\t")
    d["ts"] = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S")
    d = d.sort_values("ts").reset_index(drop=True)
    d["ny"] = d["ts"] - pd.Timedelta(hours=7)
    d = d.rename(columns=str.lower)[["ny", "open", "high", "low", "close", "tickvolume"]]
    d = d.rename(columns={"tickvolume": "volume"})
    if tf != 15:
        g = d.set_index("ny").resample(f"{tf}min", label="left", closed="left")
        d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last(), "volume": g["volume"].sum()}).dropna().reset_index()
    return d


def clock_check(d):
    mod = d["ny"].dt.hour * 60 + d["ny"].dt.minute
    rng = (d["high"] - d["low"]).groupby(mod).mean()
    return int(rng.idxmax()), float(rng.max()), float(rng.get(555, np.nan))


def run_split(d, **kw):
    """Run once on the whole file (indicators warm through the cut), tag trades by entry date."""
    st = {}
    r, ent = M.run(d, stats=st, return_entries=True, **kw)
    return r, ent, st


def summ(r):
    if len(r) == 0:
        return dict(n=0, ppt=np.nan, win=np.nan, pf=np.nan, tot=0.0)
    w = r > 0
    lo = -r[~w].sum()
    return dict(n=len(r), ppt=r.mean(), win=w.mean(), pf=r[w].sum() / lo if lo > 0 else np.nan,
                tot=r.sum())


if __name__ == "__main__":
    CUT = pd.Timestamp("2022-12-26")
    for tf in (15, 60):
        d = load(tf)
        pk, rmax, r0900 = clock_check(d)
        print(f"\nUS100 {tf}m  {d['ny'].min().date()}..{d['ny'].max().date()}  {len(d):,} bars  "
              f"clock check: mean range peaks at minute-of-day {pk} (570 = 09:30 NY)")
        cfgs = [
            ("defaults: LinReg13 x EMA48, both, opp cross+reverse, 2N stop", {}),
            ("EMA13 x LinReg48", dict(fT="EMA", sT="LinReg")),
            ("EMA13 x EMA48", dict(fT="EMA")),
            ("long only", dict(side="Long")),
            ("opp-cross exit, no reverse", dict(rev=False)),
            ("stop/target only, 3N target", dict(xmode="bracket", tgt_atr=3.0)),
            ("window 09:30-16:00 + flat 16:00", dict(win=(570, 960), flat=960)),
            ("+ 09:00 range, cross closes beyond", dict(orb="close", orb_end=555 if tf == 15 else 600)),
            ("+ fresh cross <=30 min, range close", dict(cross_mode="fresh", fresh_min=30, orb="close",
                                                         orb_end=555 if tf == 15 else 600)),
            ("+ breakeven 50 / secure 5", dict(be_pts=50, be_off=5)),
        ]
        rows = []
        for lab, kw in cfgs:
            r, ent, st = run_split(d, **kw)
            e = pd.to_datetime(ent)
            a, b = summ(r[e < CUT]), summ(r[e >= CUT])
            rows.append(dict(cfg=lab, **{f"A_{k}": v for k, v in a.items()},
                             **{f"B_{k}": v for k, v in b.items()}))
            print(f"  {lab:<56s} 2016-22: n {a['n']:5d} {a['ppt']:+7.2f} pts PF {a['pf']:.3f} | "
                  f"2023-25: n {b['n']:5d} {b['ppt']:+7.2f} pts PF {b['pf']:.3f}")
        pd.DataFrame(rows).to_csv(os.path.join(HERE, f"nas_{tf}m.csv"), index=False)
    # by year, defaults on 15m
    d = load(15)
    r, ent, _ = run_split(d)
    y = pd.Series(r, index=pd.to_datetime(ent)).groupby(lambda t: t.year)
    print("\n15m defaults by year:  " + "  ".join(f"{k}: {v.sum():+.0f} pts ({len(v)})" for k, v in y))
