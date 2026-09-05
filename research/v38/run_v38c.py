"""V38 part 3 -- THE CONTROL, which is what decides whether part 2 is a finding or drift.

Part 2 produced the shape this branch has seen before (`STUDY_V12_DONCHIAN_3020`): the
configuration FAILS on the market that chose it and HOLDS on two that had no part in the search --
US30 PF 1.32 over 523 trades, US100 PF 1.33 over 621, and the pre-2023 slices as good or better.

That is not yet evidence. Every one of these markets ROSE over the period, the rule is long-only,
and a trailing-exit long system in a rising market is a drift harvester. `CLAUDE.md`: "the right
null for a breakout system is the same trade management with a RANDOM entry", and "a random entry
at matched risk beats the Donchian breakout" is already recorded three times here.

TWO NULLS, because they answer different questions:

  MATCHED CONTROL   random entry bars drawn at the SAME minute of day, in the same block, the same
                    count, the same side, the same stop/exit/target geometry, through the same
                    one-position lock. It prices drift, session timing, barrier width and costs at
                    once. This is the question "is the TRIGGER worth anything".
  SELECTIVITY       a random filter keeping the same NUMBER of breakout bars the LRMA/MA stack
                    keeps. It prices restrictiveness alone -- `CLAUDE.md` records an ATR filter
                    that looked excellent (PF 1.42 -> 1.77) and was indistinguishable from a random
                    filter of the same selectivity. This is the question "is the FILTER worth
                    anything".

Then a per-year walk-forward on the fresh markets, and a vectorbt re-simulation of the winner as
an INDEPENDENT ENGINE -- a second implementation is the only thing that has ever caught the order
model bugs on this branch.

Usage: python3 research/v38/run_v38c.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v33")
sys.path.insert(0, "research/v38")
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
from run_v38 import hdr      # noqa: E402
from run_v38b import run_cfg, line, KEYS                      # noqa: E402

CANDS = {
    "TOP/CONSENSUS": dict(tf=30, don_e=70, don_x=30, stop_n=2.5, tp_r=0.0,
                          lr_len=50, lr_read="both", ma_len=250, ma_read="lrma>ma"),
    "ROBUST": dict(tf=30, don_e=70, don_x=30, stop_n=2.5, tp_r=0.0,
                   lr_len=80, lr_read="slope>0", ma_len=250, ma_read="close>ma"),
}
DRAWS = 400


def matched_control(P, ten, cfg, sb, mod, mask, draws=DRAWS, seed=17):
    """Same count, same minute-of-day distribution, same geometry, same lock. Random ENTRY BAR."""
    xb, pnl, _w = ten[(cfg["don_x"], cfg["stop_n"], cfg["tp_r"])]
    ok = np.flatnonzero(mask & np.isfinite(P["atr"]) & (xb >= 0))
    pool = {}
    for t in np.unique(mod[sb]):
        p = ok[mod[ok] == t]
        if len(p):
            pool[int(t)] = p
    want = mod[sb]
    rng = np.random.default_rng(seed)
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    out = []
    for _ in range(draws):
        pick = np.sort(np.array([rng.choice(pool[int(t)]) for t in want if int(t) in pool],
                                np.int64))
        k = G._lock(pick, xb, pnl, bp, bs)
        if k < 10:
            continue
        p = bp[:k]
        w, lo = p[p > 0], p[p < 0]
        out.append((float(p.mean()), float(w.sum() / abs(lo.sum())) if len(lo) else np.nan))
    return np.array(out)


def selectivity_control(P, ten, msk, cfg, mask, n_keep, draws=DRAWS, seed=23):
    """Same number of BREAKOUT bars, chosen at random instead of by the LRMA/MA stack."""
    base = msk[(cfg["don_e"], cfg["lr_len"], "off", cfg["ma_len"], "off")]
    base = base[mask[base]]
    if len(base) <= n_keep:
        return None
    xb, pnl, _w = ten[(cfg["don_x"], cfg["stop_n"], cfg["tp_r"])]
    rng = np.random.default_rng(seed)
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    out = []
    for _ in range(draws):
        pick = np.sort(rng.choice(base, size=n_keep, replace=False))
        k = G._lock(pick, xb, pnl, bp, bs)
        if k < 10:
            continue
        p = bp[:k]
        w, lo = p[p > 0], p[p < 0]
        out.append((float(p.mean()), float(w.sum() / abs(lo.sum())) if len(lo) else np.nan))
    return np.array(out)


def pval(arr, obs):
    return float(((arr >= obs).sum() + 1) / (len(arr) + 1))


def main():
    t0 = time.perf_counter()
    hdr("8. THE MATCHED CONTROL ON THE TWO FRESH MARKETS -- is the trigger worth anything?")
    print("   random entry bars at the SAME minute of day, same count, same geometry, same lock.")
    print(f"   {DRAWS} draws per cell. The rule must beat this, not zero.")
    res = []
    for mkt in ("US30L", "US100L"):
        pv = F.INSTR[mkt]["pv"]
        d = F.frame(mkt, 30)
        P = G.prep(30, d=d, pv=pv)
        msk, ten = G.masks(P), G.tensor(P)
        mod = d["mod"]
        cutoff = np.datetime64("2022-12-26").astype("datetime64[ns]").astype("int64")
        for span, mask in (("all", np.ones(P["n"], bool)), ("pre-2023", P["day"] < cutoff)):
            for nm, cfg in CANDS.items():
                m, p, sb, _w = run_cfg(P, ten, msk, cfg, mask, np.unique(P["day"][mask]))
                if m is None:
                    continue
                A = matched_control(P, ten, cfg, sb, mod, mask)
                S = selectivity_control(P, ten, msk, cfg, mask, len(sb))
                pu, pf_ = pval(A[:, 0], m["usd"]), pval(A[:, 1], m["pf"])
                print(f"\n   {mkt} {span} -- {nm}")
                print(line("rule", m))
                print(f"      matched control: $/trade mean {A[:, 0].mean():>+8.2f}  "
                      f"p95 {np.percentile(A[:, 0], 95):>+8.2f}   -> p(usd) {pu:.3f}   "
                      f"PF mean {np.nanmean(A[:, 1]):.3f} -> p(PF) {pf_:.3f}   "
                      f"{'CLEARS' if pu <= 0.05 else 'FAILS'}")
                if S is not None:
                    ps = pval(S[:, 0], m["usd"])
                    print(f"      selectivity ctrl: $/trade mean {S[:, 0].mean():>+8.2f}   "
                          f"-> p {ps:.3f}   PF mean {np.nanmean(S[:, 1]):.3f}   "
                          f"{'filter earns its keep' if ps <= 0.05 else 'a RANDOM filter of the same selectivity does as well'}")
                else:
                    ps = np.nan
                res.append(dict(mkt=mkt, span=span, cand=nm, pf=m["pf"], usd=m["usd"],
                                n=m["n"], p_matched=pu, p_sel=ps))
        if mkt == "US30L":
            hdr("9. PER-YEAR ON THE FRESH MARKETS -- which years carry it")
        yr = pd.to_datetime(P["day"]).year
        for nm, cfg in CANDS.items():
            m, p, sb, _w = run_cfg(P, ten, msk, cfg, np.ones(P["n"], bool), np.unique(P["day"]))
            y = yr[sb]
            tab = pd.DataFrame(dict(y=y, p=p)).groupby("y").agg(
                n=("p", "size"), net=("p", "sum"), per=("p", "mean"))
            pos = int((tab.net > 0).sum())
            print(f"\n   {mkt} 30m {nm}: {pos} of {len(tab)} years positive")
            print("      " + "  ".join(f"{int(i)}:{r.net:>+8,.0f}" for i, r in tab.iterrows()))
    R = pd.DataFrame(res)
    R.to_csv("research/v38/v38_controls.csv", index=False)
    hdr("VERDICT ON THE CONTROLS")
    print(f"   cells clearing the matched control at p<=0.05: "
          f"{int((R.p_matched <= 0.05).sum())} of {len(R)}")
    print(f"   cells clearing the selectivity control at p<=0.05: "
          f"{int((R.p_sel <= 0.05).sum())} of {int(R.p_sel.notna().sum())}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
