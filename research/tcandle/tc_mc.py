"""Four Monte Carlos, kept separate because they answer four different questions.

    EDGE      day-block bootstrap -- resample whole DAYS with their trades attached, then take the
              TRADE-weighted mean.  Trades cluster inside a session, so a trade-wise resample
              pretends 216 trades are 216 independent draws when they are nearer 150 days.
    PATH      permutation -- reshuffle the realised trades and re-walk the equity curve.  This
              answers a DRAWDOWN question only; permuting cannot change the endpoint, so reporting
              an endpoint distribution from it is meaningless.
    EXECUTION perturbation applied INSIDE the walk: the round turn is drawn U(0.5x, 2.0x) per
              draw, so the trade SET can change rather than only its accounting.
    DATA      price jitter with every indicator RECOMPUTED -- ATR, ADX, the EMA100 and all four
              channels are rebuilt from the jittered bars, so the SIGNAL moves, not just the fill.
              This is the demanding one; run the execution MC first so it is not mistaken for it.

Order matters when reading them: execution and data noise are cheap to survive on a system whose
stop is 2.0N and whose round turn is 1% of it, so a tight band there says nothing about the edge.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T                                     # noqa: E402


def _days(tr, ts):
    return pd.to_datetime(ts[tr["sig"].to_numpy(int)]).normalize().values


def boot_edge(tr, ts, n=4000, seed=1):
    """P(mean <= 0) and a 95% CI for the per-trade edge, resampling DAYS with their trades."""
    if not len(tr):
        return dict(mean=np.nan, lo=np.nan, hi=np.nan, p_le0=np.nan)
    d = _days(tr, ts)
    pct = tr["pct"].to_numpy(float)
    uniq, inv = np.unique(d, return_inverse=True)
    groups = [pct[inv == i] for i in range(len(uniq))]
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        out[i] = np.concatenate([groups[j] for j in pick]).mean()
    return dict(mean=float(pct.mean()), lo=float(np.percentile(out, 2.5)),
                hi=float(np.percentile(out, 97.5)), p_le0=float((out <= 0).mean()), draws=out)


def _maxdd(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]))


def perm_path(tr, n=4000, seed=2):
    """Realised drawdown against the distribution of reshuffles of the SAME trades."""
    if not len(tr):
        return dict(realised=np.nan, pct=np.nan, p99=np.nan)
    pct = tr["pct"].to_numpy(float)
    real = _maxdd(pct)
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        out[i] = _maxdd(rng.permutation(pct))
    return dict(realised=real, pct=float((out <= real).mean()),
                p99=float(np.percentile(out, 99)), draws=out)


def exec_mc(d, C, atr, mask, cost, n=200, seed=3, **kw):
    """Cost drawn U(0.5x, 2.0x) and applied INSIDE the walk, so the trade set can move."""
    rng = np.random.default_rng(seed)
    tot, per, cnt = np.empty(n), np.empty(n), np.empty(n)
    for i in range(n):
        tr = T.run(d, C, atr, mask, cost * rng.uniform(0.5, 2.0), **kw)
        tot[i] = tr["pct"].sum() if len(tr) else 0.0
        per[i] = tr["pct"].mean() if len(tr) else np.nan
        cnt[i] = len(tr)
    return dict(total=tot, per=per, n=cnt, p_le0=float((tot <= 0).mean()),
                sign_kept=float(np.mean(np.sign(tot) == np.sign(np.median(tot)))))


def jitter_mc(mkt, tf, lengths_fn, ticks, cost, adx_max=22.0, ext_max=0.0,
              n=120, seed=4, block=None):
    """Jitter every bar's OHLC, repair the bar, and RECOMPUTE every indicator from it.

    A perturbation that leaves the signal alone only prices the fill; this one moves which bars are
    breakouts at all, which is the question worth asking of a channel system."""
    d0 = T.frame(mkt, tf)
    e1, e2, x1, x2 = lengths_fn
    rng = np.random.default_rng(seed)
    n_bars = len(d0["c"])
    cut = T.split(d0)
    lo, hi = (0, cut) if block in (None, "A") else (cut, n_bars)
    tot, per, cnt = np.empty(n), np.empty(n), np.empty(n)
    for i in range(n):
        j = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in d0.items()}
        for k in ("o", "h", "l", "c"):
            j[k] = j[k] + rng.uniform(-ticks, ticks, n_bars)
        j["h"] = np.maximum.reduce([j["o"], j["h"], j["l"], j["c"]])
        j["l"] = np.minimum.reduce([j["o"], j["h"], j["l"], j["c"]])
        atr, adx, dist = T.context(j)
        C = T.channels(j, e1, e2, x1, x2)
        m = T.gate_mask(adx, dist, adx_max, ext_max) & np.isfinite(atr) & (atr > 0)
        m[:lo] = False
        m[hi:] = False
        tr = T.run(j, C, atr, m, cost)
        tot[i] = tr["pct"].sum() if len(tr) else 0.0
        per[i] = tr["pct"].mean() if len(tr) else np.nan
        cnt[i] = len(tr)
    return dict(total=tot, per=per, n=cnt, p_le0=float((tot <= 0).mean()),
                sign_kept=float(np.mean(np.sign(tot) == np.sign(np.median(tot)))))
