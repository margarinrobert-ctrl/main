"""The exit engine: stop, target, breakeven, trail, and a hard flatten at the window close.

Conventions this branch enforces, each of which has cost it money at least once:
  * the fill is the NEXT bar's open, never the signal bar's close;
  * the stop is anchored to the SIGNAL bar so a script can place it with the entry, which is what
    lets the fill bar be protected -- an unprotected fill bar is 4.4-13.0% of trades;
  * within one bar the STOP is taken before the target, the pessimistic reading, and the
    AMBIGUOUS SHARE is reported because below ~0.5 ATR the tie-break sets the answer;
  * the flatten fills at the NEXT bar's open -- `strategy.close_all()` cannot sell the close of
    the bar that triggers it;
  * ONE position at a time. Without the lock an every-bar signal is a portfolio of overlapping
    positions and every per-trade statistic is about the wrong thing.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def walk(o, h, l, c, atr, sig, side_arr, last_win, rt_pts, slip,
         stop_n, tgt_n, be_at, be_off, tr_arm, tr_dist,
         out_i, out_x, out_R, out_pts, out_why, out_mae, out_mfe, out_amb):
    n = len(c)
    k = 0
    i = 0
    lock = -1
    while i < n:
        if sig[i] and i > lock and atr[i] > 0 and np.isfinite(atr[i]):
            side = side_arr[i]
            j = i + 1
            if j >= n:
                break
            a0 = atr[i]
            ent = o[j] + side * slip
            risk = stop_n * a0
            stop = ent - side * risk
            tgt = ent + side * tgt_n * risk if tgt_n > 0 else np.nan
            mfe = 0.0
            mae = 0.0
            amb = 0
            e = j
            R = np.nan
            why = 0
            px = np.nan
            while e < n:
                hit_s = (l[e] <= stop) if side > 0 else (h[e] >= stop)
                hit_t = False
                if np.isfinite(tgt):
                    hit_t = (h[e] >= tgt) if side > 0 else (l[e] <= tgt)
                if hit_s and hit_t:
                    amb += 1
                if hit_s:
                    px = stop - side * slip
                    why = 1
                    break
                if hit_t:
                    px = tgt - side * slip
                    why = 2
                    break
                adv = side * (h[e] - ent) if side > 0 else side * (l[e] - ent)
                adverse = side * (l[e] - ent) if side > 0 else side * (h[e] - ent)
                if adv > mfe:
                    mfe = adv
                if adverse < mae:
                    mae = adverse
                if be_at > 0.0 and mfe >= be_at * risk:
                    lvl = ent + side * be_off * risk
                    if side * (lvl - stop) > 0:
                        stop = lvl
                if tr_arm > 0.0 and mfe >= tr_arm * risk:
                    lvl = ent + side * (mfe - tr_dist * risk)
                    if side * (lvl - stop) > 0:
                        stop = lvl
                if last_win[e]:
                    break
                e += 1
            if why == 0:
                ex = e + 1
                if ex >= n:
                    break
                px = o[ex] - side * slip
                why = 3
            pts = side * (px - ent) - rt_pts
            out_i[k] = i
            out_x[k] = e
            out_R[k] = pts / risk
            out_pts[k] = pts
            out_why[k] = why
            out_mae[k] = mae / a0
            out_mfe[k] = mfe / a0
            out_amb[k] = amb
            k += 1
            lock = e
            i = e + 1
        else:
            i += 1
    return k
