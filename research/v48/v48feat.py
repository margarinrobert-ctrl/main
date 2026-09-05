"""V48 -- features at the SIGNAL BAR of a Donchian breakout: risk premia, PEAD analogue, and the
declared macro-release clock.

ON "NEWS DATA", stated plainly: no news feed is attached to this session, and no release timestamps
were scraped. What IS used is the fact that US macro releases land on a FIXED, PUBLIC New York
clock -- 08:30 (CPI, NFP, PPI, claims), 10:00 (ISM, confidence), 14:00 (FOMC) -- so those windows
are DECLARED here, with fixed definitions, never searched. That is the same discipline V47 applied
to turn-of-month: a published structure may be admitted as one pre-registered hypothesis; it may not
become a grid axis. Without an actual release calendar with surprise values, this identifies WHEN a
release could have landed and never WHICH one or WHAT it said.

PEAD REMAINS AN ANALOGUE. It is defined on single-name earnings surprises and cannot be computed
from index OHLCV; the `pead.*` block measures the MECHANISM -- a standardised shock and what follows
it -- with the event found endogenously.

EVERY FEATURE IS READ AT THE SIGNAL BAR, which closes BEFORE the order is sent. `ent_bar` is the
FILL bar and reading anything there is the leak that produced a p 0.0005 result on this branch once.
`audit()` proves causality by truncation.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v46")
import v46grid as G          # noqa: E402

# Declared, not searched: the fixed New York clock US macro releases land on.
RELEASE_MIN = (510, 600, 840)          # 08:30, 10:00, 14:00
RTH_OPEN, RTH_CLOSE = 570, 960


def _r(x, n, fn, minp=None):
    return getattr(pd.Series(x).rolling(n, min_periods=minp or max(5, n // 3)), fn)().to_numpy()


def build(P):
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr = P["atr"]
    ts = pd.to_datetime(pd.Series(P["ts"]))
    mod = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    day = ts.dt.normalize().to_numpy()
    lc = np.log(np.maximum(c, 1e-9))
    r1 = np.concatenate(([np.nan], np.diff(lc)))
    n = len(c)
    f = {}

    # ------------------------------------------------ RISK PREMIA
    for w in (20, 60, 240):
        f[f"rp.rv{w}"] = _r(r1, w, "std")
    with np.errstate(divide="ignore", invalid="ignore"):
        f["rp.rv_term"] = np.where(f["rp.rv240"] > 0, f["rp.rv20"] / f["rp.rv240"], np.nan)
    f["rp.volofvol"] = _r(f["rp.rv20"], 240, "std")
    up = np.where(r1 > 0, r1, 0.0); dn = np.where(r1 < 0, r1, 0.0)
    su = np.sqrt(_r(up ** 2, 60, "mean")); sd = np.sqrt(_r(dn ** 2, 60, "mean"))
    f["rp.semi_skew"] = np.where(su > 0, sd / su, np.nan)
    f["rp.rskew"] = _r(r1, 240, "skew")
    f["rp.rkurt"] = _r(r1, 240, "kurt")
    for w in (20, 60, 240, 960):
        m = _r(r1, w, "sum")
        f[f"rp.tsmom{w}"] = m
        f[f"rp.tsmom{w}_vs"] = np.where(f["rp.rv60"] > 0, m / f["rp.rv60"], np.nan)
    rng = (h - l)
    f["rp.range_comp"] = np.where(_r(rng, 240, "mean") > 0, rng / _r(rng, 240, "mean"), np.nan)

    # session context: where in the day, and the overnight/RTH split of recent return
    in_rth = (mod >= RTH_OPEN) & (mod < RTH_CLOSE)
    f["rp.in_rth"] = in_rth.astype(float)
    r_on = np.where(~in_rth, r1, 0.0)
    r_in = np.where(in_rth, r1, 0.0)
    f["rp.on_share"] = np.where(np.abs(_r(r1, 240, "sum")) > 1e-9,
                                _r(r_on, 240, "sum") / _r(r1, 240, "sum"), np.nan)
    f["rp.on_rth_spread"] = _r(r_on, 240, "mean") - _r(r_in, 240, "mean")

    # ------------------------------------------------ PEAD ANALOGUE
    sig = _r(r1, 240, "std")
    sue = np.where(sig > 0, r1 / sig, np.nan)
    f["pead.sue"] = sue
    f["pead.abs_sue"] = np.abs(sue)
    f["pead.sue_max20"] = _r(np.abs(sue), 20, "max")
    for thr in (2.0, 3.0):
        ev = np.abs(sue) >= thr
        s = np.where(ev, np.sign(sue), 0.0)
        last = np.zeros(n); since = np.full(n, np.nan)
        cur, age = 0.0, np.nan
        for i in range(n):
            if ev[i] and np.isfinite(sue[i]):
                cur, age = s[i], 0.0
            elif np.isfinite(age):
                age += 1.0
            last[i] = cur; since[i] = age
        f[f"pead.ev{thr}_sign"] = last
        f[f"pead.ev{thr}_since"] = since
        with np.errstate(invalid="ignore"):
            f[f"pead.ev{thr}_decay"] = last * np.exp(-since / 40.0)

    # ------------------------------------------------ DECLARED RELEASE CLOCK (the "news" proxy)
    tfm = int(np.median(np.diff(mod[np.diff(mod, prepend=mod[0]) > 0])[:50])) if n > 60 else 15
    tfm = tfm if tfm in (5, 15, 30, 60) else 15
    near = np.zeros(n, bool)
    for rm in RELEASE_MIN:
        near |= (np.abs(mod - rm) < max(tfm, 15))
    f["news.in_window"] = near.astype(float)
    since_rel = np.full(n, np.nan); age = np.nan
    for i in range(n):
        if near[i]:
            age = 0.0
        elif np.isfinite(age):
            age += 1.0
        since_rel[i] = age
    f["news.bars_since"] = since_rel
    # a release lands as a volume/range spike IN that window; this measures the spike, not the news
    vr = np.where(_r(rng, 240, "mean") > 0, rng / _r(rng, 240, "mean"), np.nan)
    f["news.window_spike"] = np.where(near, vr, 0.0)
    f["news.is_fomc_hour"] = (np.abs(mod - 840) < max(tfm, 15)).astype(float)

    # ------------------------------------------------ BREAKOUT CONTEXT
    hi30 = pd.Series(h).rolling(30).max().shift(1).to_numpy()
    lo30 = pd.Series(l).rolling(30).min().shift(1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        f["bo.excess"] = np.where(atr > 0, (h - hi30) / atr, np.nan)
        f["bo.chan_w"] = np.where(atr > 0, (hi30 - lo30) / atr, np.nan)
        f["bo.pos_in_chan"] = np.where(hi30 > lo30, (c - lo30) / (hi30 - lo30), np.nan)
    adx, _p, _m = _adx(h, l, c, 14)
    f["bo.adx"] = adx
    f["bo.chop"] = G.chop_idx(h, l, c, 14)
    f["bo.close_pos"] = np.where(rng > 0, (c - l) / rng, np.nan)
    return f


def _adx(h, l, c, n):
    up = np.concatenate(([0.0], np.diff(h)))
    dn = np.concatenate(([0.0], -np.diff(l)))
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = G.true_range(h, l, c)
    atr = G.rma(tr, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * G.rma(pdm, n) / atr
        ndi = 100 * G.rma(ndm, n) / atr
        dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return G.rma(dx, n), pdi, ndi


def audit(P, probes=(20000, 40000, 60000), tol=1e-7):
    full = build(P)
    bad = {}
    for i in probes:
        if i >= P["n"]:
            continue
        Q = {k: (v[:i + 1] if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == P["n"] else v)
             for k, v in P.items()}
        Q["n"] = i + 1
        cut = build(Q)
        for k in full:
            a, b = full[k][i], cut[k][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isfinite(a) or not np.isfinite(b) or abs(a - b) > tol * max(1.0, abs(a)):
                bad.setdefault(k, []).append(i)
    return bad
