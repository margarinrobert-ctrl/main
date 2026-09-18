"""The ATR length is a bar count too -- does the reach fix have to scale it as well?

`run_c2` scaled the four CHANNELS and left `atrLen = 20` alone.  But ATR(20) is 5 hours on a 15m
chart and 80 on a 240m one, and ATR sets the STOP distance and the ladder step -- so a matched
reading that scales the channels and not the ATR is only half a units fix, and the two halves change
different parts of the geometry.  Three arms, no controls, marginal average over three markets:

    A  channels carried, ATR 20            the shipped script
    B  channels matched, ATR 20            what run_c2 measured
    C  channels matched, ATR matched       the fully reach-matched reading
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T                                     # noqa: E402
from run_c2 import lengths, REF_TF                      # noqa: E402

MKTS = ("NQ", "US100L", "US30L")


def one(mkt, tf, arm):
    d = T.frame(mkt, tf)
    if arm == "A":
        e1, e2, x1, x2 = lengths(tf, "carried")
        alen = T.SPEC["atr_len"]
    else:
        e1, e2, x1, x2 = lengths(tf, "matched")
        alen = T.SPEC["atr_len"] if arm == "B" else int(max(2, round(T.SPEC["atr_len"] * REF_TF / tf)))
    atr, adx, dist = T.context(d, atr_len=alen)
    C = T.channels(d, e1, e2, x1, x2)
    base = T.gate_mask(adx, dist, 22.0, 0.0) & np.isfinite(atr) & (atr > 0)
    cut = T.split(d)
    r = dict(mkt=mkt, tf=tf, arm=arm, atr_len=alen)
    for blk, lo, hi in (("A", 0, cut), ("B", cut, len(d["c"]))):
        m = base.copy(); m[:lo] = False; m[hi:] = False
        tr = T.run(d, C, atr, m, T.COST[mkt])
        pnl = tr["pnl"].to_numpy(float)
        r[f"n{blk}"] = len(tr)
        r[f"pct{blk}"] = tr["pct"].mean() if len(tr) else np.nan
        r[f"tot{blk}"] = tr["pct"].sum() if len(tr) else np.nan
        r[f"pf{blk}"] = (pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9)) if len(tr) else np.nan
    return r


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    rows = [one(m, tf, a) for m in MKTS for tf in (15, 30, 60, 120) for a in ("A", "B", "C")]
    df = pd.DataFrame(rows)
    df.to_csv("research/tcandle/c2b_atrscale.csv", index=False)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print("\nMARGINAL AVERAGE over the three markets")
    g = df.groupby(["arm", "tf"]).agg(nA=("nA", "sum"), pctA=("pctA", "mean"), totA=("totA", "mean"),
                                      nB=("nB", "sum"), pctB=("pctB", "mean"), totB=("totB", "mean"))
    print(g.to_string(float_format=lambda x: f"{x:,.4f}"))
    print("\nARM MEANS (all timeframes, all markets)")
    print(df.groupby("arm")[["pctA", "totA", "pctB", "totB"]].mean()
          .to_string(float_format=lambda x: f"{x:,.4f}"))
    w = df.pivot_table(index=["mkt", "tf"], columns="arm", values=["pctA", "pctB", "totA", "totB"])
    for col in ("pctA", "pctB", "totA", "totB"):
        print(f"  C beats B on {col}: {int((w[col]['C'] > w[col]['B']).sum())} of {len(w)}"
              f"   |  B beats A: {int((w[col]['B'] > w[col]['A']).sum())} of {len(w)}")
