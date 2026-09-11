"""IDM from a rolling 5-year return correlation (point in time, capped), the sizing equation in
fraction-of-capital form, and the buffered trade-to-the-edge pass."""
from __future__ import annotations
import numpy as np, pandas as pd


def idm(returns: pd.DataFrame, weights: np.ndarray, window=1280, cap=2.5, min_periods=256):
    out = pd.Series(np.nan, index=returns.index)
    R = returns.to_numpy(); n, m = R.shape
    for t in range(min_periods, n):
        lo = max(0, t - window)
        C = np.corrcoef(R[lo:t].T) if m > 1 else np.array([[1.0]])
        C = np.nan_to_num(C, nan=0.0); np.fill_diagonal(C, 1.0)
        v = float(weights @ C @ weights)
        out.iloc[t] = min(cap, 1.0 / np.sqrt(v)) if v > 0 else cap
    return out.ffill()


def target_fraction(F: pd.DataFrame, idm_s: pd.Series, weights, tau, sigma_ann: pd.DataFrame, c=1.0):
    """frac_i = (F/10) * IDM * w_i * tau / sigma_ann, times the calibration constant c."""
    w = pd.Series(weights, index=F.columns)
    return (F / 10.0).mul(idm_s, axis=0).mul(w, axis=1) * tau / sigma_ann * c


def buffer_width(idm_s: pd.Series, weights, tau, sigma_ann: pd.DataFrame, c=1.0, frac=0.10):
    w = pd.Series(weights, index=sigma_ann.columns)
    return frac * pd.DataFrame(1.0, index=sigma_ann.index, columns=sigma_ann.columns).mul(idm_s, axis=0).mul(w, axis=1) * tau / sigma_ann * c


def buffered(target: pd.DataFrame, B: pd.DataFrame):
    """Trade only when outside the band, and then to the NEAREST EDGE, not the centre."""
    T, W = target.to_numpy(), B.to_numpy()
    out = np.zeros_like(T); cur = np.zeros(T.shape[1])
    for t in range(T.shape[0]):
        for i in range(T.shape[1]):
            if np.isnan(T[t, i]) or np.isnan(W[t, i]):
                out[t, i] = cur[i]; continue
            lo, hi = T[t, i] - W[t, i], T[t, i] + W[t, i]
            if cur[i] < lo: cur[i] = lo
            elif cur[i] > hi: cur[i] = hi
            out[t, i] = cur[i]
    return pd.DataFrame(out, index=target.index, columns=target.columns)
