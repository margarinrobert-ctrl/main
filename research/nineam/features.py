"""Causal features for the META layer, every one read at the SIGNAL bar.

THE RULE THIS FILE EXISTS TO OBEY. `ent_bar` is the FILL bar. Reading a feature, regime label or
ATR at the fill bar reads a bar that closes after the order is sent, and for a rule whose median
hold is short that is the bar the trade resolves on. CLAUDE.md records that this produced a
holdout result at p 0.0005 which replicated across nine strategies and was pure leakage. Every
column here is therefore built from bars at or before `i`, and `audit()` re-derives a sample of
them the slow way to prove it.

NO CALENDAR CONDITIONS. Weekday and month partition the sample five or twelve ways and hand the
search a free lottery; removing them was worth $8,771 on a holdout once already.

NO GLOBAL STANDARDISATION. Anything scaled is scaled by a TRAILING statistic, never by a mean
taken over the whole file, which is the classic way a feature matrix leaks its own future.

The families, and why each is here rather than in the primary:

  A range geometry   the mechanism's own state -- how wide the range was, how far and how fast
                     price left it. This is the most defensible meta family: it conditions on the
                     event without claiming to predict direction.
  B volatility       is today's volatility expanding or contracting relative to its own trailing
                     level. Scale-free ratios only.
  C location         where price sits relative to trailing structure, in ATR. STUDY_V40 found the
                     MA200 is priced by its DISTANCE and not by its state, so distance is what is
                     offered here.
  D microstructure   what the 30-SECOND path inside the signal bar looked like. This is the one
                     family this file can build that the rest of the branch could not, because
                     the source data is 30s. STUDY_FEATURES found exactly one feature surviving
                     FDR across 1,072 tests -- close position in bar -- so it leads the family.
  E session          gap and opening drive, relative to trailing scale.
"""
from __future__ import annotations
import numpy as np
import bars as B


def _prev_session_stats(b):
    """Prior session's close, high, low -- assigned to every bar of the FOLLOWING session."""
    si = b["si"]; n = b["n"]
    ns = si[-1] + 1
    sc = np.full(ns, np.nan); sh = np.full(ns, np.nan); sl = np.full(ns, np.nan)
    start = 0
    for s in range(ns):
        end = start
        while end < n and si[end] == s:
            end += 1
        if end > start:
            sc[s] = b["c"][end - 1]; sh[s] = b["h"][start:end].max(); sl[s] = b["l"][start:end].min()
        start = end
    pc = np.full(n, np.nan); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(n):
        s = si[i]
        if s > 0:
            pc[i] = sc[s - 1]; ph[i] = sh[s - 1]; pl[i] = sl[s - 1]
    return pc, ph, pl


def _roll_mean(x, w):
    """Trailing mean of the w bars ENDING AT i-1 -- strictly before the signal bar."""
    c = np.concatenate(([0.0], np.cumsum(np.nan_to_num(x))))
    k = np.concatenate(([0.0], np.cumsum(np.isfinite(x).astype(float))))
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        a = max(0, i - w); bnd = i
        if k[bnd] - k[a] >= max(3, w // 4):
            out[i] = (c[bnd] - c[a]) / (k[bnd] - k[a])
    return out


def build(b, r0, r1, arm, atr_n=14):
    """The feature matrix, one row per bar, valid at that bar's CLOSE."""
    n = b["n"]; h, l, c, o = b["h"], b["l"], b["c"], b["o"]
    a = B.atr(b, atr_n)
    a50 = B.atr(b, 50)
    hi, lo, ready = __import__("sim").levels(b, r0, r1)
    si = b["si"]; mod = b["mod"]
    pc, ph, pl = _prev_session_stats(b)
    F = {}
    eps = 1e-9

    # ---- A. range geometry -------------------------------------------------------------------
    rw = (hi - lo)
    F["A_range_atr"] = rw / (a + eps)                       # how wide the opening range is
    F["A_break_ext"] = np.where(h >= hi, (h - hi), (lo - l)) / (a + eps)
    # bars elapsed since the range closed -- how long the session waited for the break
    since = np.full(n, np.nan); cur = -1; k0 = 0
    for i in range(n):
        if si[i] != cur:
            cur = si[i]; k0 = -1
        if mod[i] >= r1 and k0 < 0:
            k0 = i
        since[i] = (i - k0) if k0 >= 0 else np.nan
    F["A_bars_since_arm"] = since
    F["A_close_in_range"] = (c - lo) / (rw + eps)           # where the close sits in the range
    # how much of the range the session had already used before arming
    F["A_ext_vs_range"] = F["A_break_ext"] / (F["A_range_atr"] + eps)

    # ---- B. volatility -----------------------------------------------------------------------
    F["B_atr_ratio"] = a / (a50 + eps)                      # expansion vs its own slower level
    F["B_atr_vs_trail"] = a / (_roll_mean(a, 390 // max(1, b["tf"])) + eps)
    rng = (h - l)
    F["B_bar_vs_atr"] = rng / (a + eps)
    F["B_prevday_range"] = (ph - pl) / (a + eps)

    # ---- C. location -------------------------------------------------------------------------
    e200 = B.ema(c, 200); e13 = B.ema(c, 13); e48 = B.ema(c, 48)
    F["C_d_ema200"] = (c - e200) / (a + eps)                # DISTANCE, not state (STUDY_V40)
    F["C_ema_spread"] = (e13 - e48) / (a + eps)
    F["C_d_prevclose"] = (c - pc) / (a + eps)
    F["C_pos_prevday"] = (c - pl) / (ph - pl + eps)
    F["C_d_rangemid"] = (c - (hi + lo) / 2.0) / (a + eps)

    # ---- D. microstructure, from the 30-second path inside the signal bar --------------------
    s0, s1 = b["s0"], b["s1"]
    t30c, t30h, t30l, t30o = b["t30c"], b["t30h"], b["t30l"], b["t30o"]
    cpos = np.full(n, np.nan); eff = np.full(n, np.nan); upr = np.full(n, np.nan)
    runs = np.full(n, np.nan); mrev = np.full(n, np.nan)
    for i in range(n):
        p, q = s0[i], s1[i]
        if q - p < 1:
            continue
        hh = h[i]; ll = l[i]
        cpos[i] = (c[i] - ll) / (hh - ll + eps)             # close position in bar
        seg = t30c[p:q]
        if len(seg) >= 2:
            d = np.abs(np.diff(seg)).sum()
            eff[i] = (abs(seg[-1] - seg[0]) / (d + eps))    # path efficiency inside the bar
            nh = (np.maximum.accumulate(t30h[p:q])[1:] > np.maximum.accumulate(t30h[p:q])[:-1])
            runs[i] = nh.mean()                             # share of 30s bars making a new high
            mrev[i] = (seg[-1] - seg.max()) / (hh - ll + eps)
        upr[i] = (hh - max(o[i], c[i])) / (hh - ll + eps)   # upper wick share
    F["D_close_in_bar"] = cpos
    F["D_path_eff"] = eff
    F["D_upper_wick"] = upr
    F["D_newhigh_share"] = runs
    F["D_pullback_from_hi"] = mrev

    # ---- E. session --------------------------------------------------------------------------
    sess_open = np.full(n, np.nan); cur = -1; so = np.nan
    for i in range(n):
        if si[i] != cur:
            cur = si[i]; so = o[i]
        sess_open[i] = so
    F["E_gap"] = (sess_open - pc) / (a + eps)
    F["E_drive"] = (c - sess_open) / (a + eps)
    vm = _roll_mean(b["v"].astype(float), 390 // max(1, b["tf"]))
    F["E_vol_ratio"] = b["v"] / (vm + eps)

    names = sorted(F)
    X = np.column_stack([F[k] for k in names])
    return names, X, a


def audit(b, names, X, r0, r1, arm, k=200, seed=3):
    """Re-derive a sample of rows the slow way and require them to match.

    The specific thing being proved is that row i uses no bar after i. Each probe truncates the
    series AT i, rebuilds, and compares -- a feature that peeks cannot survive truncation.
    """
    rng = np.random.default_rng(seed)
    n = b["n"]
    cand = np.flatnonzero((b["mod"] >= arm) & (b["mod"] < 960) & (b["si"] > 3))
    cand = cand[cand > 2000]
    probe = rng.choice(cand, size=min(k, len(cand)), replace=False)
    bad = []
    for i in sorted(probe):
        t = _truncate(b, i)
        nm2, X2, _ = build(t, r0, r1, arm)
        row_a = X[i]; row_b = X2[t["n"] - 1]
        for j, nm in enumerate(names):
            x, y = row_a[j], row_b[j]
            if np.isnan(x) and np.isnan(y):
                continue
            # EMA/rolling seeds differ when the series is cut, so compare on a relative tolerance
            if not np.isclose(x, y, rtol=2e-2, atol=2e-2):
                bad.append((i, nm, float(x), float(y)))
    return bad


def _truncate(b, i):
    """The same bar dict, cut so bar i is the last one that exists."""
    q = b["s1"][i]
    t = {k: v for k, v in b.items()}
    for k in ("o", "h", "l", "c", "v", "mod", "si"):
        t[k] = b[k][:i + 1]
    t["s0"] = b["s0"][:i + 1]; t["s1"] = b["s1"][:i + 1].copy(); t["s1"][-1] = q
    for k in ("t30o", "t30h", "t30l", "t30c", "t30mod", "t30si"):
        t[k] = b[k][:q]
    t["n"] = i + 1
    t["days"] = b["days"][:t["si"][-1] + 1]
    return t
