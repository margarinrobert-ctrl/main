"""Gate 1 again, on the MATCHED-REACH primary the timeframe sweep produced.

`run_c2` measured that the script's bar-count lengths are what make it a 240m-only system: hold the
TIME reach of the 240m preset constant and the research marginal goes from negative at every faster
chart to positive at four of five.  That is a different primary from the one the presets ship, and a
better-founded one, so it gets its own Gate 1 rather than inheriting the first one's verdict.

It is also the cell with the trades.  The shipped 240m preset leaves 36 research trades on NQ, which
cannot support a 96-arm feature screen whatever it scores; the matched 30m and 60m cells carry
150-500.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T                                     # noqa: E402
from run_c2 import lengths                              # noqa: E402

CELLS = [(m, tf) for m in ("NQ", "US100L", "US30L") for tf in (30, 60, 120)]


def cell(mkt, tf, n_draw=200, adx_max=22.0, ext_max=0.0):
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    e1, e2, x1, x2 = lengths(tf, "matched")
    C = T.channels(d, e1, e2, x1, x2)
    base = T.gate_mask(adx, dist, adx_max, ext_max) & np.isfinite(atr) & (atr > 0)
    cut = T.split(d)
    cost = T.COST[mkt]
    rows = []
    for blk, lo, hi in (("A_research", 0, cut), ("B_locked", cut, len(d["c"]))):
        m = base.copy(); m[:lo] = False; m[hi:] = False
        tr = T.run(d, C, atr, m, cost)
        if not len(tr):
            continue
        sig = T.signal_bars(d, C, m, atr)
        s2m = np.isfinite(C["hi2"]) & (d["h"] > C["hi2"]) & m
        s2f = float(s2m[sig].mean()) if len(sig) else 0.0
        elig = np.zeros(len(d["c"]), bool); elig[lo:hi] = True
        elig &= np.isfinite(atr) & (atr > 0)
        ctl, ccnt = T.control_entries(d, C, atr, elig, len(sig), cost, s2_frac=s2f,
                                      seed=abs(hash((mkt, tf, blk))) % 9999, n_draw=n_draw)
        pnl = tr["pnl"].to_numpy(float)
        rows.append(dict(mkt=mkt, tf=tf, e1=e1, x1=x1, block=blk, n=len(tr), sig=len(sig),
                         pct=tr["pct"].mean(),
                         pf=pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9),
                         win=float((pnl > 0).mean()), ctl_med=float(np.median(ctl)),
                         ctl_n=float(np.median(ccnt)), p=T.pval(tr["pct"].mean(), ctl)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    out = pd.concat([cell(*c) for c in CELLS], ignore_index=True)
    out.to_csv("research/tcandle/c1b_gate1_matched.csv", index=False)
    print("=" * 100)
    print("GATE 1 on the MATCHED-REACH primary (240m reach held constant), vs a random entry")
    print("=" * 100)
    print(out.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    r = out[out.block == "A_research"]
    print(f"\nresearch cells clearing p<=0.05: {(r.p <= 0.05).sum()} of {len(r)}"
          f"   (expected by chance {0.05*len(r):.1f})")
    ok = r[(r.p <= 0.05) & (r.n >= 100)]
    if len(ok):
        b = ok.sort_values("n", ascending=False).iloc[0]
        print(f"\nELIGIBLE FOR A META LAYER (passes Gate 1 and carries >=100 research trades):")
        print(ok.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
        print(f"\n-> screen cell: {b.mkt} {int(b.tf)}m matched, {int(b.n)} research trades")
    else:
        print("\nNO CELL PASSES GATE 1 WITH ENOUGH TRADES -- a meta layer cannot be built here.")
