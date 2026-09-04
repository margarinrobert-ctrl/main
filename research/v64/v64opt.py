"""V64 -- Optuna (TPE) on the V61 CVD rule, over a CONTINUOUS space the grid could not reach.

WHY THIS IS NOT A REPEAT OF V61. `STUDY_V61_CVD_OPTIMISED` already searched 725,760 EFFECTIVE
cells of the discrete space exhaustively. An exhaustive search cannot be beaten by a sampler on
the SAME space -- a sampler can only find the same maximum with fewer evaluations -- and that
search's own verdict was that its top rows do not transfer: corr(research, locked) = -0.026
Pearson over 1,223,943 cells, top 1% of research cells -0.0017 on locked against the whole
population's +0.0508. So a TPE study is only worth running if it asks something the grid could
not, and there are exactly three such questions:

  1. THE CONTINUUM. The grid quantised every axis -- stop to {1.5, 2.0, 2.5, 3.0}, channels to
     five values, k and w to a handful. Optuna searches stop on [1.0, 4.0], both channels over
     every integer in [10, 80], the MA200 floor and the CHOP ceiling continuously. If a better
     cell exists BETWEEN the grid's rungs, this is what finds it.
  2. THE OBJECTIVE. The grid maximised research return and that is exactly what failed. Here the
     SAME space is searched three times under three objectives -- research return, the MEDIAN of
     eight walk-forward folds (`STUDY_V42`'s objective), and a two-objective Pareto front of
     return against drawdown -- so the question "does a transfer-aware objective transfer better"
     is answered by measurement instead of assertion.
  3. IMPORTANCE. fANOVA over the trial population says which axes MOVE the objective. That is a
     different and more durable question than which cell is on top, and the grid answered it only
     through one-axis marginals that cannot see interactions.

GUARD RAILS, unchanged from the rest of this branch. Every study samples and scores on the
RESEARCH block only. The locked block is read ONCE, for a set of finalists declared before the
read, with the trial count stated. The V30 surrogate test is run by holding out a WHOLE AXIS
VALUE rather than random rows, because a dense sample makes random-row CV interpolation.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v53", "research/v54", "research/v56", "research/v61"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import v61core as V  # noqa: E402

CH_MIN, CH_MAX = 10, 80
K_MIN, K_MAX = 2, 6


def build(tf):
    """V61's own build, plus the continuous-space precomputes."""
    D = V.build(tf)
    h, l, c = D["h"], D["l"], D["c"]
    sh = pd.Series(h)
    sl = pd.Series(l)
    D["ent_all"] = np.vstack([sh.rolling(n).max().shift(1).to_numpy()
                              for n in range(CH_MIN, CH_MAX + 1)])
    D["exl_all"] = np.vstack([sl.rolling(n).min().shift(1).to_numpy()
                              for n in range(CH_MIN, CH_MAX + 1)])
    import v53abs as A
    import v54cvd as C
    # the grid stopped at k=5; the continuum needs every k in range, built the same way
    D["pat_all"] = {k: (D["pats"][k][0] if k in D["pats"]
                        else C.patterns(h, l, D["cv"], k, D["n"])[0])
                    for k in range(K_MIN, K_MAX + 1)}
    D["recent"] = A.recent
    # `calm` and the prior-session-high test, exactly as `run_tf` forms them
    v = D["vpct"]
    calm = np.zeros(D["n"], np.bool_)
    calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
    D["calm"] = calm
    D["psh_ok"] = np.isfinite(D["psh"]) & (c > D["psh"])
    # V61's tensor drops the last max(HOLDS)+5 bars so no config is scored on trades that cannot
    # complete. Keeping that cutoff FIXED at the search space's maximum hold is what makes trials
    # comparable to each other and to the published grid -- a per-config cutoff would let a short
    # hold buy extra sample.
    D["last_bar"] = D["n"] - (max(V.HOLDS) + 5)
    return D


@njit(cache=True)
def _walk(o, h, l, c, atr, calm, ent_hi, ex_lo, gate, ma_d, chop, psh_ok, cut,
          stop_hi, stop_lo, tp, hold, use_ma, ma_thr, use_chop, chop_thr, use_psh,
          cost, slip, last_bar):
    """One configuration, one pass, with the position lock. Returns per-trade R, %, block, exit
    bar. The exit logic is byte-for-byte V61's `_tensor` so the two are comparable."""
    m = len(c)
    n_max = 4000
    R = np.full(n_max, np.nan)
    pct = np.full(n_max, np.nan)
    blk = np.zeros(n_max, np.int64)
    sig = np.zeros(n_max, np.int64)
    cnt = 0
    busy = -1
    for i in range(1000, last_bar):
        if i <= busy:
            continue
        a = i + 1
        anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        if not np.isfinite(ent_hi[i]) or h[i] <= ent_hi[i]:
            continue
        if not gate[i]:
            continue
        if use_ma == 1 and (not np.isfinite(ma_d[i]) or ma_d[i] < ma_thr):
            continue
        if use_chop == 1 and (not np.isfinite(chop[i]) or chop[i] > chop_thr):
            continue
        if use_psh == 1 and not psh_ok[i]:
            continue
        px = o[a] + slip
        mult = stop_hi if calm[i] else stop_lo
        risk = mult * anchor
        if risk <= 0.0:
            continue
        fixed = px - risk
        tgt = px + tp * anchor if tp > 0.0 else 1e18
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan
        j = a
        while j <= end:
            lvl = fixed
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cap = c[j - 1]
            if np.isfinite(cap) and lvl > cap:
                lvl = cap
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            if h[j] >= tgt:
                out = (tgt if o[j] < tgt else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            j = end
            out = c[j] - slip
        if cnt < n_max:
            R[cnt] = (out - px - cost) / risk
            pct[cnt] = 100.0 * (out - px - cost) / px
            blk[cnt] = 0 if i < cut else 1
            sig[cnt] = i
            cnt += 1
        busy = j
    return R[:cnt], pct[:cnt], blk[:cnt], sig[:cnt]


def evaluate(D, p, cost=None, slip=None):
    """One parameter dict -> per-trade arrays. `p` uses continuous / integer axes."""
    ei = int(np.clip(p["ent"], CH_MIN, CH_MAX)) - CH_MIN
    xi = int(np.clip(p["exN"], CH_MIN, CH_MAX)) - CH_MIN
    if p["k"] > 0:
        es = D["pat_all"][int(p["k"])]
        gate = D["recent"](es, int(p["w"]))
    else:
        gate = np.ones(D["n"], bool)
    stop = float(p["stop"])
    return _walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"],
                 D["ent_all"][ei], D["exl_all"][xi], gate,
                 D["d_ma"], D["chop"], D["psh_ok"], int(D["cut"]),
                 stop, stop - 1.0 if p["adapt"] else stop, float(p["tp"]), int(p["hold"]),
                 1 if p["use_ma"] else 0, float(p["ma_thr"]),
                 1 if p["use_chop"] else 0, float(p["chop_thr"]),
                 1 if p["psh"] else 0,
                 V.COST if cost is None else float(cost),
                 V.SLIP if slip is None else float(slip), int(D["last_bar"]))


@njit(cache=True)
def _walk_at(o, h, l, c, atr, calm, ex_lo, bars, stop_hi, stop_lo, tp, hold, cost, slip,
             last_bar):
    """The SAME exit machine, entered at a supplied list of bars with no entry condition.
    This is the matched control: identical stop, target, channel exit, clock and position lock,
    so the only thing that differs from the rule is WHICH bar the trade starts on."""
    m = len(c)
    n = len(bars)
    pct = np.full(n, np.nan)
    cnt = 0
    busy = -1
    for z in range(n):
        i = bars[z]
        if i <= busy or i < 1000 or i >= last_bar:
            continue
        a = i + 1
        anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        px = o[a] + slip
        mult = stop_hi if calm[i] else stop_lo
        risk = mult * anchor
        if risk <= 0.0:
            continue
        fixed = px - risk
        tgt = px + tp * anchor if tp > 0.0 else 1e18
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan
        j = a
        while j <= end:
            lvl = fixed
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cap = c[j - 1]
            if np.isfinite(cap) and lvl > cap:
                lvl = cap
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            if h[j] >= tgt:
                out = (tgt if o[j] < tgt else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            j = end
            out = c[j] - slip
        pct[cnt] = 100.0 * (out - px - cost) / px
        cnt += 1
        busy = j
    return pct[:cnt]


def evaluate_at(D, p, bars):
    """Matched control: the rule's geometry, someone else's entry bars."""
    xi = int(np.clip(p["exN"], CH_MIN, CH_MAX)) - CH_MIN
    stop = float(p["stop"])
    return _walk_at(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["exl_all"][xi],
                    np.asarray(bars, np.int64), stop, stop - 1.0 if p["adapt"] else stop,
                    float(p["tp"]), int(p["hold"]), V.COST, V.SLIP, int(D["last_bar"]))


# ------------------------------------------------------------------ perturbation support
def _wilder_tr(o, h, l, c, nn=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / nn, adjust=False).mean().to_numpy()


def perturb_bars(D, sigma_ticks, rng, tick=0.25):
    """Jitter every bar's OHLC and repair it so a jittered bar is still a bar.

    The noise is independent on o/h/l/c, then high is set to the maximum of the four and low to
    the minimum. This is a DATA-INTEGRITY perturbation: because the indicators are recomputed FROM
    the jittered bars it moves the SIGNAL as well as the fill, which a P&L-only jitter cannot do.
    """
    n = D["n"]
    o = D["o"] + rng.normal(0.0, sigma_ticks * tick, n)
    h = D["h"] + rng.normal(0.0, sigma_ticks * tick, n)
    l = D["l"] + rng.normal(0.0, sigma_ticks * tick, n)
    c = D["c"] + rng.normal(0.0, sigma_ticks * tick, n)
    hi = np.maximum(np.maximum(o, c), np.maximum(h, l))
    lo = np.minimum(np.minimum(o, c), np.minimum(h, l))
    return o, hi, lo, c


def evaluate_perturbed(D, p, o, h, l, c, C_mod, cost=None, slip=None):
    """The same rule on jittered bars, recomputing only the series this configuration reads."""
    import v53abs as A
    n = len(c)
    atr = _wilder_tr(o, h, l, c)
    ent = pd.Series(h).rolling(int(p["ent"])).max().shift(1).to_numpy()
    exl = pd.Series(l).rolling(int(p["exN"])).min().shift(1).to_numpy()
    if p["k"] > 0:
        es = C_mod.patterns(h, l, D["cv"], int(p["k"]), n)[0]
        gate = A.recent(es, int(p["w"]))
    else:
        gate = np.ones(n, np.bool_)
    v = D["vpct"]
    calm = np.zeros(n, np.bool_)
    calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
    stop = float(p["stop"])
    return _walk(o, h, l, c, atr, calm, ent, exl, gate,
                 D["d_ma"], D["chop"], D["psh_ok"], int(D["cut"]),
                 stop, stop - 1.0 if p["adapt"] else stop, float(p["tp"]), int(p["hold"]),
                 0, 0.0, 0, 99.0, 0,
                 V.COST if cost is None else float(cost),
                 V.SLIP if slip is None else float(slip), int(D["last_bar"]))
