"""~100,000 Turtle variants per instrument, scored on the RESEARCH block only.

THE GRID (timeframe is a parameter, not an assumption -- the spec indexes bars, so its "20-day
high" means 20 bars and the right bar size is an open question):

    timeframe        15, 30, 60, 120, 240, 1440 minutes
    entry1           10, 15, 20, 25, 30
    entry2           40, 55, 70, 90
    exit1            5, 10, 15, 20
    exit2            10, 20, 30
    atr_mult         1.0, 1.5, 2.0, 2.5, 3.0, 4.0
    pyramid_step     0 (off), 0.25, 0.5, 1.0
    max_units        1, 2, 4
    skip_after_winner  on, off

Redundant points are collapsed: with pyramiding off, `max_units` does nothing, so only one
representative of that family is enumerated. The distinct count is printed and carried into every
later p-value, because a number selected out of ~100,000 is not the number it appears to be.

Nothing here reads any out-of-sample block.
"""
from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from turtle import core, data as td

TFS = (15, 30, 60, 120, 240, 1440)
GRID = dict(entry1=(10, 15, 20, 25, 30), entry2=(40, 55, 70, 90),
            exit1=(5, 10, 15, 20), exit2=(10, 20, 30),
            atr_mult=(1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
            pyramid=((0.0, 1), (0.25, 2), (0.25, 4), (0.5, 2), (0.5, 4), (1.0, 2), (1.0, 4)),
            skip=(True, False))
MIN_TRADES = 30


def combos():
    for e1, e2, x1, x2, am, (ps, mu), sk in itertools.product(
            GRID["entry1"], GRID["entry2"], GRID["exit1"], GRID["exit2"],
            GRID["atr_mult"], GRID["pyramid"], GRID["skip"]):
        yield dict(entry1=e1, entry2=e2, exit1=x1, exit2=x2, atr_mult=am,
                   pyramid_step=ps, max_units=mu, skip_after_winner=sk)


def sweep(inst, verbose=True):
    ck = td.COSTS[inst]
    rows = []
    n_cfg = sum(1 for _ in combos())
    for tf in TFS:
        try:
            d = td.bars(inst, tf)
        except Exception as e:
            if verbose:
                print(f"  {inst} {tf}m unavailable ({str(e)[:40]})", flush=True)
            continue
        if len(d["c"]) < 400:
            if verbose:
                print(f"  {inst} {tf}m only {len(d['c'])} bars -- skipped", flush=True)
            continue
        B = td.blocks(inst, d)
        cache = {}
        got = 0
        for cfg in combos():
            r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"],
                              slip_pts=ck["slip_pts"], cache=cache, **cfg)
            sel = td.split_trades(r, B["research"])
            if sel.sum() < MIN_TRADES:
                continue
            s = td.stats(r, sel, ck["point_value"])
            s.update(cfg); s["tf"] = tf; s["inst"] = inst
            rows.append(s); got += 1
        if verbose:
            print(f"  {inst} {tf:>4}m: {got:>6} of {n_cfg} configs had >={MIN_TRADES} "
                  f"research trades", flush=True)
    df = pd.DataFrame(rows)
    if len(df):
        df["tested"] = len(df)
    return df


def main():
    out = {}
    for inst in ("NQ", "US100"):
        print(f"\n{inst}")
        df = sweep(inst)
        df.to_parquet(f"research/turtle/_sweep_{inst}.parquet")
        out[inst] = df
        print(f"  -> {len(df):,} scored configurations")
        if len(df):
            top = df.sort_values("expR", ascending=False).head(10)
            cols = ["tf", "entry1", "entry2", "exit1", "exit2", "atr_mult", "pyramid_step",
                    "max_units", "skip_after_winner", "n", "win", "expR", "totalR", "pf", "maxdd_R"]
            print(top[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    return out


if __name__ == "__main__":
    main()
