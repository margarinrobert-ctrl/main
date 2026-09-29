"""The TIMEFRAME axis, swept in both readings, and read by MARGINAL AVERAGE.

A BAR COUNT IS NOT A SETTING -- IT IS A SETTING TIMES A TIMEFRAME.  The script's four presets lock
the chart (T1/T2 240m, T3 120m, T4 60m) and its HUD turns red on any other, which is the right
instinct; but the lengths inside it are bar counts, so the SAME preset moved one chart down halves
every reach it has.  `STUDY_V57_REVERSE_ENGINEER` measured a live instance: a 90-minute pivot and a
600-minute window run as raw bar counts on a 1-minute chart became 3 and 20 minutes, one THIRTIETH
of their reach, and the rule could not see the setups it was being asked about.

So the axis is swept twice:
  CARRIED  -- 20/55/10/20 bars at every timeframe.  What the script does today.
  MATCHED  -- the TIME reach of the 240m preset held constant, so the bar counts scale with 240/tf.
              What the preset meant.

The table is read by the marginal average over markets, never by its best cell: the top row of any
grid is the maximum of its draws, and this branch has thirteen studies whose top row inverted.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T                                     # noqa: E402

MKTS = ("NQ", "US100L", "US30L")
REF_TF = 240                                            # the preset the "matched" reading preserves


def lengths(tf, mode):
    s = T.SPEC
    if mode == "carried":
        return s["e1"], s["e2"], s["x1"], s["x2"]
    k = REF_TF / tf
    return (max(2, round(s["e1"] * k)), max(2, round(s["e2"] * k)),
            max(2, round(s["x1"] * k)), max(2, round(s["x2"] * k)))


def one(mkt, tf, mode, adx_max=22.0, ext_max=0.0):
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    e1, e2, x1, x2 = lengths(tf, mode)
    C = T.channels(d, e1, e2, x1, x2)
    mask = T.gate_mask(adx, dist, adx_max, ext_max)
    cut = T.split(d)
    out = {}
    for blk, lo, hi in (("A", 0, cut), ("B", cut, len(d["c"]))):
        m = mask.copy(); m[:lo] = False; m[hi:] = False
        tr = T.run(d, C, atr, m, T.COST[mkt])
        pnl = tr["pnl"].to_numpy(float)
        out[blk] = dict(n=len(tr), pct=tr["pct"].mean() if len(tr) else np.nan,
                        pf=(pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9)) if len(tr) else np.nan)
    return dict(mkt=mkt, tf=tf, mode=mode, e1=e1, x1=x1,
                nA=out["A"]["n"], pctA=out["A"]["pct"], pfA=out["A"]["pf"],
                nB=out["B"]["n"], pctB=out["B"]["pct"], pfB=out["B"]["pf"])


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    rows = [one(m, tf, mode) for m in MKTS for tf in T.TFS for mode in ("carried", "matched")]
    df = pd.DataFrame(rows)
    df.to_csv("research/tcandle/c2_timeframe.csv", index=False)

    print("=" * 100)
    print("TIMEFRAME AXIS -- per cell (ADX<22 gate on, no EMA ceiling)")
    print("=" * 100)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    print("\n" + "=" * 100)
    print("MARGINAL AVERAGE over the three markets -- this is the row to read")
    print("=" * 100)
    for mode in ("carried", "matched"):
        s = df[df["mode"] == mode]
        g = s.groupby("tf").agg(nA=("nA", "sum"), pctA=("pctA", "mean"), pfA=("pfA", "mean"),
                                nB=("nB", "sum"), pctB=("pctB", "mean"), pfB=("pfB", "mean"))
        print(f"\n--- {mode} ---")
        print(g.to_string(float_format=lambda x: f"{x:,.4f}"))

    print("\n" + "=" * 100)
    print("WHAT MOVING THE CHART COSTS -- the same preset on a chart it was not measured on")
    print("=" * 100)
    c = df[df["mode"] == "carried"].set_index(["mkt", "tf"])
    for m in MKTS:
        base = c.loc[(m, 240)]
        for tf in (120, 60, 30, 15):
            r = c.loc[(m, tf)]
            print(f"  {m:<7} 240m -> {tf:>3}m   research pct {base.pctA:+.4f} -> {r.pctA:+.4f}"
                  f"   trades {base.nA:>4.0f} -> {r.nA:>4.0f}   reach x{tf/240:.3f}")
