"""Does raising the TRADE RATE close the detectability gap on the section-12 rule?

`STUDY_US30_SCALP_0711` sections 10 and 12 left one number governing everything: the
minimum detectable effect is `2.802 * sd / sqrt(n)`, and the best-behaved arm
(`Donchian 20 long + adx<=20`, 50/150, 07:00-11:00 NY, flat at 11:00) delivers +6.26
points against an MDE of 10.26 on 400 trades -- it needs about 1,073.

Two axes can raise n.  Cross-market pooling is a separate workstream.  The axis here is
the ENTRY CHANNEL, which is the one parameter that changes the event RATE without
touching the mechanism, the geometry, the session or the cost.

This is a LADDER, not a search, and the distinction is the whole reason it is allowed.
Section 10 established that over 1,176 cells `E[max t | pure noise] = 3.301` already
exceeds the `t = 2.802` detection threshold, so no configuration selected from a space
that size could be believed.  Over SIX ordered rungs the same expression gives ~2.2,
below the threshold -- so a single declared axis is readable where a grid is not.  The
rungs are declared here, before any of them is run, and every one is reported.

Two questions, in order:

1.  POWER.  Does a shorter channel raise n faster than it dilutes the per-trade edge?
    The statistic is the t, not the points -- equivalently the ratio of the delivered
    effect to its own MDE.  If sd and edge were flat in the channel length, t would
    rise as sqrt(n) and the answer would be trivially yes.  They are not flat, so the
    question is empirical.

2.  REPLICATION.  `adx<=20` was found at channel 20 (12 of 12 cells across three blocks
    in the team's base-rate workstream).  If it is a mechanism it holds at every rung.
    If it is the one rung where a ceiling happened to help, it does not.  This is a
    replication of an already-declared finding, not a fresh selection.

Nothing here is permitted to pick a channel.  The output is a power table and a
replication table; a winner would be the max of six draws and is not read as one.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "us30scalp"))
import s10lib as L  # noqa: E402
import s30core as S  # noqa: E402

# ----- declared before any run -------------------------------------------------------
CHANNELS = [10, 15, 20, 30, 40, 55]
ARMS = [("base", []), ("+adx<=20", ["adx<=20"]), ("+ema align", ["ema align"])]
Z80 = L.Z80


def e_max_normal(n: int) -> float:
    """Expected maximum of n iid standard normals (Bailey / Lopez de Prado)."""
    from scipy.stats import norm
    g = 0.5772156649015329
    return (1 - g) * norm.ppf(1 - 1.0 / n) + g * norm.ppf(1 - 1.0 / (n * np.e))


def signals_ch(f, ch, conds, M=None):
    """Donchian `ch` long, in-window, with the declared condition masks applied."""
    s2, d2 = S.donchian(f, ch, 1)
    if M is None:
        M = L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    keep = np.ones(len(s2), bool)
    for c in conds:
        keep &= M[c][s2]
    return s2[keep], d2[keep]


def trades_ch(f, ch, conds, M=None, **over):
    sig, sd = signals_ch(f, ch, conds, M)
    if len(sig) < 5:
        return pd.DataFrame()
    kw = dict(L.KW)
    kw.update(over)
    return S.walk(f, sig, sd, **kw)


def years(f):
    return (f.index[-1] - f.index[0]).days / 365.25


def row(t, nsess, yrs):
    d = L.stats(t, nsess)
    if not d.get("n"):
        return dict(n=0)
    d["per_yr"] = d["n"] / yrs
    d["ratio"] = d["pts"] / d["mde"] if d["mde"] > 0 else np.nan
    # trades needed for the DELIVERED effect to be detectable at 80% power
    d["n_need"] = (Z80 * d["sd"] / d["pts"]) ** 2 if d["pts"] > 0 else np.nan
    d["yrs_need"] = d["n_need"] / d["per_yr"] if d["pts"] > 0 else np.nan
    return d


def jaccard(a, b):
    A, B = set(a.tolist()), set(b.tolist())
    return len(A & B) / len(A | B) if (A | B) else np.nan


def filter_control(f, base_sig, base_side, n_keep, n_draw=400, seed=0, **over):
    """Same-selectivity random FILTER, re-simulated as a VETO.

    The comparison a condition has to beat is not zero and not a random ENTRY -- it is a
    random gate that refuses the same share of the base's own signals.  `STUDY_AUCTION`:
    a filter is a veto, not a subset, because refusing a signal releases the position lock
    and admits a later one, so the draws must be re-walked rather than sampled out of the
    base's realised trades.  Draws are kept in chronological order so the lock rejects the
    same share (`STUDY_V59`).
    """
    if n_keep < 5 or n_keep >= len(base_sig):
        return None
    kw = dict(L.KW)
    kw.update(over)
    rng = np.random.default_rng(seed)
    out = np.empty(n_draw)
    for i in range(n_draw):
        idx = np.sort(rng.choice(len(base_sig), size=n_keep, replace=False))
        t = S.walk(f, base_sig[idx], base_side[idx], **kw)
        out[i] = t["pts"].mean() if len(t) else np.nan
    return out[np.isfinite(out)]


def pval(obs, null):
    """One-sided: share of the null at or above the observed value."""
    if null is None or not len(null):
        return np.nan
    return float((null >= obs).mean())
