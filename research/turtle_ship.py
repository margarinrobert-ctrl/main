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
         verbose: bool = True, side: int = 1) -> tuple[P, pd.DataFrame]:
    """The best candidate whose neighbourhood is not a spike.

    `side = -1` runs the identical procedure on the short mirror.  That is not a strategy: it is a
    control on the PROCEDURE.  Everything downstream -- the spike test, the marginal-supported
    refinement, the locked read -- is applied to it unchanged, so whatever it produces is what this
    pipeline extracts from a side the sample was against.
    """
    tag = "long" if side > 0 else "short"
    df = pd.read_parquet(os.path.join(OUT, f"{name}_{tf}m_{tag}.parquet"))
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
        p = S.to_params(_row(r, tf, side), spec)
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
    return S.to_params(_row(best, tf, side), spec), tbl


def _row(r, tf: int, side: int = 1) -> pd.Series:
    d = {k: r[k] for k in SEL.KEY}
    d.update(sess_start=int(r.get("sess_start", 420)), sess_end=int(r.get("sess_end", 660)),
             flatten_min=int(r.get("flatten_min", 660)), side=side, tf=tf,
             adx_max=float(r.get("adx_max", 0.0)), ext_max=float(r.get("ext_max", 0.0)),
             break_ticks=float(r.get("break_ticks", 0.0)))
    return pd.Series(d)


def refine_pick(name: str, tf: int, base: P, verbose: bool = True) -> tuple[P, P, pd.DataFrame]:
    """Refine the session and gate axes around a fixed geometry.

    Returns three things: the marginal-supported configuration (what ships), the grid's argmax
    (reported as a diagnostic of what the refinement stage would have cost if taken literally),
    and the grid itself.
    """
    spec = B.INSTRUMENTS[name]
    rf = R.refine(name, tf, base)
    if verbose:
        print(f"\n--- {name} {tf}m refine: {len(rf):,} cells scored (grid {R.grid_size():,})")
        for ax in ("sess_start", "sess_end", "adx_max", "ext_max", "break_atr", "max_hold",
                   "one_shot"):
            print(f"\n  marginal effect of {ax} (median over every other axis):")
            print(R.summarise_axis(rf, ax).to_string(float_format=lambda v: f"{v:.3f}"))

    chosen, _ = R.marginal_refine(rf, verbose=verbose)
    med_atr = float(rf.break_ticks.max() / max(rf.break_atr.max(), 1e-9)) if len(rf) else 0.0
    kw = {}
    for ax, v in chosen.items():
        if ax == "break_atr":
            kw["break_ticks"] = float(v) * med_atr
        elif ax == "one_shot":
            kw["one_shot"] = bool(v)
        elif ax == "max_hold":
            kw["max_hold"] = int(v)
        else:
            kw[ax] = type(getattr(base, ax))(v)
    supported = T.replace(base, **kw)

    g = rf[(rf.n >= 200) & (rf.ex_per_trade > 0) & (rf.pf >= 1.05)]
    argmax = supported
    if len(g):
        b = g.sort_values("sharpe", ascending=False).iloc[0]
        argmax = T.replace(base, sess_start=int(b.sess_start), sess_end=int(b.sess_end),
                           adx_max=float(b.adx_max), ext_max=float(b.ext_max),
                           break_ticks=float(b.break_ticks), max_hold=int(b.max_hold),
                           one_shot=bool(b.one_shot))
    if verbose:
        diff = [k for k in ("sess_start", "sess_end", "adx_max", "ext_max", "break_ticks",
                            "max_hold", "one_shot")
                if getattr(supported, k) != getattr(base, k)]
        print(f"\n  adopted: {diff or 'nothing -- the base geometry is kept'}")
    return supported, argmax, rf


def candidates_for_pbo(name: str, tf: int, n: int = 400, seed: int = 20250822) -> pd.DataFrame:
    """A DIVERSE universe for PBO and walk-forward: a uniform random sample of the whole grid.

    The obvious universe -- a slice through the sweep's kept rows -- is the wrong one, and badly
    so.  Those rows are the top 8,000 of 645,120 ranked on the objective, so they are near-copies
    of each other: measured on US30 60m their mean pairwise daily-P&L correlation is 0.85 and the
    eigenvalue participation ratio says 300 of them carry about 1.4 independent bets.  Asking
    "does picking the in-sample best carry information" of a set whose members are all the same
    strategy answers a question nobody asked.

    Sampling the grid uniformly restores the question the protocol means: across the space that
    was actually searched, does the in-sample winner hold up out of sample?
    """
    import turtle_run_sweep as RS
    g = RS.GRID
    rng = np.random.default_rng(seed)
    rows = []
    exits = list(g.exit_len)
    for _ in range(n):
        e1 = int(rng.choice(exits))
        e2 = int(rng.choice([e for e in exits if e >= e1]))
        k1 = int(rng.choice(g.entry1))
        k2c = [k for k in g.entry2 if k >= k1]
        k2 = int(rng.choice(k2c)) if k2c else k1
        ps, mu = g.pyr[int(rng.integers(len(g.pyr)))]
        rows.append({
            "atr_len": int(rng.choice(g.atr_len)), "atr_mult": float(rng.choice(g.atr_mult)),
            "pyr_step": float(ps), "max_units": int(mu), "tp_r": float(rng.choice(g.tp_r)),
            "use_chan_exit": bool(rng.choice(g.use_chan_exit)),
            "chan_shift": int(rng.choice(g.chan_shift)),
            "armed_stop": bool(rng.choice(g.armed_stop)),
            "max_hold": int(rng.choice(g.max_hold)), "exit1": e1, "exit2": e2,
            "entry1": k1, "entry2": k2, "skip_win": bool(rng.choice(g.skip_win)),
            "one_shot": bool(rng.choice(g.one_shot)),
            "sess_start": g.sess_start, "sess_end": g.sess_end,
            "flatten_min": g.flatten_min, "side": 1})
    return pd.DataFrame(rows).drop_duplicates(subset=SEL.KEY).reset_index(drop=True)


def main() -> None:
    name, tf = sys.argv[1], int(sys.argv[2])
    reveal = "--reveal" in sys.argv
    side = -1 if "--short" in sys.argv else 1
    base, tbl = pick(name, tf, side=side)
    print(f"\n  geometry chosen: {base}")
    final_p, argmax_p, rf = refine_pick(name, tf, base)
    print(f"\n  marginal-supported: {final_p}")
    print(f"\n  grid argmax (reported, not shipped): {argmax_p}")

    k = total_trials() + R.grid_size() * 2 + len(tbl) * 16 + 300
    print(f"\n  configurations evaluated across the whole study: {k:,}")
    meta = SEL.load_meta()
    sd = float(meta[(meta.instrument == name) & (meta.tf == tf) &
                    (meta.side == side)].trial_sharpe_sd.iloc[0])

    tag = "" if side > 0 else "_short"
    with open(os.path.join(OUT, f"chosen_{name}_{tf}m{tag}.json"), "w") as fh:
        json.dump({"params": final_p.as_dict(), "argmax": argmax_p.as_dict(),
                   "base": base.as_dict(), "instrument": name, "tf": tf,
                   "n_trials": k, "trial_sd": sd}, fh, indent=1)
    if not reveal:
        print("\n  (research only -- re-run with --reveal to read the locked block)")
        return
    cand = candidates_for_pbo(name, tf)
    if side < 0:
        cand["side"] = -1
    F.final(name, tf, final_p, k, sd, candidates=cand, sweep_df=None,
            label=f"{name} {tf}m Turtle scalp 07:00-11:00"
                  + ("" if side > 0 else "  [SHORT MIRROR -- procedure control]"))


if __name__ == "__main__":
    main()
