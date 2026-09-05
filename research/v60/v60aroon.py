"""Why the Aroon oscillator cannot filter a Donchian breakout: it is implied by one.

THE THEOREM. A Donchian(E) breakout bar satisfies `close > max(high, E)[1]`, and since
`high >= close`, that bar's high exceeds every one of the previous E highs. Aroon Up over a window
N counts bars since the N-bar high, so whenever N <= E the breakout bar IS the N-bar high and

        Aroon Up = 100,  Aroon Down <= 100,  Aroon Oscillator = 100 - Down >= 0

by construction, on EVERY breakout bar, with no exceptions and no market dependence. The filter
`osc >= 0` and the filter `up >= 70` therefore remove exactly zero signals.

Where N > E the identity lapses, because the breakout only cleared E bars and the window looks
back further. That is the only region where an Aroon condition can bind at all, and this file
measures how much it binds there.

`STUDY_V16_MOMENTUM.md` reached the same conclusion empirically for 58 momentum scores -- 94.7% of
breakout bars already passed an RSI(14) >= 55 filter. Aroon is the degenerate case: 100%.
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))

import v60core as V             # noqa: E402
from run_v60 import MARKETS      # noqa: E402


def main():
    print("=" * 96)
    print("THE AROON-DONCHIAN IDENTITY, checked bar by bar on every market and every pair")
    print("=" * 96)
    print(f"{'market':<8}{'donchian':>9}{'aroon N':>9}{'breakout bars':>15}"
          f"{'Aroon Up == 100':>18}{'osc >= 0':>11}{'osc >= 50':>11}{'up >= 70':>10}")
    for mk in MARKETS:
        P = V.prep(60, mk)
        for e in V.DON_E:
            brk = P["brk"][e] & np.isfinite(P["atr"])
            for n in V.AROON_N:
                u, d = V.aroon(P["h"], P["l"], n)
                ok = brk & np.isfinite(u)
                if ok.sum() == 0:
                    continue
                osc = u - d
                print(f"{mk:<8}{e:>9}{n:>9}{int(ok.sum()):>15,}"
                      f"{(u[ok] == 100.0).mean()*100:>17.1f}%"
                      f"{(osc[ok] >= 0).mean()*100:>10.1f}%"
                      f"{(osc[ok] >= 50).mean()*100:>10.1f}%"
                      f"{(u[ok] >= 70).mean()*100:>9.1f}%")
    print("\n  Where aroon N <= donchian E the identity is EXACT: the breakout bar is the N-bar")
    print("  high, so Aroon Up is 100 and the oscillator is non-negative, always. Those filters")
    print("  cannot remove a single signal. Only aroon N > E leaves any room, and only the")
    print("  osc >= 50 rung binds materially even there.")


if __name__ == "__main__":
    main()
