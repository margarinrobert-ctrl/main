"""Validate the market-neutral candidates on research-B, which nothing has selected on.

THE RULE, FIXED BEFORE research-B IS READ
-----------------------------------------
On **research-A** only, keep configurations that clear all of:

    n >= 300 trades            enough to measure
    profit factor >= 1.05      the protocol's floor
    control excess > 0         the entry rule beats a matched random entry
    |beta to market| <= 0.30   what the whole exercise is for
    neighbourhood not a spike  one-step neighbours re-simulated, median >= 0.5x the base

and rank the survivors by **residual Sharpe** -- the Sharpe of what is left after the session's own
07:00-11:00 market move is regressed out.  Take the top one.

Then read research-B once, for that candidate and for the previously shipped 15m champion side by
side.

**The two are not like for like, and the difference matters.** research-B is genuinely
out-of-sample for the new candidate, which was selected on research-A alone.  It is *in-sample* for
the shipped champion, which was selected on the whole research block, research-B included.  So the
champion's research-B number is not evidence about the champion; it is only there as the scale
against which to read the new candidate's.

Two things this deliberately does NOT do.  It does not rank on raw Sharpe: that is the objective
that produced a champion whose holdout profit was 87% market exposure.  And it does not touch the
locked block, which has already been read once and can no longer arbitrate anything.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_neutral as N
import turtle_nsearch as NS
import turtle_sim as T
import turtle_validate as V
from turtle_sim import P

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")
pd.set_option("display.width", 240)

MIN_TRADES = 300
MIN_PF = 1.05
MAX_BETA = 0.30
TOP = 40


def spike_test(name: str, tf: int, p: P, lo: int, hi: int) -> dict:
    """Re-simulate the one-step neighbours on research-A and score them on residual Sharpe."""
    base = NS.evaluate_one(name, tf, p, lo, hi)
    vals = []
    for _, q in V.step_neighbours(p):
        st = NS.evaluate_one(name, tf, q, lo, hi)
        if st.get("n", 0) >= 50:
            vals.append(st["resid_sharpe"])
    if not vals:
        return {"verdict": "unknown", "stability": float("nan"), "neighbours": 0,
                "base": base.get("resid_sharpe", 0.0)}
    b = base.get("resid_sharpe", 0.0)
    ratio = float(np.median(vals) / b) if b > 0 else float("nan")
    verdict = "spike" if (not np.isfinite(ratio) or ratio < 0.5) else \
              ("ridge" if ratio < 0.8 else "plateau")
    return {"verdict": verdict, "stability": ratio, "neighbours": len(vals),
            "base": b, "median": float(np.median(vals)),
            "share_positive": float(np.mean(np.array(vals) > 0))}


def pick(name: str, tf: int, side: int = 1, verbose: bool = True):
    tag = f"N_{name}_{tf}m_{'long' if side > 0 else 'short'}"
    df = pd.read_parquet(os.path.join(OUT, tag + ".parquet"))
    a, b, n = N.split_ab(name, tf)
    spec = B.INSTRUMENTS[name]
    g = df[(df.n >= MIN_TRADES) & (df.pf >= MIN_PF) & (df.ex_per_trade > 0)
           & (df.beta_mkt.abs() <= MAX_BETA)]
    if verbose:
        print(f"\n--- {tag}: {len(df):,} kept rows, {len(g):,} clear the research-A gates "
              f"(n>={MIN_TRADES}, PF>={MIN_PF}, excess>0, |beta|<={MAX_BETA})")
    if not len(g):
        return None, pd.DataFrame()
    g = g.sort_values("resid_sharpe", ascending=False).drop_duplicates(subset=["n", "net"])
    g = g.head(TOP)
    rows = []
    for _, r in g.iterrows():
        p = NS.to_params(r, spec)
        sp = spike_test(name, tf, p, 0, a)
        rows.append({"atr_len": r.atr_len,
                     "entry1": r.entry1, "entry2": r.entry2, "exit1": r.exit1, "exit2": r.exit2,
                     "atr_mult": r.atr_mult, "tp_r": r.tp_r, "max_hold": r.max_hold,
                     "pyr_step": r.pyr_step, "max_units": r.max_units,
                     "use_chan_exit": r.use_chan_exit, "armed_stop": r.armed_stop,
                     "chan_shift": r.chan_shift, "skip_win": r.skip_win,
                     "n": r.n, "sharpe": r.sharpe, "resid_sharpe": r.resid_sharpe,
                     "beta": r.beta_mkt, "corr": r.corr_mkt, "beta_share": r.beta_pnl_share,
                     "pf": r.pf, "net": r.net, "excess": r.ex_per_trade,
                     "stability": sp["stability"], "verdict": sp["verdict"]})
    tbl = pd.DataFrame(rows)
    ok = tbl[tbl.verdict != "spike"]
    if verbose:
        print(f"    {len(tbl)} distinct candidates, {len(ok)} survive the spike test")
        print(tbl.head(10).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if not len(ok):
        return None, tbl
    best = ok.sort_values("resid_sharpe", ascending=False).iloc[0]
    return NS.to_params(_as_row(best, name, tf, side), B.INSTRUMENTS[name]), tbl


def _as_row(r, name, tf, side) -> pd.Series:
    d = dict(r)
    d.update(sess_start=420, sess_end=660, flatten_min=660, side=side, one_shot=False)
    return pd.Series(d)


def report(name: str, tf: int, cands: dict[str, P]) -> pd.DataFrame:
    a, b, n = N.split_ab(name, tf)
    rows = []
    for label, p in cands.items():
        for blk, lo, hi in (("research-A (selected on)", 0, a),
                            ("research-B (untouched)", a, b)):
            st = NS.evaluate_one(name, tf, p, lo, hi)
            if not st.get("n"):
                continue
            rows.append({"candidate": label, "block": blk, "n": st["n"], "net": st["net"],
                         "per_trade": st["per_trade"], "sharpe": st["sharpe"],
                         "resid_sharpe": st["resid_sharpe"], "corr": st["corr_mkt"],
                         "beta": st["beta_mkt"], "beta_share": st["beta_pnl_share"],
                         "pf": st["pf"], "maxdd": st["maxdd"], "mar": st["mar"],
                         "win": st["win_rate"], "hold": st["hold"]})
    return pd.DataFrame(rows)


def main() -> None:
    name, tf = "US30", 15
    a, b, n = N.split_ab(name, tf)
    print("=" * 116)
    print(f"MARKET-NEUTRAL SELECTION -- {name} {tf}m")
    print(f"  research-A sessions 0-{a} (selection)   research-B {a}-{b} (untouched)   "
          f"locked {b}-{n} (already read once, not used here)")
    print("=" * 116)

    long_p, long_tbl = pick(name, tf, 1)
    short_p, short_tbl = pick(name, tf, -1)

    cands: dict[str, P] = {}
    if long_p is not None:
        cands["neutral 15m long"] = long_p
    if short_p is not None:
        cands["neutral 15m SHORT (procedure control)"] = short_p
    old = P(**json.load(open(os.path.join(OUT, "chosen_US30_15m.json")))["params"])
    cands["shipped champion (ranked on raw Sharpe)"] = old

    print("\n" + "=" * 116)
    print("RESEARCH-B -- the first and only read of this block")
    print("=" * 116)
    rep = report(name, tf, cands)
    print(rep.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    rep.to_parquet(os.path.join(OUT, "neutral_validation.parquet"), index=False)
    for label, p in cands.items():
        print(f"\n  {label}:\n    {p}")


if __name__ == "__main__":
    main()
