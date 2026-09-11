"""raw = (EWMA(P, n) - EWMA(P, 4n)) / (P * sigma); scaled by the hard-coded scalar; capped +-20;
combined over the surviving sleeves with equal weights and the FDM from the spec's matrix."""
from __future__ import annotations
import numpy as np, pandas as pd


def ewma(P: pd.Series, n: int):
    return P.ewm(span=n, adjust=False).mean()


def sleeve_forecast(P: pd.Series, sigma: pd.Series, n: int, scalar: float, cap=20.0):
    raw = (ewma(P, n) - ewma(P, 4 * n)) / (P * sigma)
    return (raw * scalar).clip(-cap, cap)


def fdm(corr: np.ndarray, idx):
    v = np.full(len(idx), 1.0 / len(idx))
    C = corr[np.ix_(idx, idx)]
    return float(1.0 / np.sqrt(v @ C @ v))


def combined(P: pd.Series, sigma: pd.Series, sleeves, corr, idx, cap=20.0):
    """`idx` = indices into `sleeves` of the sleeves this instrument is allowed to run."""
    F = sum(sleeve_forecast(P, sigma, sleeves[k]["n"], sleeves[k]["scalar"], cap) for k in idx) / len(idx)
    return (F * fdm(np.asarray(corr), idx)).clip(-cap, cap)
