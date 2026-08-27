"""The second search: same space, market-neutralised objective, nested split.

`turtle_search` ranks on Sharpe.  That ranked a strategy whose holdout profit was 87% market
exposure into first place, because a rising market and an edge look identical to a Sharpe computed
on raw dollars.  This module keeps the engine, the controls and the tensor exactly as verified and
changes only the number being maximised:

    resid_sharpe = Sharpe of (daily P&L  -  beta x the session's own 07:00-11:00 market move)

Selection happens on **research-A** and nothing else.  `research-B` is never read here.
"""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_neutral as N
import turtle_search as S
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P


def sweep(name: str, tf: int, grid: S.Grid, lo: int, hi: int, side: int = 1,
          min_trades: int = 120, keep_top: int = 8000, verbose: bool = False):
    """Score every cell of `grid` on sessions [lo, hi), ranking on market-neutralised Sharpe."""
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    s = full.window(S.WIN_LO, S.WIN_HI).slice_sessions(lo, hi)
    spy = M.SESSIONS_PER_YEAR[name]
    mkt_all = N.market_pnl(s, spec, hi)
    mkt = mkt_all[lo:hi]
    daily = np.zeros(hi)
    out = np.zeros(11)

    trig = S.Triggers(s, grid.entry1, grid.entry2, grid.sess_start, grid.sess_end, side=side,
                      atr_len=grid.atr_len[0])
    n_min = len(trig.minutes)

    rows: list[tuple] = []
    n_eval = 0
    t0 = time.time()
    for al, am, (ps, mu_), tp, uce, cs, arm, mh in itertools.product(
            grid.atr_len, grid.atr_mult, grid.pyr, grid.tp_r, grid.use_chan_exit,
            grid.chan_shift, grid.armed_stop, grid.max_hold):
        base = P(atr_len=al, atr_mult=am, pyr_step=ps, max_units=mu_, tp_r=tp,
                 use_chan_exit=uce, chan_shift=cs, armed_stop=arm, max_hold=mh, side=side,
                 sess_start=grid.sess_start, sess_end=grid.sess_end,
                 flatten_min=grid.flatten_min)
        legs = {e: X.build_leg(s, base, e) for e in grid.exit_len}
        mus = {e: S.bucket_means(s, legs[e], spec, trig.mslot, n_min, 1.0, base.tp_rests)
               for e in grid.exit_len}
        # With the trailing channel off, both exit lengths are dead parameters and 21 pairings
        # collapse to one.  Evaluating the other twenty is not a robustness check, it is the same
        # strategy counted twenty-one times -- in the runtime and, worse, in the multiplicity.
        pairs = ([(grid.exit_len[0], grid.exit_len[0])] if not uce
                 else [(a, b) for a in grid.exit_len for b in grid.exit_len if b >= a])
        for e1, e2 in pairs:
            L1, L2 = legs[e1], legs[e2]
            mu1, mu2 = mus[e1], mus[e2]
            for (k1, k2), (idx, val, h1, h2) in trig.key.items():
                tot = h1.sum() + h2.sum()
                ctrl = float((h1 @ mu1 + h2 @ mu2) / tot) if tot else 0.0
                for sw in grid.skip_win:
                    S._scan_daily(idx, val, s.sess, s.c, L1, L2, sw, False, side,
                                  spec["cost_abs"], spec["cost_bp"], spec["stop_slip"],
                                  base.tp_rests, spec.get("comm", 0.0), spec["point_value"],
                                  daily, out)
                    n_eval += 1
                    if out[0] < min_trades:
                        continue
                    st = S._stats(daily[lo:hi], out, spy)
                    ns = N.neutral_stats(daily[lo:hi], mkt, spy)
                    rows.append((al, am, ps, mu_, tp, uce, cs, arm, mh, e1, e2, k1, k2, sw,
                                 st["n"], st["net"], st["per_trade"], st["sharpe"], st["pf"],
                                 st["win_rate"], st["maxdd"], st["mar"], st["units"], st["hold"],
                                 st["x_tp"], ctrl, st["per_trade"] - ctrl,
                                 ns["corr_mkt"], ns["beta_mkt"], ns["resid_sharpe"],
                                 ns["alpha"], ns["beta_pnl_share"]))
        if verbose and n_eval % 100000 < 2000:
            print(f"    {name} {tf}m  {n_eval:,} evaluated  {time.time() - t0:.0f}s", flush=True)

    cols = ["atr_len", "atr_mult", "pyr_step", "max_units", "tp_r", "use_chan_exit", "chan_shift",
            "armed_stop", "max_hold", "exit1", "exit2", "entry1", "entry2", "skip_win",
            "n", "net", "per_trade", "sharpe", "pf", "win_rate", "maxdd", "mar", "units", "hold",
            "x_tp", "ctrl_per_trade", "ex_per_trade",
            "corr_mkt", "beta_mkt", "resid_sharpe", "alpha", "beta_pnl_share"]
    df = pd.DataFrame(rows, columns=cols)
    df["instrument"], df["tf"], df["side"] = name, tf, side
    df["one_shot"] = False
    df["sess_start"], df["sess_end"], df["flatten_min"] = (grid.sess_start, grid.sess_end,
                                                           grid.flatten_min)
    meta = {"n_evaluated": n_eval, "n_scored": len(df), "seconds": time.time() - t0,
            "instrument": name, "tf": tf, "side": side, "lo": lo, "hi": hi,
            "best_resid": float(df.resid_sharpe.max()) if len(df) else 0.0,
            "best_sharpe": float(df.sharpe.max()) if len(df) else 0.0,
            "resid_sd": float(df.resid_sharpe.std(ddof=1)) if len(df) > 1 else 0.0,
            "resid_mean": float(df.resid_sharpe.mean()) if len(df) else 0.0}
    if keep_top and len(df) > keep_top:
        df = df.sort_values("resid_sharpe", ascending=False).head(keep_top)
    return df.reset_index(drop=True), meta


def evaluate_one(name: str, tf: int, p: P, lo: int, hi: int) -> dict:
    """Score one configuration on an arbitrary session range, with the market metrics."""
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    s = full.window(S.WIN_LO, S.WIN_HI).slice_sessions(lo, hi)
    spy = M.SESSIONS_PER_YEAR[name]
    mkt = N.market_pnl(s, spec, hi)[lo:hi]
    daily = np.zeros(hi)
    out = np.zeros(11)
    legs = {e: X.build_leg(s, p, e) for e in {p.exit1, p.exit2}}
    t = T.signal_bars(s, p)
    idx = np.flatnonzero(t).astype(np.int64)
    if len(idx) < 5:
        return {"n": 0}
    S._scan_daily(idx, t[idx].astype(np.int64), s.sess, s.c, legs[p.exit1], legs[p.exit2],
                  p.skip_win, p.one_shot, p.side, spec["cost_abs"], spec["cost_bp"],
                  spec["stop_slip"], p.tp_rests, spec.get("comm", 0.0), spec["point_value"],
                  daily, out)
    st = S._stats(daily[lo:hi], out, spy)
    st.update(N.neutral_stats(daily[lo:hi], mkt, spy))
    return st


def to_params(row, spec: dict) -> P:
    return P(entry1=int(row.entry1), entry2=int(row.entry2), exit1=int(row.exit1),
             exit2=int(row.exit2), atr_len=int(row.atr_len), atr_mult=float(row.atr_mult),
             pyr_step=float(row.pyr_step), max_units=int(row.max_units),
             skip_win=bool(row.skip_win), one_shot=bool(row.get("one_shot", False)),
             tp_r=float(row.tp_r), max_hold=int(row.max_hold),
             use_chan_exit=bool(row.use_chan_exit), chan_shift=int(row.chan_shift),
             armed_stop=bool(row.armed_stop), sess_start=int(row.sess_start),
             sess_end=int(row.sess_end), flatten_min=int(row.flatten_min), side=int(row.side),
             cost_abs=spec["cost_abs"], cost_bp=spec["cost_bp"], stop_slip=spec["stop_slip"])


if __name__ == "__main__":
    import json
    name, tf, side = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")
    a, b, n = N.split_ab(name, tf)
    grid = S.Grid(atr_len=(20,), chan_shift=(1, 0),
                  atr_mult=(1.0, 1.5, 2.0, 2.5, 3.0),
                  pyr=((0.0, 1), (0.5, 2), (0.5, 4), (1.0, 4)),
                  tp_r=(0.0, 1.0, 2.0, 3.0),
                  use_chan_exit=(True, False), armed_stop=(False, True), max_hold=(0, 4),
                  exit_len=(2, 3, 4, 6, 8, 12),
                  entry1=(4, 6, 8, 10, 14, 20, 28), entry2=(8, 12, 16, 24, 40, 60),
                  skip_win=(True, False), one_shot=(False,))
    df, meta = sweep(name, tf, grid, 0, a, side=side, verbose=True)
    tag = f"N_{name}_{tf}m_{'long' if side > 0 else 'short'}"
    df.to_parquet(os.path.join(OUT, tag + ".parquet"), index=False)
    with open(os.path.join(OUT, tag + ".json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"{tag}: evaluated {meta['n_evaluated']:,}  scored {meta['n_scored']:,}  "
          f"best resid {meta['best_resid']:.3f}  best raw {meta['best_sharpe']:.3f}  "
          f"resid mean {meta['resid_mean']:.3f} sd {meta['resid_sd']:.3f}  "
          f"{meta['seconds']:.0f}s", flush=True)
