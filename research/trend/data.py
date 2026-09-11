"""Daily panel from the intraday feeds. Close for signals, next OPEN for execution."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd, yaml
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63"):
    q = os.path.join(ROOT, p)
    if q not in sys.path: sys.path.insert(0, q)
import v63feeds as FD
HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.yaml")


def load_config():
    with open(CFG_PATH) as f:
        return yaml.safe_load(f)


def save_config(cfg):
    with open(CFG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def daily(feed, tf):
    # the feed loaders resolve `data/...` relative to the repo root, whatever the caller's cwd is
    cwd = os.getcwd(); os.chdir(ROOT)
    try:
        b = FD.bars(feed, tf)
    finally:
        os.chdir(cwd)
    d = b.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return d[d.index.dayofweek < 5]


def panel(cfg=None):
    """Aligned closes and opens on the common calendar; writes the holdout split date once."""
    cfg = cfg or load_config()
    closes, opens = {}, {}
    for name, u in cfg["universe"].items():
        d = daily(u["feed"], u["tf"])
        closes[name], opens[name] = d["close"], d["open"]
    C = pd.DataFrame(closes).dropna(); O = pd.DataFrame(opens).reindex(C.index)
    if cfg["holdout"]["split_date"] is None:
        k = int(len(C) * (1 - cfg["holdout"]["fraction"]))
        cfg["holdout"]["split_date"] = str(C.index[k].date())
        save_config(cfg)
    split = pd.Timestamp(cfg["holdout"]["split_date"])
    return dict(close=C, open=O, split=split, cfg=cfg)
