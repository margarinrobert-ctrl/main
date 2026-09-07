"""Daily P&L streams for every candidate strategy, on one shared session calendar.

The portfolio question only becomes answerable once every strategy is expressed as the same object:
dollars per session, per one contract, on the same 765 trading days. That is what this file builds.

A leg is included if it can be SPECIFIED and RUN, not if it was profitable. Several of these lose
money on their own -- the whole point of the exercise is whether combining them does anything, and a
correlation matrix built only from winners is a survivorship-biased correlation matrix.

Usage: python3 research/portfolio_legs.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import smc
from cmf_maxai import CMF_LEN, CMF_THRESH, cmf
from cmf_maxai import load as cmf_load
from cmf_maxai import simulate_hold
from grid import CONST
from ib_sim import simulate as ib_simulate
from nqdata import (load_bars, minute_of_day, minutes_since_open, session_index, session_slice)
from trend_pullback import load as tp_load
from trend_pullback import run as tp_run
from trend_pullback import spec as tp_spec

POINT_VALUE = 20.0
COST = 19.00
RTH_START, RTH_END = 570, 960


def _ib_bars(end_min):
    """The IB study's own loading: pre-sliced session, so exit_mso lines up bar-for-bar.

    This matters. A full-RTH series with exit_mso=149 books one extra management bar against the
    pre-sliced 09:30-11:59 series and moves the validated configuration from $25,777 to $29,657 --
    13%. The pre-sliced form is the one the published figures were measured on.
    """
    seg = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, end_min)
    mod = minute_of_day(seg.index)
    return (seg["open"].to_numpy(np.float64), seg["high"].to_numpy(np.float64),
            seg["low"].to_numpy(np.float64), seg["close"].to_numpy(np.float64),
            session_index(seg.index, RTH_START),
            minutes_since_open(mod, RTH_START).astype(np.int64),
            np.zeros(len(seg))), seg


def _daily(sess_of_trade, pnl, all_days):
    s = pd.Series(pnl, index=sess_of_trade).groupby(level=0).sum()
    return s.reindex(all_days, fill_value=0.0)


def build() -> pd.DataFrame:
    # a single canonical calendar, from the full RTH session
    full = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    all_days = np.unique(session_index(full.index, RTH_START))
    day_ts = pd.Series(full.index, index=session_index(full.index, RTH_START)).groupby(level=0).first()

    legs: dict[str, pd.Series] = {}

    # ---------- initial-balance family (09:30-11:59 slice) ----------
    bars_ib, _ = _ib_bars(719)
    IB = dict(retr=(60, 50.0, 80.0, 2.0), breakout=(60, 0.0, 80.0, 2.0))
    for name, (ibm, retr, stop, rr) in IB.items():
        r = ib_simulate(*bars_ib, ibm, retr, stop, rr, 0, 0, 0, 1.5, 40.0, 0, 10.0, 50.0, 149, *CONST)
        ent, _, _, _, _, pnl, _, _ = r
        legs[f"IB_{name}"] = _daily(bars_ib[4][ent], pnl, all_days)

    # ---------- opening-range family: the same engine with a shorter window ----------
    for mins, nm in ((15, "ORB15"), (5, "ORB5")):
        r = ib_simulate(*bars_ib, mins, 0.0, 80.0, 2.0, 0, 0, 0, 1.5, 40.0, 0, 10.0, 50.0, 149, *CONST)
        ent, _, _, _, _, pnl, _, _ = r
        legs[nm] = _daily(bars_ib[4][ent], pnl, all_days)

    # ---------- MaxAI / CMF with the $900-$1,500 barrier ----------
    seg, o, h, l, c, v, sess, m, sig = cmf_load()
    side, ti, to, pnl, why = simulate_hold(o, h, l, c, sess, sig, 45.0, 75.0, COST)
    legs["CMF_barrier"] = _daily(sess[ti], pnl, all_days)

    # ---------- trend / pullback family (EMA, VWAP, ATR-regime variants) ----------
    d = tp_load()
    TP = {
        "EMA_pullback": tp_spec(),
        "EMA_slope": tp_spec(trend_mode=1),
        "VWAP_trend": tp_spec(trend_mode=2),
        "VWAP_band": tp_spec(pull_mode=1, pull_depth=1.0),
        "ATR_highvol": tp_spec(atr_lo=0.5, atr_hi=1.0),
        "Trend_toclose": tp_spec(target_mode=2),
    }
    for nm, p in TP.items():
        s2, t2, o2, p2, r2, w2 = tp_run(d, p)
        legs[nm] = _daily(d["sess"][t2], p2, all_days)

    # ---------- smart money concepts: fresh bullish/bearish BOS with an ATR barrier ----------
    atr = smc.atr_series(h, l, c, 30)
    ph, pl, phi, pli = smc.swing_pivots(h, l, 3)
    bos, choch, bias, sbos, schoch = smc.structure(c, ph, pl)
    smc_sig = np.where((bias == 1) & (sbos < 10), 1,
                       np.where((bias == -1) & (sbos < 10), -1, 0)).astype(np.int64)
    s3, t3, o3, p3, w3 = simulate_hold(o, h, l, c, sess, smc_sig, 45.0, 75.0, COST)
    legs["SMC_BOS"] = _daily(sess[t3], p3, all_days)

    df = pd.DataFrame(legs, index=all_days)
    df.index.name = "session"
    df["ts"] = day_ts.reindex(all_days).values
    return df


if __name__ == "__main__":
    df = build()
    out = "research/portfolio_daily.parquet"
    df.to_parquet(out)
    n = df.drop(columns="ts")
    print(f"  {len(df)} sessions x {n.shape[1]} strategy legs -> {out}\n")
    print(f"  {'leg':<16}{'total $':>12}{'$/day':>9}{'active days':>13}{'daily sd':>10}{'Sharpe':>8}")
    for col in n.columns:
        s = n[col]
        sh = s.mean() / s.std() * np.sqrt(252) if s.std() > 0 else 0
        print(f"  {col:<16}{s.sum():>12,.0f}{s.mean():>9.2f}{(s != 0).sum():>13,}"
              f"{s.std():>10.0f}{sh:>8.2f}")
