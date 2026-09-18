"""THE CHECK THE FIRST TWO RUNS NEVER APPLIED TO THE OVERLAY ITSELF: the block split.

`run_ov3` showed the position lock reverses four of the five falsification tests. That result was
read over the WHOLE sample, which is exactly the mistake `STUDY_TOP5` recorded from the other
direction -- a control computed over all trades is a research-block statistic. So: split the locked
comparison at the branch's own boundary, run the placebo inside each block, and read the SHAPE. An
execution improvement that is real should be present in both; one that decays to nothing on the
block that was never used to choose K is a research artifact.

Also stresses the cost, because an entry-price improvement of this size is far larger than any
spread-capture story and needs to be described as what it is.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ov_core as O                      # noqa: E402
import overlay_eval as E                 # noqa: E402

K_MAIN = 30
pd.set_option("display.width", 200)


def line(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


if __name__ == "__main__":
    D = O.build("NQ", 1)
    n_sig = len(D["sig_bar"])
    base, _ = O.trades(D, gate=0, lock=1)
    ov, _ = O.trades(D, gate=1, K=K_MAIN, lock=1)

    # a trade belongs to the block its ENTRY bar sits in
    def blk(t):
        eb = t["entry_bar"].to_numpy()
        return np.where(D["blocks"]["research"][eb], "research", "locked")

    base = base.assign(block=blk(base))
    ov = ov.assign(block=blk(ov))

    line("A. THE BLOCK SPLIT -- the same comparison, read separately on each block")
    print(f"  {'block':10s}{'n':>7s}{'base pts':>12s}{'ovl pts':>12s}{'Δ/trade':>11s}"
          f"{'base tot':>12s}{'ovl tot':>12s}{'total Δ':>11s}{'Δ %':>8s}")
    for b in ("research", "locked"):
        bb, oo = base[base.block == b], ov[ov.block == b]
        bt, ot = bb["net"].sum(), oo["net"].sum()
        print(f"  {b:10s}{len(bb):7,d}{bb['net'].mean():12,.3f}{oo['net'].mean():12,.3f}"
              f"{oo['net'].mean()-bb['net'].mean():+11,.3f}{bt:12,.0f}{ot:12,.0f}"
              f"{ot-bt:+11,.0f}{100*(ot-bt)/bt:+8.2f}")
    print("\n  RIGHT SHAPE = present on both, decaying on locked. WRONG SHAPE = absent on")
    print("  research and appearing on locked, which this branch has recorded seven times.")

    line("B. THE PLACEBO, RUN SEPARATELY INSIDE EACH BLOCK")
    for b in ("research", "locked"):
        mask_sig = D["blocks"][b][D["sig_bar"]]
        bb = base[base.block == b]
        base_total = bb["net"].sum()
        observed = ov[ov.block == b]["net"].sum() - base_total
        obs_delays = ov[ov.block == b]["delay"].to_numpy()

        def run_fn(sample_delays, _m=mask_sig, _bt=base_total, _b=b):
            d = np.round(sample_delays(n_sig)).astype(np.int64)
            t, _ = O.trades(D, gate=2, K=K_MAIN, rand_delay=d, lock=1)
            eb = t["entry_bar"].to_numpy()
            sel = D["blocks"][_b][eb]
            return float(t["net"].to_numpy()[sel].sum() - _bt)

        pl = E.placebo_test(run_fn, obs_delays, n_sims=200, seed=7,
                            observed_improvement=observed)
        print(f"  {b:10s} observed {observed:+9,.1f}   placebo mean {pl['placebo_mean']:+9,.1f}   "
              f"5-95% [{pl['placebo_q05']:+8,.1f}, {pl['placebo_q95']:+8,.1f}]   "
              f"pctile {pl['percentile_vs_placebo']:5.1f}   p {pl['p_value_one_sided']:.4f}")

    line("C. WHAT IS THE IMPROVEMENT, IN BASIS POINTS OF THE ENTRY PRICE?")
    m = base.merge(ov[["signal_id", "entry_px"]], on="signal_id", suffixes=("_b", "_o"))
    imp = m["entry_px_b"] - m["entry_px_o"]
    bps = 1e4 * imp / m["entry_px_b"]
    print(f"  matched {len(m):,} trades")
    print(f"  mean entry improvement  {imp.mean():+.3f} points = {bps.mean():+.3f} bps")
    print(f"  median                  {imp.median():+.3f} points = {bps.median():+.3f} bps")
    print(f"  share of trades improved {100*(imp>0).mean():.1f}%  unchanged {100*(imp==0).mean():.1f}%")
    print(f"\n  half the Roll implied effective spread on this series is 0.1871 bps.")
    print(f"  the overlay is claiming {bps.mean()/0.1871:.1f}x that PER TRADE, which is far more")
    print(f"  than any spread-capture story can supply. It is not a better FILL at the same level;")
    print(f"  it is a better LEVEL, reached by waiting a median {int(ov['delay'].median())} minutes for a pullback.")
    print(f"  That is the branch's entry-mechanic finding (STUDY_LIMIT_ENTRY, research/atme/,")
    print(f"  STUDY_V58_ANATOMY), not implementation shortfall -- and it must be judged as a")
    print(f"  SIGNAL change, with the trial count that implies, not as a cost saving.")

    line("D. COST STRESS -- does the improvement survive a wider round turn?")
    print(f"  {'cost x':>8s}{'base tot':>13s}{'ovl tot':>13s}{'Δ':>11s}{'base pts':>11s}{'ovl pts':>11s}")
    for mult in (1.0, 2.0, 4.0, 8.0):
        extra = 2 * D["cost"] * (mult - 1.0)
        bt = (base["net"] - extra).sum()
        ot = (ov["net"] - extra).sum()
        print(f"  {mult:8.1f}{bt:13,.0f}{ot:13,.0f}{ot-bt:+11,.0f}"
              f"{(base['net']-extra).mean():11,.3f}{(ov['net']-extra).mean():11,.3f}")

    line("E. DELAY DISTRIBUTION -- what the gate actually does")
    d = ov["delay"]
    print(f"  mean {d.mean():.2f} min   median {d.median():.0f}   p90 {d.quantile(0.9):.0f}   "
          f"max {d.max():.0f}   share entering immediately {100*(d==0).mean():.1f}%   "
          f"share hitting the K={K_MAIN} timeout {100*(d>=K_MAIN).mean():.1f}%")
