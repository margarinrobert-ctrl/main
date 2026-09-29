"""Pool the 07:00-11:00 New York window across US30, US100 and NQ.

WHY THIS AND NOT ANOTHER SEARCH. `STUDY_US30_SCALP_0711` sections 8-11 settled that the obstacle
in this window is STATISTICAL POWER and not the rule: per-trade dispersion is 157.1 points on a
mean of +0.683, so the research block's minimum detectable effect at 80% power is 10.74 points a
trade, while PF 1.2 requires +10.61 and PF 1.5 requires +23.62. Anything worth trading IS
detectable and anything undetectable is NOT worth trading. Over 1,176 declared cells the best t
reached 1.348 against the 2.802 detectability demands and a search noise floor E[max t | noise] of
3.301. The single named next step was to POOL the window across the two other index feeds, which
triples the trade count and should take the MDE to roughly 6.2 points -- bringing PF 1.1 (+5.53)
inside the sample's resolution for the first time. This module executes that and nothing else.

THREE THINGS DECIDE WHETHER THE POWER GAIN IS REAL, and all three are measured here rather than
assumed.

  1. THE POOLING UNIT. Points are not comparable across markets. `STUDY_TURTLE_15M` charged NQ's
     1.72-point round turn in GOLD's points and reported PF 0.35 as a decisive failure. Every
     result here is pooled in ATR UNITS AT THE SIGNAL BAR and in PERCENT OF ENTRY PRICE, both
     reported, with each feed carrying its OWN cost model and its OWN ATR, and each feed's cost
     stated as a FRACTION OF THE STOP before anything is pooled.

  2. OVERLAP IS NOT INDEPENDENCE. `STUDY_TREND_LONG`: 68% of NQ's triggers fire on the EXACT SAME
     15-minute bar on US100, 79% within +-2 bars -- they are the same index on two feeds, so
     pooling them does not triple the effective sample. The trigger overlap matrix is computed
     BEFORE any p-value, on the CONTEMPORANEOUS span (which measures feed duplication) and again
     inside the pooled research sample (which is what actually sets the power).

  3. THE STANDARD ERROR MUST NOT ASSUME INDEPENDENCE. Trades on the same DATE in different markets
     are correlated, and trades within one session are correlated with each other
     (`research/edgelab`: bar-wise scoring made 17,121 of 27,786 tests "pass"). Every pooled
     standard error here is CLUSTERED BY CALENDAR DATE ACROSS ALL THREE MARKETS, so a day on which
     all three fire counts once, not three times. The effective sample size is then read off as
     (sd / SE_clustered)^2 and the MDE is computed from the clustered SE -- never from sqrt(n).

BLOCKS. Each market keeps its OWN research/holdout split at its own first ~70% of sessions, because
their spans barely overlap: US30L and US100L run 2016-2025 while NQ_1m begins 2022-12-26, so NQ's
whole history sits inside the other two's holdout calendar. That is reported as a finding rather
than hidden -- a pooled "research block" here is three market-specific blocks, not one calendar.

CLOCKS. US30_LONG_15m and US100_LONG_15m are broker-stamped New York + 7 (`v38feeds` shifts them).
`NQ_1m` IS STAMPED IN UTC and every other feed on this branch is already New York -- a loader that
forgets to convert puts a 09:30 window at 04:30, which has bitten this branch before. All three
clocks are RE-DERIVED here (mean bar range must peak at minute-of-day 570 = 09:30 New York) and the
check is printed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "mr30"))
sys.path.insert(0, os.path.join(ROOT, "research", "us30scalp"))

import s30core as S            # noqa: E402  the verified walker, clock flatten, matched control
from v38 import v38feeds as F  # noqa: E402
import nqdata                  # noqa: E402

W0, W1, FLAT = S.W0, S.W1, S.FLAT           # 420 .. 660, flat at the 11:00 OPEN

# The branch's per-market all-in round turn in INDEX POINTS, and the point value.
# `research/linreg/lrcore.py`, `research/mathmodels/mmcore.py` carry the same table.
COST = {"US30": 2.29, "US100": 1.215, "NQ": 1.72}
PV = {"US30": 5.0, "US100": 2.0, "NQ": 2.0}
MARKETS = ("US30", "US100", "NQ")

# Each market's own research cut -- its own first ~70% of SESSIONS, computed in `load_all`.
RESEARCH_FRAC = 0.70


# ------------------------------------------------------------------ loading -------------------
def _atr_mod(f):
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = (f.index.hour * 60 + f.index.minute).to_numpy()
    return f


def load_nq(tf=15):
    """NQ_1m is UTC-stamped. `nqdata.load_bars` converts to New York; the tz is then dropped so the
    index is naive New York wall clock, exactly like the two broker feeds."""
    d = nqdata.load_bars(os.path.join(ROOT, "data/NQ_1m.csv"))
    d.index = d.index.tz_localize(None)
    f = d[["open", "high", "low", "close", "volume"]].resample(f"{tf}min").agg(
        dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()
    return f


def load_all(tf=15):
    """Three feeds at `tf` minutes, naive New York, with ATR(14) and minute-of-day."""
    out = {}
    out["US30"] = _atr_mod(F.resample(F.load("US30L"), tf))
    out["US100"] = _atr_mod(F.resample(F.load("US100L"), tf))
    out["NQ"] = _atr_mod(load_nq(tf))
    return out


def split(f, frac=RESEARCH_FRAC):
    """Research = the market's own first `frac` of SESSIONS (dates), holdout = the rest."""
    days = np.unique(f.index.normalize().to_numpy())
    cut = days[int(len(days) * frac)]
    ix = f.index.normalize().to_numpy() < cut
    return dict(research=ix, holdout=~ix), pd.Timestamp(cut)


# ------------------------------------------------------------------ clock check ---------------
def clock_check(f, name):
    """Mean bar range by minute-of-day must peak at 570 = 09:30 New York. This is the branch's
    standing positive control for a feed's offset and it is re-run rather than inherited."""
    r = pd.Series(f["high"].to_numpy() - f["low"].to_numpy()).groupby(f["mod"].to_numpy()).mean()
    peak = int(r.idxmax())
    return dict(market=name, peak_mod=peak, peak_hhmm=f"{peak // 60:02d}:{peak % 60:02d}",
                ok=(peak == 570), peak_range=float(r.max()),
                rth_over_on=float(r.loc[570] / r.loc[r.index < 420].mean()))


# ------------------------------------------------------------------ triggers ------------------
def donchian(f, n, side=1):
    return S.donchian(f, n, side)


def eligible(f, mask=None):
    """The bars a matched control may draw from: in window, finite ATR, not the last two bars."""
    ok = np.isfinite(f["atr"].to_numpy()) & (f["atr"].to_numpy() > 0)
    ok &= (f["mod"].to_numpy() >= W0) & (f["mod"].to_numpy() < W1)
    ok[:60] = False
    ok[-2:] = False
    if mask is not None:
        ok &= mask
    return ok


# ------------------------------------------------------------------ the walk ------------------
def run(f, sig, side, stop, tgt, hold=0, cost=2.29, use_pts=1, tie=1, block=None):
    """`s30core.walk` with the clock flatten ON and the ambiguous share carried through, plus the
    two POOLING UNITS attached: `atr_u` = points / ATR at the SIGNAL bar (scale-free and immune to
    the synthetic-level caveat) and `pct` = percent of entry price (which is NOT immune, see the
    NQ deflator note in the study)."""
    if block is not None:
        sig_m = block[sig]
        sig, side = sig[sig_m], side[sig_m]
    if len(sig) < 3:
        return pd.DataFrame()
    t = S.walk(f, sig, side, stop_a=stop, tgt_a=tgt, hold=hold, cost=cost,
               m0=W0, m1=W1, flat=FLAT, tie=tie, use_pts=use_pts)
    if not len(t):
        return t
    at = f["atr"].to_numpy()
    t["atr_sig"] = at[t.e_bar.to_numpy() - 1]
    t["atr_u"] = t.pts / t.atr_sig
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t


NO_TARGET = 1e9      # "no target" as a barrier that can never be reached


# ------------------------------------------------------------------ statistics ----------------
def cluster_se(vals, dates):
    """Standard error of the mean CLUSTERED BY DATE. Trades on one date -- in one market or across
    three -- move together, so a naive sqrt(n) understates the error. This is the only standard
    error used for anything pooled."""
    v = np.asarray(vals, float)
    d = np.asarray(dates)
    ok = np.isfinite(v)
    v, d = v[ok], d[ok]
    n = len(v)
    if n < 5:
        return np.nan, np.nan, 0
    mu = v.mean()
    df = pd.DataFrame(dict(v=v - mu, d=d))
    g = df.groupby("d")["v"].sum().to_numpy()          # cluster sums of centred values
    var = (g ** 2).sum() / (n ** 2)                    # cluster-robust variance of the mean
    se = float(np.sqrt(max(var, 0.0)))
    sd = float(v.std(ddof=1))
    n_eff = float((sd / se) ** 2) if se > 0 else np.nan
    return se, n_eff, len(np.unique(d))


def mde(se, power=0.80, alpha=0.05):
    """Minimum detectable effect at `power`, two-sided. z(1-a/2) + z(power) = 1.960 + 0.842."""
    from math import sqrt
    try:
        from scipy.stats import norm
        z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    except Exception:
        z = 1.959964 + 0.841621
    return float(z * se), float(z)


def breakeven(stop, tgt, cost):
    """Driftless break-even win rate for a two-outcome barrier pair, all in the same unit."""
    if not np.isfinite(tgt) or tgt >= NO_TARGET / 10:
        return np.nan
    return (stop + cost) / (stop + tgt)


def pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return np.nan
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12))


def sharpe_sessions(t, f, block, col="atr_u"):
    """Sharpe ZERO-FILLED over EVERY session in the block, not over traded days only
    (`STUDY_V17`: over traded days a filter is PAID for trading less)."""
    days = pd.DatetimeIndex(f.index[block]).normalize().unique()
    if not len(days) or not len(t):
        return np.nan
    s = t.groupby("date")[col].sum().reindex(days, fill_value=0.0).to_numpy()
    return float(s.mean() / s.std(ddof=1) * np.sqrt(252)) if s.std(ddof=1) > 0 else np.nan


def summarise(t, label="", unit="atr_u"):
    if t is None or not len(t):
        return dict(cell=label, n=0)
    v = t[unit].to_numpy()
    se, n_eff, nd = cluster_se(v, t["date"].to_numpy())
    m, _ = mde(se)
    return dict(cell=label, n=len(t), days=nd, mean=float(v.mean()), sd=float(v.std(ddof=1)),
                se=se, n_eff=n_eff, t=float(v.mean() / se) if se > 0 else np.nan,
                mde80=m, inside=bool(abs(v.mean()) >= m) if np.isfinite(m) else False,
                pf=pf(v), win=float((v > 0).mean()), med_min=float(t["mins"].median()),
                amb=float(t["amb"].mean()))


# ------------------------------------------------------------------ the declared grid ---------
# 27 cells per market per parameterisation. Donchian long only -- `STUDY_US30_SCALP_0711` S3 found
# shorts lose to their controls in every short cell while longs beat theirs in 8 of 9, which is
# drift and not a signal, and the brief declares the long side.
DONCH = (10, 20, 40)
STOP_PTS = (30, 50, 100)
TGT_PTS = (100, 150, NO_TARGET)
# The SAME distances as ATR multiples, fixed on US30's research median ATR of 31.00 points, so the
# GEOMETRY is matched across markets rather than the point count. `STUDY_DL50`: the two
# parameterisations disagree, because a fixed point distance is a different geometry in 2016 than
# in 2025 -- and across markets it is a different geometry outright (30 points is 0.97N on US30 and
# 2.20N on US100).
ATR30 = 31.0045
STOP_ATR = tuple(round(s / ATR30, 4) for s in STOP_PTS)
TGT_ATR = tuple(round(t / ATR30, 4) if t < NO_TARGET / 10 else NO_TARGET for t in TGT_PTS)


def grid(param="atr"):
    st = STOP_PTS if param == "pts" else STOP_ATR
    tg = TGT_PTS if param == "pts" else TGT_ATR
    return [dict(don=d, stop=s, tgt=t, param=param)
            for d in DONCH for s in st for t in tg]


def cell_name(c):
    t = "none" if c["tgt"] >= NO_TARGET / 10 else f"{c['tgt']:g}"
    u = "pts" if c["param"] == "pts" else "N"
    return f"don{c['don']} {c['stop']:g}{u}/{t}{'' if t == 'none' else u}"


def control_draws(f, n_target, side_arr, elig, cell, cost, n_draw=200, seed=0, block=None):
    """Matched random ENTRY, SORTED so the position lock rejects the same share (`STUDY_V59`:
    unsorted draws exploded the null's spread and made everything fail). Returns, per draw, the SUM
    and COUNT of the outcome in each unit, so draws can be POOLED ACROSS MARKETS draw-for-draw
    rather than averaged after the fact."""
    rng = np.random.default_rng(seed)
    pool_ix = np.flatnonzero(elig if block is None else (elig & block))
    if len(pool_ix) < n_target or n_target < 5:
        return None
    use_pts = 1 if cell["param"] == "pts" else 0
    out = np.zeros((n_draw, 5))
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool_ix, size=n_target, replace=False))
        sd = rng.permutation(side_arr)[:len(pick)]
        t = run(f, pick, sd, cell["stop"], cell["tgt"], cost=cost, use_pts=use_pts)
        if t is None or not len(t):
            continue
        out[i] = (t["atr_u"].sum(), t["pct"].sum(), t["pts"].sum(), len(t), (t.pts > 0).sum())
    return out
