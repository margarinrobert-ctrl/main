"""Pick, refine, and read the locked block once.

The selection rule is the protocol's Stage 3, applied literally: the winner's Sharpe is not
evidence, it is the maximum of however many cells were tried, so what gets picked is not the
argmax but **the best candidate whose surface survives perturbation**.  Each of the top rows is
re-simulated against its own one-step neighbours and anything that reads as a spike is dropped
before ranking.

Then the session and gate axes are refined around that structure, and the whole thing is read once
on the locked block with the multiplicity printed first.

    python3 research/turtle_ship.py US30 30            # research only, prints the choice
    python3 research/turtle_ship.py US30 30 --reveal   # ... and reads the locked block
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_final as F
import turtle_refine as R
import turtle_search as S
import turtle_select as SEL
import turtle_sim as T
import turtle_validate as V
from turtle_sim import P

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")
pd.set_option("display.width", 220)


def total_trials() -> int:
    """Every configuration this study has evaluated, across every phase.

    Reported before any locked number.  A deflation that uses only the last phase's grid is not a
    deflation; the search that produced the candidate includes the phases that narrowed it.
    """
    meta = SEL.load_meta()
    k = int(meta.n_evaluated.sum()) if len(meta) else 0
    # phase 2 re-evaluations, phase 3 neighbourhoods and the refine grids are added by the caller
    return k


def pick(name: str, tf: int, top: int = 40, min_trades: int = 250, min_pf: float = 1.05,
         verbose: bool = True) -> tuple[P, pd.DataFrame]:
    """The best candidate whose neighbourhood is not a spike."""
    df = pd.read_parquet(os.path.join(OUT, f"{name}_{tf}m_long.parquet"))
    spec = B.INSTRUMENTS[name]
    g = df[(df.n >= min_trades) & (df.ex_per_trade > 0) & (df.pf >= min_pf)]
    if not len(g):
        raise SystemExit(f"{name} {tf}m: nothing clears the research gates "
                         f"(n>={min_trades}, excess>0, PF>={min_pf})")
    g = g.sort_values("sharpe", ascending=False)
    # De-duplicate on the outcome: large parts of the grid do not bind, so the top rows are often
    # the same strategy written several ways, and testing fifteen copies of one surface is not a
    # robustness check.
    g = g.drop_duplicates(subset=["n", "net"]).head(top)
    rows = []
    for _, r in g.iterrows():
        p = S.to_params(_row(r, tf), spec)
        nb = V.neighbourhood_direct(name, tf, p, verbose=False)
        rows.append({**{k: r[k] for k in SEL.KEY}, "sharpe": r.sharpe, "pf": r.pf, "n": r.n,
                     "per_trade": r.per_trade, "ex_per_trade": r.ex_per_trade,
                     "stability": nb["stability"], "verdict": nb["verdict"],
                     "nb_median": nb["median"]})
    tbl = pd.DataFrame(rows)
    ok = tbl[tbl.verdict != "spike"]
    if verbose:
        print(f"\n--- {name} {tf}m: {len(tbl)} distinct top candidates, "
              f"{len(ok)} survive the spike test")
        print(tbl.head(12).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if not len(ok):
        raise SystemExit(f"{name} {tf}m: every top candidate is a spike")
    best = ok.sort_values("sharpe", ascending=False).iloc[0]
    return S.to_params(_row(best, tf), spec), tbl


def _row(r, tf: int) -> pd.Series:
    d = {k: r[k] for k in SEL.KEY}
    d.update(sess_start=int(r.get("sess_start", 420)), sess_end=int(r.get("sess_end", 660)),
             flatten_min=int(r.get("flatten_min", 660)), side=1, tf=tf,
             adx_max=float(r.get("adx_max", 0.0)), ext_max=float(r.get("ext_max", 0.0)),
             break_ticks=float(r.get("break_ticks", 0.0)))
    return pd.Series(d)


def refine_pick(name: str, tf: int, base: P, min_trades: int = 200, min_pf: float = 1.05,
                top: int = 25, verbose: bool = True) -> tuple[P, pd.DataFrame]:
    """Sweep the session and gate axes around a fixed geometry, then apply the same spike test."""
    spec = B.INSTRUMENTS[name]
    rf = R.refine(name, tf, base)
    if verbose:
        print(f"\n--- {name} {tf}m refine: {len(rf):,} cells scored "
              f"(grid {R.grid_size():,})")
        for ax in ("sess_start", "sess_end", "adx_max", "ext_max", "break_atr", "max_hold",
                   "one_shot"):
            print(f"\n  marginal effect of {ax} (median over every other axis):")
            print(R.summarise_axis(rf, ax).to_string(float_format=lambda v: f"{v:.3f}"))
    g = rf[(rf.n >= min_trades) & (rf.ex_per_trade > 0) & (rf.pf >= min_pf)]
    if not len(g):
        if verbose:
            print("\n  nothing in the refine grid clears the gates; keeping the base geometry")
        return base, rf
    g = g.sort_values("sharpe", ascending=False).drop_duplicates(subset=["n", "net"]).head(top)
    rows = []
    for _, r in g.iterrows():
        p = T.replace(base, sess_start=int(r.sess_start), sess_end=int(r.sess_end),
                      adx_max=float(r.adx_max), ext_max=float(r.ext_max),
                      break_ticks=float(r.break_ticks),
                      max_hold=int(r.max_hold), one_shot=bool(r.one_shot))
        nb = V.neighbourhood_direct(name, tf, p, verbose=False)
        rows.append({"sess_start": r.sess_start, "sess_end": r.sess_end, "adx_max": r.adx_max,
                     "ext_max": r.ext_max, "break_atr": r.break_atr,
                     "break_ticks": r.break_ticks, "max_hold": r.max_hold,
                     "one_shot": r.one_shot, "n": r.n, "sharpe": r.sharpe, "pf": r.pf,
                     "per_trade": r.per_trade, "ex_per_trade": r.ex_per_trade,
                     "stability": nb["stability"], "verdict": nb["verdict"]})
    tbl = pd.DataFrame(rows)
    ok = tbl[tbl.verdict != "spike"]
    if verbose:
        print(f"\n  {len(tbl)} distinct refine candidates, {len(ok)} survive the spike test")
        print(tbl.head(15).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if not len(ok):
        return base, rf
    b = ok.sort_values("sharpe", ascending=False).iloc[0]
    return T.replace(base, sess_start=int(b.sess_start), sess_end=int(b.sess_end),
                     adx_max=float(b.adx_max), ext_max=float(b.ext_max),
                     break_ticks=float(b.break_ticks),
                     max_hold=int(b.max_hold), one_shot=bool(b.one_shot)), rf


def candidates_for_pbo(name: str, tf: int, n: int = 300) -> pd.DataFrame:
    """A spread of configurations for the PBO / walk-forward matrix.

    Deliberately not the top n: PBO asks whether SELECTING the in-sample best carries information,
    and a universe made only of winners has had that question answered for it.  This takes a
    stratified slice across the whole kept range instead.
    """
    df = pd.read_parquet(os.path.join(OUT, f"{name}_{tf}m_long.parquet"))
    df = df.drop_duplicates(subset=["n", "net"]).sort_values("sharpe", ascending=False)
    idx = np.unique(np.linspace(0, len(df) - 1, min(n, len(df))).astype(int))
    out = df.iloc[idx].copy()
    for c, v in (("sess_start", 420), ("sess_end", 660), ("flatten_min", 660), ("side", 1)):
        if c not in out.columns:
            out[c] = v
    return out


def main() -> None:
    name, tf = sys.argv[1], int(sys.argv[2])
    reveal = "--reveal" in sys.argv
    base, tbl = pick(name, tf)
    print(f"\n  geometry chosen: {base}")
    final_p, rf = refine_pick(name, tf, base)
    print(f"\n  after refinement: {final_p}")

    k = total_trials() + R.grid_size() * 2 + len(tbl) * 16 + 300
    print(f"\n  configurations evaluated across the whole study: {k:,}")
    meta = SEL.load_meta()
    sd = float(meta[(meta.instrument == name) & (meta.tf == tf) &
                    (meta.side == 1)].trial_sharpe_sd.iloc[0])

    with open(os.path.join(OUT, f"chosen_{name}_{tf}m.json"), "w") as fh:
        json.dump({"params": final_p.as_dict(), "instrument": name, "tf": tf,
                   "n_trials": k, "trial_sd": sd}, fh, indent=1)
    if not reveal:
        print("\n  (research only -- re-run with --reveal to read the locked block)")
        return
    cand = candidates_for_pbo(name, tf)
    F.final(name, tf, final_p, k, sd, candidates=cand, sweep_df=None,
            label=f"{name} {tf}m Turtle scalp 07:00-11:00")


if __name__ == "__main__":
    main()
