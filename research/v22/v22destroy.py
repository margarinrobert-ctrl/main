"""Try to destroy the vol-scaled stop.

R = pnl / (stop_mult * ATR). Widening the stop ENLARGES the denominator, so every trade in the
widened bucket has its R pulled toward zero -- and the widened bucket is the LOSING one. A policy
that only shrinks losses arithmetically is not an improvement, it is a rescaling. Three attacks:

  1. POINTS. Score the same policy in points per trade, where no denominator moves. If the gain is
     purely the rescaling, points are flat or worse.
  2. THE LOW BUCKET ALONE, at 2.0N and 2.5N, in both units, with the exit-reason split. A real
     widening converts stop-outs into channel exits; a rescaling leaves the exit mix unchanged.
  3. THE THRESHOLD. 0.5 was declared, not searched. Sweep it 0.3 to 0.7 and require the response to
     be smooth -- a spike at 0.5 is an artefact of the one number that was chosen.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v22")
import v16core as C           # noqa: E402
import v22vol as V            # noqa: E402
from v22stop import STATE, blocks, merged, hdr  # noqa: E402


if __name__ == "__main__":
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        sig = C.signals(P, 1)
        s = V.build(P["o"], P["h"], P["l"], P["c"])[STATE][sig]
        res, lock = blocks(P["sess"])
        res, lock = res[sig], lock[sig]
        good = np.isfinite(s)

        hdr(f"NQ {tf}m  ATTACK 1 -- THE SAME POLICIES IN POINTS PER TRADE (no moving denominator)")
        print(f"   {'policy':<32}{'research pts':>15}{'locked pts':>13}{'|':>4}"
              f"{'research R':>13}{'locked R':>11}")
        for lab, a, b in (("flat 2.0N", 2.0, 2.0), ("wide LOW 2.5/1.5", 2.5, 1.5),
                          ("wide LOW 2.5/2.0", 2.5, 2.0), ("INVERSE  1.5/2.5", 1.5, 2.5)):
            O = merged(P, sig, a, b, np.where(good, s <= 0.5, False))
            # points = R * stop distance, recovered per trade
            stopmult = np.where(np.where(good, s <= 0.5, False), a, b)
            pts = O["R"] * stopmult * P["atr"][sig]
            cells = []
            for blk in (res, lock):
                idx = C.take(O, blk & good & (O["xb"] >= 0))
                cells += [pts[idx].mean(), O["R"][idx].mean()]
            print(f"   {lab:<32}{cells[0]:>+15.3f}{cells[2]:>+13.3f}{'|':>4}"
                  f"{cells[1]:>+13.4f}{cells[3]:>+11.4f}")

        hdr(f"NQ {tf}m  ATTACK 2 -- THE LOW-VOL BUCKET ALONE. Does widening change the EXIT MIX?")
        low = np.where(good, s <= 0.5, False)
        print(f"   {'stop':<10}{'block':<10}{'n':>6}{'pts/trade':>12}{'R/trade':>10}"
              f"{'stopped':>10}{'channel':>10}{'med hold':>10}")
        for sm in (2.0, 2.5, 3.0):
            O = C.outcomes(P, 1, sig, stop_mult=sm, tp_r=0.0)
            for blk, tag in ((res, "research"), (lock, "locked")):
                idx = C.take(O, low & blk & (O["xb"] >= 0))
                pts = O["R"][idx] * sm * P["atr"][sig][idx]
                hold = O["xb"][idx] - sig[idx]
                print(f"   {sm:<10.1f}{tag:<10}{len(idx):>6}{pts.mean():>+12.3f}"
                      f"{O['R'][idx].mean():>+10.4f}"
                      f"{(O['why'][idx]==C.STOP).mean():>10.1%}"
                      f"{(O['why'][idx]==C.CHAN).mean():>10.1%}{np.median(hold):>10.0f}")

        hdr(f"NQ {tf}m  ATTACK 3 -- THE 0.5 THRESHOLD WAS DECLARED, NOT FOUND. Is it a spike?")
        print(f"   {'threshold':<12}{'research n':>12}{'research R':>13}{'locked n':>11}"
              f"{'locked R':>11}{'locked PF':>12}")
        for thr in (0.3, 0.4, 0.5, 0.6, 0.7):
            O = merged(P, sig, 2.5, 1.5, np.where(good, s <= thr, False))
            out = []
            for blk in (res, lock):
                idx = C.take(O, blk & good & (O["xb"] >= 0))
                r = O["R"][idx]
                out.append((len(idx), r.mean(),
                            r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan))
            print(f"   {thr:<12.1f}{out[0][0]:>12}{out[0][1]:>+13.4f}{out[1][0]:>11}"
                  f"{out[1][1]:>+11.4f}{out[1][2]:>12.3f}")
