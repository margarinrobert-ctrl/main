"""Purged, embargoed K-fold cross-validation (Lopez de Prado, Advances in Financial ML, ch. 7).

Plain K-fold leaks in a trading problem. A trade that is open across the train/test boundary shares
its outcome-determining bars with samples on the other side, so the model can be scored on
information it effectively trained on. Two corrections:

  PURGE    drop any training sample whose [entry, exit] interval overlaps the test interval.
  EMBARGO  additionally drop training samples that begin shortly AFTER the test set ends, because
           serial correlation makes those nearly as informative as the test set itself.

Without both, a meta-model on financial data reports a cross-validated score it cannot reproduce
out of sample.
"""
from __future__ import annotations

import numpy as np


class PurgedKFold:
    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, t0: np.ndarray, t1: np.ndarray):
        """t0/t1 are the start and end index of each sample, in bar units, sorted by t0."""
        n = len(t0)
        idx = np.arange(n)
        embargo = int(n * self.embargo_pct)
        for test in np.array_split(idx, self.n_splits):
            test_start, test_end = t0[test[0]], t1[test].max()
            # purge: any training sample overlapping the test window
            keep = (t1 < test_start) | (t0 > test_end)
            # embargo: and anything starting just after it
            if embargo > 0:
                hi = min(n - 1, test[-1] + embargo)
                embargo_end = t0[hi]
                keep &= ~((t0 > test_end) & (t0 <= embargo_end))
            train = idx[keep]
            train = train[~np.isin(train, test)]
            if len(train) >= 30 and len(test) >= 10:
                yield train, test
