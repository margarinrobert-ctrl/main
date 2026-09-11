"""Per-instrument cost, the Sharpe-drag rule that picks each instrument's sleeve set, turnover."""
from __future__ import annotations
import numpy as np, pandas as pd


def sleeve_set(sigma_ann_train: float, cost_bps: float, sleeves, drag_limit=0.10):
    """drag_k = turnover_k * c / sigma_ann; keep sleeves with drag <= limit. Mechanical, no choice."""
    c = cost_bps / 1e4
    keep = [k for k, s in enumerate(sleeves) if s["turnover"] * c / sigma_ann_train <= drag_limit]
    drags = {s["n"]: s["turnover"] * c / sigma_ann_train for s in sleeves}
    return keep, drags


def turnover(pos: pd.DataFrame):
    """position turns per year, per instrument: sum |delta pos| / mean |pos| / years."""
    d = pos.diff().abs().sum()
    yrs = len(pos) / 256.0
    return d / pos.abs().mean().replace(0, np.nan) / yrs / 2.0
