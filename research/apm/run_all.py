"""Run the whole battery on every dataset and write the study document.

    python3 research/apm/run_all.py                  # both instruments, full battery
    python3 research/apm/run_all.py --quick          # fewer bootstrap reps, for a smoke test
    python3 research/apm/run_all.py --only US30_15m
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apm_battery as B
import apm_stats as S
from apm_sim import SPECS, load, round_turn, simulate

OUT = "docs/ib/STUDY_APM_VALIDATION.md"
CACHE = os.environ.get(
    "APM_CACHE", "/tmp/apm_results.pkl")


def ship_index(grid):
    for i, g in enumerate(grid):
        if (g["ema_len"] == 21 and g["atr_den"] == 3.0 and g["upper"] == 100.0
                and g["vwap_mult"] == 2.5):
            return i
    raise SystemExit("the ship configuration is not in the grid")


def analyse(name, tf=15, reps=3000, n_synth=120, workers=4):
    t0 = time.time()
    d, spec, ship = load(name, tf)
    base = simulate(d, ship, start_date=0, pv=spec["pv"], tick=spec["tick"],
                    comm=spec["comm"], slip_t=spec["slip_t"])
    sess = B.session_axis(d, ship)
    print(f"  [{name}] base: {len(base.trades)} trades, ${base.trades['net'].sum():,.0f}")
    G = B.run_grid(name, tf, workers=workers)
    si = ship_index(G["grid"])
    print(f"  [{name}] grid: {G['mat'].shape[1]} configs  ({time.time()-t0:.0f}s)")
    r = dict(name=name, spec=spec, d_meta=dict(bars=d["n"], sessions=len(sess)),
             base=B.summarise(base.trades, sess, "ship"), diag=base.diag,
             s1=B.section1(name, tf, n_probe=25),
             s2=B.section2(G, si), s3=B.section3(G, si, base.trades, reps=reps),
             s4=B.section4(name, base.trades, sess, spec, d, tf),
             s5=B.section5(name, G, si, base.trades, sess, d, ship, spec, reps=reps),
             s5b=B.section5b(name, tf, n_synth=n_synth, n_noise=n_synth, workers=workers),
             grid=G, ship_idx=si, trades=base.trades, sessions=sess)
    print(f"  [{name}] done in {time.time()-t0:.0f}s")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--render-only", action="store_true",
                    help="re-render the study from the cached results of the last full run")
    a = ap.parse_args()
    import apm_report
    if a.render_only:
        with open(CACHE, "rb") as fh:
            res = pickle.load(fh)
        apm_report.write(res, OUT)
        print(f"re-rendered {OUT} from {CACHE}")
        return res
    names = [a.only] if a.only else ["NASDAQ_15m", "US30_15m"]
    reps = 400 if a.quick else 3000
    nsyn = 16 if a.quick else 120
    res = {}
    for n in names:
        print(f"[{n}] starting")
        res[n] = analyse(n, reps=reps, n_synth=nsyn, workers=a.workers)
    with open(CACHE, "wb") as fh:
        pickle.dump(res, fh)
    apm_report.write(res, OUT)
    print(f"\nwrote {OUT}")
    return res


if __name__ == "__main__":
    main()
