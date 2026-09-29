"""The adaptive exit policy: a per-trade stop and trail, sized from two causal readings.

Both scalings come from a MEASURED mechanism rather than a sweep, and each is verified in P4:

  VOLATILITY.  ATR(14) is backward-looking and volatility mean-reverts, so when vol sits LOW in
  its own distribution the ATR has already contracted and a fixed multiple of it is too SMALL.
  Measured on gold: heat in ATR units is 1.8x-2.2x larger in the bottom volatility quartile than
  the top, monotone across all four, on BOTH feeds and BOTH blocks. Shipped on NQ as V22; this is
  its first cross-market replication.

  THE CLOCK.  With a hard 11:00 flatten the trade's remaining life is known at entry, and heat
  grows with the time available to make it. `sess.mins_left` is the strongest single predictor of
  both |MAE| (IC +0.375) and give-back (+0.424) in the whole pool. A 07:15 entry and a 10:30 entry
  are not the same trade and must not carry the same stop. This term exists only BECAUSE of the
  flatten -- in an open-ended system there is no known remaining life to scale by.

The two are combined multiplicatively on a base multiple, and both are clipped so neither can
drive the stop to a level where the R denominator collapses (`STUDY_SWEEP_110K`'s channel-stop
trap, reached from the sizing side).
"""
import numpy as np
from numba import njit


def stop_multiple(base, vol_pct, mins_left, win_len, vol_lo=0.5, vol_wide=1.4, vol_tight=0.8,
                  clock_pow=0.5, clip=(0.5, 2.5)):
    """Per-trade stop in ATR. Returns an array the same length as the inputs.

    vol term:   a two-state switch, the form V22 shipped -- WIDE below the volatility median,
                TIGHT above it. A switch rather than a continuous scaling because the measured
                relation is monotone but the threshold is a plateau, and a switch cannot be
                accused of fitting a curve.
    clock term: (mins_left / win_len) ** clock_pow. At clock_pow = 0.5 this is the square-root-of-
                time scaling a random walk implies, which is the null hypothesis for how far price
                travels in the time remaining -- so it is a PREDICTION, not a fitted exponent.
    """
    v = np.where(np.isfinite(vol_pct), vol_pct, 0.5)
    vt = np.where(v <= vol_lo, vol_wide, vol_tight)
    ct = np.clip(mins_left / max(win_len, 1e-9), 0.02, 1.0) ** clock_pow
    m = base * vt * ct
    return np.clip(m, base * clip[0], base * clip[1])


@njit(cache=True)
def walk_adaptive(o, h, l, c, atr, sig_idx, side, last_win, cost_rt, slip,
                  stop_mult, trail_arm, trail_dist, be_at, be_off, tighten_at,
                  out_R, out_why, out_hold, out_mfe, out_mae):
    """Same order model as `xpath.walk_policy`, with the stop distance supplied PER TRADE.

    `stop_mult[k]` is in ATR at the signal bar, so the sizing decision is made with information
    available when the order is written -- not at the fill, which is a bar later and is the leak
    `STUDY_AUCTION` records (`ent_bar` is the FILL bar, not the signal bar)."""
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
        sm = stop_mult[k]
        stop = ent - side * sm * a0 if sm > 0 else np.nan
        mfe = 0.0; mae = 0.0; armed = False
        span = 0; e = j
        while e < n and not last_win[e]:
            span += 1; e += 1
        span += 1
        e = j; R = np.nan; why = 0
        while e < n:
            elapsed = (e - j + 1) / span if span > 0 else 1.0
            td = trail_dist * (0.5 if (tighten_at > 0.0 and elapsed >= tighten_at) else 1.0)
            hit = (l[e] <= stop) if side > 0 else (h[e] >= stop)
            if np.isfinite(stop) and hit:
                R = (side * (stop - ent) - cost_rt - slip) / a0
                why = 1
                break
            adv = (side * (h[e] - ent)) if side > 0 else (side * (l[e] - ent))
            adverse = (side * (l[e] - ent)) if side > 0 else (side * (h[e] - ent))
            if adv > mfe:
                mfe = adv
            if adverse < mae:
                mae = adverse
            if be_at > 0.0 and mfe >= be_at * a0:
                lvl = ent + side * be_off * a0
                if not np.isfinite(stop) or side * (lvl - stop) > 0:
                    stop = lvl
            if trail_arm > 0.0 and mfe >= trail_arm * a0:
                armed = True
            if armed and td > 0.0:
                lvl = ent + side * (mfe - td * a0)
                if not np.isfinite(stop) or side * (lvl - stop) > 0:
                    stop = lvl
            if last_win[e]:
                break
            e += 1
        if why == 0:
            ex = e + 1
            if ex >= n:
                out_hold[k] = -1
                continue
            R = (side * ((o[ex] - side * slip) - ent) - cost_rt) / a0
            why = 3
        out_R[k] = R
        out_why[k] = why
        out_hold[k] = e - j + 1
        out_mfe[k] = mfe / a0
        out_mae[k] = mae / a0
    return 0
