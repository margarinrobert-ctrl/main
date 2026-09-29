"""The four Monte Carlos on the configurations the study actually turns on.

CARRIED vs MATCHED is the comparison under test, so both arms go through all four -- a finding that
survives the first two and dies in the third has been priced by execution noise, not by evidence.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_mc as MC                        # noqa: E402
from run_c2 import lengths                              # noqa: E402

TICK = {"NQ": 0.25, "US100L": 0.25, "US30L": 1.0}
CELLS = [("US100L", 30), ("US30L", 30), ("NQ", 60), ("US100L", 60), ("US30L", 120)]


def arm(mkt, tf, mode, block="A"):
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    L = lengths(tf, mode)
    C = T.channels(d, *L)
    base = T.gate_mask(adx, dist, 22.0, 0.0) & np.isfinite(atr) & (atr > 0)
    cut = T.split(d)
    lo, hi = (0, cut) if block == "A" else (cut, len(d["c"]))
    m = base.copy(); m[:lo] = False; m[hi:] = False
    cost = T.COST[mkt]
    tr = T.run(d, C, atr, m, cost)
    if len(tr) < 15:
        return None
    b = MC.boot_edge(tr, d["ts"])
    p = MC.perm_path(tr)
    e = MC.exec_mc(d, C, atr, m, cost, n=150, seed=hash((mkt, tf, mode)) % 999)
    j = MC.jitter_mc(mkt, tf, L, TICK[mkt], cost, n=100, seed=(hash((mkt, tf, mode)) % 997),
                     block=block)
    return dict(mkt=mkt, tf=tf, mode=mode, block=block, n=len(tr),
                pct=tr["pct"].mean(), tot=tr["pct"].sum(),
                boot_lo=b["lo"], boot_hi=b["hi"], p_le0=b["p_le0"],
                dd=p["realised"], dd_pctile=p["pct"], dd_p99=p["p99"],
                dd_ratio=p["p99"] / max(p["realised"], 1e-9),
                exec_p_le0=e["p_le0"], exec_sign=e["sign_kept"],
                jit_p_le0=j["p_le0"], jit_sign=j["sign_kept"],
                jit_n_lo=float(np.percentile(j["n"], 5)), jit_n_hi=float(np.percentile(j["n"], 95))), \
        dict(boot=b["draws"], perm=p["draws"], exec_tot=e["total"], jit_tot=j["total"])


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    rows, keep = [], {}
    for mkt, tf in CELLS:
        for mode in ("carried", "matched"):
            for blk in ("A", "B"):
                r = arm(mkt, tf, mode, blk)
                if r is None:
                    continue
                rows.append(r[0])
                keep[(mkt, tf, mode, blk)] = r[1]
                print(f"  done {mkt} {tf}m {mode} block {blk}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("research/tcandle/c5_mc.csv", index=False)
    np.savez_compressed("research/tcandle/c5_draws.npz",
                        **{f"{k[0]}|{k[1]}|{k[2]}|{k[3]}|{n}": v[n]
                           for k, v in keep.items() for n in v})
    print("\n" + "=" * 118)
    print("FOUR MONTE CARLOS -- edge (day-block bootstrap), path (permutation), execution, data")
    print("=" * 118)
    show = ["mkt", "tf", "mode", "block", "n", "pct", "tot", "boot_lo", "boot_hi", "p_le0",
            "dd", "dd_pctile", "dd_p99", "dd_ratio", "exec_p_le0", "jit_p_le0", "jit_sign"]
    print(df[show].to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    print("\nSUMMARY BY ARM")
    g = df.groupby(["mode", "block"]).agg(cells=("pct", "size"), pct=("pct", "mean"),
                                          tot=("tot", "mean"), p_le0=("p_le0", "mean"),
                                          dd_ratio=("dd_ratio", "mean"),
                                          jit_sign=("jit_sign", "mean"))
    print(g.to_string(float_format=lambda x: f"{x:,.4f}"))
    w = df.pivot_table(index=["mkt", "tf", "block"], columns="mode", values=["pct", "tot", "p_le0"])
    print(f"\nmatched beats carried on total return in "
          f"{int((w['tot']['matched'] > w['tot']['carried']).sum())} of {len(w)} cells")
    print(f"matched has the lower P(mean<=0) in "
          f"{int((w['p_le0']['matched'] < w['p_le0']['carried']).sum())} of {len(w)} cells")
    print(f"\ncells whose day-block bootstrap EXCLUDES zero: "
          f"{int((df.p_le0 <= 0.05).sum())} of {len(df)}")
    print(f"MC p99 drawdown / realised: median {df.dd_ratio.median():.2f}x, "
          f"range {df.dd_ratio.min():.2f}-{df.dd_ratio.max():.2f}x")
