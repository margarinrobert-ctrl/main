"""The analysis pipeline: search size, direction control, coherence, finalists, locked read.

Run as `python3 research/turtle_report.py <phase>`.  Phases 1-3 touch the research block only.
Phase 4 is the locked read and is deliberately a separate command.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_search as S
import turtle_select as SEL
import turtle_sim as T
import turtle_tensor as X
import turtle_validate as V
from turtle_sim import P

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")
pd.set_option("display.width", 220)


# ================================================================= phase 1

def degeneracy(df: pd.DataFrame) -> float:
    """Distinct outcomes per configuration among the kept rows.

    Large parts of the grid do not bind.  With `use_chan_exit = false` the two exit lengths are
    dead parameters, so 21 exit pairings collapse to one; with `skip_win = false` and a short
    System 1 channel the System 2 length rarely changes a decision.  The number of INDEPENDENT
    trials is therefore far below the number of cells, and every multiplicity correction that uses
    the cell count is correspondingly conservative.  This measures the collapse where it matters --
    among the best rows, which is where the maximum comes from.
    """
    key = df[["n", "net"]].round(6).astype(str).agg("|".join, axis=1)
    return float(key.nunique() / max(len(df), 1))


def phase1() -> None:
    meta = SEL.load_meta()
    print("=" * 118)
    print("PHASE 1 -- how big was the search, and what did each side of it find?")
    print("=" * 118)
    rows = []
    for _, m in meta.sort_values(["instrument", "tf", "side"]).iterrows():
        tag = f"{m.instrument}_{m.tf}m_{'long' if m.side > 0 else 'short'}"
        f = os.path.join(OUT, tag + ".parquet")
        if not os.path.exists(f):
            continue
        df = pd.read_parquet(f)
        spy = M.SESSIONS_PER_YEAR[m.instrument]
        thr = V.expected_max_sharpe(int(m.n_evaluated), m.trial_sharpe_sd / math.sqrt(spy))
        rows.append({
            "instrument": m.instrument, "tf": m.tf,
            "side": "long" if m.side > 0 else "short",
            "cells": int(m.n_evaluated), "scored": int(m.n_scored),
            "best_sharpe": m.trial_sharpe_max, "trial_sd": m.trial_sharpe_sd,
            "noise_bar": thr * math.sqrt(spy),
            "distinct": degeneracy(df),
            "best_excess": float(df.ex_per_trade.max()),
            "sec": int(m.seconds),
        })
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\n  total cells evaluated: {t.cells.sum():,}")
    print("  `noise_bar` is E[max Sharpe] over that many INDEPENDENT trials at the observed trial")
    print("  dispersion.  The trials are not independent -- `distinct` shows how far from it they")
    print("  are among the kept rows -- so the bar is an upper bound and a best Sharpe below it is")
    print("  decisive in one direction only: it cannot be called a finding.")

    print("\n--- direction control: what a search of the same size finds on each side ---")
    piv = t.pivot_table(index=["instrument", "tf"], columns="side",
                        values=["best_sharpe", "best_excess"])
    print(piv.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\n  CLAUDE.md 4c: a long-only search on a sample that rose finds the sample, and every")
    print("  holdout agrees with it.  If the short mirror scores as well as the long side, the")
    print("  search is measuring its own size, not a direction.")


# ================================================================= phase 2

def phase2(per_instrument: int = 2500, min_trades: int = 150) -> None:
    """Re-evaluate the union of every instrument's proposals on every instrument."""
    sweeps = SEL.load_sweeps(side=1)
    print("=" * 118)
    print("PHASE 2 -- cross-instrument coherence on the research block")
    print("=" * 118)
    store = {}
    for tf in sorted(sweeps.tf.unique()):
        insts = sorted(sweeps[sweeps.tf == tf].instrument.unique())
        if len(insts) < 2:
            continue
        cand = SEL.top_union(sweeps, tf, per_instrument=per_instrument)
        print(f"\n### {tf}m -- {len(cand):,} distinct candidates, re-scored on {insts}")
        per = {nm: SEL.evaluate(nm, tf, cand) for nm in insts}
        j = SEL.coherence(per, min_trades=min_trades)
        if not len(j):
            print("   no configuration is evaluable on every instrument")
            continue
        ok = j[j.all_positive_excess & j.all_positive_sharpe & j.all_enough_trades]
        print(f"   {len(j):,} scored on all {len(insts)};  {len(ok):,} clear every instrument's "
              f"own control with a positive Sharpe and >= {min_trades} trades")
        # A three-way agreement is the goal, but its absence is a result rather than a dead end:
        # report which pairs agree so the study can say whether the structure travels at all.
        for a in insts:
            for b in insts:
                if a >= b:
                    continue
                pair_ok = j[(j[f"ex_per_trade__{a}"] > 0) & (j[f"ex_per_trade__{b}"] > 0)
                            & (j[f"sharpe__{a}"] > 0) & (j[f"sharpe__{b}"] > 0)
                            & (j[f"n__{a}"] >= min_trades) & (j[f"n__{b}"] >= min_trades)]
                print(f"     pair {a}+{b}: {len(pair_ok):,} agree "
                      f"({len(pair_ok) / max(len(j), 1):.1%} of scored)")
        if len(ok):
            cols = SEL.KEY + [f"sharpe__{nm}" for nm in insts] + \
                   [f"ex_per_trade__{nm}" for nm in insts] + ["median_sharpe", "worst_sharpe"]
            print(ok.sort_values("median_sharpe", ascending=False).head(12)[cols]
                  .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        store[tf] = j
        j.to_parquet(os.path.join(OUT, f"coherence_{tf}m.parquet"), index=False)
    return store


# ================================================================= phase 3

def phase3(tf: int, top: int = 12, draws: int = 400) -> pd.DataFrame:
    """Full validation of the coherent finalists: draw-based controls, neighbourhood, PBO, WF."""
    j = pd.read_parquet(os.path.join(OUT, f"coherence_{tf}m.parquet"))
    insts = sorted({c.split("__")[1] for c in j.columns if c.startswith("sharpe__")})
    ok = j[j.all_positive_excess & j.all_positive_sharpe & j.all_enough_trades]
    if not len(ok):
        print(f"no coherent candidate at {tf}m")
        return pd.DataFrame()
    fin = ok.sort_values("median_sharpe", ascending=False).head(top)
    print("=" * 118)
    print(f"PHASE 3 -- {len(fin)} finalists at {tf}m, research block, full controls")
    print("=" * 118)

    rows = []
    for rank, (_, r) in enumerate(fin.iterrows(), 1):
        print(f"\n--- finalist {rank}: " + "  ".join(f"{k}={r[k]}" for k in SEL.KEY))
        rec = {**{k: r[k] for k in SEL.KEY}, "rank": rank, "tf": tf}
        for nm in insts:
            spec = B.INSTRUMENTS[nm]
            full = B.load(nm, tf)
            cut = B.split_session(full)
            s = full.window(S.WIN_LO, S.WIN_HI).slice_sessions(0, cut)
            p = S.to_params(_as_row(r, tf), spec)
            st, ex = V.full_control(s, p, spec, 0, cut, nm, draws=draws)
            slot, _ = X.vol_slot(s, p.atr_len)
            trig = T.signal_bars(s, p)
            exi = X.build(s, p)
            ctrl_v = X.Control(s, trig, seed=20250822, slot=slot)
            bank_v = M.control_bank(s, exi, ctrl_v, p, spec, 0, cut, nm, draws=draws)
            exv = M.excess(st, bank_v)
            print(f"   {nm:<5} {M.fmt(st)}")
            print(f"         clock control  /trade ${ex.get('ctrl_per_trade', 0):>8.2f}  "
                  f"excess ${ex.get('ex_per_trade', 0):>8.2f} p {ex.get('p_per_trade', 1):.4f}   "
                  f"Sharpe excess {ex.get('ex_sharpe', 0):>5.2f} p {ex.get('p_sharpe', 1):.4f}")
            print(f"         vol-matched    /trade ${exv.get('ctrl_per_trade', 0):>8.2f}  "
                  f"excess ${exv.get('ex_per_trade', 0):>8.2f} p {exv.get('p_per_trade', 1):.4f}  "
                  f" Sharpe excess {exv.get('ex_sharpe', 0):>5.2f} p {exv.get('p_sharpe', 1):.4f}")
            for k, v in st.items():
                rec[f"{k}__{nm}"] = v
            rec[f"ex_pt__{nm}"] = ex.get("ex_per_trade", 0)
            rec[f"p_pt__{nm}"] = ex.get("p_per_trade", 1)
            rec[f"exv_pt__{nm}"] = exv.get("ex_per_trade", 0)
            rec[f"pv_pt__{nm}"] = exv.get("p_per_trade", 1)
            rec[f"p_sharpe__{nm}"] = ex.get("p_sharpe", 1)
            rec[f"pv_sharpe__{nm}"] = exv.get("p_sharpe", 1)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(OUT, f"finalists_{tf}m.parquet"), index=False)
    return df


def _as_row(r: pd.Series, tf: int) -> pd.Series:
    d = {k: r[k] for k in SEL.KEY}
    d.update(sess_start=420, sess_end=660, flatten_min=660, side=1, tf=tf)
    return pd.Series(d)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "1"
    if which == "1":
        phase1()
    elif which == "2":
        phase2()
    elif which == "3":
        phase3(int(sys.argv[2]))
