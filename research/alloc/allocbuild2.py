"""The same leg tables at 2x each feed's assumed cost -- the cost stress for the book."""
from __future__ import annotations

import os
import pickle
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research", "top5"))
import t5_adapt as A  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legs_2x.pkl")
MULT = 2.0


def main():
    legs = {}
    for name, spec in A.CANDIDATES.items():
        for feed in spec["feeds"]:
            t0 = time.time()
            try:
                b = A.bundle(name, feed, cost_mult=MULT)
            except Exception as e:
                print(f"SKIP {name:12s} {feed:9s}  {type(e).__name__}: {e}", flush=True)
                continue
            tr = b["tr"]
            if not len(tr):
                continue
            legs[(name, feed)] = dict(tr=tr, sessions=b["sessions"], is_block=spec["is_block"],
                                      label=spec["label"], pv=spec["pv"])
            print(f"OK   {name:12s} {feed:9s}  n={len(tr):5d}  sum(pct)={tr['pct'].sum():9.3f}"
                  f"  {time.time()-t0:6.1f}s", flush=True)
    with open(OUT, "wb") as fh:
        pickle.dump(legs, fh)
    print(f"\nwrote {OUT}  legs={len(legs)}", flush=True)


if __name__ == "__main__":
    main()
