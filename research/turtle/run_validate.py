"""Stage 2: does the BREAKOUT do anything, and does any variant survive out of sample?

The ranking statistic is not research expectancy -- that buys small samples, and on this sweep the
argmax is a 30-trade daily configuration. It is EXCESS OVER A RANDOM-ENTRY CONTROL that uses the
variant's own exit machinery, stop, pyramid ladder and costs. If a Turtle variant cannot beat
"enter at random, manage it exactly the same way", then its result belongs to the exits and to the
market's drift, not to the channel breakout the strategy is named for.

Candidates are then deduplicated by trade-set overlap and only the survivors are taken out of
sample.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from turtle import core, data as td

CFG_KEYS = ("entry1", "entry2", "exit1", "exit2", "atr_mult",
            "pyramid_step", "max_units", "skip_after_winner")


def cfg_of(row):
    c = {k: row[k] for k in CFG_KEYS}
    c["entry1"] = int(c["entry1"]); c["entry2"] = int(c["entry2"])
    c["exit1"] = int(c["exit1"]); c["exit2"] = int(c["exit2"])
    c["max_units"] = int(c["max_units"]); c["skip_after_winner"] = bool(c["skip_after_winner"])
    return c


def with_control(inst, df, top=250, draws=150, verbose=True):
    ck = td.COSTS[inst]
    out = []
    for tf, sub in df.groupby("tf"):
        d = td.bars(inst, int(tf))
        B = td.blocks(inst, d)
        cache = {}
        cand = sub.sort_values("expR", ascending=False).head(top)
        for _, row in cand.iterrows():
            cfg = cfg_of(row)
            r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"],
                              cache=cache, **cfg)
            sel = td.split_trades(r, B["research"])
            s = td.stats(r, sel, ck["point_value"])
            if s is None or s["n"] < 30:
                continue
            c = core.control(d, cfg, B["research"], s["n"], draws=draws,
                             cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], cache=cache)
            if c is None or len(c) < 20:
                continue
            s.update(cfg); s["tf"] = int(tf); s["inst"] = inst
            s["ctrl_expR"] = float(c.mean()); s["ctrl_sd"] = float(c.std())
            s["excess"] = s["expR"] - float(c.mean())
            s["p_ctrl"] = float((c >= s["expR"]).mean())
            out.append(s)
        if verbose:
            print(f"  {inst} {int(tf):>4}m: {len(cand)} candidates controlled", flush=True)
    return pd.DataFrame(out)


def dedupe(inst, df, k=6, jac=0.6):
    """Collapse variants whose research trade sets largely coincide."""
    ck = td.COSTS[inst]
    kept = []
    sets = []
    for _, row in df.sort_values("excess", ascending=False).iterrows():
        d = td.bars(inst, int(row["tf"]))
        B = td.blocks(inst, d)
        cfg = cfg_of(row)
        r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], **cfg)
        sel = td.split_trades(r, B["research"])
        ts = set(zip(r["bar_in"][sel].tolist(), [int(row["tf"])] * int(sel.sum())))
        if any(len(ts & o) / max(len(ts | o), 1) > jac for o in sets):
            continue
        sets.append(ts); kept.append(row)
        if len(kept) >= k:
            break
    return pd.DataFrame(kept)


def out_of_sample(inst, df, draws=200):
    ck = td.COSTS[inst]
    rows = []
    for _, row in df.iterrows():
        d = td.bars(inst, int(row["tf"]))
        B = td.blocks(inst, d)
        cfg = cfg_of(row)
        r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], **cfg)
        rec = dict(inst=inst, tf=int(row["tf"]), **cfg)
        for bn in [b for b in ("research", "validation", "production", "oos") if b in B]:
            sel = td.split_trades(r, B[bn])
            s = td.stats(r, sel, ck["point_value"])
            if s is None or s["n"] < 10:
                rec[f"{bn}_n"] = int(sel.sum())
                continue
            c = core.control(d, cfg, B[bn], s["n"], draws=draws,
                             cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"])
            rec[f"{bn}_n"] = s["n"]; rec[f"{bn}_win"] = s["win"]
            rec[f"{bn}_expR"] = s["expR"]; rec[f"{bn}_pf"] = s["pf"]
            if c is not None and len(c) >= 20:
                rec[f"{bn}_ctrl"] = float(c.mean())
                rec[f"{bn}_exc"] = s["expR"] - float(c.mean())
                rec[f"{bn}_p"] = float((c >= s["expR"]).mean())
        rows.append(rec)
    return pd.DataFrame(rows)


def main():
    pd.set_option("display.width", 250)
    finals = {}
    for inst in ("NQ", "US100"):
        df = pd.read_parquet(f"research/turtle/_sweep_{inst}.parquet")
        print(f"\n{inst}: {len(df):,} scored configurations on the research block")
        ctl = with_control(inst, df)
        if not len(ctl):
            continue
        ctl.to_parquet(f"research/turtle/_ctl_{inst}.parquet")
        beat = (ctl["excess"] > 0).sum()
        print(f"  of {len(ctl)} controlled candidates, {beat} beat their random-entry control "
              f"({100.0*beat/len(ctl):.0f}%), {int((ctl['p_ctrl']<0.05).sum())} at p<0.05")
        print(f"  median excess {ctl['excess'].median():+.3f} R/trade")
        short = dedupe(inst, ctl)
        cols = ["tf", "entry1", "entry2", "exit1", "exit2", "atr_mult", "pyramid_step",
                "max_units", "skip_after_winner", "n", "win", "expR", "ctrl_expR",
                "excess", "p_ctrl"]
        print("\n  distinct candidates, ranked by excess over the control (RESEARCH):")
        print(short[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        oos = out_of_sample(inst, short)
        finals[inst] = oos
        print(f"\n  OUT OF SAMPLE:")
        show = [c for c in oos.columns if c.split("_")[0] in
                ("research", "validation", "production", "oos") or c in ("tf",)]
        print(oos[["tf"] + [c for c in show if c != "tf"]].to_string(
            index=False, float_format=lambda x: f"{x:.3f}"))
        oos.to_parquet(f"research/turtle/_oos_{inst}.parquet")
    return finals


if __name__ == "__main__":
    main()
