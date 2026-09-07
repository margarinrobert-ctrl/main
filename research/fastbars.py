"""Disk-cached bar arrays, so a tuning process starts warm.

`bos_choch.prep` re-reads a 63 MB 1-minute CSV and re-resamples it on every fresh interpreter:
4.7 seconds before the first number appears. That is the single largest cost in an interactive
tuning loop, because it is paid on every script run, not once per session.

This caches the resampled arrays to `.npz` keyed by timeframe and by the source file's mtime and
size, so a data refresh invalidates it automatically. Cold start drops to about 0.2s.

The arrays are exactly what `prep` returns for the fields the tuner needs; `prep` remains the
authority and is still used to build the cache, so there is one definition of a bar, not two.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC = "data/NQ_1m.csv"
CACHE = os.environ.get("TUNER_CACHE") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "nq_bars_cache")

_MEM: dict = {}
_KEYS = ("o", "h", "l", "c", "v", "mod", "sess", "ts")


def _stamp(path=SRC):
    st = os.stat(path)
    return f"{int(st.st_mtime)}_{st.st_size}"


def bars(tf: int, src: str = SRC) -> dict:
    """OHLCV + minute-of-day + session index for a timeframe, from RAM, then disk, then CSV."""
    key = (tf, src)
    if key in _MEM:
        return _MEM[key]
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, f"{os.path.basename(src)}.{tf}m.{_stamp(src)}.npz")
    if os.path.exists(fn):
        z = np.load(fn)
        d = {k: z[k] for k in _KEYS}
    else:
        from bos_choch import prep
        p = prep(tf)
        d = {k: np.asarray(p[k]) for k in _KEYS if k != "ts"}
        d["ts"] = p["df"].index.values.astype("datetime64[ns]").astype(np.int64)
        tmp = fn + f".{os.getpid()}.tmp"
        with open(tmp, "wb") as fh:  # a handle, not a name: np.savez appends .npz to a name
            np.savez(fh, **d)
        os.replace(tmp, fn)          # atomic, so two processes racing cannot read a half file
    d["mod"] = d["mod"].astype(np.int64)
    d["n"] = len(d["c"])
    _MEM[key] = d
    return d


def sessions(tf: int):
    """Unique session ids, the per-bar index into them, and the research/locked cut.

    The cut is the first 65% of SESSIONS, matching every other module in this repository. It is
    returned rather than recomputed at each call site so that no tuning path can quietly use a
    different split."""
    d = bars(tf)
    us = np.unique(d["sess"])
    si = np.searchsorted(us, d["sess"])
    return us, si, int(0.65 * len(us))


def warm(tfs=(30, 15, 5)):
    for tf in tfs:
        t0 = time.time()
        d = bars(tf)
        print(f"  {tf:>3}m  {d['n']:>9,} bars  {time.time()-t0:.2f}s")


if __name__ == "__main__":
    warm()
