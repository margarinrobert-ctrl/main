"""The research sweep: geometry, entry channels and session, on the RESEARCH BLOCK ONLY.

The locked block is not merely ignored here -- it is never loaded.  `sweep()` slices the series to
the research sessions before it builds anything, so no path through this module can read a bar the
holdout owns.  That is a stronger guarantee than remembering to filter, and `CLAUDE.md` records
that the weaker one has failed twice on this repository.

HOW THE COST IS KEPT DOWN
-------------------------
Three observations, each worth an order of magnitude:

  * the trigger array does not depend on the exit geometry, so every (entry1, entry2) channel pair
    is materialised once per instrument and timeframe, not once per configuration;
  * the exit tensor depends on the exit length but not on which entry system it will be paired
    with, so |lengths| walks cover |lengths|^2 pairings;
  * a scan only ever visits bars where the trigger fired, which is 5-15% of them, so it walks an
    index list rather than the series.

WHAT IS RANKED, AND AGAINST WHAT
--------------------------------
Ranking on profit would rank on the bull market -- all three instruments rose over their research
blocks.  Every configuration therefore carries `ctrl_per_trade`: what the SAME geometry earns from
entries drawn uniformly from the same minutes of the day.  It is computed analytically from the
tensor (each bucket's mean is already there, so it costs a dot product of 61 numbers), which makes
it affordable on every cell rather than on the survivors.

The analytic form is an expectation over unthinned triggers and cannot see the no-overlap rule, so
it screens rather than decides.  Candidates that survive it are scored again in `turtle_validate`
against the full draw-based control, which re-runs the whole scan on random triggers and therefore
prices the thinning too.
"""
from __future__ import annotations

import itertools
import os
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P

WIN_LO, WIN_HI = 420, 720


@njit(cache=True)
def _scan_daily(tidx, tval, sess, c, L1, L2,
                skip_win, one_shot, side, cost_abs, cost_bp, stop_slip, tp_rests,
                comm, pv, daily, out):
    """Scan the trigger index list, accumulate per-session dollars, return trade aggregates.

    `L1` and `L2` are the System 1 and System 2 exit legs, each a tuple of the nine per-bar
    arrays `turtle_tensor.build_leg` returns.  They are passed as separate legs rather than as a
    stacked (2, n) array on purpose: stacking copies 15 MB per exit-length pairing and that copy,
    not the scan, was the dominant cost of the sweep.

    `out` receives (n, units_sum, net_sum, tp_exits, stop_exits, flat_exits, hold_bars_sum,
    win_dollars, loss_dollars, n_win, bp_sum).
    """
    ex1, re1, un1, gr1, rs1, rk1, av1, fi1, su1 = L1
    ex2, re2, un2, gr2, rs2, rk2, av2, fi2, su2 = L2
    for k in range(out.shape[0]):
        out[k] = 0.0
    for k in range(daily.shape[0]):
        daily[k] = 0.0

    m = tidx.shape[0]
    ptr = 0
    last_win = False
    sess_traded = -1
    while ptr < m:
        i = tidx[ptr]
        t = tval[ptr]
        if one_shot and sess[i] == sess_traded:
            ptr += 1
            continue
        if t == 1 and skip_win and last_win:
            last_win = False
            ptr += 1
            continue
        if t == 1:
            e = ex1[i]; nxt = re1[i]; u = un1[i]; g = gr1[i]
            rr = rs1[i]; a = av1[i]; f = fi1[i]; su = su1[i]
        else:
            e = ex2[i]; nxt = re2[i]; u = un2[i]; g = gr2[i]
            rr = rs2[i]; a = av2[i]; f = fi2[i]; su = su2[i]
        if e < 0:
            ptr += 1
            continue
        cost = u * (cost_abs + cost_bp * 1e-4 * a)
        if tp_rests and rr == 2:
            cost *= 0.5
        net = (g - cost - su * stop_slip) * pv - u * comm
        daily[sess[e]] += net
        out[0] += 1.0
        out[1] += u
        out[2] += net
        if rr == 2:
            out[3] += 1.0
        elif rr == 0 or rr == 1:
            out[4] += 1.0
        else:
            out[5] += 1.0
        out[6] += e - (i + 1)
        if net > 0.0:
            out[7] += net
            out[9] += 1.0
        else:
            out[8] -= net
        out[10] += net / (a * 1e-4 * pv) if a > 0.0 else 0.0

        last_win = side * (c[e] - f) > 0.0
        if one_shot:
            sess_traded = sess[i + 1]
        # advance the pointer to the first trigger at or after the re-entry bar
        while ptr < m and tidx[ptr] < nxt:
            ptr += 1
    return


def _stats(daily: np.ndarray, out: np.ndarray, spy: float) -> dict:
    n = int(out[0])
    sd = daily.std(ddof=1) if len(daily) > 1 else 0.0
    dn = daily[daily < 0]
    dsd = np.sqrt((dn ** 2).mean()) if len(dn) else 0.0
    eq = np.cumsum(daily)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    return {
        "n": n,
        "net": float(out[2]),
        "per_trade": float(out[2] / n) if n else 0.0,
        "sharpe": float(daily.mean() / sd * np.sqrt(spy)) if sd > 0 else 0.0,
        "sortino": float(daily.mean() / dsd * np.sqrt(spy)) if dsd > 0 else 0.0,
        "pf": float(out[7] / out[8]) if out[8] > 0 else (99.0 if out[7] > 0 else 0.0),
        "win_rate": float(out[9] / n) if n else 0.0,
        "maxdd": dd,
        "mar": float(out[2] / dd) if dd > 0 else 0.0,
        "units": float(out[1] / n) if n else 0.0,
        "hold": float(out[6] / n) if n else 0.0,
        "x_tp": float(out[3] / n) if n else 0.0,
        "x_stop": float(out[4] / n) if n else 0.0,
        "x_flat": float(out[5] / n) if n else 0.0,
        "bp_per_trade": float(out[10] / n) if n else 0.0,
    }


# ================================================================= trigger cache

class Triggers:
    """Every (entry1, entry2) channel pair, materialised once, with its minute histogram."""

    def __init__(self, s, entry1s, entry2s, sess_start, sess_end, side=1, break_ticks=0.0,
                 adx_max=0.0, ext_max=0.0, atr_len=20, ema_len=100):
        self.s = s
        self.key: dict = {}
        self.minutes = np.unique(s.ny_min)
        self.mslot = np.searchsorted(self.minutes, s.ny_min)
        base = P(atr_len=atr_len, ema_len=ema_len, sess_start=sess_start, sess_end=sess_end,
                 side=side, break_ticks=break_ticks, adx_max=adx_max, ext_max=ext_max)
        for e1 in entry1s:
            for e2 in entry2s:
                if e2 < e1:
                    continue
                p = T.replace(base, entry1=e1, entry2=e2)
                t = T.signal_bars(s, p)
                idx = np.flatnonzero(t).astype(np.int64)
                if len(idx) < 20:
                    continue
                h1 = np.bincount(self.mslot[t == 1], minlength=len(self.minutes)).astype(float)
                h2 = np.bincount(self.mslot[t == 2], minlength=len(self.minutes)).astype(float)
                self.key[(e1, e2)] = (idx, t[idx].astype(np.int64), h1, h2)


def bucket_means(s, leg: tuple, spec: dict, mslot: np.ndarray, n_min: int, cost_mult: float,
                 tp_rests: bool) -> np.ndarray:
    """Mean net dollars of a hypothetical entry, per draw bucket, for one exit leg.

    `mslot` is whatever bucketing the control uses -- minute-of-day alone, or minute-of-day
    crossed with an ATR quantile (`turtle_tensor.vol_slot`).  The two give different answers for a
    breakout rule and the study reports both.

    This is the matched control's expectation, already latent in the tensor: the control draws its
    entries uniformly inside each minute-of-day bucket, so the mean of the bucket IS what it earns
    there.  Bars where no trade was possible are excluded from the mean, exactly as they are
    excluded from the draw.
    """
    ex, re_, un, gr, rs, rk, av, fi, su = leg
    ok = ex >= 0
    cost = un * (spec["cost_abs"] * cost_mult + spec["cost_bp"] * cost_mult * 1e-4 * av)
    if tp_rests:
        cost = np.where(rs == T.EX_TP, cost * 0.5, cost)
    net = (gr - cost - su * spec["stop_slip"] * cost_mult) * spec["point_value"] \
        - un * spec.get("comm", 0.0) * cost_mult
    cnt = np.bincount(mslot[ok], minlength=n_min).astype(float)
    tot = np.bincount(mslot[ok], weights=net[ok], minlength=n_min)
    return np.divide(tot, cnt, out=np.zeros(n_min), where=cnt > 0)


# ================================================================= the sweep

@dataclass
class Grid:
    atr_len: tuple = (20,)
    chan_shift: tuple = (1, 0)
    atr_mult: tuple = (0.75, 1.0, 1.5, 2.0, 2.5, 3.0)
    pyr: tuple = ((0.0, 1), (0.5, 2), (0.5, 4), (1.0, 4))
    tp_r: tuple = (0.0, 1.0, 1.5, 2.0, 3.0)
    use_chan_exit: tuple = (True, False)
    armed_stop: tuple = (False, True)
    max_hold: tuple = (0,)
    exit_len: tuple = (2, 3, 4, 6, 8, 12)
    entry1: tuple = (4, 6, 8, 10, 14, 20, 28)
    entry2: tuple = (8, 12, 16, 24, 40, 60)
    skip_win: tuple = (True, False)
    one_shot: tuple = (False,)
    sess_start: int = 420
    sess_end: int = 660
    flatten_min: int = 660

    def size(self) -> int:
        geo = (len(self.atr_len) * len(self.atr_mult) * len(self.pyr) * len(self.tp_r)
               * len(self.use_chan_exit) * len(self.armed_stop) * len(self.max_hold)
               * len(self.chan_shift))
        pairs = sum(1 for a in self.exit_len for b in self.exit_len if b >= a)
        ent = sum(1 for a in self.entry1 for b in self.entry2 if b >= a)
        return geo * pairs * ent * len(self.skip_win) * len(self.one_shot)


def sweep(name: str, tf: int, grid: Grid, side: int = 1, cost_mult: float = 1.0,
          min_trades: int = 150, keep_top: int = 4000, verbose: bool = True) -> pd.DataFrame:
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    cut = B.split_session(full)
    s = full.window(WIN_LO, WIN_HI).slice_sessions(0, cut)      # research block, window only
    spy = M.SESSIONS_PER_YEAR[name]
    n_sess = int(s.sess.max()) + 1
    daily = np.zeros(n_sess)
    out = np.zeros(11)

    trig = Triggers(s, grid.entry1, grid.entry2, grid.sess_start, grid.sess_end, side=side,
                    atr_len=grid.atr_len[0])
    # `signal_bars` reads ATR only to reject warm-up bars, so one trigger set covers every
    # atr_len in the grid; the sets are rebuilt per atr_len only if that ever stops being true.
    trig_by_atr = {grid.atr_len[0]: trig}
    for al in grid.atr_len[1:]:
        trig_by_atr[al] = Triggers(s, grid.entry1, grid.entry2, grid.sess_start, grid.sess_end,
                                   side=side, atr_len=al)
    n_min = len(trig.minutes)

    rows: list[tuple] = []
    # Every trial's Sharpe is kept, not just the survivors'.  The Deflated Sharpe Ratio needs the
    # cross-sectional dispersion of the trials that were actually run, and a study that reports
    # only the winners cannot supply it -- which is the single most common way a search result is
    # overstated.
    all_sharpe: list[np.ndarray] = []
    buf_sharpe = np.empty(1 << 16, np.float32)
    nb = 0
    n_eval = 0
    t0 = time.time()
    ngeo = 0
    for al, am, (ps, mu_), tp, uce, cs, arm, mh in itertools.product(
            grid.atr_len, grid.atr_mult, grid.pyr, grid.tp_r, grid.use_chan_exit,
            grid.chan_shift, grid.armed_stop, grid.max_hold):
        base = P(atr_len=al, atr_mult=am, pyr_step=ps, max_units=mu_, tp_r=tp,
                 use_chan_exit=uce, chan_shift=cs, armed_stop=arm, max_hold=mh, side=side,
                 sess_start=grid.sess_start, sess_end=grid.sess_end,
                 flatten_min=grid.flatten_min)
        tg = trig_by_atr[al]
        legs = {e: X.build_leg(s, base, e) for e in grid.exit_len}
        mus = {e: bucket_means(s, legs[e], spec, tg.mslot, n_min, cost_mult, base.tp_rests)
               for e in grid.exit_len}
        ngeo += 1
        for e1 in grid.exit_len:
            for e2 in grid.exit_len:
                if e2 < e1:
                    continue
                L1, L2 = legs[e1], legs[e2]
                mu1, mu2 = mus[e1], mus[e2]
                for (k1, k2), (idx, val, h1, h2) in tg.key.items():
                    tot = h1.sum() + h2.sum()
                    ctrl = float((h1 @ mu1 + h2 @ mu2) / tot) if tot else 0.0
                    for sw in grid.skip_win:
                        for os_ in grid.one_shot:
                            _scan_daily(idx, val, s.sess, s.c, L1, L2,
                                        sw, os_, side,
                                        spec["cost_abs"] * cost_mult,
                                        spec["cost_bp"] * cost_mult,
                                        spec["stop_slip"] * cost_mult, base.tp_rests,
                                        spec.get("comm", 0.0) * cost_mult, spec["point_value"],
                                        daily, out)
                            n_eval += 1
                            if out[0] < min_trades:
                                continue
                            st = _stats(daily, out, spy)
                            if nb == buf_sharpe.shape[0]:
                                all_sharpe.append(buf_sharpe.copy())
                                nb = 0
                            buf_sharpe[nb] = st["sharpe"]
                            nb += 1
                            rows.append((al, am, ps, mu_, tp, uce, cs, arm, mh, e1, e2, k1, k2,
                                         sw, os_, st["n"], st["net"], st["per_trade"],
                                         st["sharpe"], st["sortino"], st["pf"], st["win_rate"],
                                         st["maxdd"], st["mar"], st["units"], st["hold"],
                                         st["x_tp"], st["x_stop"], st["x_flat"],
                                         st["bp_per_trade"], ctrl, st["per_trade"] - ctrl))
        if verbose and ngeo % 100 == 0:
            print(f"    {name} {tf}m  geometry {ngeo}  rows {len(rows):,}  "
                  f"{time.time() - t0:.0f}s", flush=True)

    cols = ["atr_len", "atr_mult", "pyr_step", "max_units", "tp_r", "use_chan_exit", "chan_shift",
            "armed_stop", "max_hold", "exit1", "exit2", "entry1", "entry2", "skip_win", "one_shot",
            "n", "net", "per_trade", "sharpe", "sortino", "pf", "win_rate", "maxdd", "mar",
            "units", "hold", "x_tp", "x_stop", "x_flat", "bp_per_trade",
            "ctrl_per_trade", "ex_per_trade"]
    all_sharpe.append(buf_sharpe[:nb].copy())
    trials = np.concatenate(all_sharpe) if all_sharpe else np.zeros(0, np.float32)
    df = pd.DataFrame(rows, columns=cols)
    df["instrument"] = name
    df["tf"] = tf
    df["side"] = side
    df["sess_start"] = grid.sess_start
    df["sess_end"] = grid.sess_end
    df["flatten_min"] = grid.flatten_min
    meta = {"n_evaluated": n_eval, "n_scored": int(len(df)),
            "trial_sharpe_mean": float(trials.mean()) if len(trials) else 0.0,
            "trial_sharpe_sd": float(trials.std(ddof=1)) if len(trials) > 1 else 0.0,
            "trial_sharpe_max": float(trials.max()) if len(trials) else 0.0,
            "seconds": time.time() - t0}
    if keep_top and len(df) > keep_top:
        df = df.sort_values("sharpe", ascending=False).head(keep_top)
    return df.reset_index(drop=True), meta, trials


def to_params(row, spec: dict, cost_mult: float = 1.0) -> P:
    return P(entry1=int(row.entry1), entry2=int(row.entry2), exit1=int(row.exit1),
             exit2=int(row.exit2), atr_len=int(row.atr_len), atr_mult=float(row.atr_mult),
             pyr_step=float(row.pyr_step), max_units=int(row.max_units),
             skip_win=bool(row.skip_win), one_shot=bool(row.one_shot),
             adx_max=float(getattr(row, "adx_max", 0.0)),
             ext_max=float(getattr(row, "ext_max", 0.0)),
             break_ticks=float(getattr(row, "break_ticks", 0.0)),
             tp_r=float(row.tp_r), max_hold=int(row.max_hold),
             use_chan_exit=bool(row.use_chan_exit), chan_shift=int(row.chan_shift),
             armed_stop=bool(row.armed_stop),
             sess_start=int(row.sess_start), sess_end=int(row.sess_end),
             flatten_min=int(row.flatten_min), side=int(row.side),
             cost_abs=spec["cost_abs"] * cost_mult, cost_bp=spec["cost_bp"] * cost_mult,
             stop_slip=spec["stop_slip"] * cost_mult)


if __name__ == "__main__":
    g = Grid()
    print(f"grid size per instrument-timeframe: {g.size():,}")
    t0 = time.time()
    df = sweep("BTC", 30, Grid(atr_len=(20,), atr_mult=(1.5, 2.0), pyr=((0.0, 1),),
                               tp_r=(0.0, 2.0), use_chan_exit=(True,), armed_stop=(False,),
                               exit_len=(3, 6), entry1=(6, 10), entry2=(12, 24)),
               keep_top=0)
    print(f"smoke: {len(df)} rows in {time.time() - t0:.1f}s")
    print(df.sort_values("sharpe", ascending=False).head(8).to_string(index=False))
