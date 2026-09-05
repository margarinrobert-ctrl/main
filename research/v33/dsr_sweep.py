"""How much of the verdict is the multiplicity assumption?

The deflated Sharpe needs N, the number of INDEPENDENT trials. 51,840 configurations are nowhere
near 51,840 independent experiments -- they share entry channels, they share exit channels, and the
filters are nested subsets of one another, so most of them are the same trades counted again
(`STUDY_RULE_ANATOMY` found eight conditions in an earlier pool were literal duplicates). Reporting
one DSR against one assumed N hides that, so the whole curve is printed and the reader can see
where the verdict flips.

Two anchors are marked on it: 576, the number of distinct PRICE WALKS in the grid (every filter
combination is a subset of one of these), and 51,840, the raw configuration count.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402
import v33robust as RB        # noqa: E402

N_WALKS = len(V.TF) * len(V.ENTRY_N) * len(V.EXIT_N) * len(V.STOP) * len(V.TP_R)
GRID = 51840


def sweep(market, p, ns=(1, 5, 20, 50, 100, 250, N_WALKS, 2000, 10000, GRID)):
    blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
    R, days = [], []
    for tag in ("train", "valid"):
        r, d, _P, _O, _i = V.trades(market, p, blocks[tag])
        R.append(r); days.append(d)
    R, days = np.concatenate(R), np.concatenate(days)
    m = V.metrics(R, days, V.prep(market, p.tf, p.entry_n, p.exit_n))
    print(f"   observed annualised Sharpe on TRAIN+VALID: {m['sharpe']:+.3f} over {m['days']} days,"
          f" {m['n']} trades")
    print(f"   {'assumed N':>12}{'null max Sharpe':>18}{'deflated prob':>16}   verdict")
    flip = None
    for n in ns:
        ds = RB.deflated_sharpe(m["daily"], n)
        tag = ""
        if n == N_WALKS:
            tag = "  <- distinct price walks in the grid"
        if n == GRID:
            tag = "  <- raw configuration count"
        v = "passes" if ds["dsr"] > 0.95 else "fails"
        if flip is None and ds["dsr"] <= 0.95:
            flip = n
        print(f"   {n:>12,}{ds['sr_null_ann']:>+18.3f}{ds['dsr']:>16.4f}   {v}{tag}")
    print(f"\n   The verdict flips from pass to fail between {ns[max(0, list(ns).index(flip) - 1)]:,}"
          f" and {flip:,} independent trials." if flip else "\n   Passes at every N tested.")


if __name__ == "__main__":
    cand = V.Params(tf=60, entry_n=40, exit_n=20, stop=2.5, tp_r=2.0, chop_max=45.0,
                    adx_min=None, session=(570, 960), vol_policy=(2.5, 1.5), side=1)
    print("=" * 116)
    print("DEFLATED SHARPE vs the assumed number of independent trials -- US30 long candidate")
    print("=" * 116)
    sweep("US30", cand)
