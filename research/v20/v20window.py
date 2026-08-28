"""What an entry window and a fixed flatten do to V20, measured before the knobs are shipped.

A SMALL FIXED SET, NOT A SWEEP. Seven windows and three flatten times, chosen because they are the
sessions people name -- not swept over every start and end, which on a base with no edge would be a
pure lottery. The set is declared here, the count is stated, and the defaults that ship are OFF.

THE FLATTEN FILLS AT THE NEXT BAR'S OPEN, because `strategy.close_all()` issued at a bar's close
cannot sell that close. The engine was already changed to match the script for V16 (`flat_open`), so
the figures below are the script's, not an idealisation of them.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402
from v20run import control   # noqa: E402

TF = 30
PICK = "C close>value"
WINDOWS = [("all hours", 0, 1440), ("07:00-11:00", 420, 660), ("08:00-12:00", 480, 720),
           ("09:30-11:00", 570, 660), ("09:30-12:00", 570, 720), ("09:30-16:00", 570, 960),
           ("13:00-16:00", 780, 960)]


def run_win(P, block, lo, hi, flat_mod=0, reading=PICK, side=1):
    sig_all = C.signals(P, side)
    mod = P["mod"]
    m = block[sig_all] & L.confirm(P, reading, side)[sig_all]
    m &= ((mod[sig_all] >= lo) & (mod[sig_all] < hi)) if lo <= hi else \
         ((mod[sig_all] >= lo) | (mod[sig_all] < hi))
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=L.SPEC["stop"], tp_r=L.SPEC["tp_r"], flat_mod=flat_mod)
    return O, C.take(O, np.ones(len(sig), bool))


if __name__ == "__main__":
    print("=" * 116)
    print(f"THE ENTRY WINDOW ON V20 -- Donchian 30/20, 2.0N, 2R, linreg 50 ({PICK}), {TF}m, long")
    print("=" * 116)
    print("   Seven windows, fixed in advance. Entries are restricted; an open trade still exits on")
    print("   its own stop, channel or target however long that takes.\n")
    CT = {k: L.ctx(k, TF) for k in L.MARKETS}
    print(f"   {'window':<14}" + "".join(f"{k:>11}" for k in L.MARKETS)
          + f"{'pooled EV':>12}{'pooled PF':>11}{'n':>8}")
    best = {}
    for lab, lo, hi in WINDOWS:
        cells, allr = [], []
        for k in L.MARKETS:
            P = CT[k]
            res, lock = L.blocks(P)
            O, i = run_win(P, lock, lo, hi)
            m = L.metrics(P, O, i, lock)
            cells.append(f"{m['ev']:+.4f}" if m["n"] >= 15 else "  thin")
            if m["n"] >= 15:
                allr.append(O["R"][i])
        pooled = np.concatenate(allr) if allr else np.array([0.0])
        w, losses = pooled[pooled > 0], pooled[pooled < 0]
        pf = w.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.nan
        best[lab] = pooled.mean()
        print(f"   {lab:<14}" + "".join(f"{c:>11}" for c in cells)
              + f"{pooled.mean():>+12.4f}{pf:>11.3f}{len(pooled):>8}")
    print("\n   LOCKED block. Pooled across five markets in R, so points are never added across")
    print("   instruments. `thin` means fewer than 15 trades survived the window.")

    print("\n" + "=" * 116)
    print("THE FLATTEN -- forcing the trade out, filled at the NEXT OPEN as a script must")
    print("=" * 116)
    print(f"   {'window':<14}{'flatten':>10}" + "".join(f"{k:>11}" for k in L.MARKETS)
          + f"{'pooled EV':>12}")
    for lab, lo, hi in [("all hours", 0, 1440), ("09:30-16:00", 570, 960)]:
        for fm, ftag in ((0, "none"), (960, "16:00"), (1140, "19:00")):
            cells, allr = [], []
            for k in L.MARKETS:
                P = CT[k]
                res, lock = L.blocks(P)
                O, i = run_win(P, lock, lo, hi, flat_mod=fm)
                m = L.metrics(P, O, i, lock)
                cells.append(f"{m['ev']:+.4f}" if m["n"] >= 15 else "  thin")
                if m["n"] >= 15:
                    allr.append(O["R"][i])
            pooled = np.concatenate(allr) if allr else np.array([0.0])
            print(f"   {lab:<14}{ftag:>10}" + "".join(f"{c:>11}" for c in cells)
                  + f"{pooled.mean():>+12.4f}")
        print()
    print("   Seven windows and three flatten times were tested. At that multiplicity nothing here")
    print("   would clear a correction even if it looked good, which is why both ship OFF.")
