"""Re-rank the saved grid under the corrected objective WITHOUT re-walking the price.

The grid CSVs already hold every metric the objective reads, so a change to the objective is an
arithmetic re-rank rather than a re-run. That matters for reproducibility: the trials are the same
trials, and only the ordering function moved.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402
import v33opt as O            # noqa: E402

TRIALS = "research/v33/trials"


def rescore(market, side, top=400):
    df = pd.read_csv(f"{TRIALS}/grid_{market}_{side}.csv")
    P0 = V.prep(market, V.TF[0], V.ENTRY_N[0], V.EXIT_N[0])
    blocks = V.splits(P0["sess"])
    years = {tf: len(np.unique(V.prep(market, tf, V.ENTRY_N[0], V.EXIT_N[0])["sess"]
                               [blocks["train"] if tf == V.TF[0] else
                                V.splits(V.prep(market, tf, V.ENTRY_N[0],
                                                V.EXIT_N[0])["sess"])["train"]]))
                 / V.TRADING_DAYS for tf in V.TF}
    df["trades_per_year"] = df.n / df.tf.map(years)
    sc = []
    for r in df.itertuples():
        m = dict(sharpe=r.sharpe, pf=r.pf, retdd=r.retdd, n=r.n, dd=r.dd, net=r.net,
                 top1_share=r.top1, trades_per_year=r.trades_per_year)
        sc.append(V.score(m, robust=0.0)[0])
    df["score_norobust"] = sc
    df.to_csv(f"{TRIALS}/grid_{market}_{side}.csv", index=False)
    d = O.add_robustness(market, df, side, top=top)
    d.to_csv(f"{TRIALS}/robust_{market}_{side}.csv", index=False)
    return df, d


if __name__ == "__main__":
    for market in ("US30", "NQ"):
        for side in (1, -1):
            df, d = rescore(market, side)
            print(f"   {market} side {side:+d}: rescored {len(df):,}; "
                  f"top score {d.score.max():.4f}, "
                  f"{int((d.score > 0.999).sum())} saturated at 1.000, "
                  f"median trades/year in the top 400 {d.n.div(d.tf.map({15: 1, 30: 1, 60: 1})).median():.0f}",
                  flush=True)
