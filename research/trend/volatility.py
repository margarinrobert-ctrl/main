"""sigma_short = EWM std(span 32); sigma_long = mean of sigma_short over the last 2560 bars,
expanding until available; blend 0.70 / 0.30. Every operation is causal."""
from __future__ import annotations
import numpy as np, pandas as pd


def estimate(returns: pd.DataFrame, span_short=32, long_window=2560, blend_short=0.70):
    s_short = returns.ewm(span=span_short, adjust=False).std()
    s_long = s_short.rolling(long_window, min_periods=span_short).mean()
    exp = s_short.expanding(min_periods=span_short).mean()
    s_long = s_long.fillna(exp)
    return blend_short * s_short + (1.0 - blend_short) * s_long
