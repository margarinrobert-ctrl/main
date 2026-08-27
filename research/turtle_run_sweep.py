"""Driver: run one (instrument, timeframe, side) sweep and write it to disk.

Split into its own entry point so the eight instrument/timeframe pairs, on both sides, can run as
separate processes -- the sweep is single-threaded numba and the box has four cores.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_search as S

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")

GRID = S.Grid(
    atr_len=(20,),
    chan_shift=(1, 0),
    atr_mult=(1.0, 1.5, 2.0, 2.5, 3.0),
    pyr=((0.0, 1), (0.5, 4), (1.0, 4)),
    tp_r=(0.0, 1.0, 2.0, 3.0),
    use_chan_exit=(True, False),
    armed_stop=(False, True),
    max_hold=(0,),
    exit_len=(2, 3, 4, 6, 8, 12),
    entry1=(4, 6, 8, 10, 14, 20, 28),
    entry2=(8, 12, 16, 24, 40, 60),
    skip_win=(True, False),
    one_shot=(False,),
)


def main() -> None:
    name, tf, side = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    os.makedirs(OUT, exist_ok=True)
    tag = f"{name}_{tf}m_{'long' if side > 0 else 'short'}"
    df, meta, trials = S.sweep(name, tf, GRID, side=side, keep_top=8000, verbose=False)
    df.to_parquet(os.path.join(OUT, tag + ".parquet"), index=False)
    np.save(os.path.join(OUT, tag + "_trials.npy"), trials)
    meta.update(instrument=name, tf=tf, side=side, grid=GRID.size())
    with open(os.path.join(OUT, tag + ".json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"{tag}: evaluated {meta['n_evaluated']:,}  scored {meta['n_scored']:,}  "
          f"best Sharpe {meta['trial_sharpe_max']:.2f}  "
          f"trial sd {meta['trial_sharpe_sd']:.3f}  {meta['seconds']:.0f}s", flush=True)


if __name__ == "__main__":
    main()
