"""V52 -- the Turtle script, reduced to ONE entry and ONE exit, with the four requested filters and
with ITS OWN TWO GATES SWEPT IN BOTH DIRECTIONS.

WHY BOTH DIRECTIONS. The pasted script gates on `ADX < 22` and on `distance above EMA100 < 3.964`
-- two CEILINGS. `STUDY_TURTLE_15M` already found both of them INVERTED on 15m NQ (as floors,
ADX >= 20 and EMA distance >= 3.0 ATR, PF went 0.94 -> 1.58 research and 1.56 holdout), and V51
has just found the same inversion again on the MA 200 across three blocks at p 0.001. So the
ceiling and the floor are both put on the grid and the data decides, on this script's own geometry.

WHAT IS REMOVED AND WHY IT IS SAID OUT LOUD:
  * SYSTEM 2 (the 55-bar entry with its 20-bar exit) is gone, as asked. The two channel lengths
    survive as an AXIS -- one entry, either length -- so nothing is silently lost.
  * The SKIP-AFTER-A-WINNER rule goes with System 2: it exists to decide which System 1 breakouts
    to take when System 2 is there to catch the ones skipped. With one system it is a pure
    signal-remover and the script it came from computed it from a mid-bar `close`.
  * THE PYRAMID LADDER IS NOT SWEPT AND IS SET TO ONE UNIT. A trade's outcome under a ladder
    depends on the ladder, so it cannot live in a cached exit tensor -- and the branch has measured
    the answer twice: same rules on US30 15m, three units run a max drawdown of 4,428 all-hours
    against 1,488-1,573 for one unit at the SAME profit factor.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v51")
import v51feat as V51       # noqa: E402

COSTS = V51.COSTS
ENT_N = (20, 55)                 # the Turtle's own two, now an axis rather than two systems
EXIT_N = (10, 20)
STOP_N = (1.5, 2.0, 2.5, 3.0)    # 2.0 is the Turtle's N; the rest bracket it
MAX_HOLD = V51.MAX_HOLD
WINDOWS, SESS, FLAT_CFG = V51.WINDOWS, V51.SESS, V51.FLAT_CFG
MA200_MODES, CROSS_MODES, ABS_MODES, VOL_MULT = (V51.MA200_MODES, V51.CROSS_MODES,
                                                 V51.ABS_MODES, V51.VOL_MULT)
# The script's gate is the FIRST entry of each pair; its mirror is the second.
ADX_MODES = ("off", "ADX < 22  (the script)", "ADX >= 22", "ADX >= 25")
EXT_MODES = ("off", "dist < 3.964 ATR  (the script)", "dist >= 1.5 ATR", "dist >= 3.0 ATR")


def dmi_adx(h, l, c, n=14):
    """Wilder's ADX. `ta.dmi` returns [+DI, -DI, ADX] and destructuring its FIRST element
    substitutes +DI for ADX silently -- a trap this branch has already shipped once."""
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = V51.true_range(h, l, c)
    atr = V51.rma(tr, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi = 100.0 * V51.rma(plus, n) / np.where(atr > 0, atr, np.nan)
        mdi = 100.0 * V51.rma(minus, n) / np.where(atr > 0, atr, np.nan)
        dx = 100.0 * np.abs(pdi - mdi) / np.where((pdi + mdi) > 0, pdi + mdi, np.nan)
    return V51.rma(np.nan_to_num(dx), n)


def build(market, tf):
    P = V51.build(market, tf)
    P["ent_hi"] = {n: pd.Series(P["h"]).rolling(n).max().shift(1).to_numpy() for n in ENT_N}
    P["exit_lo"] = {n: pd.Series(P["l"]).rolling(n).min().shift(1).to_numpy() for n in EXIT_N}
    P["adx"] = dmi_adx(P["h"], P["l"], P["c"])
    ema100 = pd.Series(P["c"]).ewm(span=100, adjust=False).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        P["ext"] = (P["c"] - ema100) / np.where(P["atr"] > 0, P["atr"], np.nan)
    return P


def entry_mask(P, n):
    m = np.asarray(P["h"] > P["ent_hi"][n], bool).copy()
    m[:300] = False
    m[-(MAX_HOLD + 5):] = False
    m &= (np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["ma_dist"])
          & np.isfinite(P["adx"]) & np.isfinite(P["ext"]))
    return m


def filter_masks(P, sig):
    MA, CX, AB, SS = V51.filter_masks(P, sig)
    a = P["adx"][sig]
    AD = np.zeros((len(ADX_MODES), len(sig)), bool)
    AD[0] = True
    AD[1] = a < 22.0
    AD[2] = a >= 22.0
    AD[3] = a >= 25.0
    e = P["ext"][sig]
    EX = np.zeros((len(EXT_MODES), len(sig)), bool)
    EX[0] = True
    EX[1] = e < 3.964
    EX[2] = e >= 1.5
    EX[3] = e >= 3.0
    return MA, CX, AB, SS, AD, EX
