"""Choosing from the sweep: coherence across instruments, not the maximum on one.

The single most dangerous number in this study is the best Sharpe on one instrument.  All three
research blocks are drifting samples, the grid has 645,120 cells per run, and the maximum of that
many cells is large whether or not anything is there.

What is not cheap to fake is the SAME parameter combination working on a stock index, a metal and
a cryptocurrency.  Those three have different microstructure, different participants, different
sessions and cost regimes an order of magnitude apart -- 0.5 bp a round turn on US30 against 10 bp
on BTC.  A configuration that clears its own matched control on all three is being asked a question
a per-instrument maximum never has to answer.

So selection runs in two steps.  The per-instrument sweeps propose; this module takes the UNION of
their proposals, re-evaluates every candidate on every instrument -- including instruments whose
own sweep never ranked it -- and scores the combination.  Re-evaluating the union rather than
intersecting the top lists matters: a configuration that ranks 4,000th on gold and 12th on US30 and
12th on BTC never appears in an intersection of top-100s, and it is exactly the kind of candidate
this study is looking for.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_search as S
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P

SWEEP = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")

KEY = ["atr_len", "atr_mult", "pyr_step", "max_units", "tp_r", "use_chan_exit", "chan_shift",
       "armed_stop", "max_hold", "exit1", "exit2", "entry1", "entry2", "skip_win", "one_shot"]
GEO = ["atr_len", "atr_mult", "pyr_step", "max_units", "tp_r", "use_chan_exit", "chan_shift",
       "armed_stop", "max_hold"]


def load_sweeps(side: int = 1) -> pd.DataFrame:
    tag = "long" if side > 0 else "short"
    frames = []
    for f in sorted(os.listdir(SWEEP)):
        if f.endswith(f"_{tag}.parquet"):
            frames.append(pd.read_parquet(os.path.join(SWEEP, f)))
    if not frames:
        raise FileNotFoundError(f"no {tag} sweeps in {SWEEP}")
    return pd.concat(frames, ignore_index=True)


def load_meta() -> pd.DataFrame:
    import json
    rows = []
    for f in sorted(os.listdir(SWEEP)):
        if f.endswith(".json"):
            with open(os.path.join(SWEEP, f)) as fh:
                rows.append(json.load(fh))
    return pd.DataFrame(rows)


# ================================================================= evaluate a candidate set

def evaluate(name: str, tf: int, cand: pd.DataFrame, side: int = 1, cost_mult: float = 1.0,
             sess_start: int = 420, sess_end: int = 660, flatten_min: int = 660,
             lo: int | None = None, hi: int | None = None) -> pd.DataFrame:
    """Score every row of `cand` on one instrument, grouped by geometry so tensors are reused.

    `lo`/`hi` bound the sessions scored.  They default to the research block, and nothing here
    will read past it unless a caller deliberately asks: `sweep`-style slicing is applied to the
    series itself when the range ends at the split.
    """
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    cut = B.split_session(full)
    lo = 0 if lo is None else lo
    hi = cut if hi is None else hi
    # Always slice to the scored range.  The aggregate counters the scan returns cover every trade
    # it took, so scoring a sub-range of a wider series would report the sub-range's Sharpe next to
    # the whole series' trade count and per-trade result.  Slicing makes the two agree by
    # construction -- and for the default range it also means locked bars are never materialised.
    s = full.window(S.WIN_LO, S.WIN_HI).slice_sessions(lo, hi)
    n_sess = hi
    daily = np.zeros(n_sess)
    out = np.zeros(11)
    spy = M.SESSIONS_PER_YEAR[name]

    trig_cache: dict = {}
    minutes = np.unique(s.ny_min)
    mslot = np.searchsorted(minutes, s.ny_min)

    rows = []
    for geo, grp in cand.groupby(GEO, sort=False):
        g = dict(zip(GEO, geo))
        base = P(side=side, sess_start=sess_start, sess_end=sess_end, flatten_min=flatten_min,
                 atr_len=int(g["atr_len"]), atr_mult=float(g["atr_mult"]),
                 pyr_step=float(g["pyr_step"]), max_units=int(g["max_units"]),
                 tp_r=float(g["tp_r"]), use_chan_exit=bool(g["use_chan_exit"]),
                 chan_shift=int(g["chan_shift"]), armed_stop=bool(g["armed_stop"]),
                 max_hold=int(g["max_hold"]))
        legs, mus = {}, {}
        for e in sorted(set(grp.exit1) | set(grp.exit2)):
            legs[e] = X.build_leg(s, base, int(e))
            mus[e] = S.bucket_means(s, legs[e], spec, mslot, len(minutes), cost_mult,
                                    base.tp_rests)
        for _, r in grp.iterrows():
            tk = (int(r.entry1), int(r.entry2), int(r.atr_len))
            if tk not in trig_cache:
                p = T.replace(base, entry1=tk[0], entry2=tk[1], atr_len=tk[2])
                t = T.signal_bars(s, p)
                idx = np.flatnonzero(t).astype(np.int64)
                h1 = np.bincount(mslot[t == 1], minlength=len(minutes)).astype(float)
                h2 = np.bincount(mslot[t == 2], minlength=len(minutes)).astype(float)
                trig_cache[tk] = (idx, t[idx].astype(np.int64), h1, h2)
                if len(trig_cache) > 600:
                    trig_cache.clear()
                    trig_cache[tk] = (idx, t[idx].astype(np.int64), h1, h2)
            idx, val, h1, h2 = trig_cache[tk]
            if len(idx) < 20:
                continue
            e1, e2 = int(r.exit1), int(r.exit2)
            tot = h1.sum() + h2.sum()
            ctrl = float((h1 @ mus[e1] + h2 @ mus[e2]) / tot) if tot else 0.0
            S._scan_daily(idx, val, s.sess, s.c, legs[e1], legs[e2], bool(r.skip_win),
                          bool(r.one_shot), side, spec["cost_abs"] * cost_mult,
                          spec["cost_bp"] * cost_mult, spec["stop_slip"] * cost_mult,
                          base.tp_rests, spec.get("comm", 0.0) * cost_mult, spec["point_value"],
                          daily, out)
            st = S._stats(daily[lo:hi], out, spy)
            rows.append({**{k: r[k] for k in KEY}, **st, "ctrl_per_trade": ctrl,
                         "ex_per_trade": st["per_trade"] - ctrl,
                         "instrument": name, "tf": tf, "side": side,
                         "sess_start": sess_start, "sess_end": sess_end,
                         "flatten_min": flatten_min})
    return pd.DataFrame(rows)


# ================================================================= coherence

def coherence(per_inst: dict[str, pd.DataFrame], min_trades: int = 150) -> pd.DataFrame:
    """Join per-instrument scores on the parameter key and score the combination.

    Two summaries, deliberately different in spirit:

      * `worst_*` -- the weakest instrument.  A gate, because a configuration that loses on one of
        three has not demonstrated a mechanism; it has demonstrated two samples.
      * `median_*` -- what to rank on.  Ranking on the worst instrument is the over-correction
        `CLAUDE.md` measured as costing $18,970 on a parameter neighbourhood, and the same
        reasoning applies across a three-element panel: the minimum of three noisy numbers is
        mostly noise.
    """
    frames = []
    for nm, df in per_inst.items():
        d = df.set_index(KEY)[["n", "sharpe", "pf", "per_trade", "ex_per_trade", "net",
                               "win_rate", "maxdd", "mar", "units", "hold", "x_tp"]]
        d.columns = [f"{c}__{nm}" for c in d.columns]
        frames.append(d)
    j = pd.concat(frames, axis=1, join="inner").reset_index()
    if not len(j):
        return j
    names = list(per_inst)
    for stat in ("sharpe", "ex_per_trade", "pf", "n", "per_trade"):
        cols = [f"{stat}__{nm}" for nm in names]
        j[f"median_{stat}"] = j[cols].median(axis=1)
        j[f"worst_{stat}"] = j[cols].min(axis=1)
    j["all_positive_excess"] = (j[[f"ex_per_trade__{nm}" for nm in names]] > 0).all(axis=1)
    j["all_positive_sharpe"] = (j[[f"sharpe__{nm}" for nm in names]] > 0).all(axis=1)
    j["all_enough_trades"] = (j[[f"n__{nm}" for nm in names]] >= min_trades).all(axis=1)
    j["n_instruments"] = len(names)
    return j


def top_union(sweeps: pd.DataFrame, tf: int, per_instrument: int = 2500,
              metric: str = "sharpe") -> pd.DataFrame:
    """Union of each instrument's top candidates at one timeframe, de-duplicated on the key."""
    sel = sweeps[sweeps.tf == tf]
    parts = []
    for nm, g in sel.groupby("instrument"):
        parts.append(g.sort_values(metric, ascending=False).head(per_instrument))
        # also take the top of the control-excess ordering: a cell can have a modest Sharpe and
        # the largest excess in the grid, and that ordering is the one with a mechanism behind it.
        parts.append(g.sort_values("ex_per_trade", ascending=False).head(per_instrument // 2))
    u = pd.concat(parts, ignore_index=True)
    return u.drop_duplicates(subset=KEY)[KEY].reset_index(drop=True)


__all__ = ["load_sweeps", "load_meta", "evaluate", "coherence", "top_union", "KEY", "GEO"]
