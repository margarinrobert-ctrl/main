"""The matched control on the walk-forward's out-of-sample trades.

A walk-forward total is not evidence until it beats an entry that carries no information. Each arm
is scored against random entries drawn from the bars it was ELIGIBLE to trade in the same test
windows, running the IDENTICAL stop, target, channel exit, clock and position lock -- so the only
thing that differs is which bar the trade starts on. 1,000 draws.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "v61"))

import v64opt as O  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)

TFS = (15, 30, 60)
ARMS = {
    "FIXED incumbent (30m)": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, k=3, w=20),
    "FIXED 15m preset": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, k=3, w=30),
    "WFO modal cell (15/15/30/2.5/0/3/40)": dict(tf=15, ent=15, exN=30, stop=2.5, tp=0.0,
                                                 k=3, w=40),
}


def full(p):
    return dict(hold=480, adapt=0, use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0, **p)


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in TFS}
    times = {tf: pd.DatetimeIndex(Ds[tf]["ix"]) for tf in TFS}
    q = pd.PeriodIndex(times[30], freq="Q").unique().sort_values()
    oos_start = q[4].start_time          # the first quarter any fold could test on

    print("=" * 122)
    print("THE MATCHED CONTROL on the walk-forward out-of-sample span "
          f"({oos_start.date()} onward -- every quarter after the first training window)")
    print("=" * 122)
    print(f"  {'arm':40s}{'n':>6s}{'observed %/t':>14s}{'total %':>10s}"
          f"{'control med':>13s}{'control 5-95%':>24s}{'p':>8s}")
    rng = np.random.default_rng(11)
    for nm, cfg in ARMS.items():
        D = Ds[cfg["tf"]]
        p = full(cfg)
        R, pct, blk, sig = O.evaluate(D, p)
        ts = times[cfg["tf"]][sig]
        m = np.asarray(ts >= oos_start)
        obs = pct[m]
        if len(obs) < 10:
            print(f"  {nm:40s}  too few out-of-sample trades")
            continue
        # the eligible pool: any bar in the same span with a finite ATR and a formed channel
        ent = D["ent_all"][int(cfg["ent"]) - O.CH_MIN]
        ok = np.isfinite(ent) & np.isfinite(D["atr"]) & (D["atr"] > 0)
        ok &= np.asarray(times[cfg["tf"]] >= oos_start)
        ok[:1000] = False
        ok[int(D["last_bar"]):] = False
        pool = np.flatnonzero(ok)
        draws = np.zeros(1000)
        for d in range(1000):
            pick = np.sort(rng.choice(pool, size=min(len(obs) * 3, len(pool)), replace=False))
            v = O.evaluate_at(D, p, pick)
            draws[d] = v.mean() if len(v) else 0.0
        pv = float((draws >= obs.mean()).mean())
        print(f"  {nm:40s}{len(obs):>6d}{obs.mean():>14.4f}{obs.sum():>10.2f}"
              f"{np.median(draws):>13.4f}"
              f"   [{np.quantile(draws, .05):+9.4f}, {np.quantile(draws, .95):+8.4f}]"
              f"{pv:>8.3f}")
    print("\n  The control is oversampled 3x on entry bars and then thinned by the SAME position")
    print("  lock, so it lands near the rule's own trade count rather than clustering -- the")
    print("  construction STUDY_V59 had to fix after an unsorted control rejected nothing.")
