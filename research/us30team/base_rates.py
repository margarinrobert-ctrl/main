"""Do ADX, ATR and EMA carry information on a US30 Donchian breakout bar in 07:00-11:00 New York,
or are they the trigger restated? The base rate is computed BEFORE any P&L, because on this branch
that two-line query has pre-empted whole studies eight times.

THE RECORD THIS IS TESTING AGAINST (CLAUDE.md, verbatim counts):
    RSI(14)>=55        passes  94.7% of breakout bars   lift 1.9-3.2x
    Aroon osc>=0       passes 100.0%                    lift 1.00x   (an identity: the breakout bar
                                                                      IS the N-bar high)
    MACD>0             passes  99.8-100.0%
    MFI(9)>=50         passes  91.7%
    EMA13>EMA48        passes  82.6%                    lift 2.24x
    close>EMA50        passes  93.7%
    %K vs session VWAP corr    0.831                    (the continuous form of the same query)
    ADX>=25            passes  55.6% against 50.0%      lift 1.11x   -- the weakest lift recorded,
                                                                      which is why ADX is the one
                                                                      family with a prior of being
                                                                      genuinely independent here.
A condition passing >95% of the trigger's own bars is flagged INERT: it cannot refuse a trade, so
it cannot carry information whatever its P&L reads.

THREE THINGS THIS BRANCH HAS LEARNED THE HARD WAY AND THAT ARE BUILT IN HERE RATHER THAN OPTIONAL.

1. A CAUSAL TIME-OF-DAY BASELINE, NEVER A TRAILING MEAN. `STUDY_VWAP_STOCH_ATR` measured an RTH bar
   clearing its own 50-bar trailing ATR mean 98.9% of the time against 25.1% overnight -- on a
   24-hour tape `atr / sma(atr, n)` is a clock, so every rung of it is inert on any session-
   restricted trigger. `tod_baseline` takes the mean at THIS minute-of-day over PRIOR sessions only,
   minimum 20 observations.

2. AN MA IS PRICED BY ITS DISTANCE, NOT BY THE CROSS. `STUDY_V40`: `(close - MA200)/ATR` in the top
   half of breakout bars was the ONLY survivor of 34 declared cells, while "close above the MA200"
   -- the base condition -- was worth nothing alone. So EMA200 enters here as a signed distance
   ladder in ATR units and `close > EMA200` is carried only as the degenerate rung of that ladder.

3. A FILTER IS A VETO, NOT A SUBSET. `STUDY_AUCTION`: refusing a signal releases the position lock
   and admits a LATER breakout the unfiltered run never saw, so a conditional split of realised
   trades answers a different question from the one a script asks. Every P&L number here filters
   the TRIGGERS and re-simulates end to end, and every control is a random gate of the SAME
   SELECTIVITY re-simulated the same way.

BOTH DIRECTIONS, ALWAYS. The ATR-state sign has moved SIX times on this branch (V28 bottom-fifth,
V63 expansion floors, V39 calm inverting, VWAP_STOCH ceilings, ...) and ADX has inverted repeatedly
(`STUDY_TURTLE_15M` used both gates INVERTED at 15m and they transferred; `STUDY_V52` found the same
two gates beaten by a random filter at 240m). So every ADX and ATR reading is declared as a FLOOR
and as a CEILING. Run both directions or run neither.

BLOCKS AND SPEND. All selection on A_research (US30L before 2023-01-01). ONE read of B_holdout and
ONE of C_forward (US30_ISO after 2025-07-16, a DIFFERENT PROVIDER), on cells named before either is
opened. A and B are heavily spent -- six studies have read them -- so C is the only genuinely
unread block and it is read last.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "us30scalp"))
sys.path.insert(0, os.path.join(ROOT, "research", "dl50"))
import s30core as S            # noqa: E402  walker with the 11:00 clock flatten
import d50core as D            # noqa: E402  Wilder's ADX returning BOTH DIs

COST = S.COST                  # 2.29 index points round turn
W0, W1, FLAT = S.W0, S.W1, S.FLAT

# Declared BEFORE any result is seen. `use_pts=1`, so these are absolute index points.
GEOMS = {"30/150": dict(stop_a=30.0, tgt_a=150.0),
         "50/150": dict(stop_a=50.0, tgt_a=150.0)}
WALK_KW = dict(hold=0, cost=COST, m0=W0, m1=W1, flat=FLAT, tie=0, use_pts=0)


# --------------------------------------------------------------- causal baselines -------------
def tod_baseline(v, mod, min_obs=20):
    """Mean of v at this minute-of-day over PRIOR sessions only (the current bar is excluded and
    contributes only to later bars). Returns NaN until `min_obs` prior observations exist."""
    out = np.full(len(v), np.nan)
    acc = {}
    for i in range(len(v)):
        m = int(mod[i])
        s, n = acc.get(m, (0.0, 0))
        if n >= min_obs:
            out[i] = s / n
        if np.isfinite(v[i]):
            acc[m] = (s + v[i], n + 1)
    return out


def _ema(x, span):
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def _cross_age(fast, slow, look):
    """Bars since the last bullish cross of `fast` over `slow`; True if it happened within `look`
    bars INCLUDING the current one. Causal by construction -- a cross at bar i is knowable at i."""
    up = (fast > slow)
    fresh = up & ~np.r_[False, up[:-1]]
    idx = np.flatnonzero(fresh)
    age = np.full(len(fast), np.inf)
    if len(idx):
        pos = np.searchsorted(idx, np.arange(len(fast)), side="right") - 1
        ok = pos >= 0
        age[ok] = np.arange(len(fast))[ok] - idx[pos[ok]]
    return age <= look


# --------------------------------------------------------------- the condition pool -----------
def build(f):
    """~23 declared conditions in three families, every one causal at the bar it is read on.
    Returns (DataFrame of boolean columns, DataFrame of the raw continuous values behind them)."""
    c = f["close"].to_numpy()
    at = f["atr"].to_numpy()
    mod = f["mod"].to_numpy()

    adx, pdi, ndi = D.adx(f, 14)
    atr_tod = at / tod_baseline(at, mod)
    atr_pct = pd.Series(at).rolling(250).rank(pct=True).to_numpy()
    e13, e34, e48, e89 = (_ema(c, n) for n in (13, 34, 48, 89))
    e200 = _ema(c, 200)
    d200 = (c - e200) / np.where(at > 0, at, np.nan)

    raw = pd.DataFrame(dict(adx=adx, pdi=pdi, ndi=ndi, di_gap=pdi - ndi,
                            atr_tod=atr_tod, atr_pct=atr_pct, d200=d200,
                            ema_gap=(e13 - e48) / np.where(at > 0, at, np.nan)), index=f.index)

    X = pd.DataFrame(index=f.index)
    # ---- ADX family, BOTH DIRECTIONS
    for k in (15, 20, 25, 30):
        X[f"adx>={k}"] = adx >= k
    for k in (20, 25):
        X[f"adx<={k}"] = adx <= k
    X["+DI>-DI"] = pdi > ndi
    X["-DI>+DI"] = ndi > pdi
    # ---- ATR family, BOTH DIRECTIONS. Expansion is vs the CAUSAL TIME-OF-DAY baseline.
    for k in (1.0, 1.2):
        X[f"atr/tod>={k}"] = atr_tod >= k
    for k in (1.0, 0.8):
        X[f"atr/tod<={k}"] = atr_tod <= k
    for k in (0.5, 0.8):
        X[f"atrpct250>={k}"] = atr_pct >= k
    for k in (0.5, 0.2):
        X[f"atrpct250<={k}"] = atr_pct <= k
    # ---- EMA family. The 200 enters as a DISTANCE ladder, not as a cross (STUDY_V40).
    X["ema13>48"] = e13 > e48
    X["ema13<48"] = e13 < e48
    X["ema13x48 fresh<=5"] = _cross_age(e13, e48, 5)
    X["ema13>34>89"] = (e13 > e34) & (e34 > e89)
    X["d_ema200>=0"] = d200 >= 0.0            # the degenerate rung: "close above the EMA200"
    X["d_ema200>=1.0"] = d200 >= 1.0
    X["d_ema200>=2.0"] = d200 >= 2.0
    X["d_ema200<=1.0"] = d200 <= 1.0          # the "not extended" ceiling, inverted in V52/TURTLE15
    return X.astype(bool), raw


def valid_mask(f, X, raw, warm=900):
    """Bars where every condition in the pool is defined. `warm` covers the EMA200 (span 200) and
    the 250-bar ATR percentile; the time-of-day baseline needs 20 prior sessions on top."""
    v = np.isfinite(raw[["adx", "atr_tod", "atr_pct", "d200", "ema_gap"]].to_numpy()).all(1)
    v &= np.isfinite(f["atr"].to_numpy()) & (f["atr"].to_numpy() > 0)
    v[:warm] = False
    v[-2:] = False
    return v


# --------------------------------------------------------------- the base-rate query ----------
INERT = 0.95


def base_rates(X, sig_mask, pop_mask):
    """Share of BREAKOUT bars passing, share of ALL in-window bars passing, and the LIFT. This is
    the query that runs before any P&L; a column at >=95% on the trigger's own bars is INERT."""
    rows = []
    for col in X.columns:
        v = X[col].to_numpy()
        p_sig = float(v[sig_mask].mean())
        p_pop = float(v[pop_mask].mean())
        rows.append(dict(cond=col, p_sig=p_sig, p_pop=p_pop,
                         lift=p_sig / max(p_pop, 1e-12), n_sig=int(v[sig_mask].sum()),
                         inert=p_sig >= INERT))
    return pd.DataFrame(rows)


def signal_bar_corr(X, sig_mask, thresh=0.90):
    """A filter only ever acts on the bars the base fires on, so the correlation that matters is
    the one restricted to those bars (STUDY_V40). This branch has caught its own pool duplicating
    SEVEN times, twice at rho EXACTLY 1.0000."""
    sub = X.loc[sig_mask].astype(float)
    keep = [c for c in sub.columns if sub[c].std() > 0]
    C = sub[keep].corr()
    dup = []
    for i, a in enumerate(keep):
        for b in keep[i + 1:]:
            r = C.loc[a, b]
            if abs(r) >= thresh:
                dup.append(dict(a=a, b=b, rho=float(r)))
    return C, pd.DataFrame(dup).sort_values("rho", key=np.abs, ascending=False) if dup else \
        pd.DataFrame(columns=["a", "b", "rho"])


# --------------------------------------------------------------- P&L as a VETO ----------------
def run_cell(f, sig, side, geom, **over):
    kw = dict(WALK_KW); kw.update(GEOMS[geom]); kw["use_pts"] = 1; kw.update(over)
    return S.walk(f, sig, side, **kw)


def mde(sd, n, alpha_z=2.802):
    """Minimum detectable effect at 80% power, two-sided 5%: z = 1.96 + 0.842 = 2.802."""
    return alpha_z * sd / np.sqrt(max(n, 1))


def score(t, label="", geom="30/150"):
    if not len(t):
        return dict(rule=label, geom=geom, n=0)
    p = t["pts"].to_numpy()
    stop, tgt = GEOMS[geom]["stop_a"], GEOMS[geom]["tgt_a"]
    be = (stop + COST) / (stop + tgt)      # driftless break-even for the two-outcome pair
    res = t[t.why.isin([0, 1])]
    return dict(rule=label, geom=geom, n=len(t), pts=float(p.mean()), sd=float(p.std(ddof=1)),
                mde=float(mde(p.std(ddof=1), len(p))), pf=S.pf(p), win=float((p > 0).mean()),
                be=float(be), res_win=float((res.why == 1).mean()) if len(res) else np.nan,
                amb=float(t["amb"].mean()), flat_sh=float((t.why == 3).mean()),
                tot=float(p.sum()))


def veto_control(f, sig, side, keep_n, geom, n_draw=400, seed=0):
    """A RANDOM GATE of the same selectivity: keep `keep_n` of the trigger's own signal bars at
    random and RE-SIMULATE end to end, so the position lock releases exactly as it does for the
    real gate. Returns the draw means in points."""
    rng = np.random.default_rng(seed)
    sig = np.asarray(sig); side = np.asarray(side)
    if keep_n < 5 or keep_n > len(sig):
        return np.array([])
    out = []
    for _ in range(n_draw):
        j = np.sort(rng.choice(len(sig), size=keep_n, replace=False))
        t = run_cell(f, sig[j], side[j], geom)
        if len(t) >= 5:
            out.append(t["pts"].mean())
    return np.asarray(out)


def pval(obs, draws):
    """One-sided: the share of same-selectivity random gates that do at least as well."""
    d = np.asarray(draws)
    d = d[np.isfinite(d)]
    return float((d >= obs).mean()) if len(d) else np.nan


# NOTE recorded here because it cost a run: `stack` is a DataFrame METHOD, so a column named
# `stack` makes `df.stack == "x"` evaluate to a scalar False and every mask built from it selects
# nothing -- silently, with no error. The drop-one table printed empty rows on the first pass for
# exactly that reason. Same class as `.first`, `.align` and `agg` already recorded on this branch.
# Column names used here are therefore checked against `dir(pd.DataFrame)` before use.
def shadow_check(cols):
    import pandas as _pd
    bad = [c for c in cols if hasattr(_pd.DataFrame, str(c))]
    return bad
