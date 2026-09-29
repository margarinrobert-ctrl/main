"""Gate 1 and the base rates -- both BEFORE any feature is scored.

Order matters and is the whole point.  A meta layer on a primary with no edge produces a primary
with no edge and fewer trades, so the primary is scored alone first and the number is frozen.  And
the base rate of every proposed pattern is read on THE TRIGGER'S OWN BARS before its P&L, because a
condition that passes 95% of the bars the rule already fires on cannot be a filter whatever its
backtest says -- eight separate families on this branch turned out to be the trigger restated.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_feat as CF                       # noqa: E402

CELLS = [("NQ", 240, "T1"), ("NQ", 240, "T2"), ("NQ", 120, "T3"), ("NQ", 60, "T4"),
         ("US100L", 240, "T1"), ("US100L", 120, "T3"), ("US100L", 60, "T4"),
         ("US30L", 240, "T1"), ("US30L", 120, "T3"), ("US30L", 60, "T4")]


def cell(mkt, tf, preset, n_draw=200):
    p = T.PRESETS[preset]
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    C = T.channels(d, T.SPEC["e1"], T.SPEC["e2"], T.SPEC["x1"], T.SPEC["x2"])
    mask = T.gate_mask(adx, dist, p["adx_max"], p["ext_max"])
    cut = T.split(d)
    cost = T.COST[mkt]
    rows = []
    for blk, lo, hi in (("A_research", 0, cut), ("B_locked", cut, len(d["c"]))):
        m = mask.copy()
        m[:lo] = False
        m[hi:] = False
        tr = T.run(d, C, atr, m, cost)
        if not len(tr):
            continue
        sig = T.signal_bars(d, C, m, atr)
        elig = np.zeros(len(d["c"]), bool)
        elig[lo:hi] = True
        elig &= np.isfinite(atr) & (atr > 0)
        s2m = np.isfinite(C["hi2"]) & (d["h"] > C["hi2"]) & m
        s2_frac = float(s2m[sig].mean()) if len(sig) else 0.0
        ctl, ccnt = T.control_entries(d, C, atr, elig, len(sig), cost, s2_frac=s2_frac,
                                      seed=hash((mkt, tf, blk)) % 9999, n_draw=n_draw)
        pnl = tr["pnl"].to_numpy(float)
        pf = pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9)
        rows.append(dict(mkt=mkt, tf=tf, preset=preset, block=blk, n=len(tr), sig=len(sig),
                         pct=tr["pct"].mean(), pf=pf, win=float((pnl > 0).mean()),
                         ctl_med=float(np.median(ctl)), ctl_n=float(np.median(ccnt)),
                         s2f=s2_frac,
                         p=T.pval(tr["pct"].mean(), ctl),
                         cost_risk=float(cost / (T.SPEC["atr_mult"] * np.nanmedian(tr["sig_atr"])))))
    return pd.DataFrame(rows)


def base_rates(mkt="NQ", tf=240, preset="T1"):
    p = T.PRESETS[preset]
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    C = T.channels(d, T.SPEC["e1"], T.SPEC["e2"], T.SPEC["x1"], T.SPEC["x2"])
    mask = T.gate_mask(adx, dist, p["adx_max"], p["ext_max"])
    cut = T.split(d)
    m = mask.copy(); m[cut:] = False
    sig = T.signal_bars(d, C, m, atr)
    F = CF.build(d, atr)
    pop = np.zeros(len(d["c"]), bool); pop[:cut] = True
    pop &= np.isfinite(atr) & (atr > 0)
    rows = []
    for k, v in F.items():
        b = np.unique(v[np.isfinite(v)])
        if len(b) <= 2 and set(b.tolist()) <= {0.0, 1.0}:
            on_sig = float(np.nanmean(v[sig]))
            on_pop = float(np.nanmean(v[pop]))
        else:                                   # continuous -> cut at its RESEARCH median
            thr = float(np.nanmedian(v[pop]))
            on_sig = float(np.nanmean(v[sig] >= thr))
            on_pop = float(np.nanmean(v[pop] >= thr))
        rows.append(dict(feat=k, on_signal=on_sig, on_pop=on_pop,
                         lift=on_sig / on_pop if on_pop > 0 else np.nan))
    return pd.DataFrame(rows).sort_values("on_signal", ascending=False), sig, F, pop


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print("=" * 96)
    print("GATE 1 -- the pasted script's presets against a matched RANDOM ENTRY")
    print("=" * 96)
    out = pd.concat([cell(*c) for c in CELLS], ignore_index=True)
    out.to_csv("research/tcandle/c1_gate1.csv", index=False)
    print(out.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    r = out[out.block == "A_research"]
    print(f"\nresearch blocks clearing p<=0.05: {(r.p <= 0.05).sum()} of {len(r)}"
          f"   (expected by chance {0.05*len(r):.1f})")

    print("\n" + "=" * 96)
    print("BASE RATES on the trigger's own bars -- NQ 240m T1, research block")
    print("=" * 96)
    br, sig, F, pop = base_rates()
    br.to_csv("research/tcandle/c1_baserates.csv", index=False)
    print(f"signal bars: {len(sig)}   population bars: {int(pop.sum())}\n")
    print(br.head(14).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
    print("   ...")
    print(br.tail(8).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
    inert = br[(br.on_signal >= 0.95) | (br.on_signal <= 0.02)]
    print(f"\nINERT on the trigger's own bars (pass >=95% or <=2%): {len(inert)} of {len(br)}")
    print("  " + ", ".join(inert.feat.tolist()))
