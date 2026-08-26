"""The locked read.  Once, for every candidate at the same time, with the multiplicity first.

Run after every research-side number is fixed and every `chosen_*.json` has been written.  It
reads each candidate on the holdout in one pass and prints them together, including two that are
not products:

  * the **Phase-1 geometry** next to the marginal-supported one, so the refinement stage's
    contribution is visible rather than assumed;
  * the **short mirror**, put through the identical pipeline.  It is a control on the PROCEDURE.
    On the research block the short winner beat its own matched control by $95 a trade at p =
    0.0025 -- more than the long winner did -- which is the clearest possible demonstration that a
    control p-value computed on a selected winner is not a p-value.  If the short survives the
    holdout too, this pipeline extracts noise and the long result means nothing.

    python3 research/turtle_reveal.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_final as F
import turtle_refine as R
import turtle_select as SEL
import turtle_ship as SH
from turtle_sim import P

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")


def total_k() -> int:
    """Every configuration this study evaluated, across every phase."""
    meta = SEL.load_meta()
    sweep = int(meta.n_evaluated.sum())
    chosen = [f for f in os.listdir(OUT) if f.startswith("chosen_")]
    refine = R.grid_size() * len(chosen)
    # the spike test re-simulates ~16 neighbours for each of 40 candidates per pick, twice
    # (geometry and refinement), plus the PBO universe
    neighbours = 40 * 16 * 2 * len(chosen)
    pbo = 400 * len(chosen)
    return sweep + refine + neighbours + pbo


def main() -> None:
    k = total_k()
    meta = SEL.load_meta()
    print("=" * 108)
    print("THE LOCKED READ")
    print("=" * 108)
    print(f"  {len(meta)} sweeps x {int(meta.n_evaluated.iloc[0]):,} cells = "
          f"{int(meta.n_evaluated.sum()):,}")
    print(f"  plus refinement grids, spike tests and PBO universes -> {k:,} configurations")
    print("  Every number below is the FIRST time the locked block has been consulted.")

    jobs = []
    for f in sorted(os.listdir(OUT)):
        if not f.startswith("chosen_") or not f.endswith(".json"):
            continue
        with open(os.path.join(OUT, f)) as fh:
            j = json.load(fh)
        nm, tf = j["instrument"], int(j["tf"])
        short = f.endswith("_short.json")
        sd = float(meta[(meta.instrument == nm) & (meta.tf == tf)
                        & (meta.side == (-1 if short else 1))].trial_sharpe_sd.iloc[0])
        tag = "SHORT MIRROR (procedure control)" if short else "long"
        jobs.append((nm, tf, P(**j["params"]), sd, f"{nm} {tf}m {tag} -- marginal-supported"))
        if not short:
            jobs.append((nm, tf, P(**j["base"]), sd,
                         f"{nm} {tf}m long -- Phase-1 geometry, unrefined"))

    results = {}
    for nm, tf, p, sd, label in jobs:
        cand = SH.candidates_for_pbo(nm, tf)
        if p.side < 0:
            cand["side"] = -1
        try:
            results[label] = F.final(nm, tf, p, k, sd, candidates=cand, label=label)
        except Exception as e:                                # pragma: no cover - diagnostics
            print(f"  {label}: FAILED {e}")

    print("\n" + "=" * 108)
    print("SUMMARY -- research vs locked, every candidate")
    print("=" * 108)
    rows = []
    for label, r in results.items():
        rows.append({
            "candidate": label,
            "res_n": r["research"]["n"], "res_sharpe": r["research"]["sharpe"],
            "res_pf": r["research"]["pf"],
            "lk_n": r["locked"]["n"], "lk_sharpe": r["locked"]["sharpe"],
            "lk_pf": r["locked"]["pf"], "lk_per_trade": r["locked"]["per_trade"],
            "lk_excess": r["locked"].get("ex_per_trade", float("nan")),
            "lk_p": r["locked"].get("p_per_trade", float("nan")),
            "gates": int(r["gates"]["pass"].sum()),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    df.to_parquet(os.path.join(OUT, "locked_summary.parquet"), index=False)


if __name__ == "__main__":
    main()
