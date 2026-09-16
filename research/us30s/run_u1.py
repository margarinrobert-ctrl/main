"""U1 -- what a 30-second US30 series actually buys: the intrabar tie-break, answered.

`STUDY_US30_SCALP_0711` could not say which barrier came first on **14.03%** of its 0.5N trades,
and the two conventions read PF 0.604 (stop-first) against 1.056 (target-first) -- a 5.27-point
spread a trade, LARGER than any edge in that study and opposite in sign. Its own conclusion was
that "a sub-1N barrier result on US30 is a statement about the convention, not about the market",
and that the first thing that would move it is finer bars. This is that test, and it is the whole
reason this feed is worth having.

The method is the one `STUDY_VOLBO_BREAKOUT` used to settle the same question on NQ: take the
SAME trades at the SAME geometry on the SAME 15-minute bars, then walk the finer series inside
each ambiguous bar and see which barrier the path reaches first. Nothing is re-optimised and no
new rule is introduced -- the only thing that changes is the resolution the exits are read at.

Three resolutions are reported because the gradient is the evidence: 15 minutes (what the study
had), 1 minute (what it asked for) and 30 seconds (what arrived). If the ambiguous share does not
fall toward zero the feed has not helped; if it does, the convention stops being a free parameter.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import us30s as U

STOPS = [0.5, 0.75, 1.0, 1.5, 3.0]      # in ATR, as the study declared them
RR = 1.0                                 # target = stop, the geometry the 14.03% was measured at
ATR_N = 14
WIN = (420, 660)                          # 07:00-11:00 New York, the study's window


def atr(d, n=ATR_N):
    h, l, c = d.high.to_numpy(), d.low.to_numpy(), d.close.to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


def donchian_signals(d, n=20):
    """The study's trigger: a long break of the 20-bar high, inside the window, one per bar."""
    hi = pd.Series(d.high).rolling(n).max().shift(1).to_numpy()
    ok = (d["mod"].to_numpy() >= WIN[0]) & (d["mod"].to_numpy() < WIN[1]) & np.isfinite(hi)
    return np.flatnonzero(ok & (d.high.to_numpy() > hi))


def first_touch(path_h, path_l, stop, tgt, side=1):
    """Walk a finer path and return 'stop' / 'tgt' / None -- whichever level is reached first.
    Ties WITHIN one fine bar remain ties and are counted, not guessed."""
    for hh, ll in zip(path_h, path_l):
        hit_s = ll <= stop if side > 0 else hh >= stop
        hit_t = hh >= tgt if side > 0 else ll <= tgt
        if hit_s and hit_t:
            return None          # still ambiguous, even here
        if hit_s:
            return "stop"
        if hit_t:
            return "tgt"
    return "open"


def main():
    print("=" * 108)
    print("U1  THE INTRABAR TIE-BREAK ON US30, AT THREE RESOLUTIONS")
    print("=" * 108)

    fine = {k: U.load(k) for k in (0.5, 1)}
    bars = U.load(15)
    bars["atr"] = atr(bars)
    sig = donchian_signals(bars)
    print(f"  15-minute bars {len(bars):,}   Donchian-20 long breaks in 07:00-11:00 NY: {len(sig)}")
    print(f"  finer paths: 30s {len(fine[0.5]):,} bars, 1m {len(fine[1]):,} bars\n")

    idx = {k: v.set_index("ny") for k, v in fine.items()}
    rows = []
    for st in STOPS:
        amb = tot = 0
        agree = {0.5: {"stop": 0, "tgt": 0, "amb": 0}, 1: {"stop": 0, "tgt": 0, "amb": 0}}
        for i in sig:
            a = bars.atr.iloc[i]
            if not np.isfinite(a) or a <= 0 or i + 1 >= len(bars):
                continue
            ent = bars.open.iloc[i + 1]
            stop, tgt = ent - st * a, ent + st * RR * a
            # the FIRST 15-minute bar of the trade decides whether the study could resolve it
            b = bars.iloc[i + 1]
            tot += 1
            if not (b.low <= stop and b.high >= tgt):
                continue
            amb += 1
            t0, t1 = b.ny, b.ny + pd.Timedelta(minutes=15)
            for k in (0.5, 1):
                w = idx[k].loc[(idx[k].index >= t0) & (idx[k].index < t1)]
                r = first_touch(w.high.to_numpy(), w.low.to_numpy(), stop, tgt) if len(w) else None
                agree[k]["amb" if r in (None, "open") else r] += 1
        rows.append(dict(stop=f"{st}N", trades=tot,
                         amb15=f"{amb/max(tot,1):.2%}",
                         n_amb=amb,
                         res_1m=f"{1 - agree[1]['amb']/max(amb,1):.2%}",
                         res_30s=f"{1 - agree[0.5]['amb']/max(amb,1):.2%}",
                         stop_first=agree[0.5]["stop"], tgt_first=agree[0.5]["tgt"],
                         still_amb=agree[0.5]["amb"]))
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    print("\n  `amb15`   = share of trades whose stop and target both sit inside the FIRST 15m bar")
    print("              -- this is the quantity the study could not resolve (it measured 14.03%)")
    print("  `res_30s` = share of those the 30-second path DOES resolve")
    print("  stop_first / tgt_first = how the resolved ones actually went, which is the answer")
    print("              the convention was standing in for")
    tot_amb = t.n_amb.sum()
    sf, tf_, sa = t.stop_first.sum(), t.tgt_first.sum(), t.still_amb.sum()
    if tot_amb:
        print(f"\n  pooled over the five stops: {tot_amb} ambiguous trades, "
              f"{1 - sa/tot_amb:.2%} resolved at 30 seconds")
        print(f"  of the resolved: STOP first {sf} ({sf/max(sf+tf_,1):.2%}), "
              f"TARGET first {tf_} ({tf_/max(sf+tf_,1):.2%})")
        print(f"  the branch's standing convention takes the STOP always, so it is correct on "
              f"{sf/max(sf+tf_,1):.1%} of them")


if __name__ == "__main__":
    main()
