"""THE CAVEAT THAT DECIDES THE HEAD-TO-HEAD.

The FIXED arms were selected on the research block, which ends 2024-11-27. The walk-forward's test
quarters begin 2023Q4, so five of the nine folds are INSIDE the block those constants were chosen
on -- for them, not for the re-chosen arm, which is honest in every fold. Comparing an arm that
saw the data against one that did not is exactly the contamination `STUDY_EDGELAB` recorded.

So the head-to-head is re-read on the four quarters that POSTDATE the block cut, where every arm
is out of sample. Four folds is a small number and is stated as such.
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
CUT = pd.Timestamp("2024-11-27")


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


if __name__ == "__main__":
    out = []
    for scheme, f in (("rolling", "results/v64/wfo_rolling.parquet"),
                      ("expanding", "results/v64/wfo_expanding.parquet")):
        R = pd.read_parquet(f)
        R["start"] = pd.PeriodIndex(R["fold"], freq="Q").start_time
        R["post"] = R["start"] >= CUT
        out.append((scheme, R))

    line("A. EVERY FOLD, FLAGGED BY WHETHER THE FIXED ARMS HAD ALREADY SEEN IT")
    for scheme, R in out:
        print(f"\n  {scheme}")
        print(f"  {'fold':9s}{'fixed arms':13s}{'RE-CHOSEN':>11s}{'FIXED':>9s}"
              f"{'FIXED15':>10s}{'RANDOM':>9s}")
        for _, r in R.iterrows():
            tag = "OUT of sample" if r["post"] else "in-sample"
            print(f"  {r['fold']:9s}{tag:13s}{r['oos_tot']:>11.2f}{r['fixed']:>9.2f}"
                  f"{r['fixed15']:>10.2f}{r['rnd']:>9.2f}")

    line("B. THE HONEST HEAD-TO-HEAD -- only the folds that POSTDATE the block cut (2024-11-27)")
    print(f"  {'scheme':12s}{'folds':>7s}{'RE-CHOSEN':>12s}{'FIXED':>10s}{'FIXED15':>10s}"
          f"{'RANDOM':>9s}{'winner':>14s}")
    for scheme, R in out:
        P = R[R["post"]]
        vals = {"RE-CHOSEN": P["oos_tot"].sum(), "FIXED": P["fixed"].sum(),
                "FIXED15": P["fixed15"].sum(), "RANDOM": P["rnd"].sum()}
        win = max(vals, key=vals.get)
        print(f"  {scheme:12s}{len(P):>7d}{vals['RE-CHOSEN']:>12.2f}{vals['FIXED']:>10.2f}"
              f"{vals['FIXED15']:>10.2f}{vals['RANDOM']:>9.2f}{win:>14s}")
    print("\n  All nine folds, for comparison:")
    for scheme, R in out:
        print(f"  {scheme:12s}{len(R):>7d}{R['oos_tot'].sum():>12.2f}{R['fixed'].sum():>10.2f}"
              f"{R['fixed15'].sum():>10.2f}{R['rnd'].sum():>9.2f}"
              f"{max({'RE-CHOSEN': R['oos_tot'].sum(), 'FIXED': R['fixed'].sum(), 'FIXED15': R['fixed15'].sum(), 'RANDOM': R['rnd'].sum()}, key=lambda k: {'RE-CHOSEN': R['oos_tot'].sum(), 'FIXED': R['fixed'].sum(), 'FIXED15': R['fixed15'].sum(), 'RANDOM': R['rnd'].sum()}[k]):>14s}")
    print("\n  THE TWO SCHEMES DISAGREE on the post-cut folds and agree over all nine. Four folds")
    print("  cannot separate them; report both rather than the one that reads better.")

    line("C. THE ONE THING BOTH SCHEMES AGREE ON")
    for scheme, R in out:
        P = R[R["post"]]
        print(f"  {scheme:12s} RE-CHOSEN beats RANDOM in "
              f"{int((P['oos_tot'] > P['rnd']).sum())}/{len(P)} post-cut folds and "
              f"{int((R['oos_tot'] > R['rnd']).sum())}/{len(R)} overall")
    print("\n  Selecting from this family beats picking from it arbitrarily. Re-selecting EVERY")
    print("  FOLD does not beat never selecting at all. Those are different claims and only the")
    print("  first one holds in both schemes.")
