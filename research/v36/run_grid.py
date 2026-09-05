"""PHASE 2 -- the stop, target and entry grid, on TRAIN only.

PHASE 1 SAID WHY THIS IS THE RIGHT NEXT TEST. The declared baseline lost 0.042-0.237 R per trade in
all eight cells, and the decomposition names the cause: stopped trades average -1.164 R and targets
pay +1.360 R against a nominal 1.5R -- both gaps are cost -- so the break-even win rate is 46.1%
against an actual 43.2%. And the median risk is 3.735 ATR with a p90 of 84.8 points, because
`max(ATR, sweep extreme)` anchors the stop to a sweep that can be a long way from the IFVG. The
geometry, not the trigger, is what phase 1 measured.

DECLARED GRID, stated before it is run:
    sweep definition   wick, close, pen_only, displace                     4
    entry timeframe    5m, 15m                                             2
    entry mode         edge, mid, close                                    3
    stop mode          atr, sweep, max                                     3
    ATR period         14, 20, 30                                          3
    stop multiplier    0.5, 0.75, 1.0, 1.25, 1.5                           5
    target             0.75R, 1.0R, 1.25R, 1.5R, 2.0R                      5
    = 5,400 cells. TRAIN ONLY. Nothing here touches validation or out-of-sample.

Read the MARGINAL average per axis, never the top cell -- the top cell is the maximum of 5,400
draws.
"""
from __future__ import annotations

import sys
import time
import itertools

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402
import setup as S             # noqa: E402
import engine as E            # noqa: E402
from run_base import splits, metrics   # noqa: E402

ENTRIES = ("edge", "mid", "close")
STOPS = ("atr", "sweep", "max")
ATR_P = (14, 20, 30)
STOP_K = (0.5, 0.75, 1.0, 1.25, 1.5)
TP_R = (0.75, 1.0, 1.25, 1.5, 2.0)


def hdr(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


if __name__ == "__main__":
    t0 = time.perf_counter()
    d = LV.load()
    atrs = {p: I.ema(I.true_range(d["h"], d["l"], d["c"]), p) for p in ATR_P}
    atr1 = atrs[14]
    pools = S.build_pools(d)
    ifv = {}
    for tf in (5, 15):
        r = S.htf_frame(d, tf)
        at = I.ema(I.true_range(r["h"], r["l"], r["c"]), 14)
        ifv[tf] = (r, S.find_ifvgs(r, S.find_fvgs(r, at)))

    SU = {}
    for defn in S.SWEEP_DEFS:
        sl = S.find_sweeps(d, pools, +1, defn=defn, atr=atr1)
        ss = S.find_sweeps(d, pools, -1, defn=defn, atr=atr1)
        for tf in (5, 15):
            r, iv = ifv[tf]
            su = pd.concat([S.setups(d, +1, sl, iv, r, tf), S.setups(d, -1, ss, iv, r, tf)],
                           ignore_index=True).sort_values("inv_bar_1m").reset_index(drop=True)
            if len(su):
                SU[(defn, tf)] = su

    total = (len(SU) * len(ENTRIES) * len(STOPS) * len(ATR_P) * len(STOP_K) * len(TP_R))
    hdr(f"V36 PHASE 2 -- {total:,} declared cells, TRAIN only")
    rows = []
    done = 0
    for (defn, tf), su in SU.items():
        sb = su.inv_bar_1m.to_numpy(np.int64)
        atr_by_p = {p: atrs[p][sb] for p in ATR_P}
        for ent, stp, p, k, tp in itertools.product(ENTRIES, STOPS, ATR_P, STOP_K, TP_R):
            tr, info = E.run(d, su, atr_by_p[p], entry=ent, stop=stp, stop_k=k,
                             stop_buf=0.25, tp="R", tp_r=tp, retest_bars=60)
            done += 1
            if len(tr) < 40:
                continue
            m = splits(d["tday"], tr.fill_bar.to_numpy())["train"]
            if m.sum() < 40:
                continue
            mm = metrics(tr.R.to_numpy()[m], tr.pnl.to_numpy()[m],
                         d["tday"][tr.fill_bar.to_numpy()[m]])
            if mm is None:
                continue
            rows.append(dict(defn=defn, tf=tf, entry=ent, stop=stp, atr_p=p, stop_k=k, tp_r=tp,
                             fill=info["fill_rate"], **mm))
        print(f"      {defn} {tf}m done  ({done:,}/{total:,})", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("research/v36/v36_phase2.csv", index=False)
    hdr("THE SHAPE OF THE GRID, before its top row")
    print(f"   {len(df):,} scorable of {total:,}   share with PF > 1: "
          f"{float((df.pf > 1).mean()):.3f}   median PF {df.pf.median():.3f}   "
          f"best PF {df.pf.max():.3f}   median R/trade {df.R.median():+.4f}")
    print("\n   MARGINAL AVERAGE PER AXIS -- this is what the grid says, not its maximum")
    for ax in ("defn", "tf", "entry", "stop", "atr_p", "stop_k", "tp_r"):
        g = df.groupby(ax).agg(n=("R", "size"), R=("usd", "mean"), pf=("pf", "mean"),
                               win=("win", "mean"), sh=("sharpe", "mean"))
        print(f"      {ax}")
        for k_, r_ in g.iterrows():
            print(f"         {str(k_):<10} cells {int(r_.n):>5}   R {r_.R:>+8.4f}   "
                  f"PF {r_.pf:>6.3f}   win {r_.win:>5.3f}   Sharpe {r_.sh:>+6.2f}")
    hdr("TOP 15 CELLS ON TRAIN -- the maximum of a 5,400-cell search, read with that in mind")
    print(f"   {'defn':<10}{'tf':>4}{'entry':>7}{'stop':>7}{'atrP':>6}{'k':>6}{'tp':>6}"
          f"{'fill':>7}{'n':>6}{'R/trade':>10}{'PF':>7}{'win':>7}{'Sharpe':>8}{'DD':>8}")
    for r_ in df.nlargest(15, "usd").itertuples():
        print(f"   {r_.defn:<10}{r_.tf:>4}{r_.entry:>7}{r_.stop:>7}{r_.atr_p:>6}{r_.stop_k:>6.2f}"
              f"{r_.tp_r:>6.2f}{r_.fill:>7.3f}{r_.n:>6}{r_.usd:>+10.2f}{r_.pf:>7.3f}{r_.win:>7.3f}"
              f"{r_.sharpe:>+8.2f}{r_.dd:>8.1f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
