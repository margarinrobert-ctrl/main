"""Time-aware splits: discovery / validation / production, plus purged walk-forward (brief 32,33,47).

THREE BLOCKS, and the third is never touched during search (brief section 47):

    DISCOVERY    2016-11 -> 2021-12   feature search, setup search, every parameter choice
    VALIDATION   2022-01 -> 2023-12   frozen rules only
    PRODUCTION   2024-01 -> 2025-10   read ONCE, at the very end

PURGING AND EMBARGO (brief 33). A triple-barrier label started at bar i can still be resolving
many bars later, so a naive split lets a training label overlap a test bar. `purge` removes from
the training side any trade whose holding window reaches into the test block, and `embargo` drops
a further margin of bars after the test block before training resumes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DISCOVERY_END = "2022-01-01"
VALIDATION_END = "2024-01-01"


def blocks(d):
    ix = pd.DatetimeIndex(d["idx"])
    disc = np.asarray(ix < pd.Timestamp(DISCOVERY_END))
    val = np.asarray((ix >= pd.Timestamp(DISCOVERY_END)) & (ix < pd.Timestamp(VALIDATION_END)))
    prod = np.asarray(ix >= pd.Timestamp(VALIDATION_END))
    return dict(discovery=disc, validation=val, production=prod)


def describe(d):
    ix = pd.DatetimeIndex(d["idx"]); b = blocks(d)
    for k, m in b.items():
        print(f"  {k:<11} {int(m.sum()):>7,} bars   {ix[m][0].date()} -> {ix[m][-1].date()}")
    return b


def walk_forward(d, n_folds=6, train_frac=0.6, max_hold=16, embargo=32, within=None):
    """Rolling train/test folds over the DISCOVERY+VALIDATION span, purged and embargoed.

    Yields (fold, train_mask, test_mask). `within` optionally restricts to a boolean mask (e.g.
    the discovery block) so production is never involved.
    """
    n = len(d["c"])
    base = np.ones(n, bool) if within is None else np.asarray(within, bool)
    idx = np.flatnonzero(base)
    if len(idx) < 1000:
        return
    seg = len(idx) // (n_folds + 1)
    for f in range(n_folds):
        tr_lo = 0
        tr_hi = seg * (f + 1)
        te_lo = tr_hi
        te_hi = min(tr_hi + seg, len(idx))
        if te_hi - te_lo < 100:
            break
        train = np.zeros(n, bool); test = np.zeros(n, bool)
        train[idx[tr_lo:tr_hi]] = True
        test[idx[te_lo:te_hi]] = True
        # purge: a training signal whose label can still be open once testing starts
        cut = idx[te_lo]
        purge_from = max(0, cut - max_hold - 1)
        train[purge_from:cut] = False
        # embargo after the test block, so a later fold's training does not resume immediately
        emb_hi = min(n, idx[te_hi - 1] + embargo)
        train[idx[te_hi - 1]:emb_hi] = False
        yield f, train, test
