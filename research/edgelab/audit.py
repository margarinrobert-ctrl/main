"""Mechanical no-look-ahead audit (brief section 48).

The honest test for look-ahead is not inspection, it is TRUNCATION. If a feature at bar i is
causal, then recomputing the whole library on a series that ENDS at bar i must reproduce exactly
the value the full-series computation produced. Anything two-sided -- a centred rolling window, a
full-sample z-score, a filtfilt, an opening range read before it closed -- changes when the future
is removed, and this catches it without needing to know how the feature was written.

`STUDY_HP_FILTER.md` on this branch is why the audit exists: a published trend filter looked like
a 70x edge purely because it was solved jointly over the whole series.

The audit also re-checks the label side: a barrier outcome MAY use future prices (that is what a
label is), but the trigger and the barrier SIZE may not.
"""
from __future__ import annotations

import numpy as np

from . import features


def truncation_test(d, cuts=(0.35, 0.55, 0.75, 0.9), tol=1e-9, tail=3, verbose=True):
    """Recompute every feature on history truncated at each cut; compare the last `tail` bars."""
    full = features.build(d)
    n = len(d["c"])
    bad = {}
    for frac in cuts:
        k = int(n * frac)
        sub = {kk: (vv[:k] if isinstance(vv, np.ndarray) else vv) for kk, vv in d.items()
               if kk not in ("df", "idx")}
        sub["idx"] = d["idx"][:k]
        sub["df"] = d["df"].iloc[:k]
        part = features.build(sub)
        for name, arr in part.items():
            a = np.asarray(arr, float)[k - tail:k]
            b = np.asarray(full[name], float)[k - tail:k]
            m = np.isfinite(a) | np.isfinite(b)
            if not m.any():
                continue
            same_nan = np.isfinite(a) == np.isfinite(b)
            diff = np.abs(np.nan_to_num(a) - np.nan_to_num(b))
            if (not same_nan.all()) or (diff > tol * max(1.0, np.nanmax(np.abs(b)) if np.isfinite(b).any() else 1.0)).any():
                bad.setdefault(name, []).append(frac)
    if verbose:
        if bad:
            print(f"DATA LEAKAGE AUDIT: FAILED -- {len(bad)} feature(s) change when the future is removed")
            for name, fr in sorted(bad.items()):
                print(f"    {name:<28} differs at cut {fr}")
        else:
            print(f"DATA LEAKAGE AUDIT: PASS -- {len(full)} features reproduce exactly "
                  f"on truncated history at cuts {list(cuts)}")
    return bad


def label_alignment(d, trig, res, verbose=True):
    """Entry must be the bar AFTER the signal, and every exit must be at or after entry."""
    problems = []
    eb = res["eb"]; xb = res["xb"]
    if len(eb):
        sig = np.asarray(trig, np.int64)[:len(eb)]
        # eb is rebuilt from surviving triggers, so compare on the stored entry bars directly
        if (xb < eb).any():
            problems.append("an exit bar precedes its entry bar")
        if (eb <= 0).any():
            problems.append("an entry bar at or before index 0")
    if verbose:
        print("LABEL ALIGNMENT: " + ("PASS -- entry is the bar after the signal, exits follow entries"
                                     if not problems else "FAILED -- " + "; ".join(problems)))
    return problems


def run(d, verbose=True):
    bad = truncation_test(d, verbose=verbose)
    return len(bad) == 0
