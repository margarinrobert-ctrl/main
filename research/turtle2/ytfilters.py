"""The YouTube variant's two entry filters: a higher-timeframe 50 EMA, and "avoid major S/R".

FROM THE VIDEO, as specified:
  BUY  price ABOVE the 50 EMA on the HIGHER timeframe, and AVOID major resistance.
  HTF  5m / 15m / 1H charts -> 4H.  (4H -> daily and daily -> weekly are also given but the
       charts under test here are 5m, 15m and 1H, so HTF is 4H throughout.)
  major resistance = the DAILY, WEEKLY and MONTHLY high. Note this is NARROWER than the ten
       levels built in `levels.py`: the 1H and 4H extremes are not "major".
  sells are the mirror: price below the HTF 50 EMA, avoid major support (daily/weekly/monthly low).

THE HTF EMA IS WHERE THIS KIND OF STRATEGY LEAKS, and the leak is the single most common defect in
published multi-timeframe scripts. Reading a 4H EMA on a 15-minute chart has two defensible
meanings and one indefensible one:

  CLOSED    (default) the EMA of the last COMPLETED 4H bar. Constant for four hours, never revised,
            and what a non-repainting `request.security(..., lookahead_off)` gives you.
  RUNNING   the EMA updated with the developing 4H bar's close-so-far. Still causal -- it uses only
            bars up to now -- but it CHANGES within the 4H bar, so a rule written against it is a
            different rule.
  the leak  the EMA of the 4H bar that CONTAINS the current 15-minute bar, computed on the whole
            4H series. That reads up to 3h45m of future data and is what a naive resample-and-
            reindex produces. It is not implemented here, and `audit()` is what proves it is not.

`audit()` recomputes the filter on history ENDING at bar i and requires an exact match, the same
truncation test that caught the overnight-aggregate leak in `STUDY_SCALP_TREND.md`.

THE AVOID-RESISTANCE TOLERANCE IS NOT IN THE VIDEO and is therefore a stated choice, not a fitted
one: a long is blocked when major resistance sits within `tol` multiples of the trade's OWN RISK
above the entry. Tying it to the trade's risk rather than to a fixed distance makes it scale-free
across a 1.1 EURUSD and a 66,000 BTC, and means it is not a free parameter in price units. The
default is 1.0R -- "do not buy something that cannot reach its first target without hitting a major
level". Sensitivity across a pre-declared grid is reported as robustness, never used to select.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import levels as L

HTF_FOR = {5: "4H", 15: "4H", 60: "4H", 240: "D", 1440: "W"}
MAJOR = ("D", "W", "M")
DEFAULT_TOL_R = 1.0


def _htf_key(ix, htf):
    return L._period_key(pd.DatetimeIndex(ix), htf)


def htf_ema(idx, close, htf="4H", period=50, mode="closed"):
    """The HTF 50 EMA mapped onto the base series, without reading into the current HTF bar."""
    ix = pd.DatetimeIndex(idx)
    key = _htf_key(ix, htf)
    df = pd.DataFrame({"c": close, "k": key})
    # the HTF bar's close is the LAST base close inside it
    agg = df.groupby("k", sort=True)["c"].last()
    ema = agg.ewm(span=period, adjust=False).mean()
    if mode == "closed":
        # shift by one HTF bar: at any base bar, use the last COMPLETED HTF bar's EMA
        src = ema.shift(1)
        return src.reindex(key).to_numpy()
    if mode == "running":
        # running EMA of the developing bar: prior EMA blended with the close so far
        prev = ema.shift(1).reindex(key).to_numpy()
        a = 2.0 / (period + 1.0)
        run = np.where(np.isfinite(prev), prev + a * (close - prev), np.nan)
        first = ~pd.Series(key).duplicated(keep="first").to_numpy()
        return np.where(first, prev, run)
    raise ValueError(mode)


def major_levels(idx, h, l):
    """Prior daily, weekly and monthly highs and lows -- the video's 'major' set."""
    lv = L.build(idx, h, l, timeframes=MAJOR)
    highs = np.vstack([lv[f"prior_{t}_high"] for t in MAJOR])
    lows = np.vstack([lv[f"prior_{t}_low"] for t in MAJOR])
    return highs, lows


def blocked(entry, risk, side, highs, lows, tol_r=DEFAULT_TOL_R):
    """True where a major level sits within tol_r * risk in the trade's direction of travel."""
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if side == 1:
            above = np.where(highs > entry[None, :], highs, np.nan)
            nearest = np.nanmin(above, axis=0)
            return np.isfinite(nearest) & ((nearest - entry) < tol_r * risk)
        below = np.where(lows < entry[None, :], lows, np.nan)
        nearest = np.nanmax(below, axis=0)
        return np.isfinite(nearest) & ((entry - nearest) < tol_r * risk)


def audit(idx, close, h, l, htf="4H", checks=25, seed=5, verbose=True):
    """Truncation audit on the HTF EMA and the major levels together."""
    rng = np.random.default_rng(seed)
    n = len(close)
    full_e = htf_ema(idx, close, htf)
    fh, fl = major_levels(idx, h, l)
    pts = rng.choice(np.arange(int(0.4 * n), n), size=min(checks, n // 4), replace=False)
    bad = []
    for i in sorted(pts):
        pe = htf_ema(idx[:i + 1], close[:i + 1], htf)
        ph, pl = major_levels(idx[:i + 1], h[:i + 1], l[:i + 1])
        pairs = [("htf_ema", full_e[i], pe[i])]
        for j, t in enumerate(MAJOR):
            pairs.append((f"{t}_high", fh[j, i], ph[j, i]))
            pairs.append((f"{t}_low", fl[j, i], pl[j, i]))
        for name, a, b in pairs:
            if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, equal_nan=True):
                bad.append((int(i), name, float(a), float(b)))
    if verbose:
        tot = len(pts) * (1 + 2 * len(MAJOR))
        if bad:
            print(f"  TRUNCATION AUDIT FAILED on {len(bad)} of {tot} checks")
            for r in bad[:8]:
                print(f"    bar {r[0]}  {r[1]}  full {r[2]:.5f}  truncated {r[3]:.5f}")
        else:
            print(f"  truncation audit PASSED: {tot} checks, 0 mismatches")
    return bad
