"""The uncensored path of every signal to the 11:00 flatten, and the exit policies tested on it.

WHY UNCENSORED FIRST. A stop CENSORS the adverse excursion: a trade heading for -3.0 ATR that is
stopped at -2.0 records -2.0, so a mean MAE mixes real heat on survivors with the stop distance on
the stopped, weighted by a stop-out rate that varies with everything. `STUDY_V43_MAE_MFE` measured
the damage -- the spread between entries is LARGER uncensored (1.534 ATR) than censored (0.779) --
so the diagnosis is run with no stop at all, and only then are stops applied.

AND IN ATR AT ENTRY, NEVER IN R. R = mult x ATR puts the stop back in the denominator, so ranking
entries by MAE-in-R ranks the stop you happened to choose. Same study: V40 is 8th of 8 on MAE-in-R
and 2nd on MAE-in-ATR.

The exit policies are applied to the SAME path, so every comparison is paired trade for trade and
the difference is the policy rather than a different sample. Intrabar ordering is resolved
pessimistically (stop before target within a bar) and the ambiguous share is reported, because
below about 0.5 ATR the tie-break sets the answer and not the market.
"""
import numpy as np
from numba import njit

FLAT_OPEN = 1          # a flatten fills at the NEXT bar's open; a script cannot sell the close
                       # of the bar that triggers it (STUDY_V63, the `flat_open` engine change)


@njit(cache=True)
def walk_paths(o, h, l, c, atr, sig_idx, side, last_win, cost_rt, slip,
               out_mae, out_mfe, out_t_mae, out_t_mfe, out_end, out_hold,
               out_amb, out_atr0, out_ent, out_maxadv_after_mfe):
    """One pass per signal, NO STOP AND NO TARGET -- the path as the market actually made it.

    Records, in ATR at the entry bar: worst adverse excursion, best favourable excursion, the bar
    each happened on, the terminal (flatten) result, and the WORST GIVE-BACK AFTER THE MFE, which
    is the number the 'secure the winner' question is actually about."""
    n = len(c)
    for k in range(len(sig_idx)):
        i = sig_idx[k]
        j = i + 1                                    # fill at the next bar's open
        if j >= n:
            out_hold[k] = -1
            continue
        a0 = atr[i]
        if not (a0 > 0) or not np.isfinite(a0):
            out_hold[k] = -1
            continue
        ent = o[j] + side * slip
        out_ent[k] = ent
        out_atr0[k] = a0
        mae = 0.0; mfe = 0.0; tmae = 0; tmfe = 0; amb = 0
        after = 0.0                                  # worst pullback from the running MFE
        e = j
        while e < n:
            adv = side * (h[e] - ent) if side > 0 else side * (l[e] - ent)
            adverse = side * (l[e] - ent) if side > 0 else side * (h[e] - ent)
            if adv > mfe:
                mfe = adv; tmfe = e - j; after = 0.0
            else:
                gb = mfe - adv                       # how far below the peak this bar traded
                dd = mfe - (side * (l[e] - ent) if side > 0 else side * (h[e] - ent))
                if dd > after:
                    after = dd
            if adverse < mae:
                mae = adverse; tmae = e - j
            if adv > 0.0 and adverse < 0.0:
                amb += 1
            if last_win[e]:
                break
            e += 1
        ex = e + FLAT_OPEN
        if ex >= n:
            out_hold[k] = -1
            continue
        px = o[ex] - side * slip
        out_mae[k] = mae / a0
        out_mfe[k] = mfe / a0
        out_t_mae[k] = tmae
        out_t_mfe[k] = tmfe
        out_end[k] = (side * (px - ent) - cost_rt) / a0
        out_hold[k] = e - j + 1
        out_amb[k] = amb
        out_maxadv_after_mfe[k] = after / a0
    return 0


@njit(cache=True)
def walk_policy(o, h, l, c, atr, sig_idx, side, last_win, cost_rt, slip,
                stop_atr, tgt_atr, be_at, be_off, trail_arm, trail_atr, tighten_at,
                out_R, out_why, out_hold, out_mfe):
    """The same paths under one exit policy. Every argument is in ATR at the ENTRY bar.

      stop_atr    initial stop distance;  0 = none (a stop that cannot bind)
      tgt_atr     take profit;            0 = none
      be_at       move the stop to breakeven+be_off once this much favourable excursion is seen
      trail_arm   arm a trailing stop once this much favourable excursion is seen; 0 = never
      trail_atr   the trail's distance behind the running high
      tighten_at  fraction of the window elapsed after which the trail halves (0 = off)

    Intrabar the STOP is taken before the target and before the trail, which is the pessimistic
    convention and the one this branch uses everywhere.
    """
    n = len(c)
    for k in range(len(sig_idx)):
        i = sig_idx[k]
        j = i + 1
        if j >= n:
            out_hold[k] = -1
            continue
        a0 = atr[i]
        if not (a0 > 0) or not np.isfinite(a0):
            out_hold[k] = -1
            continue
        ent = o[j] + side * slip
        stop = ent - side * stop_atr * a0 if stop_atr > 0 else np.nan
        tgt = ent + side * tgt_atr * a0 if tgt_atr > 0 else np.nan
        mfe = 0.0; armed = False
        # how many bars the window has left, for the time-based tightening
        span = 0
        e = j
        while e < n and not last_win[e]:
            span += 1; e += 1
        span += 1
        e = j; R = np.nan; why = 0
        while e < n:
            elapsed = (e - j + 1) / span if span > 0 else 1.0
            tr_mult = trail_atr * (0.5 if (tighten_at > 0.0 and elapsed >= tighten_at) else 1.0)
            hit_stop = False; hit_tgt = False
            if np.isfinite(stop):
                hit_stop = (l[e] <= stop) if side > 0 else (h[e] >= stop)
            if np.isfinite(tgt):
                hit_tgt = (h[e] >= tgt) if side > 0 else (l[e] <= tgt)
            if hit_stop:
                R = (side * (stop - ent) - cost_rt) / a0 - slip / a0
                why = 1
                break
            if hit_tgt:
                R = (side * (tgt - ent) - cost_rt) / a0 - slip / a0
                why = 2
                break
            adv = (side * (h[e] - ent)) if side > 0 else (side * (l[e] - ent))
            if adv > mfe:
                mfe = adv
            if be_at > 0.0 and mfe >= be_at * a0:
                lvl = ent + side * be_off * a0
                if not np.isfinite(stop) or side * (lvl - stop) > 0:
                    stop = lvl
            if trail_arm > 0.0 and mfe >= trail_arm * a0:
                armed = True
            if armed and tr_mult > 0.0:
                lvl = ent + side * (mfe - tr_mult * a0)
                if not np.isfinite(stop) or side * (lvl - stop) > 0:
                    stop = lvl
            if last_win[e]:
                break
            e += 1
        if why == 0:
            ex = e + FLAT_OPEN
            if ex >= n:
                out_hold[k] = -1
                continue
            R = (side * ((o[ex] - side * slip) - ent) - cost_rt) / a0
            why = 3
        out_R[k] = R
        out_why[k] = why
        out_hold[k] = e - j + 1
        out_mfe[k] = mfe / a0
    return 0
