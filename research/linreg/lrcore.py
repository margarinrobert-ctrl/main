"""A linear regression as the PRIMARY, with ATR doing the risk. Not a filter on someone else's rule.

WHY THIS IS A DIFFERENT QUESTION FROM THE THREE PRIOR LINREG STUDIES. `STUDY_V20_LINREG`,
`STUDY_V25_LINREG_CROSS` and `STUDY_V38_LINREG_GRID` all put a regression on top of a Donchian
breakout as a CONFIRMATION and all three found it worthless -- V20 measured the most literal reading
passing 12.1% of breakout bars (lift 0.24x) because a breakout has just jumped above the range the
line is fitted to. None of them ran the regression as the entry itself. That is what this does.

PHASE 0 -- what is being claimed. A regression line is a least-squares estimate of where price
"should" be, and its residual band is a scale-free distance from that estimate. Two mechanisms are
possible and they point OPPOSITE WAYS, so both are declared and neither is chosen after the fact:
  TREND      the slope carries information about the next move   (continuation)
  REVERSION  a large residual is corrected                       (mean reversion)
No counterparty is named for either -- this is a fitted pattern, not a flow mechanism, so it carries
the full deflation burden.

FIVE DECLARED READINGS, all mirrored for the short side so no freedom is spent on direction:
  S  slope > 0                              the fitted line is rising          (trend, state)
  X  slope crosses 0                        the fit turns up                   (trend, event)
  V  close > value                          price above the line               (V20's best reading)
  B  close > value + k*sigma                breakout of the regression channel (trend, event)
  R  close < value - k*sigma                reversion to the line              (mean reversion)

ATR does three jobs and each is a declared axis: the STOP (n x ATR), the TARGET (in R), and the
channel width if `k` is expressed in ATR rather than residual sigma -- both are run.

Exits: the opposite reading, the stop, the target, or a hold cap. Scored in PERCENT OF ENTRY PRICE,
because the stop moves with ATR and R would divide by a moving denominator.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
from v38 import v38feeds as F  # noqa: E402

COST = {"US30L": 2.29, "US100L": 1.215, "NQ": 1.72}
PTS = {"US30L": 1.0, "US100L": 1.0, "NQ": 1.0}


def load(name, tf=15):
    """15m feeds resampled up; NQ comes from the 1-minute file and is UTC-stamped."""
    if name == "NQ":
        d = pd.read_csv(os.path.join(ROOT, "data/NQ_1m.csv"))
        c = {x.lower(): x for x in d.columns}
        ts = pd.to_datetime(d[c.get("datetime", c.get("date", list(d.columns)[0]))], utc=True)
        d.index = pd.DatetimeIndex(ts).tz_convert("America/New_York").tz_localize(None)
        d = d.rename(columns={c["open"]: "open", c["high"]: "high", c["low"]: "low",
                              c["close"]: "close"})
        f = d[["open", "high", "low", "close"]]
    else:
        f = F.load(name)[["open", "high", "low", "close"]]
    if tf != (1 if name == "NQ" else 15):
        f = f.resample(f"{tf}min", label="left", closed="left").agg(
            dict(open="first", high="max", low="min", close="last")).dropna()
    f = f.copy()
    f["atr"] = atr(f, 14)
    f["mod"] = f.index.hour * 60 + f.index.minute
    return f


def atr(f, n=14):
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


@njit(cache=True)
def _ols(c, n):
    """Rolling least squares on the last n closes. Returns value (the fit AT the current bar),
    slope per bar, and the residual standard deviation. Causal: bar i uses bars i-n+1..i."""
    m = len(c)
    val = np.full(m, np.nan); slp = np.full(m, np.nan); sig = np.full(m, np.nan)
    sx = 0.0; sxx = 0.0
    for k in range(n):
        sx += k
        sxx += k * k
    den = n * sxx - sx * sx
    for i in range(n - 1, m):
        sy = 0.0; sxy = 0.0
        for k in range(n):
            y = c[i - n + 1 + k]
            sy += y
            sxy += k * y
        b = (n * sxy - sx * sy) / den
        a = (sy - b * sx) / n
        v = a + b * (n - 1)
        ss = 0.0
        for k in range(n):
            e = c[i - n + 1 + k] - (a + b * k)
            ss += e * e
        val[i] = v; slp[i] = b; sig[i] = np.sqrt(ss / n)
    return val, slp, sig


def ols(c, n):
    return _ols(np.ascontiguousarray(c, dtype=np.float64), int(n))


@njit(cache=True)
def _walk(o, h, l, c, at, mod, sig_up, sig_dn, exit_up, exit_dn, side_want,
          stop_mult, tp_r, hold, m0, m1, cost):
    """sig_up/sig_dn are the entry masks per side; exit_* the opposite-reading masks."""
    n = len(c)
    eb = np.full(n, -1, np.int64); out = np.empty(n)
    sd = np.empty(n, np.int64); hl = np.empty(n, np.int64); cf = np.empty(n)
    cnt = 0; last = -1
    for i in range(1, n - 1):
        if i <= last or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if m0 >= 0 and (mod[i] < m0 or mod[i] >= m1):
            continue
        s = 0
        if sig_up[i] == 1 and side_want >= 0:
            s = 1
        elif sig_dn[i] == 1 and side_want <= 0:
            s = -1
        if s == 0:
            continue
        j = i + 1
        ent = o[j]
        risk = stop_mult * at[i]
        stop = ent - s * risk
        targ = ent + s * tp_r * risk if tp_r > 0 else 0.0
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if tp_r > 0 and (((h[t] >= targ) if s > 0 else (l[t] <= targ))):
                x = t; px = targ
                break
            if t > j and ((s > 0 and exit_up[t] == 1) or (s < 0 and exit_dn[t] == 1)):
                x = t; px = c[t]
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        eb[cnt] = j
        out[cnt] = 100.0 * (s * (px - ent) - cost) / ent
        sd[cnt] = s; hl[cnt] = x - j; cf[cnt] = cost / risk
        cnt += 1
        last = x
    return eb[:cnt], out[:cnt], sd[:cnt], hl[:cnt], cf[:cnt]


@njit(cache=True)
def _walk_at(o, h, l, c, at, exit_up, exit_dn, sig, side, stop_mult, tp_r, hold, cost):
    """The matched control: given signal bars and sides, run the IDENTICAL management."""
    n = len(c); m = len(sig)
    out = np.full(m, np.nan)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        s = side[q]; j = i + 1
        ent = o[j]; risk = stop_mult * at[i]
        stop = ent - s * risk
        targ = ent + s * tp_r * risk if tp_r > 0 else 0.0
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if tp_r > 0 and (((h[t] >= targ) if s > 0 else (l[t] <= targ))):
                x = t; px = targ
                break
            if t > j and ((s > 0 and exit_up[t] == 1) or (s < 0 and exit_dn[t] == 1)):
                x = t; px = c[t]
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[q] = 100.0 * (s * (px - ent) - cost) / ent
        last = x
    return out


def readings(f, n, k, k_in_atr):
    """The five declared readings, as (entry_up, entry_dn, exit_up, exit_dn) integer masks."""
    c = f["close"].to_numpy()
    val, slp, sig = ols(c, n)
    band = (k * f["atr"].to_numpy()) if k_in_atr else (k * sig)
    up_state = slp > 0
    out = {}
    out["S slope state"] = (up_state, ~up_state & np.isfinite(slp), ~up_state & np.isfinite(slp), up_state)
    xs_up = up_state & np.r_[False, ~up_state[:-1]]
    xs_dn = (~up_state & np.isfinite(slp)) & np.r_[False, up_state[:-1]]
    out["X slope cross"] = (xs_up, xs_dn, xs_dn, xs_up)
    av = c > val
    out["V close>value"] = (av, (~av) & np.isfinite(val), (~av) & np.isfinite(val), av)
    bu, bd = c > val + band, c < val - band
    out["B channel break"] = (bu, bd, c < val, c > val)
    out["R channel revert"] = (bd, bu, c > val, c < val)
    for kk in out:
        out[kk] = tuple(np.asarray(x, dtype=np.int64) for x in out[kk])
    return out, val, slp, sig


def pf(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan
