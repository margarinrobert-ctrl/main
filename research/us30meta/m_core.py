"""THE META LAYER ON THE SECTION-12 US30 PRIMARY -- and only the meta layer.

THE PRIMARY IS FIXED AND NOTHING HERE CAN CHANGE IT. `research/us30scalp/s10lib.py`: Donchian 20
long, US30 07:00-11:00 New York, flat at the 11:00 OPEN, 50-point stop / 150-point target, arms
`base` / `+adx<=20` / `+ema align` / `+both` (and `conventional` kept as the arm that must lose).
That rule EMITS EVENTS. Everything in this package SCORES those events and nothing in it can create
one. A feature layer that can also fire a trade will always find something, and the thing it finds
is the maximum of the search.

PHASE 0 -- WHAT IS BEING CLAIMED, WRITTEN BEFORE THE CODE.
  The primary is a fitted pattern, not a mechanism: `STUDY_US30_SCALP_0711` section 12 derived it
  from three component readings (ADX inverted, EMA alignment carrying, ATR at chance) rather than
  from a named counterparty. So it carries the FULL deflation burden and no story protects it.
  What the meta layer is allowed to claim is narrower: that some causal state of the market at the
  SIGNAL BAR separates the breakouts worth taking from the ones that are not. If that is true the
  separation must survive a same-selectivity random gate; if it is only true where it was fitted it
  is the search.

THE HARD CONSTRAINT, AND IT IS THE POINT OF THIS WORKSTREAM. `STUDY_US30_SCALP_0711` sections 9
and 13: per-trade dispersion on this primary is 73.2 points on 400 research trades, so the MINIMUM
DETECTABLE EFFECT at 80% power is 10.26 points a trade, PF 1.2 requires +10.61, and every one of
the thirty cells in the section-13 battery is INSIDE its own MDE. A filter that raises profit
factor by REMOVING trades raises the MDE at the same time. So `mde()` is printed beside every
uplift in this package and the verdict states plainly whether the number is inside it.

TWO EVENT STREAMS, AND THEY ANSWER DIFFERENT QUESTIONS.
  LOCKED   -- what one account actually takes: `s10lib.trades`, one live position, later signals
              swallowed while a trade is open. This is the ONLY stream Gate 1 and Gate 2 score.
  UNLOCKED -- every eligible signal bar labelled with the points it would have earned under the
              identical geometry, with no position lock. `STUDY_S3_NEURAL_NET`: the lock decides
              which events one account can ACT on, not which have a well-defined outcome, and
              training on 400 locked rows against 50 features is fitting noise.
              `STUDY_CONFORMAL` did the same thing from the other side -- train on the family,
              score the cell. The strategy still runs LOCKED at inference and every reported
              number is a locked number.

WHAT THE BRANCH ALREADY KNOWS AND THIS FILE DOES NOT RE-DISCOVER.
  `STUDY_V27_HMM`   the standard HMM read is a TWO-SIDED filter: fit-on-all + smoothed decode gave
                    locked PF 1.351 where the causal version of the SAME model and rule gave 0.973,
                    with nearly identical TRADE COUNTS -- the leak is invisible in the count. Both
                    fixes are mandatory: parameters from a block ending before the labelled bar,
                    and the FILTERED posterior. Filtered-vs-smoothed agreement runs 96-97% here,
                    which is exactly why it is easy to miss, so it is reported as a diagnostic.
  `STUDY_V67`       an HMM's states ARE volatility states (p_side vs realised vol -0.478) and the
                    Markov apparatus collapses to the state label (Jaccard 0.9757 on a signal with
                    25,044 distinct values). Both are measured here before the HMM is credited.
  `STUDY_V66_DL_META` feature engineering has been SUBTRACTIVE five times: 65 features scored IC
                    0.0983, seven volatility features 0.1407, one Parkinson estimator 0.1501. The
                    seeded family ablation is run expecting the answer "delete most of the inputs".
  `STUDY_AUCTION`   a conditional split of realised trades is NOT a filter test. Filter the
                    TRIGGERS and re-simulate -- refusing a trade frees the position lock and admits
                    a later breakout the ungated run never saw. Gate 2 is a VETO here, scored
                    against a random gate of the same selectivity, also re-simulated.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "research"), os.path.join(ROOT, "research/us30scalp"),
          os.path.join(ROOT, "research/mr30")):
    if p not in sys.path:
        sys.path.insert(0, p)

import s30core as S       # noqa: E402
import s10lib as L        # noqa: E402

Z80 = 2.802               # two-sided 5% + 80% power
OUT = os.path.join(ROOT, "results/us30meta")
os.makedirs(OUT, exist_ok=True)

FEEDS = (("US30L", ("A_research", "B_holdout")), ("US30I", ("C_forward",)))

# ------------------------------------------------------------------ arms -----------------------
# `s10lib.ARMS` is the fixed section-12 set and is NOT edited here. One arm is ADDED, on the
# coordinator's measurement in `research/us30rate/` (STUDY_US30_SCALP_0711 sections 14-15): over six
# declared channel rungs x three blocks, `+adx<=20` beats its own same-selectivity random veto in 15
# of 18 cells but only 3 of 6 on the RESERVED forward feed (median p 0.617), while `+ema align` is
# 18 of 18 including 6/6 forward -- and the EMA stack DECOMPOSES: `ema34>ema89` alone is 3/3 blocks
# at the best p in that table (0.030) while `ema13>ema34` alone is 9/18 at median p 0.575 with mean
# PF exactly 1.000. So the slow half is the condition and the 13-EMA is free. A meta layer measured
# on top of an arm that fails the reserved block inherits that failure, so the uplift is reported
# over BOTH and the slow-EMA arm is the one the verdict is written about.
ARM_CONDS = dict(L.ARMS)
ARM_CONDS["+ema34>89"] = ["ema34>89"]


def masks(f):
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    M = L.build_masks(h, l, c)
    M["ema34>89"] = L.ema(c, 34) > L.ema(c, 89)
    return M


# ------------------------------------------------------------------ detectability --------------
def mde(sd, n):
    """Minimum detectable effect at 80% power, in the units of `sd`. The number that decides
    whether an uplift is an improvement or a story."""
    return Z80 * sd / np.sqrt(max(n, 1)) if n > 1 else np.nan


def mde_split(a, b):
    """Two-sample MDE for KEPT vs REJECTED -- disjoint sets, so this is the honest resolution of
    a gate's separation. (Kept vs base is not: kept is a subset of base.)"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return np.nan
    return Z80 * np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))


def pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan


# ------------------------------------------------------------------ the two streams -------------
@njit(cache=True)
def _label_unlocked(o, h, l, c, mod, day, sig, stop_p, tgt_p, cost, flat):
    """Every signal bar labelled independently -- NO position lock. Same geometry, same clock
    flatten filling at the open of the first bar at or after `flat`, same refusal of a fill that
    would land at or after the bell. Used for TRAINING ONLY."""
    n = len(c)
    m = len(sig)
    eb = np.full(m, -1, np.int64)
    xb = np.full(m, -1, np.int64)
    pts = np.zeros(m)
    why = np.zeros(m, np.int64)
    amb = np.zeros(m, np.int64)
    cnt = 0
    for q in range(m):
        i = sig[q]
        if i + 1 >= n:
            continue
        j = i + 1
        if mod[j] >= flat or day[j] != day[i]:
            continue
        ent = o[j]
        stop = ent - stop_p
        targ = ent + tgt_p
        x = -1
        px = 0.0
        w = 2
        a = 0
        for t in range(j, n):
            if mod[t] >= flat or day[t] != day[j]:
                x = t; px = o[t]; w = 3
                break
            hs = l[t] <= stop
            ht = h[t] >= targ
            if hs and ht:
                a = 1
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = targ; w = 1
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[cnt] = j; xb[cnt] = x
        pts[cnt] = px - ent - cost
        why[cnt] = w; amb[cnt] = a
        cnt += 1
    return eb[:cnt], xb[:cnt], pts[:cnt], why[:cnt], amb[:cnt], sig[:cnt]


def arm_signals(f, arm, M=None, gate=None):
    """Signal BARS for one arm, optionally vetoed by a per-bar boolean `gate`."""
    conds = ARM_CONDS[arm]
    sig, side = L.signals(f, conds, bm=None, M=M)
    if gate is not None:
        sig, side = sig[gate[sig]], side[gate[sig]]
    return sig, side


def locked(f, arm, M=None, gate=None, blk=None):
    """The LOCKED trade table -- one live position, exactly what the account takes."""
    sig, side = arm_signals(f, arm, M=M, gate=gate)
    if blk is not None:
        keep = np.isin(sig, np.flatnonzero(blk))
        sig, side = sig[keep], side[keep]
    if len(sig) < 5:
        return pd.DataFrame()
    return S.walk(f, sig, side, **L.KW)


def unlocked(f, arm, M=None):
    """Every eligible signal bar labelled -- the TRAINING set. Never used to score anything."""
    sig, _ = arm_signals(f, arm, M=M)
    mod = f["mod"].to_numpy().astype(np.int64)
    inwin = (mod >= S.W0) & (mod < S.W1)
    at = f["atr"].to_numpy()
    ok = inwin[sig] & np.isfinite(at[sig]) & (at[sig] > 0)
    sig = sig[ok].astype(np.int64)
    day = f.index.normalize().astype(np.int64).to_numpy()
    eb, xb, pts, why, amb, sb = _label_unlocked(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        mod, day, sig, float(L.KW["stop_a"]), float(L.KW["tgt_a"]), S.COST, int(L.KW["flat"]))
    t = pd.DataFrame(dict(sig_bar=sb, e_bar=eb, x_bar=xb, pts=pts, why=why, amb=amb))
    t["ts"] = f.index[sb]
    t["day"] = t.ts.dt.normalize()
    t["R"] = t.pts / float(L.KW["stop_a"])
    return t


# ------------------------------------------------------------------ nulls ------------------------
def random_gate_control(f, arm, n_keep, M=None, blk=None, n_draw=400, seed=0):
    """A random gate of the SAME SELECTIVITY, re-simulated end to end. Not a subset of realised
    trades: the draw picks signal BARS, the walker is re-run, and the position lock is re-applied
    in the null exactly as it is in the rule (`STUDY_AUCTION`, `STUDY_XAU_CVD_FEATURES`)."""
    sig, side = arm_signals(f, arm, M=M)
    if blk is not None:
        keep = np.isin(sig, np.flatnonzero(blk))
        sig, side = sig[keep], side[keep]
    if n_keep < 5 or n_keep > len(sig):
        return None, None
    rng = np.random.default_rng(seed)
    means, ns = np.full(n_draw, np.nan), np.zeros(n_draw)
    for i in range(n_draw):
        pick = np.sort(rng.choice(len(sig), size=n_keep, replace=False))
        t = S.walk(f, sig[pick], side[pick], **L.KW)
        if len(t):
            means[i] = t["pts"].mean()
            ns[i] = len(t)
    m = np.isfinite(means)
    return means[m], ns[m]


def matched_entry_control(f, arm, n_target, M=None, blk=None, n_draw=400, seed=0):
    """Gate 1's null: the same number of entries drawn from every eligible in-window bar, SORTED
    so the lock rejects the same share (`STUDY_V59`)."""
    mod = f["mod"].to_numpy()
    at = f["atr"].to_numpy()
    elig = (mod >= S.W0) & (mod < S.W1) & np.isfinite(at) & (at > 0)
    elig[:120] = False
    elig[-3:] = False
    if blk is not None:
        elig &= blk
    return S.control(f, n_target, np.ones(n_target, np.int64), elig,
                     n_draw=n_draw, seed=seed, **L.KW)


def day_bootstrap(pts, days, n=2000, seed=0, base=None):
    """Day-block bootstrap: resample whole SESSIONS with their trades attached."""
    rng = np.random.default_rng(seed)
    ud = np.unique(days)
    idx = {d: np.flatnonzero(days == d) for d in ud}
    out = np.full(n, np.nan)
    for j in range(n):
        pick = rng.choice(ud, len(ud), replace=True)
        sel = np.concatenate([idx[d] for d in pick])
        if len(sel):
            out[j] = pts[sel].mean()
    out = out[np.isfinite(out)]
    if base is None:
        return out, float(np.mean(out <= 0))
    return out, float(np.mean(out <= base))


def line(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118, flush=True)
