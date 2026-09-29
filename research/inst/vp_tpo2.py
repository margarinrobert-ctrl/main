"""Parameterised TPO single-print feature: bin size in three modes (absolute points, fraction of
price, fraction of the session's ATR), letter length in minutes, ceiling in ATR -- so the profile
construction can be swept and a SCALE-INVARIANT definition ported to other markets. The carry rule
is vp_tpo.build's: before 16:00 New York a bar reads the previous completed session's profile,
from 16:00 the same day's; early closes complete when a later bar exists."""
import math, numpy as np, pandas as pd
RTH0, RTH1 = 570, 960

def single_print_above(o, h, l, c, atr, mod, ix, tbin=2.5, letter=30, mode="abs", side="above"):
    """Per bar: the nearest prior-session single-print bin CENTRE strictly above (or below) the
    close's bin, in price. mode: 'abs' = tbin points; 'pct' = tbin x the session's first close;
    'atr' = tbin x the session's median ATR. Returns (level array, bin size used per bar)."""
    n = len(c); ix = pd.DatetimeIndex(ix); day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    in_rth = (mod >= RTH0) & (mod < RTH1)
    out = np.full(n, np.nan); binsz = np.full(n, np.nan)
    last_sp = None; last_tb = np.nan          # frozen: array of single-print bin indices (ints) and its bin size
    def assign(idx):
        if last_sp is None or len(idx) == 0: return
        for i in idx:
            cb = math.floor(c[i] / last_tb)
            if side == "above":
                k = np.searchsorted(last_sp, cb, side="right")       # first sp bin > cb
                if k < len(last_sp): out[i] = (last_sp[k] + 0.5) * last_tb
            else:
                k = np.searchsorted(last_sp, cb, side="left") - 1    # last sp bin < cb
                if k >= 0: out[i] = (last_sp[k] + 0.5) * last_tb
            binsz[i] = last_tb
    for s in np.unique(day):
        d = np.flatnonzero(day == s); idx = d[in_rth[d]]
        assign(d[mod[d] < RTH1])
        if len(idx):
            tb = tbin if mode == "abs" else (tbin * c[idx[0]] if mode == "pct" else tbin * np.nanmedian(atr[idx]))
            if not np.isfinite(tb) or tb <= 0: tb = 2.5
            a = np.floor(l[idx] / tb).astype(int); b = np.floor(h[idx] / tb).astype(int)
            lo, hi = a.min(), b.max(); cnt = np.zeros(hi - lo + 1, np.int32); lastL = np.full(hi - lo + 1, -1)
            for k in range(len(idx)):
                Lt = (mod[idx[k]] - RTH0) // letter
                for q in range(a[k] - lo, b[k] - lo + 1):
                    if lastL[q] != Lt: cnt[q] += 1; lastL[q] = Lt
            if mod[idx[-1]] >= RTH1 - 15 or idx[-1] < n - 1:
                last_sp = np.flatnonzero(cnt == 1) + lo; last_tb = tb
        assign(d[mod[d] >= RTH1])
    return out, binsz
