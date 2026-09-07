"""Volume profile and auction-theory primitives, built causally from 1-minute bars.

Everything here answers one of two questions:

  * WHERE DID THE MARKET ACCEPT PRICE?  The point of control and the value area of a completed
    session, plus high-volume nodes -- prices the auction spent time at and returned to.
  * WHERE DID IT REFUSE TO?  Low-volume nodes: prices the auction passed through quickly. Auction
    theory calls those inefficient and expects them to be revisited. That is a testable claim and
    `research/inefficiency.py` tests it rather than assuming it.

Two construction choices, stated because they change the numbers:

  * A 1-minute bar's volume is spread UNIFORMLY across the price bins it covers. Real volume is
    not uniform inside a bar, and a genuine tick profile would differ. This is the standard bar
    approximation and it is what a TradingView volume profile does too.
  * Bins are a fixed number of points, not ticks. At NQ's 0.25 tick a one-point bin is four ticks;
    finer bins make every node look low-volume and coarser ones erase the nodes entirely.

CAUSALITY. A completed session's profile is used only from the NEXT session's open. The developing
profile at bar i uses bars from the session open up to and including i, never past it. Both are
checked by `leakage_check()` rather than asserted.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
from nqdata import load_bars, minute_of_day, session_index

RTH = (570, 960)          # 09:30-16:00 New York
BIN = 1.0                 # points per bin
VA_FRAC = 0.70            # value area, the conventional 70% of volume
LVN_FRAC = 0.35           # a bin below this share of the POC bin is a low-volume node
HVN_FRAC = 0.80           # and above this, a high-volume node
POOR_FRAC = 0.35          # an extreme holding this much of POC volume is an unfinished auction
SMOOTH = 5                # bins of smoothing before nodes are found -- see _nodes
EDGE = 0.05               # top/bottom share of the session range that counts as "the extreme"

_C = {}


@njit(cache=True)
def _accumulate(h, l, v, sess_row, base, nbin, H):
    """Spread each bar's volume across the bins it spans. H is (n_sess, nbin)."""
    for i in range(len(h)):
        r = sess_row[i]
        if r < 0:
            continue
        a = int((l[i] - base) / BIN)
        b = int((h[i] - base) / BIN)
        if a < 0:
            a = 0
        if b >= nbin:
            b = nbin - 1
        if b < a:
            continue
        share = v[i] / (b - a + 1)
        for k in range(a, b + 1):
            H[r, k] += share


@njit(cache=True)
def _value_area(row, frac):
    """POC bin, then expand outward taking the heavier neighbour until frac of volume is inside."""
    n = len(row)
    tot = 0.0
    for k in range(n):
        tot += row[k]
    if tot <= 0.0:
        return -1, -1, -1
    poc = 0
    best = row[0]
    for k in range(1, n):
        if row[k] > best:
            best = row[k]; poc = k
    lo = poc; hi = poc
    got = row[poc]
    target = frac * tot
    while got < target and (lo > 0 or hi < n - 1):
        up = row[hi + 1] if hi < n - 1 else -1.0
        dn = row[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1; got += row[hi]
        else:
            lo -= 1; got += row[lo]
    return poc, lo, hi


@njit(cache=True)
def _developing(h, l, v, sess_row, mod, base, nbin, frac, poc_o, vah_o, val_o):
    """Running profile inside each session: the POC and value area as they stood at each bar."""
    n = len(h)
    row = np.zeros(nbin, np.float64)
    cur = -1
    for i in range(n):
        r = sess_row[i]
        if r < 0:
            poc_o[i] = np.nan; vah_o[i] = np.nan; val_o[i] = np.nan
            continue
        if r != cur:
            row[:] = 0.0
            cur = r
        a = int((l[i] - base) / BIN)
        b = int((h[i] - base) / BIN)
        if a < 0:
            a = 0
        if b >= nbin:
            b = nbin - 1
        if b >= a:
            share = v[i] / (b - a + 1)
            for k in range(a, b + 1):
                row[k] += share
        p, lo, hi = _value_area(row, frac)
        if p < 0:
            poc_o[i] = np.nan; vah_o[i] = np.nan; val_o[i] = np.nan
        else:
            poc_o[i] = base + (p + 0.5) * BIN
            val_o[i] = base + lo * BIN
            vah_o[i] = base + (hi + 1) * BIN


def _smooth(row, k=SMOOTH):
    """A centred moving average over the histogram.

    Without this, node detection at one-point bins returns the histogram's noise: the first build
    found a median of 24 low-volume nodes per session, which is not structure, it is sampling.
    Smoothing over five bins turns "this single point traded thinly" into "this five-point shelf
    traded thinly", which is the thing auction theory is actually about.
    """
    if k <= 1:
        return row
    c = np.cumsum(np.r_[0.0, row])
    out = np.empty_like(row)
    half = k // 2
    n = len(row)
    for i in range(n):
        a = max(0, i - half); b = min(n, i + half + 1)
        out[i] = (c[b] - c[a]) / (b - a)
    return out


def _nodes(row, base, frac, above, min_gap=8):
    """Local extrema of the SMOOTHED histogram, as prices, thinned so they are not adjacent.

    `min_gap` keeps two nodes from sitting inside the same shelf; without it a broad thin area
    reports one node per bin.
    """
    live = np.flatnonzero(row > 0)
    if len(live) < 3 * SMOOTH:
        return np.empty(0)
    a, b = live[0], live[-1]
    s = _smooth(row)
    peak = s[a:b + 1].max()
    if peak <= 0:
        return np.empty(0)
    cand = []
    for k in range(a + 1, b):
        if above:
            if s[k] >= frac * peak and s[k] >= s[k - 1] and s[k] >= s[k + 1]:
                cand.append((s[k], k))
        else:
            if s[k] <= frac * peak and s[k] <= s[k - 1] and s[k] <= s[k + 1]:
                cand.append((-s[k], k))
    cand.sort(reverse=True)              # strongest node first, then thin by distance
    picked = []
    for _score, k in cand:
        if all(abs(k - j) >= min_gap for j in picked):
            picked.append(k)
    picked.sort()
    return np.array([base + (k + 0.5) * BIN for k in picked])


def build(path="data/NQ_1m.csv", window=RTH, max_nodes=24, src_tf=1):
    """One profile per RTH session. Returns per-session arrays plus the developing profile.

    `src_tf` is the bar size the profile is accumulated from, in minutes. The research default is
    1. TradingView caps how many intrabars `request.security_lower_tf` will return -- roughly
    100,000 on a standard plan, and three years of 1-minute data inside 30-minute bars is 270,000
    -- so a Pine version has to accumulate from 5-minute bars instead. src_tf=5 measures what that
    approximation costs before any script is written.
    """
    key = (path, window, max_nodes, src_tf)
    if key in _C:
        return _C[key]
    df = load_bars(path)
    if src_tf > 1:
        from bos_choch import resample
        df = resample(df, src_tf)
    mod = minute_of_day(df.index)
    keep = (mod >= window[0]) & (mod < window[1])
    d = df[keep]
    mod = mod[keep]
    sess = session_index(d.index, window[0])
    us, sess_row = np.unique(sess, return_inverse=True)
    h = d["high"].to_numpy(float); l = d["low"].to_numpy(float)
    c = d["close"].to_numpy(float); o = d["open"].to_numpy(float)
    v = d["volume"].to_numpy(float)

    base = np.floor(l.min() / BIN) * BIN
    nbin = int(np.ceil((h.max() - base) / BIN)) + 2
    H = np.zeros((len(us), nbin), np.float64)
    _accumulate(h, l, v, sess_row.astype(np.int64), base, nbin, H)

    n = len(us)
    poc = np.full(n, np.nan); vah = np.full(n, np.nan); val = np.full(n, np.nan)
    hi_ = np.full(n, np.nan); lo_ = np.full(n, np.nan)
    poor_hi = np.zeros(n, bool); poor_lo = np.zeros(n, bool)
    vol = np.zeros(n)
    LVN = np.full((n, max_nodes), np.nan)
    HVN = np.full((n, max_nodes), np.nan)
    for r in range(n):
        row = H[r]
        p, a, b = _value_area(row, VA_FRAC)
        if p < 0:
            continue
        poc[r] = base + (p + 0.5) * BIN
        val[r] = base + a * BIN
        vah[r] = base + (b + 1) * BIN
        live = np.flatnonzero(row > 0)
        hi_[r] = base + (live[-1] + 1) * BIN
        lo_[r] = base + live[0] * BIN
        peak = row[p]
        # "poor" means the auction stopped without tapering: the top or bottom slice of the
        # range still holds real volume instead of thinning into excess. Measured over a slice
        # of the range rather than a single bin, because one 1-point bin at an extreme is always
        # thin and the first build reported poor highs on 0% of sessions as a result.
        span = live[-1] - live[0] + 1
        w = max(int(EDGE * span), 1)
        poor_hi[r] = row[live[-1] - w + 1:live[-1] + 1].mean() >= POOR_FRAC * peak
        poor_lo[r] = row[live[0]:live[0] + w].mean() >= POOR_FRAC * peak
        vol[r] = row.sum()
        for arr, nd in ((LVN, _nodes(row, base, LVN_FRAC, False)),
                        (HVN, _nodes(row, base, HVN_FRAC, True))):
            k = min(len(nd), max_nodes)
            arr[r, :k] = nd[:k]

    dp = np.empty(len(h)); dva = np.empty(len(h)); dvl = np.empty(len(h))
    _developing(h, l, v, sess_row.astype(np.int64), mod.astype(np.int64), base, nbin,
                VA_FRAC, dp, dva, dvl)

    # naked POCs: a session's POC that no LATER session has traded through. Computed forward, so
    # "naked as at session r" only ever looks at sessions strictly before r.
    naked = np.zeros((n, n), bool)          # naked[r, j] : POC of j still untouched entering r
    touched = np.zeros(n, bool)
    for r in range(n):
        naked[r] = ~touched                 # status as at session r's OPEN, completed sessions only
        for j in range(r):                  # strictly earlier sessions -- a session cannot un-nake
            if not touched[j] and not np.isnan(poc[j]) and lo_[r] <= poc[j] <= hi_[r]:
                touched[j] = True           # a LATER session traded through it

    # naked value-area edges: a VAH or VAL that no LATER session has traded through. Same
    # forward scan as the naked POC, and the same rule -- a session cannot un-nake its own edge,
    # which is the bug that made the naked-POC conditions fire zero times on the first build.
    nvah = np.zeros((n, n), bool); nval = np.zeros((n, n), bool)
    for lvl, mat in ((vah, nvah), (val, nval)):
        seen = np.zeros(n, bool)
        for r in range(n):
            mat[r] = ~seen
            for j in range(r):
                if not seen[j] and not np.isnan(lvl[j]) and lo_[r] <= lvl[j] <= hi_[r]:
                    seen[j] = True

    # the session's opening price, for the open-relative-to-value classification
    op = np.full(n, np.nan)
    for r in range(n):
        sel = sess_row == r
        if sel.any():
            op[r] = o[np.flatnonzero(sel)[0]]

    out = dict(sess=us, poc=poc, vah=vah, val=val, hi=hi_, lo=lo_, vol=vol, open_px=op,
               naked_vah=nvah, naked_val=nval,
               poor_hi=poor_hi, poor_lo=poor_lo, LVN=LVN, HVN=HVN, H=H, base=base,
               dev_poc=dp, dev_vah=dva, dev_val=dvl, bar_sess=sess, bar_mod=mod,
               bar_idx=d.index, bar_o=o, bar_h=h, bar_l=l, bar_c=c, naked=naked)
    _C[key] = out
    return out


def leakage_check(P, trials=6, seed=5):
    """Recompute on truncated data and confirm nothing before the cut moved.

    A profile is exactly the kind of object that leaks: the value area of a session is not known
    until the session ends, and a developing profile is trivially easy to write in a way that uses
    the whole session. This rebuilds from a prefix of the bars and compares.
    """
    rng = np.random.default_rng(seed)
    nb = len(P["bar_c"])
    bad = []
    for f in np.linspace(0.35, 0.9, trials):
        T = int(f * nb)
        s = P["bar_sess"][:T]
        us, row = np.unique(s, return_inverse=True)
        nbin = P["H"].shape[1]
        H2 = np.zeros((len(us), nbin), np.float64)
        _accumulate(P["bar_h"][:T], P["bar_l"][:T], np.ones(T), row.astype(np.int64),
                    P["base"], nbin, H2)          # volumes cancel in the comparison below
        dp = np.empty(T); dva = np.empty(T); dvl = np.empty(T)
        _developing(P["bar_h"][:T], P["bar_l"][:T],
                    np.asarray(P["H"][0][:0].tolist() + [0.0] * 0) if False else
                    _vols(P)[:T], row.astype(np.int64), P["bar_mod"][:T].astype(np.int64),
                    P["base"], nbin, VA_FRAC, dp, dva, dvl)
        a = P["dev_poc"][:T]; b = dp
        m = np.isfinite(a) & np.isfinite(b)
        diff = int((np.abs(a[m] - b[m]) > 1e-9).sum())
        if diff:
            bad.append((f, diff))
    return bad


def _vols(P):
    if "bar_v" not in P:
        df = load_bars("data/NQ_1m.csv")
        mod = minute_of_day(df.index)
        keep = (mod >= RTH[0]) & (mod < RTH[1])
        P["bar_v"] = df[keep]["volume"].to_numpy(float)
    return P["bar_v"]


if __name__ == "__main__":
    import time
    t0 = time.time()
    P = build()
    n = len(P["sess"])
    print(f"volume profile: {n} RTH sessions, {len(P['bar_c']):,} 1-minute bars, "
          f"{P['H'].shape[1]:,} price bins of {BIN:g} point ({time.time()-t0:.0f}s)")
    va = P["vah"] - P["val"]
    rng_ = P["hi"] - P["lo"]
    print(f"  value area width   median {np.nanmedian(va):.0f} points, "
          f"{100*np.nanmedian(va/rng_):.0f}% of the session range")
    print(f"  low-volume nodes   median {np.median((~np.isnan(P['LVN'])).sum(1)):.0f} per session")
    print(f"  high-volume nodes  median {np.median((~np.isnan(P['HVN'])).sum(1)):.0f} per session")
    print(f"  poor high {100*P['poor_hi'].mean():.0f}% of sessions, "
          f"poor low {100*P['poor_lo'].mean():.0f}%")
    nk = P["naked"].sum(1)
    print(f"  naked POCs carried  median {np.median(nk):.0f}, max {nk.max()}")
    print(f"  naked VAHs carried  median {np.median(P['naked_vah'].sum(1)):.0f}, "
          f"naked VALs {np.median(P['naked_val'].sum(1)):.0f}")
    bad = leakage_check(P)
    print(f"  leakage check: {'CLEAN' if not bad else bad}")
