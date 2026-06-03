"""Regime classification from the rolling Hurst exponent (Section 2.4).

    H > trend_th   -> "trend"
    H < revert_th  -> "revert"
    else           -> "random"

Thresholds are configurable (handoff Section 2.4).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RegimeThresholds:
    trend: float = 0.55
    revert: float = 0.45


def classify(H, thresholds: RegimeThresholds | None = None):
    """Map an array of Hurst values to regime labels.

    Returns an object array of {"trend","revert","random","na"}.
    """
    th = thresholds or RegimeThresholds()
    H = np.asarray(H, dtype=float)
    out = np.empty(H.size, dtype=object)
    for i, h in enumerate(H):
        if np.isnan(h):
            out[i] = "na"
        elif h > th.trend:
            out[i] = "trend"
        elif h < th.revert:
            out[i] = "revert"
        else:
            out[i] = "random"
    return out
