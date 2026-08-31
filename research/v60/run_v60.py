"""The V60 sweep, on the research block only. Nothing here reads the locked block.

THE COUNT, stated the way `CLAUDE.md` requires rather than the way that sounds largest. The grid
is 388,800 nominal cells per market at one timeframe, and it is run on three markets, so
1,166,400 configurations are evaluated. Of those, 142,560 per market are DISTINCT -- with the EMA
condition off, `ema_f`, `ema_s` and `win` change nothing, and in `state` mode `win` changes
nothing, so 246,240 of the 388,800 are duplicates of cells already in the grid. 427,680 distinct
across the three markets.

ONE TIMEFRAME IS SWEPT: 60 minutes. `v60core.TFS` carries three because `prep` accepts any of
them, but the sweep and every number published from it are 60-minute. A count that multiplied by
the timeframes not run would be exactly the overstatement `STUDY_RULE_ANATOMY.md` caught.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))

import v60core as V             # noqa: E402

MARKETS = ("US100L", "NQ", "US30L")


def run(market, tf=60, save=True):
    t0 = time.time()
    P, keys, geoms, sig_flat, off, ln, xb_all, pnl_all, day_id, cut, nres, nlock = \
        V.build(tf, market)
    out = np.zeros(len(keys) * len(geoms) * 12)
    V.sweep(sig_flat, off, ln, xb_all, pnl_all, P["atr"], day_id, nres, nlock, cut, out)
    M = V.metrics(out, len(keys), len(geoms), nres, nlock)
    if save:
        os.makedirs("results/v60", exist_ok=True)
        np.savez_compressed(f"results/v60/{market}_{tf}.npz",
                            **{k: v.astype(np.float32) for k, v in M.items()},
                            cut=cut, nres=nres, nlock=nlock, nbars=P["n"])
        import pickle
        with open(f"results/v60/{market}_{tf}_keys.pkl", "wb") as fh:
            pickle.dump(dict(keys=keys, geoms=geoms), fh)
    return P, keys, geoms, M, nres, nlock, time.time() - t0


def main():
    per = V.N_NOMINAL // len(V.TFS)
    dist = len(list(V.signal_keys())) * V.N_GEOM
    print(f"60m only: {per:,} nominal cells per market x {len(MARKETS)} markets = "
          f"{per * len(MARKETS):,} evaluated; {dist:,} DISTINCT per market "
          f"({dist * len(MARKETS):,} in all)")
    for mk in MARKETS:
        P, keys, geoms, M, nres, nlock, el = run(mk)
        n = M["n"][:, :, 0]
        ok = n >= 30
        usd = M["usd"][:, :, 0]
        print(f"\n=== {mk} 60m: {P['n']:,} bars, research {nres} days / locked {nlock} "
              f"({el:.1f}s)")
        print(f"    scorable configurations (>=30 research trades): {int(ok.sum()):,} of "
              f"{n.size:,}")
        print(f"    profitable on research: {float((usd[ok] > 0).mean())*100:.1f}%   "
              f"median $/trade {np.nanmedian(usd[ok]):+.2f}   median PF "
              f"{np.nanmedian(M['pf'][:, :, 0][ok]):.3f}")


if __name__ == "__main__":
    main()
