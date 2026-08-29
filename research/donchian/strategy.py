"""The Donchian breakout strategy family. Baseline first, filters later."""
import numpy as np, pandas as pd
from engine import (donchian, atr, ema, true_range, build_walk, simulate,
                    stats, MAXHOLD)

WIN_START, WIN_END = 420, 660          # 07:00 - 11:00 New York, in minutes


def signals(df, n_entry=20, win=(WIN_START, WIN_END), long_only=False,
            confirm="close", buffer_atr=0.0, atr_n=14):
    """Baseline Donchian breakout triggers on CLOSED bars.

    confirm='close' : bar CLOSES beyond the channel (conservative, no lookahead)
    confirm='high'  : bar TRADES beyond it (a resting stop order would have filled)
    buffer_atr      : require the break to exceed the channel by k * ATR
    """
    hi, lo = donchian(df, n_entry)
    a = atr(df, atr_n)
    c, h, l = df.close.values, df.high.values, df.low.values
    tod = df.tod.values
    px = c if confirm == "close" else h
    pxl = c if confirm == "close" else l
    up = px > (hi + buffer_atr * a)
    dn = pxl < (lo - buffer_atr * a)
    inwin = (tod >= win[0]) & (tod < win[1])
    ok = inwin & ~np.isnan(hi) & ~np.isnan(a) & (a > 0)
    up &= ok; dn &= ok
    if long_only:
        dn[:] = False
    idx = np.where(up | dn)[0]
    side = np.where(up[idx], 1, -1).astype(np.int64)
    return idx, side, a


def run(df, walk, n_entry=20, stop_mult=1.5, targ_mult=2.0, max_hold=16,
        flat_tod=WIN_END, cost_pts=2.0, slip_pts=0.25, win=(WIN_START, WIN_END),
        atr_n=14, confirm="close", buffer_atr=0.0, long_only=False,
        one_per_session=True, idx_side=None):
    """Full baseline: break the channel, enter next open, ATR stop and target."""
    if idx_side is None:
        idx, side, a = signals(df, n_entry, win, long_only, confirm, buffer_atr, atr_n)
    else:
        idx, side = idx_side
        a = atr(df, atr_n)
    if len(idx) == 0:
        return pd.DataFrame(columns=["sig_bar", "side", "net"])
    if one_per_session:
        # first signal of each session only - stops one trending day dominating
        s = df.sess.values[idx]
        keep = np.concatenate([[True], s[1:] != s[:-1]])
        idx, side = idx[keep], side[keep]

    fill = walk["opens"][idx, 0]
    entry = fill + side * slip_pts                       # slippage always against
    av = a[idx]
    stop = entry - side * stop_mult * av
    targ = entry + side * targ_mult * av if targ_mult > 0 else \
        np.where(side > 0, np.inf, -np.inf)
    return simulate(walk, idx, side.astype(np.float64), entry, stop, targ,
                    max_hold=max_hold, flat_tod=flat_tod, cost_pts=cost_pts)
