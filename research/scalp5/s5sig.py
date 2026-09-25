"""FIVE DECLARED INTRADAY DESIGNS for 07:00-11:00 New York, each with its mechanism named first.

A HYPOTHESIS COUNT IS NOT A DIVERSIFICATION COUNT. Eight breakout hypotheses on this branch
correlated 0.87-0.96 in daily returns, because adding an MTF or volume filter to a breakout makes
the same strategy with fewer trades. So these five are chosen to be different MECHANISMS, not
different indicators, and the correlation matrix at the end is the test of whether that worked.

  S1  OPENING DRIVE CONTINUATION
      Counterparty: whoever is short the overnight inventory that has to be covered once the cash
      session prices it. The 08:30 releases and the 09:30 open force a repricing at a fixed time
      and participants who must adjust do so then. Reading: a sustained displacement from a
      PRE-MARKET-ANCHORED average, taken WITH the drive, while the session VWAP is still close
      enough that the move is not already exhausted. Descends from the APM/session-VWAP result,
      which cleared a coin-flip-side control on NQ and US100.

  S2  PRIOR-SESSION LEVEL RECLAIM
      Counterparty: resting stop and limit orders parked at yesterday's extreme, which is the one
      reference every participant can see. This is the ONE engineered feature that survived on
      this branch (V17): a breakout must also be above the last COMPLETED RTH session's high, and
      it is a LEVEL rather than a trend -- the prior CLOSE does nothing (p 0.150) and every daily
      trend state tested does nothing.

  S3  ORDER-FLOW EXHAUSTION REVERSAL
      Counterparty: sellers who have run out of size. Price makes a lower low while cumulative
      volume delta makes a HIGHER low, at CONFIRMED pivots (a pivot at i needs i-k..i+k, so it is
      knowable at i+k and never at the pivot). The only rule on this branch that has cleared a
      same-selectivity control on BOTH blocks. The delta is a PROXY -- no feed here carries
      aggressor tags, so each sub-bar's whole volume is signed by its own direction.

  S4  STRETCH FADE INTO CONTRACTING VOLATILITY
      Counterparty: a one-sided flow paying for immediacy. Price is more than k ATR from the
      session VWAP while realised volatility is FALLING, so the move is being made by fewer and
      fewer participants. Twelve independent routes on this branch end in mean reversion; this is
      the design that faces that way on purpose.

  S5  RANGE EXPANSION, COST-GATED
      Counterparty: none named -- this is the one design that is a pattern, and it carries the
      full deflation burden for it. It exists because the arithmetic says a scalp lives or dies on
      the round turn as a fraction of risk, so it trades the resolution of the opening range ONLY
      when the ATR clears its own CAUSAL TIME-OF-DAY baseline. Compression setups are
      anti-selective on cost (a low-ATR bar is where a fixed round turn looms largest); this is
      that finding used the right way round.

EVERY FEATURE IS CAUSAL and the time-of-day baselines are built from PRIOR SESSIONS ONLY. On a
23-hour tape a trailing mean is a clock in disguise: an RTH bar clears its own trailing ATR mean
almost always, so `atr / sma(atr)` measures the session and not the volatility.
"""
import numpy as np, pandas as pd


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def tod_baseline(vals, mod, day, min_obs=20):
    """Mean at THIS minute-of-day over PRIOR sessions only. Causal by construction."""
    df = pd.DataFrame({"v": vals, "m": mod, "d": day})
    g = df.groupby("m")["v"]
    csum = g.cumsum() - df.v
    cnt = g.cumcount()
    return np.where(cnt >= min_obs, csum / np.maximum(cnt, 1), np.nan)


def session_vwap(D, anchor=None):
    """VWAP anchored at `anchor` minutes (default the window open), reset daily, causal."""
    a = D["win_open"] if anchor is None else anchor
    tp = (D["h"] + D["l"] + D["c"]) / 3.0
    on = D["mod"] >= a
    df = pd.DataFrame({"pv": np.where(on, tp * D["v"], 0.0),
                       "vv": np.where(on, D["v"], 0.0), "d": D["day"]})
    g = df.groupby("d")
    vw = (g.pv.cumsum() / g.vv.cumsum().replace(0, np.nan)).to_numpy()
    vw[~on] = np.nan
    return vw


def prev_rth_levels(D, rth=(570, 960)):
    """Yesterday's completed 09:30-16:00 high and low, frozen and forward-filled.

    Assigned on EVERY session, not only those that later have RTH bars -- the truncation audit on
    this branch caught exactly that defect (a previous-day value existing only where the current
    day happened to have data)."""
    m = (D["mod"] >= rth[0]) & (D["mod"] < rth[1]) & (D["wd"] < 5)
    df = pd.DataFrame({"d": D["day"], "h": D["h"], "l": D["l"]})[m]
    g = df.groupby("d").agg(hi=("h", "max"), lo=("l", "min"))
    g = g.reindex(sorted(set(D["day"].tolist()))).shift(1).ffill()
    return (pd.Series(D["day"]).map(g.hi).to_numpy(),
            pd.Series(D["day"]).map(g.lo).to_numpy())


def cvd_proxy(D, base_1m):
    """Cumulative volume delta from the 1-MINUTE series, mapped up to the trading bar.

    Each 1m bar's WHOLE volume is signed by its own direction, which is TradingView's own rule and
    is a PROXY: no feed here carries aggressor tags. Reset at the window open so the reading is
    about today's session. The map takes the LAST completed 1m bar at or before each trading bar's
    close, so nothing from inside the forming bar leaks."""
    b = base_1m
    sgn = np.sign(b["close"].to_numpy() - b["open"].to_numpy())
    sgn[sgn == 0] = 0.0
    dv = sgn * b["volume"].to_numpy()
    mod1 = (b.index.hour * 60 + b.index.minute).to_numpy()
    day1 = b.index.normalize().values.astype("datetime64[D]").astype(np.int64)
    on = mod1 >= D["win_open"]
    cum = pd.DataFrame({"x": np.where(on, dv, 0.0), "d": day1}).groupby("d").x.cumsum().to_numpy()
    cum[~on] = np.nan
    s = pd.Series(cum, index=b.index)
    return s.reindex(D["ix"], method="ffill").to_numpy()


def _pivots(x, k):
    """Confirmed pivot lows/highs: a pivot at i is STAMPED at i+k, never at i."""
    n = len(x)
    lo = np.zeros(n, bool); hi = np.zeros(n, bool)
    for i in range(k, n - k):
        w = x[i - k:i + k + 1]
        if x[i] == np.nanmin(w):
            lo[i + k] = True
        if x[i] == np.nanmax(w):
            hi[i + k] = True
    return lo, hi


def build(D, base_1m):
    """Everything the five designs read. Returns a dict of causal series."""
    o, h, l, c, v, atr = D["o"], D["h"], D["l"], D["c"], D["v"], D["atr"]
    mod, day, inw = D["mod"], D["day"], D["inw"]
    F = {}
    F["vwap"] = session_vwap(D)
    F["d_vwap"] = (c - F["vwap"]) / np.maximum(atr, 1e-9)
    # a PRE-OPEN anchored average: seeded before 07:00 so it carries the overnight
    F["ema_pre"] = _ema(c, 42)
    F["drive"] = (c - F["ema_pre"]) / np.maximum(atr, 1e-9)
    F["atr_tod"] = atr / np.maximum(tod_baseline(atr, mod, day), 1e-9)
    F["vol_tod"] = v / np.maximum(tod_baseline(v.astype(float), mod, day), 1e-9)
    rv = pd.Series(np.diff(np.log(np.maximum(c, 1e-9)), prepend=np.nan) ** 2)
    F["rv_fast"] = rv.rolling(12, min_periods=6).mean().to_numpy() ** .5
    F["rv_slow"] = rv.rolling(60, min_periods=20).mean().to_numpy() ** .5
    F["rv_ratio"] = F["rv_fast"] / np.maximum(F["rv_slow"], 1e-12)
    ph, pl = prev_rth_levels(D)
    F["prev_hi"], F["prev_lo"] = ph, pl
    F["cvd"] = cvd_proxy(D, base_1m)
    # the opening range of the window, frozen once it completes
    ormin = D["win_open"] + 30
    m = inw & (mod < ormin)
    df = pd.DataFrame({"d": day, "h": h, "l": l})[m]
    g = df.groupby("d").agg(hi=("h", "max"), lo=("l", "min"))
    F["or_hi"] = pd.Series(day).map(g.hi).to_numpy()
    F["or_lo"] = pd.Series(day).map(g.lo).to_numpy()
    F["or_done"] = inw & (mod >= ormin)
    return F


# ------------------------------------------------------------------ the five designs
def s1_opening_drive(D, F, p):
    """Sustained displacement from the pre-open anchor, taken WITH it, VWAP not yet stretched."""
    d = F["drive"]
    sust = np.ones(len(d), bool)
    for k in range(1, p["bars"] + 1):
        sust &= np.roll(d, k) * np.sign(d) > 0
    fresh = np.abs(np.roll(d, p["bars"] + 1)) < p["thr"]
    early = D["mod"] < D["win_open"] + p["cutoff"]
    band = np.abs(F["d_vwap"]) <= p["band"]
    lg = D["inw"] & early & band & sust & fresh & (d >= p["thr"])
    sh = D["inw"] & early & band & sust & fresh & (d <= -p["thr"])
    return np.nan_to_num(lg, nan=False), np.nan_to_num(sh, nan=False)


def s2_level_reclaim(D, F, p):
    """A close beyond yesterday's completed RTH extreme that was not already beyond it."""
    c, hi, lo = D["c"], F["prev_hi"], F["prev_lo"]
    up = (c > hi + p["buf"] * D["atr"]) & (np.roll(c, 1) <= np.roll(hi, 1))
    dn = (c < lo - p["buf"] * D["atr"]) & (np.roll(c, 1) >= np.roll(lo, 1))
    strong = (c - D["l"]) / np.maximum(D["h"] - D["l"], 1e-9)
    return (np.nan_to_num(D["inw"] & up & (strong >= p["pos"]), nan=False),
            np.nan_to_num(D["inw"] & dn & (strong <= 1 - p["pos"]), nan=False))


def s3_flow_exhaustion(D, F, p):
    """Price lower low + CVD higher low at CONFIRMED pivots, and the bearish mirror."""
    plo, phi = _pivots(D["l"], p["k"])
    pho, _ = _pivots(D["h"], p["k"])
    n = D["n"]
    lg = np.zeros(n, bool); sh = np.zeros(n, bool)
    li = np.flatnonzero(plo)
    for a, b in zip(li[:-1], li[1:]):
        if b - a > p["w"]:
            continue
        ia, ib = a - p["k"], b - p["k"]
        if D["l"][ib] < D["l"][ia] and F["cvd"][ib] > F["cvd"][ia]:
            lg[b] = True
    hj = np.flatnonzero(_pivots(D["h"], p["k"])[1])
    for a, b in zip(hj[:-1], hj[1:]):
        if b - a > p["w"]:
            continue
        ia, ib = a - p["k"], b - p["k"]
        if D["h"][ib] > D["h"][ia] and F["cvd"][ib] < F["cvd"][ia]:
            sh[b] = True
    return lg & D["inw"], sh & D["inw"]


def s4_stretch_fade(D, F, p):
    """Fade a stretch from the session VWAP while realised volatility is CONTRACTING."""
    stretch = F["d_vwap"]
    calm = F["rv_ratio"] <= p["rv"]
    turn_dn = (D["c"] < D["o"]) & (np.roll(D["c"], 1) > np.roll(D["o"], 1))
    turn_up = (D["c"] > D["o"]) & (np.roll(D["c"], 1) < np.roll(D["o"], 1))
    lg = D["inw"] & calm & (stretch <= -p["k"]) & turn_up
    sh = D["inw"] & calm & (stretch >= p["k"]) & turn_dn
    return np.nan_to_num(lg, nan=False), np.nan_to_num(sh, nan=False)


def s5_range_expansion(D, F, p):
    """The opening range resolving, gated on the ATR clearing its causal time-of-day baseline."""
    live = F["or_done"] & (F["atr_tod"] >= p["atr_floor"]) & (F["vol_tod"] >= p["vol_floor"])
    up = (D["c"] > F["or_hi"]) & (np.roll(D["c"], 1) <= np.roll(F["or_hi"], 1))
    dn = (D["c"] < F["or_lo"]) & (np.roll(D["c"], 1) >= np.roll(F["or_lo"], 1))
    return (np.nan_to_num(live & up, nan=False), np.nan_to_num(live & dn, nan=False))


DESIGNS = {
    "S1 opening drive":   (s1_opening_drive, dict(thr=1.5, bars=2, cutoff=90, band=2.5)),
    "S2 level reclaim":   (s2_level_reclaim, dict(buf=0.05, pos=0.6)),
    "S3 flow exhaustion": (s3_flow_exhaustion, dict(k=3, w=20)),
    "S4 stretch fade":    (s4_stretch_fade,   dict(k=2.0, rv=1.0)),
    "S5 range expansion": (s5_range_expansion, dict(atr_floor=1.0, vol_floor=1.0)),
}
