"""Build every (strategy, feed) trade table ONCE and cache it.

The eight engines on this branch each take seconds to minutes to run; the allocation study
reads them many times. This module is the only thing that calls them.
"""
from __future__ import annotations

import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research", "top5"))
import t5_adapt as A  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legs.pkl")


def main():
    legs = {}
    for name, spec in A.CANDIDATES.items():
        for feed in spec["feeds"]:
            t0 = time.time()
            try:
                b = A.bundle(name, feed)
            except Exception as e:
                print(f"SKIP {name:12s} {feed:9s}  {type(e).__name__}: {e}", flush=True)
                continue
            tr = b["tr"]
            if not len(tr):
                print(f"SKIP {name:12s} {feed:9s}  no trades", flush=True)
                continue
            legs[(name, feed)] = dict(tr=tr, sessions=b["sessions"], is_block=spec["is_block"],
                                      label=spec["label"], pv=spec["pv"])
            print(f"OK   {name:12s} {feed:9s}  n={len(tr):5d}  {time.time()-t0:6.1f}s  "
                  f"blocks={tr['block'].value_counts().to_dict()}", flush=True)
    with open(OUT, "wb") as fh:
        pickle.dump(legs, fh)
    print(f"\nwrote {OUT}  legs={len(legs)}", flush=True)


if __name__ == "__main__":
    main()
