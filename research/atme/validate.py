"""Validation for an ATME configuration: out-of-sample, plateau, cost stress, Monte Carlo.

Everything here takes a configuration already frozen on the research block. The one addition over
the earlier validators is a MECHANIC-ISOLATION test: the same configuration is re-run with only
the entry mechanic swapped back to a market order, so the limit/stop mechanic's contribution is
measured on its own rather than inferred from the total.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import feeds, fast
from scalp import core
from hypo.metrics import suite
from atme.engine import walk, MARKET, LIMIT, STOPENTRY
from atme.sweep import WINDOW, signal_mask

MODE = {"market": MARKET, "limit": LIMIT, "stop": STOPENTRY}


def evaluate(inst, tf, cfg, block="research", cost_mult=1.0, stride=1, min_trades=40,
             force_market=False):
    lo, hi = WINDOW
    d = feeds.bars(inst, tf)
    B = core.blocks(inst, d)
    if block not in B or B[block].sum() == 0:
        return None
    days = fast.day_index(d)
    ck = core.COSTS[inst]
    hs = ck.spread_at(d["mod"]) * cost_mult
    m = signal_mask(d, cfg["signal"]) & B[block]
    m[:300] = False
    trig = np.flatnonzero(m & np.isfinite(d["atr"]) & (d["atr"] > 0)).astype(np.int64)
    if stride > 1:
        trig = trig[::stride]
    if len(trig) < min_trades:
        return None
    em = MARKET if force_market else MODE[cfg["entry_mode"]]
    R, filled, why, held, mfe, mae = walk(
        d["o"], d["h"], d["l"], d["c"], d["atr"], np.asarray(d["mod"], np.int64), trig,
        np.int64(em), float(cfg["entry_k"]), np.int64(cfg["entry_wait"]),
        float(cfg["stop_atr"]), float(cfg["trail_atr"]), float(cfg["be_trig"]), 0.0,
        float(cfg["tp_r"]), float(cfg["partial"]), float(cfg["partial_r"]),
        np.int64(cfg["hold"]), np.int64(hi), 0.0, np.int64(cfg["give_up_bar"]),
        hs, ck.slip_entry * cost_mult, ck.slip_stop * cost_mult, ck.commission * cost_mult)
    got = filled == 1
    if got.sum() < min_trades:
        return None
    s = suite(R[got], days[trig][:len(R)][got], min_trades=min_trades)
    if s:
        s["fill_rate"] = 100.0 * float(got.mean())
        s["market"] = inst
        s["block"] = block
    return s


def blocks_table(cfg, markets, stride=1):
    rows = []
    for inst, tf in markets:
        for bn in ("research", "validation", "test", "untouched", "oos"):
            s = evaluate(inst, tf, cfg, block=bn, stride=stride)
            if s:
                rows.append(s)
    return pd.DataFrame(rows)


def mechanic_isolation(cfg, markets, block="research", stride=1):
    """How much of the result is the entry MECHANIC rather than everything else?"""
    rows = []
    for inst, tf in markets:
        a = evaluate(inst, tf, cfg, block, stride=stride)
        b = evaluate(inst, tf, cfg, block, stride=stride, force_market=True)
        if a and b:
            rows.append(dict(market=inst,
                             with_mechanic=a["expR"], as_market=b["expR"],
                             delta=a["expR"] - b["expR"],
                             fill_rate=a["fill_rate"],
                             n_mech=a["n"], n_market=b["n"]))
    return pd.DataFrame(rows)


def plateau(cfg, markets, block="research", stride=1):
    """Neighbourhood in the two continuous knobs that matter: entry offset and stop width."""
    rows = []
    for inst, tf in markets:
        for ek in (cfg["entry_k"] * f for f in (0.5, 0.75, 1.0, 1.25, 1.5)):
            for sk in (cfg["stop_atr"] * f for f in (0.5, 0.75, 1.0, 1.5, 2.0)):
                c2 = dict(cfg); c2["entry_k"] = ek; c2["stop_atr"] = sk
                s = evaluate(inst, tf, c2, block, stride=stride)
                rows.append(dict(market=inst, entry_k=round(ek, 3), stop_atr=round(sk, 3),
                                 expR=(s["expR"] if s else np.nan)))
    df = pd.DataFrame(rows)
    return df, float((df["expR"] > 0).mean())


def cost_stress(cfg, markets, mults=(0.5, 1.0, 1.5, 2.0), block="research", stride=1):
    rows = []
    for mult in mults:
        for inst, tf in markets:
            s = evaluate(inst, tf, cfg, block, cost_mult=mult, stride=stride)
            rows.append(dict(cost_mult=mult, market=inst,
                             expR=(s["expR"] if s else np.nan)))
    return pd.DataFrame(rows).pivot(index="cost_mult", columns="market", values="expR")
