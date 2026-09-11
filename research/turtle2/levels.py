"""Multi-timeframe support/resistance: prior 1H, 4H, daily, weekly and monthly highs and lows.

TEN LEVELS, five timeframes x {high, low}, available at every bar of the base series.

THE ONLY THING THAT MATTERS HERE IS CAUSALITY, and this branch has been bitten by exactly this
shape before: `STUDY_SCALP_TREND.md` records an overnight aggregate that read its OWN still-forming
group's running high, low and last close -- future data, caught only by the truncation audit. A
period high is a leak the moment it includes a bar that has not happened yet.

So each level is built two ways and both are exposed, because they answer different questions and
only one of them is safe by construction:

  PRIOR       the high/low of the last COMPLETED period. Constant for the whole of the current
              period, and unambiguously causal. This is what "last week's high" means to a trader.
  DEVELOPING  the running high/low of the CURRENT period, using only bars up to and including the
              present one. Causal too, but it CHANGES within the period, so a rule written against
              it is not the same rule as one written against `prior`.

`audit()` recomputes every level on history that ENDS at bar i and requires an exact match. That is
the only honest leakage test and it is what caught the earlier bug.

PERIOD BOUNDARIES ARE A CHOICE, not a fact, and they move the levels:
  1H, 4H    clock-aligned on the New York wall clock (4H at 00/04/08/12/16/20)
  daily     the 17:00 New York session boundary, matching `daily.py` and the CME convention
  weekly    Sunday 17:00 New York, the futures week
  monthly   calendar month on the New York clock
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TIMEFRAMES = ("1H", "4H", "D", "W", "M")


def _period_key(ix: pd.DatetimeIndex, tf: str) -> np.ndarray:
    """An integer id per period, constant within a period and increasing across them."""
    ns = np.asarray(ix.view("int64"))
    if tf == "1H":
        return ns // 3_600_000_000_000
    if tf == "4H":
        return ns // (4 * 3_600_000_000_000)
    shifted = ix + pd.Timedelta(hours=7)
    if tf == "D":
        return np.asarray(shifted.normalize().view("int64")) // 86_400_000_000_000
    if tf == "W":
        return (np.asarray(shifted.view("int64")) // 86_400_000_000_000 + 4) // 7
    if tf == "M":
        return np.asarray(shifted.year) * 12 + np.asarray(shifted.month)
    raise ValueError(tf)


def _running(vals, key, how):
    """Running extreme within each period, using only bars up to and including each one."""
    out = np.empty(len(vals))
    cur = np.nan; last = None
    for i in range(len(vals)):
        k = key[i]
        if k != last:
            cur = vals[i]; last = k
        else:
            cur = max(cur, vals[i]) if how == "max" else min(cur, vals[i])
        out[i] = cur
    return out


def _prior(vals, key, how):
    """The completed previous period's extreme, held constant through the current period."""
    out = np.full(len(vals), np.nan)
    cur = np.nan; prev = np.nan; last = None
    for i in range(len(vals)):
        k = key[i]
        if k != last:
            prev = cur
            cur = vals[i]; last = k
        else:
            cur = max(cur, vals[i]) if how == "max" else min(cur, vals[i])
        out[i] = prev
    return out


def build(idx, h, l, timeframes=TIMEFRAMES):
    """All ten levels (five timeframes x high/low), in both `prior` and `developing` forms."""
    ix = pd.DatetimeIndex(idx)
    out = {}
    for tf in timeframes:
        k = _period_key(ix, tf)
        out[f"prior_{tf}_high"] = _prior(h, k, "max")
        out[f"prior_{tf}_low"] = _prior(l, k, "min")
        out[f"dev_{tf}_high"] = _running(h, k, "max")
        out[f"dev_{tf}_low"] = _running(l, k, "min")
    return out


def nearest(px, lv, keys=None):
    """Distance from price to the closest level above and below, in price units.

    Returns (dist_up, dist_down, n_above, n_below). NaN where no level exists on that side.
    """
    keys = keys or [k for k in lv if k.startswith("prior_")]
    stack = np.vstack([lv[k] for k in keys])
    above = np.where(stack > px[None, :], stack, np.nan)
    below = np.where(stack < px[None, :], stack, np.nan)
    # a bar early in the series can have no level on one side at all; that is NaN, not an error
    import warnings
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        up = np.nanmin(above, axis=0) - px
        dn = px - np.nanmax(below, axis=0)
    return up, dn, np.sum(np.isfinite(above), axis=0), np.sum(np.isfinite(below), axis=0)


def audit(idx, h, l, checks=40, seed=3, verbose=True):
    """Truncation audit: recompute every level on history ENDING at bar i and require a match.

    The only leakage test that cannot be fooled by inspection. Anything that reads a bar after i
    changes value when the series is truncated at i.
    """
    full = build(idx, h, l)
    rng = np.random.default_rng(seed)
    n = len(h)
    pts = rng.choice(np.arange(int(0.3 * n), n), size=min(checks, n // 4), replace=False)
    bad = []
    for i in sorted(pts):
        part = build(idx[:i + 1], h[:i + 1], l[:i + 1])
        for k in full:
            a, b = full[k][i], part[k][i]
            if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, equal_nan=True):
                bad.append((int(i), k, float(a), float(b)))
    if verbose:
        if bad:
            print(f"  TRUNCATION AUDIT FAILED on {len(bad)} of {len(pts)*len(full)} checks")
            for row in bad[:8]:
                print(f"    bar {row[0]}  {row[1]}  full {row[2]:.5f}  truncated {row[3]:.5f}")
        else:
            print(f"  truncation audit PASSED: {len(pts)} bars x {len(full)} levels, "
                  f"{len(pts)*len(full)} checks, 0 mismatches")
    return bad
