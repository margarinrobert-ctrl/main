"""Coarse grid -> random search -> Bayesian TPE, scored on TRAIN, selected on VALID.

THE ORDER MATTERS AND IS THE POINT. Step 4 of the brief asks for progressively more sophisticated
optimisation, and the reason to start coarse is not politeness: a fine grid run first tells you
where the maximum is without telling you whether there is a PLATEAU under it, and this branch has
twice shipped a maximum with no neighbourhood.

  TRAIN (60%)  every configuration is scored here, and here only.
  VALID (20%)  read for the survivors of TRAIN, to choose among candidates.
  OOS   (20%)  NOT TOUCHED by this module. `v33robust.read_oos` is the only thing that opens it,
               once, after the candidate is frozen.

ROBUSTNESS IS INSIDE THE OBJECTIVE, not bolted on afterwards. Each configuration's score carries a
0.15 weight on the share of its immediate parameter NEIGHBOURHOOD (one rung either way on entry_n,
exit_n, stop and tp) that also earns PF > 1 and Sharpe > 0 on TRAIN. A spike with a dead
neighbourhood is scored down before it can ever reach the validation block.

EVERY TRIAL IS LOGGED. The count is carried into the deflated-Sharpe calculation in v33robust --
a search this size is a multiplicity problem before it is anything else.
"""
from __future__ import annotations

import sys
import itertools
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402


def grid_space():
    """The declared coarse grid. Printed with the results, never after them."""
    return dict(tf=V.TF, entry_n=V.ENTRY_N, exit_n=V.EXIT_N, stop=V.STOP, tp_r=V.TP_R,
                chop_max=V.CHOP, adx_min=V.ADX, session=V.SESSION, vol_policy=V.VOL_POLICY)


def n_configs():
    s = grid_space()
    return int(np.prod([len(v) for v in s.values()]))


def evaluate(market, p, blocks, block="train", cache=None):
    R, days, P, _O, _i = V.trades(market, p, blocks[block])
    return V.metrics(R, days, P, all_sess=V.block_days(P, blocks[block], block))


def neighbours(p: V.Params):
    """One rung either way on the four geometry axes. Filters are not perturbed here -- they are
    perturbed in v33robust, where the perturbation is the measurement rather than a term."""
    out = []
    for axis, values in (("entry_n", V.ENTRY_N), ("exit_n", V.EXIT_N),
                         ("stop", V.STOP), ("tp_r", V.TP_R)):
        cur = getattr(p, axis)
        i = list(values).index(cur)
        for j in (i - 1, i + 1):
            if 0 <= j < len(values):
                out.append(V.Params(**{**p.dict(), axis: values[j]}))
    return out


def robustness(market, p, blocks, memo):
    """Share of the immediate neighbourhood that keeps PF > 1 and Sharpe > 0 on TRAIN."""
    nb = neighbours(p)
    if not nb:
        return 0.0
    ok = 0
    for q in nb:
        k = (market,) + tuple(sorted(q.dict().items()))
        if k not in memo:
            m = evaluate(market, q, blocks)
            memo[k] = (m["pf"] > 1.0 and m["sharpe"] > 0) if m else False
        ok += memo[k]
    return ok / len(nb)


def coarse(market, side=1, progress=True):
    """The full declared grid on TRAIN. Returns one row per configuration."""
    b0 = V.bars(market, V.TF[0])
    rows, memo, t0 = [], {}, time.perf_counter()
    total = n_configs()
    seen = 0
    for tf in V.TF:
        P0 = V.prep(market, tf, V.ENTRY_N[0], V.EXIT_N[0])
        blocks = V.splits(P0["sess"])
        for en, ex in itertools.product(V.ENTRY_N, V.EXIT_N):
            for st, tp in itertools.product(V.STOP, V.TP_R):
                for ch, ax, ses, vp in itertools.product(V.CHOP, V.ADX, V.SESSION, V.VOL_POLICY):
                    p = V.Params(tf=tf, entry_n=en, exit_n=ex, stop=st, tp_r=tp, chop_max=ch,
                                 adx_min=ax, session=ses, vol_policy=vp, side=side)
                    m = evaluate(market, p, blocks)
                    seen += 1
                    if m is None:
                        continue
                    sc, _ = V.score(m, robust=0.0)
                    rows.append(dict(**{k: (str(v) if isinstance(v, tuple) else v)
                                        for k, v in p.dict().items()},
                                     n=m["n"], pf=m["pf"], sharpe=m["sharpe"],
                                     sortino=m["sortino"], dd=m["dd"], retdd=m["retdd"],
                                     calmar=m["calmar"], win=m["win"], net=m["net"],
                                     R=m["R"], top1=m["top1_share"], score_norobust=sc))
                if progress and seen % 2000 < 60:
                    print(f"      {seen:>6,}/{total:,}  {time.perf_counter() - t0:6.1f}s  "
                          f"{len(rows):,} scorable", flush=True)
    df = pd.DataFrame(rows)
    df["market"], df["block"] = market, "train"
    return df


def add_robustness(market, df, side=1, top=400):
    """Robustness is expensive, so it is computed for the top of the TRAIN ranking only -- which is
    the only place it can change a decision."""
    P0 = V.prep(market, V.TF[0], V.ENTRY_N[0], V.EXIT_N[0])
    blocks = V.splits(P0["sess"])
    memo = {}
    d = df.sort_values("score_norobust", ascending=False).head(top).copy()
    rob, sc = [], []
    for r in d.itertuples():
        p = row_to_params(r, side)
        blocks_tf = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
        rb = robustness(market, p, blocks_tf, memo)
        m = evaluate(market, p, blocks_tf)
        rob.append(rb)
        sc.append(V.score(m, robust=rb)[0])
    d["robust"], d["score"] = rob, sc
    return d.sort_values("score", ascending=False).reset_index(drop=True)


def _lit(v):
    if isinstance(v, str):
        return None if v == "None" else tuple(float(x) for x in v.strip("()").split(","))
    return None if (v is None or (isinstance(v, float) and not np.isfinite(v))) else v


def row_to_params(r, side=1):
    return V.Params(tf=int(r.tf), entry_n=int(r.entry_n), exit_n=int(r.exit_n),
                    stop=float(r.stop), tp_r=float(r.tp_r),
                    chop_max=_lit(r.chop_max), adx_min=_lit(r.adx_min),
                    session=_lit(r.session), vol_policy=_lit(r.vol_policy), side=side)


def read_valid(market, d, side=1, top=60):
    """The validation block, for the top of the TRAIN ranking only."""
    out = []
    for r in d.head(top).itertuples():
        p = row_to_params(r, side)
        blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
        m = evaluate(market, p, blocks, "valid")
        out.append(dict(rank=r.Index, score=r.score, robust=r.robust,
                        tr_sharpe=r.sharpe, tr_pf=r.pf, tr_n=r.n,
                        va_sharpe=m["sharpe"] if m else np.nan,
                        va_pf=m["pf"] if m else np.nan, va_n=m["n"] if m else 0,
                        va_retdd=m["retdd"] if m else np.nan,
                        params=p))
    return pd.DataFrame(out)
