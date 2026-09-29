"""Positive controls, then the causality audit. Nothing touches a strategy until both pass."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathmodels import mmcore as M  # noqa: E402

RNG = np.random.default_rng(11)


def main():
    print("POSITIVE CONTROLS -- can each estimator recover a parameter it was handed?\n")
    d = M.controls()
    for r in d.itertuples():
        t = "" if not np.isfinite(r.truth) else f"{r.truth:.4f}"
        print(f"  {r.test:<24} truth {t:>8}   got {r.got:>9.4f}   {r.extra}")

    print("\nCAUSALITY AUDIT -- rebuild each state from history ENDING at the bar")
    f = M.load("US30L", 30).iloc[:12000]
    S = M.states(f, 500)
    probes = RNG.choice(np.arange(3000, len(f) - 5), size=8, replace=False)
    bad = {c: 0 for c in S.columns}
    for i in sorted(probes):
        sub = M.states(f.iloc[: i + 1], 500)
        for c in S.columns:
            a, b = S[c].to_numpy()[i], sub[c].to_numpy()[-1]
            if not (np.isnan(a) and np.isnan(b)) and abs(np.nan_to_num(a) - np.nan_to_num(b)) > 1e-8:
                bad[c] += 1
    tot = sum(bad.values())
    print(f"  mismatches {tot} / {len(probes) * len(S.columns)}   " +
          (", ".join(f"{k} {v}" for k, v in bad.items() if v) if tot else "all clean"))

    print("\nWHAT THE STATES LOOK LIKE ON REAL PRICE (US30 30m, whole file)")
    f = M.load("US30L", 30)
    S = M.states(f, 500)
    print(S.describe().T[["count", "mean", "std", "min", "50%", "max"]].round(4).to_string())


if __name__ == "__main__":
    main()
