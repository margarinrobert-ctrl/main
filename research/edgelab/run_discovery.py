"""Stage 1: search the DISCOVERY block. Singles -> pairs -> triples, matched control throughout.

Runs over a GRID of geometries and windows rather than one, because the brief asks which stop,
which target and which part of the morning -- and because a condition that only works at one
geometry is a coincidence, not a mechanism (CLAUDE.md).

Nothing here reads validation or production.
"""
from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import data, features, labels, splits, discover, fast

WINDOWS = {"07:00-11:00": (420, 660), "09:30-11:00": (570, 660), "10:00-11:00": (600, 660)}
GEOMS = [(1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (2.5, 1.0), (1.5, 1.5), (2.0, 0.75)]


def bh(p, q=0.10):
    p = np.asarray(p, float); n = len(p)
    if n == 0:
        return np.zeros(0, bool)
    o = np.argsort(p); r = np.arange(1, n + 1)
    keep = p[o] <= q * r / n
    out = np.zeros(n, bool)
    if keep.any():
        out[o[:np.max(np.flatnonzero(keep)) + 1]] = True
    return out


def one(d, F, C, disc, stop_k, rr, lo, hi, max_hold=16, top1=30, top2=30, draws=150):
    P = labels.precompute(d, stop_k, rr=rr, max_hold=max_hold, lo=lo, hi=hi)
    win = (d["mod"] >= lo) & (d["mod"] < hi)
    s1 = fast.sweep(P, C, disc, draws=draws)
    if not len(s1):
        return pd.DataFrame()
    s1["stage"] = 1
    keep = s1.head(top1)["cond"].tolist()
    pairs = {}
    for a, b in itertools.combinations(keep, 2):
        m = C[a] & C[b] & win
        if m.sum() >= 150:
            pairs[f"{a} AND {b}"] = m
    s2 = fast.sweep(P, pairs, disc, draws=draws) if pairs else pd.DataFrame()
    if len(s2):
        s2["stage"] = 2
    trips = {}
    for pn in (s2.head(top2)["cond"].tolist() if len(s2) else []):
        a, b = pn.split(" AND ")
        for cnd in keep:
            if cnd in (a, b):
                continue
            m = C[a] & C[b] & C[cnd] & win
            if m.sum() >= 150:
                trips[f"{pn} AND {cnd}"] = m
    s3 = fast.sweep(P, trips, disc, draws=draws) if trips else pd.DataFrame()
    if len(s3):
        s3["stage"] = 3
    out = pd.concat([x for x in (s1, s2, s3) if len(x)], ignore_index=True)
    out["stop_atr"] = stop_k; out["rr"] = rr; out["win_lo"] = lo; out["win_hi"] = hi
    out["max_hold"] = max_hold
    return out


def main(out_path="research/edgelab/_discovery.parquet"):
    d = data.bars(15)
    F = features.build(d)
    B = splits.blocks(d)
    disc = B["discovery"]
    C = discover.conditions(F)
    print(f"{len(C)} conditions, {len(F)} features, discovery block "
          f"{int(disc.sum()):,} bars\n")
    frames = []
    for wname, (lo, hi) in WINDOWS.items():
        Cw = {k: (v & (d["mod"] >= lo) & (d["mod"] < hi)) for k, v in C.items()}
        for stop_k, rr in GEOMS:
            r = one(d, F, Cw, disc, stop_k, rr, lo, hi)
            if len(r):
                r["window"] = wname
                frames.append(r)
                b = r.iloc[0]
                print(f"  {wname}  stop {stop_k}xATR  target {rr}R   tested {len(r):>5}   "
                      f"best excess {r['excess'].max():>6.2f}   best E[R] {r['expR'].max():>+7.3f}",
                      flush=True)
    allr = pd.concat(frames, ignore_index=True)
    allr["tests_in_family"] = len(allr)
    allr["bh_pass"] = bh(allr["p_win"].to_numpy(), 0.10)
    allr.to_parquet(out_path)
    print(f"\nFAMILY SIZE {len(allr):,} tests across {len(WINDOWS)} windows x {len(GEOMS)} geometries")
    print(f"{int(allr['bh_pass'].sum())} pass Benjamini-Hochberg at q=0.10 on the control p-value")
    pos = allr[(allr["expR"] > 0) & (allr["n"] >= 150)]
    print(f"{len(pos)} have positive net expectancy with n>=150\n")
    cols = ["window", "stop_atr", "rr", "cond", "n", "win", "ctrl_win", "excess",
            "expR", "excess_R", "p_win", "ambig", "stage"]
    print("TOP 25 BY NET EXPECTANCY (discovery -- selection, not evidence)")
    print(allr[allr["n"] >= 150].sort_values("expR", ascending=False)
          .head(25)[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    return allr


if __name__ == "__main__":
    main()
