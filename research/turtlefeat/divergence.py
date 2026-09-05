"""RSI / Stochastic bullish divergence and volume spikes — built CONFIRMED-ONLY, and audited.

THE LEAK THIS FILE EXISTS TO AVOID. A pivot low at bar i is defined by the bars on BOTH sides of
it: l[i] must be the lowest of l[i-k .. i+k]. That fact is not knowable at bar i -- it is knowable
at bar i+k, once the right-hand side has printed. Virtually every published divergence indicator
marks the signal at the pivot, which back-tests beautifully and cannot be traded, because at the
moment the marker appears the move it "predicted" has already happened.

Here every pivot becomes visible only at `pivot_index + confirm`, and a divergence between two
pivots becomes visible only when the SECOND one confirms. `audit()` recomputes the whole family on
history truncated at bar i and requires an exact match; the same test caught a real look-ahead in
`STUDY_SCALP_TREND.md` that reading the code had missed.

BULLISH DIVERGENCE, as measured here: price prints a LOWER confirmed pivot low while the oscillator
prints a HIGHER low at the corresponding pivot. Strength is reported two ways, because they answer
different questions -- the raw oscillator gap, and that gap divided by how far price fell, which
normalises for how big the price leg was.

VOLUME SPIKE is deliberately given two baselines. Against a rolling median it answers "is this bar
busy for this market"; against the expanding mean for the SAME MINUTE OF DAY it answers "is this bar
busy for this time", which is the question that matters intraday, where 09:30 is always heavy and
11:45 never is. The time-of-day baseline is expanding and shifted, so today never sees itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CONFIRM = 3          # bars of right-hand side needed before a pivot is knowable


def rsi(c, n=14):
    d = np.diff(np.asarray(c, float), prepend=np.asarray(c, float)[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(dn > 0, up / dn, np.inf)
    return 100.0 - 100.0 / (1.0 + rs)


def stoch_k(h, l, c, n=14, smooth=3):
    hh = pd.Series(h).rolling(n, min_periods=n).max().to_numpy()
    ll = pd.Series(l).rolling(n, min_periods=n).min().to_numpy()
    rng = hh - ll
    k = np.where(rng > 0, 100.0 * (np.asarray(c, float) - ll) / rng, np.nan)
    return pd.Series(k).rolling(smooth, min_periods=1).mean().to_numpy()


def confirmed_pivot_lows(l, k=CONFIRM):
    """Index array of pivot lows, each paired with the bar at which it becomes KNOWABLE."""
    l = np.asarray(l, float)
    n = len(l)
    piv = []
    for i in range(k, n - k):
        w = l[i - k:i + k + 1]
        if l[i] == np.min(w) and np.argmin(w) == k:
            piv.append((i, i + k))          # (where it is, when you may use it)
    return piv


def bullish_divergence(l, osc, k=CONFIRM, max_gap=60):
    """Features that are NaN/0 until the second pivot of the pair has confirmed.

    `max_gap` caps how far apart the two pivots may be, in bars: a "divergence" spanning half the
    session is not the pattern anyone means by the word.
    """
    l = np.asarray(l, float); osc = np.asarray(osc, float)
    n = len(l)
    present = np.zeros(n); since = np.full(n, np.nan)
    osc_gap = np.zeros(n); norm_gap = np.zeros(n); price_leg = np.zeros(n)
    piv = confirmed_pivot_lows(l, k)
    for a in range(1, len(piv)):
        (i1, _), (i2, vis) = piv[a - 1], piv[a]
        if vis >= n or (i2 - i1) > max_gap:
            continue
        if not (np.isfinite(osc[i1]) and np.isfinite(osc[i2])):
            continue
        # price lower low, oscillator higher low
        if l[i2] < l[i1] and osc[i2] > osc[i1]:
            drop = (l[i1] - l[i2]) / l[i1] if l[i1] > 0 else np.nan
            gap = osc[i2] - osc[i1]
            present[vis] = 1.0
            osc_gap[vis] = gap
            price_leg[vis] = drop
            norm_gap[vis] = gap / (100.0 * drop) if drop and drop > 0 else 0.0
    # `since` is filled by a plain forward scan over `present`. An earlier version filled it up
    # to the NEXT pivot's confirmation bar, which meant bar t knew when a future pivot would
    # confirm -- a look-ahead the truncation audit caught (full +37 against truncated +999).
    last = -1
    for t in range(n):
        if last >= 0:
            since[t] = t - last
        if present[t] > 0:
            last = t
            since[t] = 0.0
    return dict(present=present, since=since, osc_gap=osc_gap,
                norm_gap=norm_gap, price_leg=price_leg)


def build(o, h, l, c, v, idx, k=CONFIRM):
    """The full confirmation-entry family: RSI divergence, Stoch divergence, volume spikes."""
    ix = pd.DatetimeIndex(idx)
    F = {}
    r = rsi(c); s = stoch_k(h, l, c)
    F["rsi"] = r
    F["stoch_k"] = s
    for name, osc in (("rsi", r), ("stoch", s)):
        D = bullish_divergence(l, osc, k)
        F[f"{name}_div_bull"] = D["present"]
        F[f"{name}_div_since"] = np.where(np.isfinite(D["since"]), D["since"], 999.0)
        F[f"{name}_div_gap"] = D["osc_gap"]
        F[f"{name}_div_gap_norm"] = D["norm_gap"]
        F[f"{name}_div_recent20"] = (pd.Series(D["present"]).rolling(20, min_periods=1)
                                     .max().to_numpy())

    v = np.asarray(v, float)
    med = pd.Series(v).rolling(50, min_periods=10).median().to_numpy()
    F["vspike_med"] = v / np.where(med > 0, med, np.nan)
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    tod = pd.DataFrame({"mod": mod, "v": v})
    base = tod.groupby("mod")["v"].transform(lambda x: x.expanding().mean().shift(1)).to_numpy()
    F["vspike_tod"] = v / np.where(base > 0, base, np.nan)
    F["vspike_flag"] = (F["vspike_tod"] >= 1.5).astype(float)
    F["vspike_flag2"] = (F["vspike_tod"] >= 2.0).astype(float)
    for nm in ("rsi", "stoch"):
        F[f"{nm}_div_x_vspike"] = F[f"{nm}_div_recent20"] * np.nan_to_num(F["vspike_tod"], nan=0.0)
    return F


def audit(o, h, l, c, v, idx, checks=10, seed=6, verbose=True):
    full = build(o, h, l, c, v, idx)
    rng = np.random.default_rng(seed)
    n = len(c)
    pts = rng.choice(np.arange(int(0.6 * n), n - 1), size=min(checks, n // 10), replace=False)
    bad = []
    for i in sorted(pts):
        part = build(o[:i + 1], h[:i + 1], l[:i + 1], c[:i + 1], v[:i + 1], idx[:i + 1])
        for kk in full:
            a, b = full[kk][i], part[kk][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True):
                bad.append((int(i), kk, float(a), float(b)))
    if verbose:
        tot = len(pts) * len(full)
        if bad:
            names = sorted({r[1] for r in bad})
            print(f"  TRUNCATION AUDIT FAILED: {len(bad)}/{tot} checks, features: {names[:6]}")
            for nm in names[:5]:
                ex = next(r for r in bad if r[1] == nm)
                print(f"    {nm:<22} bar {ex[0]}  full {ex[2]:+.6g}  truncated {ex[3]:+.6g}")
        else:
            print(f"  truncation audit PASSED: {tot} checks, 0 mismatches")
    return bad
