"""The V16 Pine's order model in Python, diffed against the engine.

A Pine port cannot be asserted by reading it. This one has three places to go wrong and all three
have gone wrong on this branch before:

  * THE EXIT IS LIVE ON THE ENTRY BAR. The engine starts its walk at the fill bar, so the bracket
    has to ride with the entry. A port that waits for the next bar leaves 4-13% of trades uncovered.
  * THE WORKING STOP IS THE NEARER OF THE ATR STOP AND THE CHANNEL, and Pine expresses that as
    `strategy.exit(stop=, loss=)`, which takes whichever produces the SMALLER LOSS -- exactly
    max(ATR stop, channel) for a long. Writing it as two orders races them.
  * THE CHANNEL IS READ AT THE PLACING BAR WITHOUT `[1]`. The order goes out at this bar's close
    and is live on the next, so `ta.lowest(low, n)` here is the window the engine reads on the bar
    it fires. The `[1]` that looks right beside the ENTRY channel makes every exit a bar stale.

And one rule with no equivalent in the engine's inner loop: a position cannot re-arm on the bar it
closed on. The engine's lock requires the next signal bar to be strictly after the exit bar; Pine
is flat at that bar's close and would take it.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C          # noqa: E402

COLS = ["sig", "ent", "exit", "px0", "exitpx", "R", "reason"]


def run_pine(P, side=1, exit_n=20, stop_mult=2.0, block=None):
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr = P["atr"]
    ent = P["ent_hi"] if side > 0 else P["ent_lo"]
    ex = P["ex_lo"] if side > 0 else P["ex_hi"]
    fee2, f_taker, f_stop = P["fee2"], P["f_taker"], P["f_stop"]
    n = len(c)
    rows = []
    i = 1
    closed_bar = -1
    while i < n - 1:
        ok = (np.isfinite(atr[i]) and atr[i] > 0 and np.isfinite(ent[i])
              and ((h[i] > ent[i]) if side > 0 else (l[i] < ent[i]))
              and (block is None or block[i]) and i > closed_bar)
        if not ok:
            i += 1
            continue
        a = atr[i]                       # sigAtr, frozen for the trade
        eb = i + 1
        px0 = o[eb]
        stop = px0 - side * stop_mult * a
        j = eb
        while j < n:
            ch = ex[j]
            lvl = stop
            if np.isfinite(ch):
                lvl = max(lvl, ch) if side > 0 else min(lvl, ch)
            cap = c[j - 1]               # a sell stop cannot rest above the market
            lvl = min(lvl, cap) if side > 0 else max(lvl, cap)
            if (l[j] <= lvl) if side > 0 else (h[j] >= lvl):
                pnl = side * (lvl - px0) - fee2 - f_taker[eb] - f_stop[j]
                rows.append((i, eb, j, px0, lvl, pnl / (stop_mult * a), "stop"))
                break
            j += 1
        else:
            break
        closed_bar = j
        i = j + 1
    return pd.DataFrame(rows, columns=COLS)


if __name__ == "__main__":
    import v16phase2 as P2
    print("V16: the engine vs the shipped script's order model\n")
    hdr = (f"{'tf / side / block':<26}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'exit bar':>10}"
           f"{'eng R':>9}{'pine R':>9}{'corr':>9}")
    print(hdr); print("-" * len(hdr))
    for tf in (15, 30):
        P, pool, res, lock = P2.ctx(tf, exit_n=20)
        for side in (1, -1):
            for bn, bb in (("research", res), ("locked", lock)):
                O, idx, _s, _k = P2.leg(P, pool, side, bb, None, 0)
                e = pd.DataFrame(dict(sig=O["sig"][idx], exit=O["xb"][idx], R=O["R"][idx]))
                q = run_pine(P, side=side, block=bb)
                j = e.set_index("sig").join(q.set_index("sig"), how="inner",
                                            lsuffix="_e", rsuffix="_q")
                sx = float((j["exit_e"] == j["exit_q"]).mean()) if len(j) else np.nan
                cr = np.corrcoef(j.R_e, j.R_q)[0, 1] if len(j) > 2 else np.nan
                ov = len(set(e.sig) & set(q.sig)) / max(len(set(e.sig)), 1)
                lab = f"{tf}m {'long' if side > 0 else 'short'} {bn}"
                print(f"{lab:<26}{len(e):>7}{len(q):>8}{ov:>10.1%}{sx:>10.1%}"
                      f"{e.R.sum():>+9.1f}{q.R.sum():>+9.1f}{cr:>9.4f}")
