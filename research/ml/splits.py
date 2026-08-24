"""Purged, embargoed, session-aware splitting.

The reason this exists rather than sklearn's KFold: a triple-barrier label at bar i is determined by
bars up to i + horizon. A fold boundary drawn without purging puts the answer to a validation
question inside the training set. In this repository that mistake has flipped the SIGN of a result
twice -- meta-labelling ($441/trade in CV, -$245 on the holdout) and the SMC model (+$26.24 vs
-$56.97) -- and both were already using purged CV. Without it the numbers are worse still.
"""
from __future__ import annotations

import numpy as np


class PurgedKFold:
    """K-fold over time-ordered rows, purging label overlap and embargoing after each test fold.

    Parameters
    ----------
    n_splits : number of contiguous test folds.
    horizon  : label horizon in BARS. Training rows whose label window reaches into the test fold
               are dropped -- that is the purge.
    embargo  : extra bars dropped after the test fold, as a fraction of the sample. Serial
               correlation does not stop at the label horizon, so the embargo covers the rest.
    """

    def __init__(self, n_splits: int = 5, horizon: int = 120, embargo: float = 0.01):
        if n_splits < 2:
            raise ValueError("n_splits must be at least 2")
        self.n_splits = n_splits
        self.horizon = int(horizon)
        self.embargo = float(embargo)

    def split(self, n: int):
        idx = np.arange(n)
        emb = int(n * self.embargo)
        bounds = np.linspace(0, n, self.n_splits + 1).astype(int)
        for k in range(self.n_splits):
            lo, hi = bounds[k], bounds[k + 1]
            test = idx[lo:hi]
            # purge: a training row at t is unusable if t + horizon reaches the test fold,
            # and unusable if the test fold's own labels reach t.
            keep = np.ones(n, bool)
            keep[max(0, lo - self.horizon):min(n, hi + self.horizon + emb)] = False
            train = idx[keep]
            if len(train) and len(test):
                yield train, test

    def get_n_splits(self, *_):
        return self.n_splits


def locked_split(sess: np.ndarray, holdout_frac: float = 0.2):
    """Split on SESSION boundaries, not row boundaries, so no day straddles the cut.

    Returns (research_mask, holdout_mask). The holdout is the LAST `holdout_frac` of sessions.
    """
    days = np.unique(sess)
    cut = days[int(len(days) * (1 - holdout_frac))]
    return sess < cut, sess >= cut


def session_folds(sess: np.ndarray, n_splits: int = 5):
    """Contiguous folds that respect session boundaries. Use when the horizon is 'to the close'."""
    days = np.unique(sess)
    bounds = np.linspace(0, len(days), n_splits + 1).astype(int)
    for k in range(n_splits):
        test_days = set(days[bounds[k]:bounds[k + 1]])
        test = np.isin(sess, list(test_days))
        yield ~test, test
