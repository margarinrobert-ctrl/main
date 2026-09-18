"""Cached-outcome scoring: the same numbers as `discover.score`, roughly 300x faster.

`labels.precompute` stores the outcome of a long entered at every eligible bar for one fixed
geometry. A condition's trades are then just that array indexed by the condition's bars, and a
minute-of-day matched control is a resample of the same array -- no simulation in the loop at all.
`assert_matches` checks the two paths agree trade for trade before any result is believed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _pools(P, block):
    """Valid bar indices grouped by minute of day, within a block."""
    ok = P["valid"] & np.asarray(block, bool)
    idx = np.flatnonzero(ok)
    mod = P["mod"][idx]
    order = np.argsort(mod, kind="stable")
    idx = idx[order]; mod = mod[order]
    uniq, start = np.unique(mod, return_index=True)
    ends = np.r_[start[1:], len(idx)]
    return {int(u): idx[s:e] for u, s, e in zip(uniq, start, ends)}


def score(P, mask, block, pools=None, draws=200, min_n=60, seed=11, rng=None):
    """Condition stats plus a minute-of-day matched control, all by indexing."""
    sel = np.flatnonzero(P["valid"] & np.asarray(mask, bool) & np.asarray(block, bool))
    if len(sel) < min_n:
        return None
    R = P["R"][sel]
    win = 100.0 * float((R > 0).mean()); mR = float(R.mean())
    pools = pools if pools is not None else _pools(P, block)
    mod = P["mod"][sel]
    counts = np.bincount(mod, minlength=1440)
    keys = [m for m in np.flatnonzero(counts) if m in pools]
    if not keys:
        return None
    rng = rng or np.random.default_rng(seed)
    W = np.empty(draws); E = np.empty(draws)
    for k in range(draws):
        parts = []
        for m in keys:
            pool = pools[m]; need = min(counts[m], len(pool))
            parts.append(pool[rng.integers(0, len(pool), need)])
        cR = P["R"][np.concatenate(parts)]
        W[k] = 100.0 * float((cR > 0).mean()); E[k] = float(cR.mean())
    losses = R[R <= 0]
    return dict(n=len(R), win=win, expR=mR,
                pf=float(R[R > 0].sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
                ctrl_win=float(W.mean()), ctrl_expR=float(E.mean()),
                excess=win - float(W.mean()), excess_R=mR - float(E.mean()),
                p_win=float((W >= win).mean()), p_R=float((E >= mR).mean()),
                ambig=100.0 * float(P["ambig"][sel].mean()),
                mfe=float(np.nanmean(P["mfe"][sel])), mae=float(np.nanmean(P["mae"][sel])),
                held=float(np.median(P["held"][sel])))


def sweep(P, conds, block, draws=120, min_n=60, seed=11, progress=None):
    pools = _pools(P, block)
    rng = np.random.default_rng(seed)
    rows = []
    for i, (name, m) in enumerate(conds.items()):
        s = score(P, m, block, pools=pools, draws=draws, min_n=min_n, rng=rng)
        if s:
            s["cond"] = name
            rows.append(s)
        if progress and (i + 1) % progress == 0:
            print(f"    {i+1}/{len(conds)}", flush=True)
    df = pd.DataFrame(rows)
    return df.sort_values("excess", ascending=False).reset_index(drop=True) if len(df) else df


def assert_matches(d, P, mask, block, stop_k, rr, max_hold, tol=1e-9):
    """The cached path must reproduce the direct simulation exactly."""
    from . import labels
    from .analysis import eligible
    idx = eligible(d, block & mask)
    direct = labels.label(d, idx, stop_k * d["atr"][idx], rr=rr, max_hold=max_hold)
    sel = np.flatnonzero(P["valid"] & mask & block)
    a = np.sort(direct["R"]); b = np.sort(P["R"][sel])
    assert len(a) == len(b), f"trade count differs: direct {len(a)} vs cached {len(b)}"
    md = float(np.max(np.abs(a - b)))
    assert md < tol, f"max |R| difference {md}"
    return len(a), md


# --------------------------------------------------------------------------- day-aware scoring
def day_index(d):
    import pandas as pd
    return pd.DatetimeIndex(d["idx"]).normalize().values.astype("datetime64[D]").astype(np.int64)


def _day_pools(P, block, days):
    """Eligible bars grouped by (day, minute-of-day) so a control draw can copy a day's shape."""
    ok = np.flatnonzero(P["valid"] & np.asarray(block, bool))
    by_day = {}
    for i in ok:
        by_day.setdefault(int(days[i]), []).append(i)
    return {k: np.array(v) for k, v in by_day.items()}


def score_days(P, mask, block, days, day_pools=None, draws=400, min_days=25, seed=17, rng=None):
    """Day-clustered scoring.

    Trades inside one session are not independent -- the top rules here fire 2-3 times a day on
    the same move -- so the unit of inference is the DAY. The statistic is the mean R per day; the
    control draws the same NUMBER of days from the block and, within each, the same number of
    entries, so it matches clustering and trade count as well as timing.
    """
    sel = np.flatnonzero(P["valid"] & np.asarray(mask, bool) & np.asarray(block, bool))
    if len(sel) < min_days:
        return None
    sd = days[sel]
    uniq, inv = np.unique(sd, return_inverse=True)
    if len(uniq) < min_days:
        return None
    per_day = np.bincount(inv)
    R = P["R"][sel]
    day_mean = np.bincount(inv, weights=R) / per_day
    stat = float(day_mean.mean())
    win = 100.0 * float((R > 0).mean())
    day_pools = day_pools if day_pools is not None else _day_pools(P, block, days)
    keys = np.array(list(day_pools.keys()))
    rng = rng or np.random.default_rng(seed)
    ctrl_stat = np.empty(draws); ctrl_win = np.empty(draws)
    nd = len(uniq)
    for k in range(draws):
        pick = keys[rng.integers(0, len(keys), nd)]
        vals = np.empty(nd); allR = []
        for j, dk in enumerate(pick):
            pool = day_pools[int(dk)]
            take = pool[rng.integers(0, len(pool), min(per_day[j], len(pool)))]
            rr = P["R"][take]
            vals[j] = rr.mean(); allR.append(rr)
        ctrl_stat[k] = vals.mean()
        cc = np.concatenate(allR)
        ctrl_win[k] = 100.0 * float((cc > 0).mean())
    losses = R[R <= 0]
    return dict(n=len(R), days=nd, per_day=float(per_day.mean()),
                win=win, expR=float(R.mean()), day_R=stat,
                pos_days=100.0 * float((day_mean > 0).mean()),
                pf=float(R[R > 0].sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
                ctrl_day_R=float(ctrl_stat.mean()), ctrl_win=float(ctrl_win.mean()),
                excess=win - float(ctrl_win.mean()),
                excess_day_R=stat - float(ctrl_stat.mean()),
                p_day=float((ctrl_stat >= stat).mean()),
                ambig=100.0 * float(P["ambig"][sel].mean()))


# --------------------------------------------------------------- day-block, trade-weighted
def score_block_bootstrap(P, mask, block, days, day_pools=None, draws=400, min_days=25,
                          seed=29, rng=None):
    """Day-BLOCK bootstrap of the TRADE-WEIGHTED mean R -- the statistic that is the economics.

    `score_days` compares the mean of per-day means. That is a valid unit of inference, but it
    weights a one-trade day equally with a twelve-trade day, and on a trend-following intraday
    system those are not the same thing: the profitable days are precisely the high-activity
    trending ones, so a per-day mean can be strongly negative while the account is positive.

    This resamples whole DAYS with all of their trades attached -- so clustering is respected --
    and computes the trade-weighted mean of the resampled set. The control does the same from
    random days at matched per-day counts. It answers "does this rule earn more per trade than
    entering the same number of times on random days", which is the question a trader has.
    """
    sel = np.flatnonzero(P["valid"] & np.asarray(mask, bool) & np.asarray(block, bool))
    if len(sel) < min_days:
        return None
    sd = days[sel]
    uniq, inv = np.unique(sd, return_inverse=True)
    nd = len(uniq)
    if nd < min_days:
        return None
    R = P["R"][sel]
    by_day = [R[inv == j] for j in range(nd)]
    per_day = np.array([len(x) for x in by_day])
    stat = float(R.mean())

    rng = rng or np.random.default_rng(seed)
    boot = np.empty(draws)
    for k in range(draws):
        pick = rng.integers(0, nd, nd)
        boot[k] = float(np.concatenate([by_day[j] for j in pick]).mean())

    day_pools = day_pools if day_pools is not None else _day_pools(P, block, days)
    keys = np.array(list(day_pools.keys()))
    ctrl = np.empty(draws)
    for k in range(draws):
        take = keys[rng.integers(0, len(keys), nd)]
        parts = []
        for j, dk in enumerate(take):
            pool = day_pools[int(dk)]
            parts.append(pool[rng.integers(0, len(pool), min(per_day[j], len(pool)))])
        ctrl[k] = float(P["R"][np.concatenate(parts)].mean())
    return dict(n=len(R), days=nd, expR=stat,
                boot_p05=float(np.percentile(boot, 5)),
                boot_p50=float(np.percentile(boot, 50)),
                boot_p95=float(np.percentile(boot, 95)),
                p_self_negative=float((boot <= 0).mean()),
                ctrl_expR=float(ctrl.mean()),
                excess=stat - float(ctrl.mean()),
                p_vs_ctrl=float((ctrl >= stat).mean()))
