"""Market regime classification from OHLCV, on five independent axes rather than one label.

One label ("trending", "choppy") forces unrelated things into the same bucket and then cannot
answer "when does this strategy work". Five axes can: a session is *both* high-volatility and
mean-reverting, and a strategy may care about one and not the other.

    trend       trending / choppy / mean-reverting      Hurst, ADX, variance ratio
    volatility  low / normal / high                     ATR against its own trailing distribution
    vol shape   compressing / stable / expanding        ATR20 vs ATR100
    liquidity   thin / normal / deep                    Amihud illiquidity
    direction   down / flat / up                        50-session drift

Plus an unsupervised Gaussian-mixture regime over the same inputs, as a cross-check that the
hand-cut axes are not inventing structure.

Every label for session s is computed from bars that closed BEFORE session s begins. That is not
a detail: a regime label built from the session it labels makes every regime study circular, and
this repository has already published one look-ahead of exactly that shape.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import features as FT
from bos_choch import prep

AXES = ["trend", "volatility", "vol shape", "liquidity", "direction"]
LABELS = {
    "trend": ["mean-reverting", "choppy", "trending"],
    "volatility": ["low vol", "normal vol", "high vol"],
    "vol shape": ["compressing", "stable", "expanding"],
    "liquidity": ["thin", "normal", "deep"],
    "direction": ["down", "flat", "up"],
}


def _session_agg(x, sess, how="mean"):
    s = pd.Series(x).groupby(sess)
    return (s.mean() if how == "mean" else s.last()).to_numpy()


def _tercile_causal(x, lo=33.3, hi=66.7, warm=120):
    """Bucket each value against the distribution of everything BEFORE it. Terciles cut on the
    whole series would let the future decide today's label."""
    out = np.full(len(x), 1, np.int64)
    v = np.asarray(x, float)
    for i in range(len(v)):
        if i < warm or not np.isfinite(v[i]):
            out[i] = 1
            continue
        past = v[:i]
        past = past[np.isfinite(past)]
        if len(past) < warm:
            out[i] = 1
            continue
        a, b = np.percentile(past, [lo, hi])
        out[i] = 0 if v[i] <= a else (2 if v[i] >= b else 1)
    return out


def classify(tf=30, n_states=4, seed=11):
    d = prep(tf)
    F = FT.build(d)
    sess = d["sess"]
    us = np.unique(sess)

    raw = {
        "trend": _session_agg(np.nan_to_num(F["Hurst 256"], nan=0.5) * 100
                              + np.nan_to_num(F["ADX"], nan=20.0), sess),
        "volatility": _session_agg(np.nan_to_num(F["ATR z100"]), sess),
        "vol shape": _session_agg(np.nan_to_num(F["ATR20 / ATR100"], nan=1.0), sess),
        "liquidity": -_session_agg(np.nan_to_num(F["illiquidity z100"]), sess),
        "direction": _session_agg(np.nan_to_num(F["return 50b / ATR"]), sess),
    }
    # shift one session: a label for session s uses only sessions before it
    lab = {}
    for k, v in raw.items():
        prev = np.r_[np.nan, v[:-1]]
        lab[k] = _tercile_causal(prev)

    X = np.column_stack([np.r_[np.nan, raw[k][:-1]] for k in AXES])
    ok = np.isfinite(X).all(axis=1)
    from sklearn.mixture import GaussianMixture
    Xs = (X[ok] - X[ok].mean(0)) / np.maximum(X[ok].std(0), 1e-9)
    gm = GaussianMixture(n_states, covariance_type="full", random_state=seed, n_init=3).fit(Xs)
    state = np.full(len(us), -1, np.int64)
    state[ok] = gm.predict(Xs)
    return dict(sessions=us, labels=lab, state=state, raw=raw, n_states=n_states, tf=tf)


def describe(R):
    """What each unsupervised state actually is, in the language of the axes."""
    out = {}
    for s in range(R["n_states"]):
        m = R["state"] == s
        if m.sum() == 0:
            continue
        parts = []
        for ax in AXES:
            v = R["labels"][ax][m]
            best = np.bincount(v, minlength=3).argmax()
            share = 100 * (v == best).mean()
            if share > 45:
                parts.append(f"{LABELS[ax][best]} {share:.0f}%")
        out[s] = (int(m.sum()), ", ".join(parts))
    return out


def by_regime(R, ent_sess, pnl):
    """A strategy's P&L split by every axis and by the unsupervised state."""
    us = R["sessions"]
    si = np.searchsorted(us, us)          # sessions are already the index space
    rows = []
    for ax in AXES:
        lv = R["labels"][ax]
        for k, nm in enumerate(LABELS[ax]):
            m = lv[ent_sess] == k
            rows.append((ax, nm, int(m.sum()), float(pnl[m].sum()),
                         float(pnl[m].mean()) if m.sum() else 0.0,
                         float(100 * (pnl[m] > 0).mean()) if m.sum() else 0.0))
    for s in range(R["n_states"]):
        m = R["state"][ent_sess] == s
        rows.append(("state", f"state {s}", int(m.sum()), float(pnl[m].sum()),
                     float(pnl[m].mean()) if m.sum() else 0.0,
                     float(100 * (pnl[m] > 0).mean()) if m.sum() else 0.0))
    return rows


def works_where(rows, min_trades=15):
    """The two sentences the spec asks for: when does it work, when should it be avoided."""
    good = [r for r in rows if r[2] >= min_trades and r[4] > 0]
    bad = [r for r in rows if r[2] >= min_trades and r[4] <= 0]
    good.sort(key=lambda r: -r[4]); bad.sort(key=lambda r: r[4])
    return good[:4], bad[:4]


if __name__ == "__main__":
    R = classify()
    print(f"{len(R['sessions'])} sessions classified on {len(AXES)} axes "
          f"plus {R['n_states']} unsupervised states\n")
    for ax in AXES:
        v = R["labels"][ax]
        print(f"  {ax:<12}" + "  ".join(
            f"{LABELS[ax][k]} {100*(v==k).mean():.0f}%" for k in range(3)))
    print()
    for s, (n, txt) in describe(R).items():
        print(f"  state {s}: {n:>4} sessions   {txt}")
