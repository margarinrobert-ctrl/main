"""V61 stage D -- the ablation the whole study exists to make readable.

ONE geometry, the CVD gate switched on and off and swept, both blocks. Everything else identical,
so the difference is the gate and nothing else. Two geometries are run: the one the search picked
(F2) and the one the strategy ships with (S).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v61core as V                              # noqa: E402
from run_v61b import tf_data, geo_index, set_rows, take, stats  # noqa: E402
from run_v61 import AXES                         # noqa: E402

GEOS = {
    "F2 geometry (15m, Donchian 15/30, 3.0N, 6 ATR target)":
        dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=240, adapt=0, ma=-99.0, chop=99.0,
             psh=0),
    "shipped geometry (30m, Donchian 20/20, 2.0N, no target)":
        dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, ma=-99.0, chop=99.0,
             psh=0),
}
GATES = ["off", "k2w20", "k3w10", "k3w20", "k3w30", "k4w20", "k5w20", "k5w40"]


def main():
    print(__doc__)
    for label, base in GEOS.items():
        print("=" * 104)
        print(label)
        print("=" * 104)
        print(f"  {'gate':8s} {'keep':>6s} | {'n':>4s} {'pct/tr':>8s} {'total':>8s} {'PF':>5s} "
              f"{'Sh':>6s}  research | {'n':>4s} {'pct/tr':>8s} {'total':>8s} {'PF':>5s} "
              f"{'Sh':>6s}  locked")
        D, res = tf_data(base["tf"])
        g = geo_index(res["G"], base)
        for gate in GATES:
            cell = dict(base, cvd=gate)
            sel, pool = set_rows(D, res, cell)
            tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
            line = f"  {gate:8s} {100*len(sel)/len(pool):5.1f}% |"
            for blk in ("res", "lock"):
                s = stats(tr, D["cut"], blk)
                if s is None:
                    line += f" {'--':>4s}" + " " * 33
                    continue
                line += (f" {s['n']:4d} {s['pct']:+8.4f} {s['tot']:+8.2f} {s['pf']:5.2f} "
                         f"{s['sh']:+6.2f}          |")
            print(line)
        print()





def extra():
    """The two nulls for the cell the ablation table points at.

    IT WAS PICKED AFTER THE LOCKED BLOCK WAS READ, from a 16-cell table, so these p-values are
    descriptive. They are run because a recommendation without a null attached is not one.
    """
    import run_v61c as C
    cells = {
        "15m k3w30 (the ablation's best total with the gate kept)":
            dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=240, adapt=0, ma=-99.0,
                 chop=99.0, psh=0, cvd="k3w30"),
        "15m off (the same geometry with no gate)":
            dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=240, adapt=0, ma=-99.0,
                 chop=99.0, psh=0, cvd="off"),
    }
    print("=" * 104)
    print("D2. THE TWO NULLS FOR THE ABLATION'S PICK -- descriptive, chosen after the locked read")
    print("=" * 104)
    for name, cell in cells.items():
        D, res = tf_data(cell["tf"])
        g = geo_index(res["G"], cell)
        sel, pool = set_rows(D, res, cell)
        tr = take(sel, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g)
        rate = len(sel) / len(pool)
        import run_v61b as B
        ctl = B.control(pool, None, res["rows"], res["xb"], res["R"], res["pts"], res["epx"], g,
                        D["cut"], rate)
        for blk in ("res", "lock"):
            s = stats(tr, D["cut"], blk)
            c = ctl[blk][np.isfinite(ctl[blk])]
            pf = float(np.mean(c >= s["pct"])) if len(c) and rate < 0.999 else np.nan
            re = C.random_entry(D, cell, s["n"], blk)
            pe = float(np.mean(re >= s["pct"]))
            print(f"  {name[:52]:52s} {blk:5s} n {s['n']:4d} rule {s['pct']:+.4f} | "
                  f"same-selectivity filter {np.median(c) if len(c) else np.nan:+.4f} p "
                  f"{pf:.3f} | random entry {np.median(re):+.4f} p {pe:.3f}")


if __name__ == "__main__":
    main()
    extra()
