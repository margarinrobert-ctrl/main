"""Event streams for the 07:00-11:00 gold window, and the causal features that score them.

TWO PRIMARIES, deliberately, so nothing found in the EXIT is a property of one entry:
  E_BREAK   a Donchian breakout of the last `n` bars, taken inside the window, both sides.
  E_ALL     every in-window bar. Not a strategy -- it is the population, and it is what makes the
            heat diagnosis a statement about the SESSION rather than about a rule.

FEATURES ARE CAUSAL BY CONSTRUCTION and every one is checked by `truncation_audit`: recompute the
value on history that ENDS at the signal bar and require it to match. That test caught two real
leaks on this branch that inspection missed.

VOLUME FEATURES ARE BUILT ONLY WHERE VOLUME IS REAL. On XAUUSD15_MT the sixth column is the bar's
length in minutes, so the `vlm.` family is emitted as NaN there and every downstream count reports
how many features were actually available. Silently letting NaN through is how a feed defect turns
into a fake result.

AND PARTICIPATION AND VOLATILITY ARE MEASURED AGAINST A CAUSAL TIME-OF-DAY BASELINE, never a
trailing mean: on a 24-hour tape an active-hours bar clears its own trailing ATR mean almost
always, so `atr / sma(atr)` is a clock in disguise (STUDY_VWAP_STOCH_ATR). The baseline here is
the mean at THIS minute-of-day over PRIOR sessions only, with a 20-session minimum.
"""
import numpy as np, pandas as pd


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _roll(x, n, fn="mean"):
    s = pd.Series(x).rolling(n, min_periods=max(3, n // 3))
    return getattr(s, fn)().to_numpy()


def tod_baseline(vals, mod, day, min_obs=20):
    """Mean of `vals` at this minute-of-day over PRIOR sessions only. Causal by construction."""
    df = pd.DataFrame({"v": vals, "m": mod, "d": day})
    g = df.groupby("m")["v"]
    csum = g.cumsum() - df.v                       # exclude the current bar
    cnt = g.cumcount()
    out = np.where(cnt >= min_obs, csum / np.maximum(cnt, 1), np.nan)
    return out


def events(D, kind="break", don=20, side=1):
    """Signal bar indices. `break`: close through the `don`-bar extreme, inside the window."""
    h, l, c, inw = D["h"], D["l"], D["c"], D["inw"]
    if kind == "all":
        return np.flatnonzero(inw)
    hi = pd.Series(h).rolling(don).max().shift(1).to_numpy()
    lo = pd.Series(l).rolling(don).min().shift(1).to_numpy()
    s = (c > hi) if side > 0 else (c < lo)
    return np.flatnonzero(np.nan_to_num(s & inw, nan=False))


def build_features(D, with_volume=True):
    """Causal features at every bar, grouped by declared prefix. Returns (dict, list-of-names)."""
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    atr, mod, day = D["atr"], D["mod"], D["day"]
    n = D["n"]
    rng = h - l
    body = np.abs(c - o)
    uw = h - np.maximum(o, c)
    lw = np.minimum(o, c) - l
    ret = np.diff(np.log(np.maximum(c, 1e-9)), prepend=np.nan)
    F = {}

    # ---- vol.  realised volatility and its own history. V22's shipped result lives here.
    F["vol.atr_pct100"] = pd.Series(atr).rolling(100).rank(pct=True).to_numpy()
    F["vol.atr_pct500"] = pd.Series(atr).rolling(500).rank(pct=True).to_numpy()
    F["vol.rv20"] = _roll(ret ** 2, 20) ** .5
    F["vol.rv96"] = _roll(ret ** 2, 96) ** .5
    F["vol.rv_ratio"] = F["vol.rv20"] / np.maximum(F["vol.rv96"], 1e-12)
    tb = tod_baseline(atr, mod, day)
    F["vol.atr_tod"] = atr / np.maximum(tb, 1e-9)          # causal time-of-day baseline
    F["vol.atr_slope"] = atr / np.maximum(_ema(atr, 20), 1e-9)
    F["vol.range_exp"] = rng / np.maximum(atr, 1e-9)

    # ---- bar.  the shape of the signal bar itself
    F["bar.close_pos"] = np.where(rng > 0, (c - l) / np.maximum(rng, 1e-9), .5)
    F["bar.body_share"] = body / np.maximum(rng, 1e-9)
    F["bar.upper_wick"] = uw / np.maximum(rng, 1e-9)
    F["bar.lower_wick"] = lw / np.maximum(rng, 1e-9)
    F["bar.gap_prev"] = (o - np.roll(c, 1)) / np.maximum(atr, 1e-9)

    # ---- loc.  where price sits in structures it can actually see
    for k in (20, 50, 200):
        e = _ema(c, k)
        F[f"loc.d_ema{k}"] = (c - e) / np.maximum(atr, 1e-9)
    hi50 = pd.Series(h).rolling(50).max().shift(1).to_numpy()
    lo50 = pd.Series(l).rolling(50).min().shift(1).to_numpy()
    F["loc.chan_pos50"] = (c - lo50) / np.maximum(hi50 - lo50, 1e-9)
    F["loc.excess_hi50"] = (c - hi50) / np.maximum(atr, 1e-9)

    # ---- sess. the session's own structure, frozen where it must be
    ovn_hi = np.full(n, np.nan); ovn_lo = np.full(n, np.nan)
    win_o = np.full(n, np.nan); mins_left = np.full(n, np.nan)
    ws, we = D["win_start"], D["win_end"]
    dfx = pd.DataFrame({"d": day, "m": mod, "h": h, "l": l, "o": o})
    # the OVERNIGHT block is everything before the window opens on the same NY date -- knowable at
    # the window open and frozen thereafter, so no bar reads a still-forming group.
    pre = dfx.m < ws
    gp = dfx[pre].groupby("d")
    ohi, olo = gp.h.max(), gp.l.min()
    ovn_hi = dfx.d.map(ohi).to_numpy(); ovn_lo = dfx.d.map(olo).to_numpy()
    first = dfx[dfx.m >= ws].groupby("d").head(1)
    wo = pd.Series(first.o.to_numpy(), index=first.d.to_numpy())
    win_o = dfx.d.map(wo).to_numpy()
    mins_left = (we - mod).astype(float)
    F["sess.ovn_pos"] = (c - ovn_lo) / np.maximum(ovn_hi - ovn_lo, 1e-9)
    F["sess.ovn_width"] = (ovn_hi - ovn_lo) / np.maximum(atr, 1e-9)
    F["sess.d_win_open"] = (c - win_o) / np.maximum(atr, 1e-9)
    F["sess.mins_left"] = mins_left
    F["sess.frac_elapsed"] = 1.0 - mins_left / (we - ws)

    # ---- mom.  short-horizon momentum, which on this branch keeps coming back negative
    for k in (4, 16, 48):
        F[f"mom.roc{k}"] = (c - np.roll(c, k)) / np.maximum(atr, 1e-9)
        F[f"mom.roc{k}"][:k] = np.nan
    F["mom.run_up"] = (c - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(atr, 1e-9)

    # ---- vlm.  volume, ONLY where the column is real. Prefix is `vlm.` and not `vol.`, which
    #      owns volatility -- sharing a prefix credits one family's weight to the other.
    if with_volume and np.isfinite(v).any():
        vb = tod_baseline(v, mod, day)
        F["vlm.tod_ratio"] = v / np.maximum(vb, 1e-9)
        F["vlm.z20"] = (v - _roll(v, 20)) / np.maximum(_roll(v, 20, "std"), 1e-9)
        F["vlm.trend"] = _roll(v, 5) / np.maximum(_roll(v, 50), 1e-9)
    else:
        for k in ("vlm.tod_ratio", "vlm.z20", "vlm.trend"):
            F[k] = np.full(n, np.nan)
    return F, sorted(F)


def truncation_audit(D, names, probes=40, seed=0, with_volume=True):
    """Recompute every feature on history ENDING at bar i and require the value to match.

    The only honest leakage test on this branch: it caught overnight aggregates reading their own
    still-forming group, and previous-day stats dropping out of a groupby index. Inspection missed
    both."""
    rng = np.random.default_rng(seed)
    full, _ = build_features(D, with_volume)
    idx = np.flatnonzero(D["inw"])
    idx = idx[idx > 3000]
    probe = rng.choice(idx, size=min(probes, len(idx)), replace=False)
    bad = []
    for i in sorted(probe):
        Dt = {k: (val[:i + 1] if isinstance(val, np.ndarray) and val.shape[:1] == (D["n"],) else val)
              for k, val in D.items()}
        Dt["n"] = i + 1
        tr, _ = build_features(Dt, with_volume)
        for nm in names:
            a, b = full[nm][i], tr[nm][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True):
                bad.append((nm, int(i), float(a), float(b)))
    return bad
