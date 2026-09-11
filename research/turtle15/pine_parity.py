"""Does the shipped Pine reproduce mirror.run, and where exactly does it not?

A Pine port cannot be asserted by reading it. This transcribes the SHIPPED SCRIPT'S ORDER MODEL
-- orders placed at a bar's close are live from the next bar, one ladder rung per bar, no exit
order during the entry bar -- and runs it on the same bars as the engine, with the ENGINE'S
tie-break (stop wins when target and stop share a bar) so the only surviving differences are
order TIMING. Anything this prints is a real property of the port, not an artefact of the test.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15")
import fastbars, mirror, feats  # noqa: E402

PRESETS = {
    "#1":  dict(e1=30, x1=20, atr_mult=2.0, units=2, adx=25.0, dist=0.0, vol=1.0, tp=1.0),
    "#5":  dict(e1=30, x1=20, atr_mult=2.5, units=3, adx=25.0, dist=0.0, vol=1.2, tp=1.0),
    "#8":  dict(e1=30, x1=20, atr_mult=2.5, units=3, adx=15.0, dist=0.0, vol=0.0, tp=2.0),
    "#10": dict(e1=10, x1=20, atr_mult=2.0, units=2, adx=25.0, dist=1.0, vol=1.2, tp=1.0),
}


def gate(F, p, n):
    g = np.ones(n, bool)
    if p["adx"] > 0:
        g &= np.nan_to_num(F["adx"] >= p["adx"], nan=False)
    if p["dist"] > 0:
        g &= np.nan_to_num(F["ema_dist_atr"] >= p["dist"], nan=False)
    if p["vol"] > 0:
        g &= np.nan_to_num(F["atr_ratio"] >= p["vol"], nan=False)
    return g


def run_pine(d, mask, atr, C, atr_mult, pyr, max_units, tp_r, cost, skip_win=True,
             flat_mod=None):
    """The SHIPPED SCRIPT's semantics, bar-close order placement and all.

    The protective bracket is placed on the SIGNAL bar alongside the entry, so it is live during
    the entry bar -- `loss`/`profit` are measured by Pine from the actual fill, which is what the
    engine anchors to while the position is one unit. Its channel leg reads the SIGNAL bar's
    channel, one bar staler than the engine's.

    `flat_mod` reproduces the script's flatten: a market order placed at the CLOSE of the first
    bar with mod >= flat_mod, filling at the NEXT bar's open. The engine exits at that bar's
    close, so this is one bar later and at a different price."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    rows = []
    units = last_cnt = sys_on = 0
    sig_atr = last_fill = next_add = avg = np.nan
    last_win = False
    exit_bar = -1
    sig_bar = -1
    pend = None                  # market order + its bracket -> fills at next open
    pend_flat = False            # close_all placed at the last close, fills at THIS open
    lad_lvl = None               # ladder stop order live THIS bar
    ex_stop = ex_tp = None       # exit levels live THIS bar
    for t in range(1, n):
        # ---- A: intrabar, resolving orders placed at t-1's close ----------------------------
        if pend_flat:
            pend_flat = False
            if units > 0:
                pnl = (o[t] - avg) * units - cost * units      # fills at THIS bar's open
                rows.append((sig_bar, t, units, avg, o[t], pnl))
                last_win = pnl > 0
                exit_bar = t
                units = last_cnt = sys_on = 0
                sig_atr = last_fill = next_add = avg = np.nan
                lad_lvl = ex_stop = ex_tp = None
            pend = None
        if pend is not None:
            sys_on, sig_atr, sig_bar, ch_sig = pend
            avg = last_fill = o[t]
            units = 1
            next_add = last_fill + pyr * sig_atr
            pend = None
            lad_lvl = None                        # ladder is not live until this bar's close
            a_stop = last_fill - atr_mult * sig_atr
            ex_stop = a_stop if not np.isfinite(ch_sig) else max(a_stop, ch_sig)
            ex_tp = (avg + tp_r * atr_mult * sig_atr) if (tp_r is not None and tp_r > 0) else None
        elif lad_lvl is not None:
            # EVERY remaining rung is resting simultaneously, so several can fill in one bar --
            # the rung levels are deterministic (entry + k * pyr * N), so they can all be placed.
            for lvl_k in lad_lvl:
                if units >= max_units or h[t] < lvl_k:
                    break
                last_fill = lvl_k
                avg = (avg * units + last_fill) / (units + 1)
                units += 1
                next_add = last_fill + pyr * sig_atr
        if units > 0 and ex_stop is not None:
            hit_sl = l[t] <= ex_stop
            hit_tp = ex_tp is not None and h[t] >= ex_tp
            if hit_sl or hit_tp:
                lvl = ex_stop if hit_sl else ex_tp     # engine tie-break: stop wins
                pnl = (lvl - avg) * units - cost * units
                rows.append((sig_bar, t, units, avg, lvl, pnl))
                last_win = pnl > 0
                exit_bar = t
                units = last_cnt = sys_on = 0
                sig_atr = last_fill = next_add = avg = np.nan
                lad_lvl = ex_stop = ex_tp = None
        # ---- B: at the close of t, place the orders that are live on t+1 ---------------------
        last_cnt = units
        lad_lvl = ex_stop = ex_tp = None
        if units == 0:
            if mask[t] and np.isfinite(atr[t]) and atr[t] > 0 and t > exit_bar:
                s2 = np.isfinite(C["hi2"][t]) and h[t] > C["hi2"][t]
                s1 = np.isfinite(C["hi1"][t]) and h[t] > C["hi1"][t]
                sysn = 2 if s2 else (1 if s1 else 0)
                if sysn == 1 and skip_win and last_win:
                    last_win = False
                elif sysn > 0:
                    pend = (sysn, atr[t], t, C["lo1"][t] if sysn == 1 else C["lo2"][t])
        else:
            if 0 < units < max_units and pyr > 0 and np.isfinite(last_fill):
                lad_lvl = [last_fill + k * pyr * sig_atr for k in range(1, max_units - units + 1)]
            ch = C["lo1"][t] if sys_on == 1 else C["lo2"][t]
            a_stop = last_fill - atr_mult * sig_atr
            ex_stop = a_stop if not np.isfinite(ch) else max(a_stop, ch)
            if tp_r is not None and tp_r > 0:
                ex_tp = avg + tp_r * atr_mult * sig_atr
        # the flatten runs LAST and cancels what the blocks above just placed
        if flat_mod is not None and d["mod"][t] >= flat_mod:
            lad_lvl = ex_stop = ex_tp = None
            if units > 0:
                pend_flat = True
            pend = None
    return pd.DataFrame(rows, columns=["sig", "exit", "units", "entry", "lvl", "pnl"])


if __name__ == "__main__":
    d = fastbars.bars(15)
    n = len(d["c"])
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    cost = 1.72
    Fc = feats.build(d, atr, mirror.channels(d["h"], d["l"]))
    print(f"NQ 15m, {n:,} bars, cost {cost} pts/unit round turn\n")
    hdr = (f"{'preset':6} {'engine n':>9} {'pine n':>8} {'same sig':>9} {'sig match':>10} "
           f"{'eng pts/tr':>11} {'pine pts/tr':>12} {'eng PF':>7} {'pine PF':>8}")
    print(hdr); print("-" * len(hdr))
    for name, p in PRESETS.items():
        C = mirror.channels(d["h"], d["l"], p["e1"], 55, p["x1"], 20)
        g = gate(Fc, p, n)
        e = mirror.run(d, 1, g, atr, C, atr_mult=p["atr_mult"], max_units=p["units"],
                       cost=cost, tp_r=p["tp"])
        q = run_pine(d, g, atr, C, p["atr_mult"], 0.5, p["units"], p["tp"], cost)
        se, sq = set(e.sig.tolist()), set(q.sig.tolist())
        both = se & sq
        pf = lambda x: (x[x > 0].sum() / abs(x[x < 0].sum())) if (x < 0).any() else np.nan
        print(f"{name:6} {len(e):>9,} {len(q):>8,} {len(both):>9,} "
              f"{len(both)/max(len(se),1):>9.1%} {e.pnl.mean():>11.2f} {q.pnl.mean():>12.2f} "
              f"{pf(e.pnl.to_numpy()):>7.2f} {pf(q.pnl.to_numpy()):>8.2f}")
