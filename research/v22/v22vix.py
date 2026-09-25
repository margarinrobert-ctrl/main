"""The VIX study proper: SPX daily paired with VIX daily, 2012-01-03 to 2020-11-04.

WHY THIS FILE EXISTS AND `v22vol.py` IS NOT ENOUGH. A realised-volatility family substitutes for
the VIX's LEVEL and its own term structure. It cannot substitute for the one thing the VIX carries
that no price history contains: the IMPLIED side. VIX minus contemporaneous realised volatility is
the VOLATILITY RISK PREMIUM -- what the option market charges over what the tape delivered -- and it
is the only genuinely new column here. Every other VIX feature is a noisier copy of something
`v22vol.py` already builds from bars.

EVERY FEATURE IS READ AT THE CLOSE OF DAY t AND SCORED AGAINST DAYS t+1..t+h. Nothing is centred,
nothing is smoothed two-sided, and no rolling window extends past t (STUDY_HP_FILTER).

CAVEATS THAT TRAVEL WITH EVERY NUMBER BELOW, stated before the tables rather than after:
  * SPX ends 2020-11-04, so the locked block CONTAINS COVID. One four-week volatility event sits in
    the held-out block and will dominate any VIX-conditioned statistic there. Read the locked column
    as "does this survive the largest vol shock in the sample", not as a clean out-of-sample read.
  * These are DAILY bars on the cash index. The branch's shipped rules are 15m and 30m futures. A
    daily VIX regime is evidence about the equity complex, not a drop-in filter for an intraday NQ
    strategy, and it is not presented as one.
  * There is no VIX9D or VIX3M here, so the IMPLIED term structure -- the part of the VIX complex
    with the best-documented forecasting record -- cannot be built. Only the implied-vs-realised
    spread is available.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v18")
import v18diag as G           # noqa: E402

SPX = "data/SPX.csv"
VIX = "data/VIX_daily.csv"


def load():
    s = pd.read_csv(SPX, parse_dates=["Date"])
    v = pd.read_csv(VIX, parse_dates=["Date"])
    s = s[["Date", "Open", "High", "Low", "Close"]].rename(
        columns={"Open": "o", "High": "h", "Low": "l", "Close": "c"})
    v = v[["Date", "Open", "High", "Low", "Close"]].rename(
        columns={"Open": "vo", "High": "vh", "Low": "vl", "Close": "vx"})
    d = s.merge(v, on="Date", how="inner").sort_values("Date").reset_index(drop=True)
    # A quoted zero in either series is a missing value, not a price (STUDY_SPREAD_TRUTH).
    for k in ("o", "h", "l", "c", "vx"):
        d = d[d[k] > 0]
    return d.reset_index(drop=True)


def _roll(x, n, fn):
    return pd.Series(x).rolling(n, min_periods=n).apply(fn, raw=True).to_numpy()


def rmean(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def rstd(x, n):
    return pd.Series(x).rolling(n, min_periods=n).std(ddof=1).to_numpy()


def rpct(x, n):
    """Rank of today within the trailing n days, in [0,1]. Causal: the window ENDS at t."""
    return pd.Series(x).rolling(n, min_periods=n).rank(pct=True).to_numpy()


def true_range(h, l, c):
    pc = np.roll(c, 1)
    pc[0] = np.nan
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)


def features(d):
    """~40 causal VIX / VIX-vs-realised readings, all knowable at the close of day t."""
    c, h, l = d.c.to_numpy(), d.h.to_numpy(), d.l.to_numpy()
    vx, vh, vl, vo = d.vx.to_numpy(), d.vh.to_numpy(), d.vl.to_numpy(), d.vo.to_numpy()
    r = np.concatenate([[np.nan], np.diff(np.log(c))])
    F = {}

    # --- A. LEVEL AND STATE. The plain reading, plus the two scale-free versions of it.
    F["vix"] = vx
    F["log_vix"] = np.log(vx)
    for n in (60, 250, 500):
        F[f"vix_pct{n}"] = rpct(vx, n)
        F[f"vix_z{n}"] = (vx - rmean(vx, n)) / rstd(vx, n)
    for n in (10, 50, 200):
        F[f"vix_ma{n}"] = vx / rmean(vx, n)

    # --- B. CHANGE. A vol SPIKE and a vol LEVEL are different states.
    for n in (1, 5, 20):
        F[f"vix_d{n}"] = vx / np.concatenate([np.full(n, np.nan), vx[:-n]]) - 1.0
    F["vix_accel"] = F["vix_d5"] - F["vix_d20"]

    # --- C. THE VOLATILITY RISK PREMIUM. The only column no price history can supply.
    for n in (10, 20, 60):
        rv = rstd(r, n) * np.sqrt(252) * 100.0
        F[f"rv{n}"] = rv
        F[f"vrp{n}"] = vx - rv                 # points of implied over realised
        F[f"vrp_ratio{n}"] = vx / rv           # scale-free version of the same thing
        F[f"vrp_z{n}"] = (F[f"vrp{n}"] - rmean(F[f"vrp{n}"], 250)) / rstd(F[f"vrp{n}"], 250)
        F[f"vrp_pct{n}"] = rpct(F[f"vrp{n}"], 250)

    # --- D. VOL OF VOL, and the shape of the VIX's own bar.
    for n in (10, 20, 60):
        F[f"vov{n}"] = rstd(np.concatenate([[np.nan], np.diff(np.log(vx))]), n)
    F["vix_range"] = (vh - vl) / vx
    F["vix_barpos"] = np.where(vh > vl, (vx - vl) / (vh - vl), 0.5)
    F["vix_gap"] = vo / np.concatenate([[np.nan], vx[:-1]]) - 1.0

    # --- E. TERM STRUCTURE PROXY. Without VIX9D/VIX3M the only slope available is the VIX
    #        against its OWN trailing average. It is a proxy and is labelled as one.
    for a, b in ((5, 20), (10, 60), (20, 120)):
        F[f"vixts_{a}_{b}"] = rmean(vx, a) / rmean(vx, b)

    return F


def forward_er(c, hzn):
    """|net move| / sum |daily moves| over the NEXT h days. 1.0 = a straight line, ~0 = chop."""
    n = len(c)
    out = np.full(n, np.nan)
    dc = np.abs(np.diff(c))
    for i in range(n - hzn - 1):
        s = dc[i:i + hzn].sum()
        if s > 0:
            out[i] = abs(c[i + hzn] - c[i]) / s
    return out


def forward_vol(c, hzn):
    r = np.concatenate([[np.nan], np.diff(np.log(c))])
    out = np.full(len(c), np.nan)
    for i in range(len(c) - hzn - 1):
        out[i] = np.nanstd(r[i + 1:i + 1 + hzn], ddof=1) * np.sqrt(252) * 100.0
    return out


def bh(p, q=0.10):
    p = np.asarray(p, float)
    o = np.argsort(p)
    m = len(p)
    below = p[o] <= q * np.arange(1, m + 1) / m
    out = np.zeros(m, bool)
    if below.any():
        out[o[:np.max(np.flatnonzero(below)) + 1]] = True
    return out


def blocks(n, frac=0.65):
    i = np.arange(n)
    return i < int(n * frac), i >= int(n * frac)


def hdr(t):
    print("\n" + "=" * 116)
    print(t)
    print("=" * 116)


# ---------------------------------------------------------------------------------------------
# A DELIBERATELY SMALL DAILY ENGINE. Donchian 30 entry / 20 exit, long, ATR stop, no target -- the
# same geometry the branch ships intraday, so the VIX overlay is the only thing that differs.
# Barriers inside one bar are resolved as a STOP always, and the ambiguous share is reported.
# ---------------------------------------------------------------------------------------------
def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()


def shift(x, k=1):
    o = np.full(len(x), np.nan)
    o[k:] = x[:-k]
    return o


def donchian(d, entry_n=30, exit_n=20, atr_len=14):
    h, l, c = d.h.to_numpy(), d.l.to_numpy(), d.c.to_numpy()
    atr = ema(true_range(h, l, c), atr_len)
    ent_hi = shift(pd.Series(h).rolling(entry_n, min_periods=entry_n).max().to_numpy())
    ex_lo = shift(pd.Series(l).rolling(exit_n, min_periods=exit_n).min().to_numpy())
    m = np.isfinite(ent_hi) & (h > ent_hi) & np.isfinite(atr) & (atr > 0)
    m[-3:] = False
    return np.flatnonzero(m).astype(np.int64), atr, ex_lo


def walk(d, sig, atr, ex_lo, stop_mult=2.0, cost_bp=2.0):
    """Returns exit bar, R, exit reason, MAE and MFE in ATR units. Cost is a round turn in bp."""
    o, h, l, c = (d[k].to_numpy() for k in ("o", "h", "l", "c"))
    n = len(c)
    xb = np.full(len(sig), -1, np.int64)
    R = np.full(len(sig), np.nan)
    why = np.zeros(len(sig), np.int64)   # 0 stop, 1 channel
    mae = np.full(len(sig), np.nan)
    mfe = np.full(len(sig), np.nan)
    amb = 0
    for k, i in enumerate(sig):
        eb = i + 1
        if eb >= n:
            continue
        px = o[eb]
        a = atr[i]
        stop = px - stop_mult * a
        lo, hi = px, px
        for j in range(eb, n):
            lo = min(lo, l[j])
            hi = max(hi, h[j])
            lvl, w = stop, 0
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl, w = ch, 1
            lvl = min(lvl, c[j - 1])
            if l[j] <= lvl:
                xb[k], why[k] = j, w
                gross = lvl - px
                R[k] = (gross - px * cost_bp / 10000.0) / (stop_mult * a)
                break
        if xb[k] < 0:
            continue
        mae[k] = (px - lo) / a
        mfe[k] = (hi - px) / a
    return dict(sig=sig, xb=xb, R=R, why=why, mae=mae, mfe=mfe, amb=amb)


def lock(O, keep):
    """Position lock: one trade at a time, in signal order."""
    out, last = [], -1
    for k in range(len(O["sig"])):
        if not keep[k] or O["xb"][k] < 0 or O["sig"][k] <= last:
            continue
        out.append(k)
        last = O["xb"][k]
    return np.array(out, np.int64)


def pf(r):
    return float(r[r > 0].sum() / abs(r[r < 0].sum())) if (r < 0).any() else np.nan
