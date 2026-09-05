"""Engineered features for a breakout, in six families -- none of them a momentum oscillator.

V16 tested 2,167 momentum conditions on a Donchian breakout and found nothing, for a reason that
generalises: a breakout IS a momentum event, so 95% of breakout bars already pass an RSI filter and
the filter can only discard trades. Anything built on top of a breakout therefore has to describe
something the breakout does NOT already say. That is the design constraint for every feature here.

  A  BREAKOUT ANATOMY      how this particular break happened -- penetration depth, where the bar
                           closed inside its own range, its size, its volume, its gap. The trigger
                           says a break occurred; none of this says how convincing it was.
  B  CHANNEL GEOMETRY      the shape of the range being broken -- its width against ATR, that
                           width's own percentile, how long the channel has been stale. A break out
                           of a coiled range and a break out of an already-wide one are different
                           events wearing the same trigger.
  C  HIGHER-TIMEFRAME      the causal daily trend and position in the prior day's range. Strictly
                           keyed on the daily bar CLOSED before the intraday bar -- research/
                           daily_trend.py does the mapping so an intraday bar never sees its own day.
  D  VOLATILITY REGIME     is volatility expanding or contracting, and is it steady. A stop sized
                           in ATR is a bet on ATR's own persistence, which is measurable.
  E  PATH STRUCTURE        efficiency, up-bar fraction, run length, semivariance asymmetry -- how
                           the last twenty bars GOT here, which a channel break does not encode.
  F  SELF-STATE            the rule's own recent record. Sequence-dependent, so it cannot live in
                           this array pool; v17run.py evaluates it inside the position lock.

EVERY FEATURE IS TESTED IN BOTH DIRECTIONS. On this branch two shipped filters turned out to point
the wrong way at 15 minutes (ADX and EMA distance, both ceilings that should have been floors), and
the only reason that was found is that the reverse was tested. Both directions are counted in the
multiplicity rather than quietly chosen.

EVERYTHING IS READ AT THE SIGNAL BAR. Reading any of it at the fill bar is the leakage that once
produced p 0.0005 across nine of nine strategies.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I       # noqa: E402


def _safe(x, lo=1e-12):
    return np.where(np.abs(x) < lo, np.nan, x)


def _pct_rank(x, n):
    """Rolling percentile of the current value within the last n, in [0,1]. Causal by construction."""
    s = pd.Series(x)
    return s.rolling(n).apply(lambda w: float((w[:-1] <= w[-1]).mean()), raw=True).to_numpy()


def _bars_since_new_high(h, n):
    """Bars since the n-bar high was last set -- how stale the level being broken is."""
    hh = pd.Series(h).rolling(n).max().to_numpy()
    out = np.full(len(h), np.nan)
    last = -1
    for i in range(len(h)):
        if np.isfinite(hh[i]) and h[i] >= hh[i]:
            last = i
        out[i] = (i - last) if last >= 0 else np.nan
    return out


def _max_run_up(c, n):
    up = np.r_[False, np.diff(c) > 0].astype(float)
    s = pd.Series(up)
    grp = s.rolling(n)
    return grp.apply(lambda w: float(np.max(np.diff(np.flatnonzero(
        np.r_[True, w == 0, True])) - 1)) if (w == 0).any() else float(len(w)), raw=True).to_numpy()


def build(P, entry_n=55, daily=None):
    h, l, c, o, v = P["h"], P["l"], P["c"], P["o"], P["b"]["v"]
    atr = P["atr"]
    ent_hi, ent_lo = P["ent_hi"], I.shift(I.rmin(l, entry_n), 1)
    rng = h - l
    out = {}
    G = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)

    # ---- A. breakout anatomy ------------------------------------------------------------
    out["A_pen_high"] = ((h - ent_hi) / _safe(atr), 0.0, (0.0, 0.1, 0.25, 0.5, 0.75, 1.0))
    out["A_pen_close"] = ((c - ent_hi) / _safe(atr), 0.0, (-0.25, 0.0, 0.1, 0.25, 0.5, 0.75))
    out["A_close_pos"] = ((c - l) / _safe(rng), 0.5, (-0.3, -0.15, 0.0, 0.15, 0.3, 0.45))
    out["A_bar_range"] = (rng / _safe(atr), 1.0, (-0.5, -0.25, 0.0, 0.25, 0.5, 1.0))
    out["A_body"] = (np.abs(c - o) / _safe(rng), 0.5, (-0.35, -0.2, 0.0, 0.2, 0.35, 0.45))
    out["A_gap"] = ((o - I.shift(c, 1)) / _safe(atr), 0.0, (-0.25, -0.1, 0.0, 0.1, 0.25, 0.5))
    vmed = pd.Series(v).rolling(50).median().to_numpy()
    out["A_rvol"] = (v / _safe(vmed), 1.0, (-0.5, -0.25, 0.0, 0.25, 0.5, 1.0))

    # ---- B. channel geometry ------------------------------------------------------------
    width = (ent_hi - ent_lo) / _safe(atr)
    out["B_width"] = (width, 6.0, (-3.0, -1.5, 0.0, 1.5, 3.0, 5.0))
    out["B_width_pct"] = (_pct_rank(width, 200), 0.5, (-0.35, -0.2, 0.0, 0.2, 0.35, 0.45))
    out["B_stale"] = (_bars_since_new_high(h, entry_n), float(entry_n),
                      (-50.0, -25.0, -10.0, 0.0, 10.0, 25.0))
    out["B_pos_in_ch"] = ((I.shift(c, 1) - ent_lo) / _safe(ent_hi - ent_lo), 0.5,
                          (-0.3, -0.15, 0.0, 0.15, 0.3, 0.45))
    out["B_top_slope"] = (I.lin_slope(ent_hi, 20) / _safe(atr), 0.0,
                          (-0.05, -0.02, 0.0, 0.02, 0.05, 0.1))

    # ---- C. higher-timeframe context ----------------------------------------------------
    if daily is not None:
        out["C_D_dist_ema200"] = (daily["D dist EMA200 / ATR"], 0.0, (-4.0, -1.0, 0.0, 2.0, 5.0, 10.0))
        out["C_D_adx"] = (daily["D ADX"], 20.0, (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0))
        out["C_D_ema_gap"] = (daily["D EMA20-EMA50 / close"] * 100.0, 0.0,
                              (-1.0, -0.5, 0.0, 0.5, 1.0, 2.0))
        for k, lab in (("D close>EMA200", "C_D_above200"), ("D EMA20>EMA50", "C_D_ema20_50"),
                       ("D uptrend + ADX>20", "C_D_uptrend_adx"), ("D +DI>-DI", "C_D_di")):
            out[lab] = (np.asarray(daily[k], float), 0.5, (0.0,))
    pdc = P.get("pdc")
    if pdc is not None:
        out["C_dist_pdc"] = ((c - pdc) / _safe(atr), 0.0, (-2.0, -0.5, 0.0, 0.5, 2.0, 4.0))
        out["C_pos_pdr"] = ((c - P["pdl"]) / _safe(P["pdh"] - P["pdl"]), 0.5,
                            (-0.4, -0.2, 0.0, 0.25, 0.5, 1.0))
        out["C_dist_pdh"] = ((c - P["pdh"]) / _safe(atr), 0.0, (-2.0, -0.5, 0.0, 0.5, 1.5, 3.0))

    # ---- D. volatility regime -----------------------------------------------------------
    atr_sma = pd.Series(atr).rolling(100).mean().to_numpy()
    out["D_atr_ratio"] = (atr / _safe(atr_sma), 1.0, (-0.4, -0.2, 0.0, 0.2, 0.4, 0.8))
    out["D_atr_pct"] = (_pct_rank(atr, 200), 0.5, (-0.35, -0.2, 0.0, 0.2, 0.35, 0.45))
    out["D_vol_of_vol"] = (pd.Series(atr).rolling(20).std(ddof=0).to_numpy() /
                           _safe(pd.Series(atr).rolling(20).mean().to_numpy()), 0.15,
                           (-0.1, -0.05, 0.0, 0.05, 0.1, 0.2))
    lr = np.r_[np.nan, np.diff(np.log(np.maximum(c, 1e-12)))]
    sd_s = pd.Series(lr).rolling(10).std(ddof=0).to_numpy()
    sd_l = pd.Series(lr).rolling(60).std(ddof=0).to_numpy()
    out["D_vol_ratio"] = (sd_s / _safe(sd_l), 1.0, (-0.4, -0.2, 0.0, 0.2, 0.4, 0.8))
    park = np.sqrt(pd.Series(np.log(np.maximum(h, 1e-12) / np.maximum(l, 1e-12)) ** 2)
                   .rolling(20).mean().to_numpy() / (4 * np.log(2)))
    out["D_park_cc"] = (park / _safe(pd.Series(lr).rolling(20).std(ddof=0).to_numpy()), 1.0,
                        (-0.4, -0.2, 0.0, 0.2, 0.4, 0.8))

    # ---- E. path structure --------------------------------------------------------------
    net = np.abs(c - I.shift(c, 20))
    tot = pd.Series(np.abs(np.r_[0, np.diff(c)])).rolling(20).sum().to_numpy()
    out["E_eff"] = (net / _safe(tot), 0.3, (-0.2, -0.1, 0.0, 0.1, 0.2, 0.35))
    out["E_up_frac"] = (pd.Series((np.r_[0, np.diff(c)] > 0).astype(float)).rolling(20)
                        .mean().to_numpy(), 0.5, (-0.15, -0.08, 0.0, 0.08, 0.15, 0.2))
    dn = np.where(lr < 0, lr, 0.0)
    up = np.where(lr > 0, lr, 0.0)
    sdn = pd.Series(dn).rolling(20).std(ddof=0).to_numpy()
    sup = pd.Series(up).rolling(20).std(ddof=0).to_numpy()
    out["E_semivar"] = (sdn / _safe(sup), 1.0, (-0.4, -0.2, 0.0, 0.2, 0.4, 0.8))
    out["E_dd20"] = ((pd.Series(c).rolling(20).max().to_numpy() - c) / _safe(atr), 0.0,
                     (0.0, 0.5, 1.0, 2.0, 3.0, 5.0))
    return out


def conditions(pool):
    """One row per (feature, level, DIRECTION). The offset is a delta from the feature's own
    centre, so the LEVEL tested is `centre + offset` and the label carries that level, not the
    delta. Both directions are tested and both are counted in the multiplicity."""
    rows = []
    for name, (x, center, offs) in pool.items():
        for o in offs:
            lvl = center + o
            rows.append((f"{name} >= {lvl:g}", x, lvl, +1))
            if len(offs) > 1:
                rows.append((f"{name} <= {lvl:g}", x, lvl, -1))
    return rows


def mask_for(score, level, direction):
    """NaN reads as FALSE in both directions -- a missing feature must never pass a filter."""
    v = np.asarray(score, float)
    ok = np.isfinite(v)
    return ok & ((v >= level) if direction > 0 else (v <= level))


if __name__ == "__main__":
    sys.path.insert(0, "research/v16")
    import v16core as C
    P = C.prep(15, entry_n=55, exit_n=20, atr_len=20)
    pool = build(P, entry_n=55)
    rows = conditions(pool)
    fam = {}
    for k in pool:
        fam.setdefault(k.split("_")[0], []).append(k)
    print(f"{len(pool)} features, {len(rows)} conditions (both directions counted)\n")
    for f in sorted(fam):
        cov = {k: float(np.isfinite(pool[k][0]).mean()) for k in fam[f]}
        print(f"  {f}  {len(fam[f]):>2} features   min finite {min(cov.values()):.3f} "
              f"({min(cov, key=cov.get)})")
