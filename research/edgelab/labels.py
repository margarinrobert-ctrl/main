"""Triple-barrier labels, MFE/MAE, and the intrabar-ambiguity accounting (brief 16, 17, 38).

THE AMBIGUITY PROBLEM, which is the single biggest execution risk in this brief. On a 15-minute
bar a long can see both its stop and its target inside the SAME candle, and OHLC alone cannot say
which came first. The brief (section 38) forbids resolving that in the strategy's favour. So:

    * the resolution rule is STOP FIRST, always -- the pessimistic branch;
    * every trade carries an `ambig` flag when the bar that closed it touched both barriers;
    * `summary()` reports the ambiguous share, because a setup whose result depends on a large
      ambiguous fraction is not measurable on this data at all.

At 1:1 with a tight stop this fraction is large, and that is a finding about the data rather than
about any strategy. 1-minute US100 data would shrink it; this file is 15-minute only.

NO LOOK-AHEAD. The signal bar is `i`. Entry is the OPEN of bar `i+1`. Barriers are sized from
information available at the close of `i`. The forward walk starts at `i+1`. Future prices touch
the LABEL only, never a feature.
"""
from __future__ import annotations

import numpy as np
from numba import njit

STOP, TARGET, TIME, FLAT = 1, 2, 3, 4


@njit(cache=True)
def _walk(o, h, l, c, mod, trig, stop_pts, rr, max_hold, flat_mod,
          half_spread, slip_entry, slip_stop, slip_target, commission):
    n = len(c); m = len(trig)
    R = np.zeros(m); why = np.zeros(m, np.int64); ambig = np.zeros(m, np.uint8)
    eb = np.zeros(m, np.int64); xb = np.zeros(m, np.int64)
    mfe = np.zeros(m); mae = np.zeros(m); bars_held = np.zeros(m, np.int64)
    k = 0
    for t in range(m):
        i = trig[t]
        e = i + 1
        if e >= n or stop_pts[t] <= 0.0:
            continue
        entry = o[e]
        sp = stop_pts[t]
        st = entry - sp
        tg = entry + rr * sp
        hi = entry; lo = entry
        j = e; done = 0
        while j < n and (j - e) < max_hold:
            if h[j] > hi:
                hi = h[j]
            if l[j] < lo:
                lo = l[j]
            hit = l[j] <= st
            won = h[j] >= tg
            if hit and won:
                ambig[k] = 1
            if hit:                      # conservative: stop resolves first, always
                px = st if o[j] >= st else o[j]
                gross = px - entry - slip_stop
                why[k] = STOP; xb[k] = j; done = 1
                break
            if won:
                px = tg if o[j] <= tg else o[j]
                gross = px - entry - slip_target
                why[k] = TARGET; xb[k] = j; done = 1
                break
            if flat_mod > 0 and mod[j] >= flat_mod:
                gross = c[j] - entry
                why[k] = FLAT; xb[k] = j; done = 1
                break
            j += 1
        if done == 0:
            if j >= n:
                continue
            j = min(j, n - 1)
            gross = c[j] - entry
            why[k] = TIME; xb[k] = j
        cost = half_spread[e] + half_spread[xb[k]] + slip_entry + commission
        R[k] = (gross - cost) / sp
        mfe[k] = (hi - entry) / sp
        mae[k] = (entry - lo) / sp
        eb[k] = e; bars_held[k] = xb[k] - e
        k += 1
    return R[:k], why[:k], ambig[:k], eb[:k], xb[:k], mfe[:k], mae[:k], bars_held[:k]


def label(d, trig, stop_pts, rr=1.0, max_hold=16, flat_mod=960, costs=None):
    """Triple-barrier outcomes in R, net of costs. `stop_pts` is per-trigger, in index points."""
    from .data import Costs
    costs = costs or Costs()
    trig = np.ascontiguousarray(np.asarray(trig, np.int64))
    sp = np.ascontiguousarray(np.asarray(stop_pts, float))
    hs = costs.spread_at(d["mod"])
    R, why, ambig, eb, xb, mfe, mae, held = _walk(
        d["o"], d["h"], d["l"], d["c"], np.asarray(d["mod"], np.int64), trig, sp,
        float(rr), int(max_hold), int(flat_mod), hs,
        costs.slip_entry, costs.slip_stop, costs.slip_target, costs.commission)
    return dict(R=R, why=why, ambig=ambig, eb=eb, xb=xb, mfe=mfe, mae=mae, held=held)


def summary(res, tag="", block=None):
    R = res["R"] if block is None else res["R"][block]
    if len(R) == 0:
        return None
    why = res["why"] if block is None else res["why"][block]
    am = res["ambig"] if block is None else res["ambig"][block]
    win = float((R > 0).mean())
    wins, losses = R[R > 0], R[R <= 0]
    pf = float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf
    return dict(tag=tag, n=len(R), win=100.0 * win, expR=float(R.mean()), pf=pf,
                ambig=100.0 * float(am.mean()),
                tgt=100.0 * float((why == TARGET).mean()),
                stp=100.0 * float((why == STOP).mean()),
                tim=100.0 * float(((why == TIME) | (why == FLAT)).mean()))


def fmt(s):
    if s is None:
        return "  (no trades)"
    return (f"  n={s['n']:>6}  win {s['win']:>5.1f}%  E[R] {s['expR']:>+6.3f}  PF {s['pf']:>5.2f}"
            f"  ambiguous {s['ambig']:>4.1f}%   exits tgt/stop/time "
            f"{s['tgt']:.0f}/{s['stp']:.0f}/{s['tim']:.0f}")


# --------------------------------------------------------------------------- cached outcomes
def precompute(d, stop_k, rr=1.0, max_hold=16, flat_mod=960, costs=None, lo=420, hi=660):
    """Outcome of a long entered at EVERY eligible bar, for one fixed geometry.

    A trade's result depends only on its signal bar and the geometry -- entries here do not block
    one another -- so the whole search can index into this instead of re-simulating. That is what
    makes a 200-draw matched control affordable as a GATE rather than a final check, which is the
    lesson `docs/ib/STUDY_TUNER.md` records on the NQ side.

    Returns a dict of full-length arrays with NaN / -1 at bars that are not tradable.
    """
    n = len(d["c"])
    mod = d["mod"]; atr = d["atr"]
    ok = (mod >= lo) & (mod < hi) & np.isfinite(atr) & (atr > 0)
    ok[:300] = False
    idx = np.flatnonzero(ok)
    r = label(d, idx, stop_k * atr[idx], rr=rr, max_hold=max_hold, flat_mod=flat_mod, costs=costs)
    R = np.full(n, np.nan); AM = np.zeros(n, np.uint8)
    MFE = np.full(n, np.nan); MAE = np.full(n, np.nan)
    WHY = np.zeros(n, np.int64); HELD = np.full(n, -1, np.int64)
    sig = r["eb"] - 1                       # signal bar = entry bar - 1
    R[sig] = r["R"]; AM[sig] = r["ambig"]; MFE[sig] = r["mfe"]; MAE[sig] = r["mae"]
    WHY[sig] = r["why"]; HELD[sig] = r["held"]
    return dict(R=R, ambig=AM, mfe=MFE, mae=MAE, why=WHY, held=HELD,
                valid=np.isfinite(R), mod=np.asarray(mod, int))
