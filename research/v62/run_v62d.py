"""V62 stage D -- the cells the drop-one and the neighbourhood point at.

EVERY NUMBER IN THIS FILE IS POST-HOC. The locked block was read in stage B and the cells below
were chosen after seeing it, so the p-values are descriptive and the multiplicity is unbounded.
It is run because the drop-one said the two confirmations subtract and the neighbourhood said the
3 ATR target is the wrong rung, and the obvious combination of those two facts has to be priced
rather than assumed.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_v62c import BEST, SHIP, score, line  # noqa: E402

CELLS = {
    "best cell as found":                       dict(BEST),
    "  ... with NO target":                     dict(BEST, tp=0.0),
    "  ... no target, drop both confirmations": dict(BEST, tp=0.0, mfi="off", mfi_n=0, ema="off",
                                                     ema_f=0, ema_s=0),
    "  ... and exit channel 20":                dict(BEST, tp=0.0, exN=20, mfi="off", mfi_n=0,
                                                     ema="off", ema_f=0, ema_s=0),
    "  ... and a fixed 2.5N stop":              dict(BEST, tp=0.0, exN=20, stop=2.5, adapt=0,
                                                     mfi="off", mfi_n=0, ema="off", ema_f=0,
                                                     ema_s=0),
    "V61 incumbent":                            dict(SHIP),
}


def main():
    print(__doc__)
    print("=" * 118)
    for lab, cell in CELLS.items():
        print(line(lab, score(cell)))
        print("      " + ", ".join(f"{k}={cell[k]}" for k in
                                   ("tf", "ent", "exN", "stop", "tp", "adapt", "cvd", "mfi",
                                    "ema")))


if __name__ == "__main__":
    main()
