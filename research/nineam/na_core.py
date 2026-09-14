"""The 09:00-09:30 New York pre-open range, broken after the 09:30 cash open, with an EMA 13/48
cross as the momentum confirmation and LonesomeTheBlue's support/resistance channels as a third
gate.

PHASE 0, WRITTEN BEFORE ANY CODE RAN, AND IT IS NOT A STRONG STORY.
  The half hour before the cash open is where overnight inventory is repositioned ahead of the
  opening auction, so its extremes are levels at which a lot of resting orders sit. That names a
  population of orders; it does not name a counterparty who MUST trade at a bad time. There is no
  redemption, no roll, no margin call. Under `references/mechanisms.md` this is a FITTED PATTERN
  wearing a story, and it therefore carries the full deflation burden rather than escaping it.

WHAT THIS BRANCH ALREADY KNOWS, so none of it is re-discovered:
  `STUDY_V35_BALANCE`  swept 11 window starts x 4 lengths against 150 random same-length
                       same-session controls each: 0 of 38 cells clear p<=0.05 where 1.9 are
                       expected, the classic Initial Balance scores excess +0.0314 at p 0.353, and
                       the conclusion was DO NOT RE-RUN THE INITIAL BALANCE IN ANY FORM. The
                       09:00 x 30-minute cell is almost certainly inside that sweep. What is NOT
                       inside it is the CONJUNCTION asked for here -- the EMA cross and the S/R
                       channel -- which V35 never tested.
  `STUDY_V35_BALANCE`  also: the nearer edge breaks first 78.6% of the time by pure arithmetic, the
                       "80% rule" measures 0.937 against 0.968 for random same-length windows, and
                       79% direction accuracy buys no edge. So a high break-direction hit rate here
                       is expected and is not evidence.
  `STUDY_V41_EMA_DONCHIAN`  EMA13>EMA48 holds on 82.6% of breakout bars against 36.9% of bars in
                       general. The STATE form is very nearly the trigger restated; only the
                       RECENCY form binds. Both are declared here and the base rate is measured on
                       the trigger's own bars BEFORE any P&L.
  `STUDY_V55` / `STUDY_V51` / `STUDY_V52`  the 13x48 cross has now failed a held-back read three
                       times. It is included because it was asked for, not because it is promising.
  `STUDY_MA_LAG`       MA TYPE is not a degree of freedom for a single average -- SMA(11), LMA(16)
                       and EMA(11) share a lag of 5, correlate 0.9999+ and overlap 89.5-97.3% of
                       triggers. The "MA 3 in 1" indicator's type selector is therefore tested as a
                       CHECK on that finding, not as a search axis.

BLOCKS.  NQ 1-minute is the only feed that can resolve a 09:00-09:30 window exactly, and it is also
the most spent block on this branch. US100_LONG_15m and US30_LONG_15m CAN carry it -- the window is
exactly the 09:00 and 09:15 bars and 09:30 is a clean bar boundary -- so unlike
`STUDY_IB25_RETRACEMENT` this question IS answerable cross-market. US30_ISO_15m is a DIFFERENT
PROVIDER over a span no search here has touched and is reserved as the forward block.

COST.  Charged from the first run, never added later, and swept so the break-even is measured.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "v38"))
import v38feeds as F  # noqa: E402

# round turn in index points: broker + exchange + the NFA line + slippage (STUDY_COSTS)
COST = {"NQ": 1.72, "US100L": 1.215, "US30L": 2.29, "US30I": 2.29}
PV = {"NQ": 2.0, "US100L": 1.0, "US30L": 5.0, "US30I": 5.0}
CUT = {"NQ": "2025-01-01", "US100L": "2023-06-01", "US30L": "2023-01-01", "US30I": None}
# US30_ISO OVERLAPS US30_LONG in calendar (both carry 2024-08 .. 2025-07), so only the span AFTER
# US30_LONG ends is genuinely unseen. `mr30core` reserves exactly this date and it is kept here.
ISO_FROM = "2025-07-16"

RS, RE = 540, 570      # 09:00 .. 09:30 New York, in minutes of day
OPEN_M = 570           # the 09:30 cash open


# ----------------------------------------------------------------------------- data
def load(name="NQ", tf=15):
    """New York time on every feed. NQ_1m is stamped in UTC and everything else here is already NY
    -- a loader that forgets the conversion puts a 09:30 window at 04:30 (CLAUDE.md)."""
    if name == "NQ":
        d = pd.read_csv(os.path.join(ROOT, "data/NQ_1m.csv"))
        ix = pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True)) \
            .tz_convert("America/New_York").tz_localize(None)
        f = pd.DataFrame({c: d[c].to_numpy(float) for c in
                          ("open", "high", "low", "close", "volume")}, index=ix)
    elif name == "US30I":
        d = pd.read_csv(os.path.join(ROOT, "data/US30_ISO_15m.csv"), parse_dates=["ny"])
        f = pd.DataFrame({c: d[c].to_numpy(float) for c in
                          ("open", "high", "low", "close", "volume")}, index=d["ny"])
    else:
        f = F.load(name)[["open", "high", "low", "close", "volume"]]
    f = f.sort_index()
    f = f[~f.index.duplicated(keep="first")]
    base = 1 if name == "NQ" else 15
    if tf != base:
        f = f.resample(f"{tf}min", origin="start_day").agg(
            dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = f.index.hour * 60 + f.index.minute
    f["day"] = (f.index.normalize().view("int64") // 86_400_000_000_000).astype(np.int64)
    return f


def blocks(f, name="NQ"):
    cut = CUT[name]
    if name == "US30I":
        return {"C_forward": np.asarray(f.index >= ISO_FROM)}
    if cut is None:
        return {"C_forward": np.ones(len(f), bool)}
    ix = np.asarray(f.index < cut)
    return {"A_research": ix, "B_holdout": ~ix}


# ----------------------------------------------------------------------------- the range
def ranges(f, rs=RS, re_=RE):
    """Per-session high/low of the bars whose STAMP lies in [rs, re_). On a 15-minute feed that is
    exactly the 09:00 and 09:15 bars; on 1-minute it is the thirty minutes 09:00..09:29. The value
    is knowable at the close of the last such bar and is used only from re_ onward, so it is causal
    by construction -- the truncation audit checks it rather than the comment asserting it."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    h = f["high"].to_numpy(); l = f["low"].to_numpy()
    m = (mod >= rs) & (mod < re_)
    n = len(f)
    rhi = np.full(n, np.nan); rlo = np.full(n, np.nan); rn = np.zeros(n, np.int64)
    g = pd.DataFrame({"day": day[m], "h": h[m], "l": l[m]}).groupby("day")
    agg = g.agg(hi=("h", "max"), lo=("l", "min"), k=("h", "size"))
    dmap_hi = agg["hi"].to_dict(); dmap_lo = agg["lo"].to_dict(); dmap_k = agg["k"].to_dict()
    rhi = np.array([dmap_hi.get(d, np.nan) for d in day])
    rlo = np.array([dmap_lo.get(d, np.nan) for d in day])
    rn = np.array([dmap_k.get(d, 0) for d in day], np.int64)
    return rhi, rlo, rn



def hour_candle(f, hs=480, he=540):
    """The 08:00-09:00 New York HOURLY candle, built from the chart's own bars per session.

    Open = the open of the first bar stamped at or after `hs`; close = the close of the last bar
    stamped before `he`; high/low over the same set. It COMPLETES at 09:00, before the 09:00 range
    starts and ninety minutes before the 09:30 arm, so a signal bar reading it is causal by
    construction -- the truncation audit checks that rather than the comment asserting it.

    Declared in MINUTES like every other reach on this branch, so the same numbers mean the same
    thing on a 1-minute chart as on a 15-minute one (`STUDY_V57`). Returns per-bar arrays broadcast
    over the session: open, high, low, close, and the count of constituent bars.
    """
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    o = f["open"].to_numpy(); h = f["high"].to_numpy()
    l = f["low"].to_numpy(); c = f["close"].to_numpy()
    m = (mod >= hs) & (mod < he)
    g = pd.DataFrame({"day": day[m], "mod": mod[m], "o": o[m], "h": h[m],
                      "l": l[m], "c": c[m]}).sort_values(["day", "mod"])
    agg = g.groupby("day").agg(op=("o", "first"), hi=("h", "max"),
                               lo=("l", "min"), cl=("c", "last"), k=("o", "size"))
    mo = agg["op"].to_dict(); mh = agg["hi"].to_dict()
    ml = agg["lo"].to_dict(); mc = agg["cl"].to_dict(); mk = agg["k"].to_dict()
    return (np.array([mo.get(d, np.nan) for d in day]),
            np.array([mh.get(d, np.nan) for d in day]),
            np.array([ml.get(d, np.nan) for d in day]),
            np.array([mc.get(d, np.nan) for d in day]),
            np.array([mk.get(d, 0) for d in day], np.int64))


def hour_side(f, hs=480, he=540, reading="direction", body_atr=0.0):
    """The 08:00 hour's DIRECTION as +1 / -1 / 0, under three declared readings.

    `direction`  close > open  -- the literal ask.
    `body`       the same, but only when |close - open| >= body_atr x ATR at the hour's close;
                 otherwise 0, i.e. the hour has no opinion and the gate passes nothing.
    `closepos`   where the close sits in the HOUR'S OWN range: upper half bullish, lower half
                 bearish. A different reading of the same hour rather than a second parameter.
    """
    ho, hh, hl, hc, hk = hour_candle(f, hs, he)
    at = f["atr"].to_numpy()
    out = np.zeros(len(f), np.int64)
    ok = np.isfinite(ho) & np.isfinite(hc) & (hk > 0)
    if reading == "closepos":
        rng = hh - hl
        good = ok & np.isfinite(rng) & (rng > 0)
        pos = np.where(good, (hc - hl) / np.where(rng > 0, rng, 1.0), np.nan)
        out = np.where(good & (pos > 0.5), 1, np.where(good & (pos < 0.5), -1, 0)).astype(np.int64)
        return out
    body = np.abs(hc - ho)
    good = ok
    if reading == "body":
        good = good & np.isfinite(at) & (at > 0) & (body >= body_atr * at)
    out = np.where(good & (hc > ho), 1, np.where(good & (hc < ho), -1, 0)).astype(np.int64)
    return out

# ----------------------------------------------------------------------------- moving averages
def ma(x, n, kind="ema"):
    s = pd.Series(x)
    if kind == "ema":
        return s.ewm(span=n, adjust=False).mean().to_numpy()
    if kind == "sma":
        return s.rolling(n).mean().to_numpy()
    if kind == "wma":
        w = np.arange(1, n + 1, dtype=float)
        return s.rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True).to_numpy()
    if kind == "hull":
        h1 = ma(x, max(1, n // 2), "wma"); h2 = ma(x, n, "wma")
        return ma(2 * h1 - h2, max(1, int(round(np.sqrt(n)))), "wma")
    raise ValueError(kind)


def vwma(x, v, n):
    num = pd.Series(x * v).rolling(n).sum().to_numpy()
    den = pd.Series(v).rolling(n).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def ema_state(f, fast=13, slow=48, kind="ema"):
    """Returns (state, age) -- state = fast>slow, age = bars since the most recent UP cross, causal
    at every bar. `age` is a forward scan, not a fill-forward to the NEXT cross
    (`STUDY_DIVERGENCE_CONFIRM`'s leak)."""
    c = f["close"].to_numpy()
    if kind == "vwma":
        a = vwma(c, f["volume"].to_numpy(), fast); b = vwma(c, f["volume"].to_numpy(), slow)
    else:
        a = ma(c, fast, kind); b = ma(c, slow, kind)
    st = np.zeros(len(c), bool)
    ok = np.isfinite(a) & np.isfinite(b)
    st[ok] = a[ok] > b[ok]
    up = np.zeros(len(c), bool)
    up[1:] = st[1:] & ~st[:-1]
    age = np.full(len(c), 10 ** 6, np.int64)
    last = -10 ** 6
    for i in range(len(c)):
        if up[i]:
            last = i
        age[i] = i - last
    dn = np.zeros(len(c), bool)
    dn[1:] = (~st[1:]) & st[:-1]
    aged = np.full(len(c), 10 ** 6, np.int64)
    last = -10 ** 6
    for i in range(len(c)):
        if dn[i]:
            last = i
        aged[i] = i - last
    return st, age, aged


# ----------------------------------------------------------------------------- S/R channels
def sr_levels(f, at, prd=10, chan_w=5.0, min_strength=1, maxnum=6, loopback=290, look=300):
    """LonesomeTheBlue's support/resistance channels, evaluated ONLY at the bars in `at`.

    His algorithm: collect pivot highs and lows with period `prd` over the last `loopback` bars;
    for each pivot open a channel of width `chan_w`% of (highest(high,look) - lowest(low,look));
    a pivot joins a channel if it lies inside; keep the strongest `maxnum` non-overlapping
    channels. A pivot at bar j needs bars j-prd..j+prd so it is knowable at j+prd, never at j --
    the confirmation lag `STUDY_DIVERGENCE_CONFIRM` found is applied here rather than assumed away.

    Returns (lo, hi) arrays of shape (len(at), maxnum), NaN-padded.
    """
    h = f["high"].to_numpy(); l = f["low"].to_numpy()
    n = len(h)
    ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for j in range(prd, n - prd):
        w = h[j - prd:j + prd + 1]
        if h[j] == w.max() and np.argmax(w) == prd:
            ph[j] = True
        w = l[j - prd:j + prd + 1]
        if l[j] == w.min() and np.argmin(w) == prd:
            pl[j] = True
    out_lo = np.full((len(at), maxnum), np.nan)
    out_hi = np.full((len(at), maxnum), np.nan)
    for q, i in enumerate(at):
        if i < look + prd:
            continue
        cw = (h[i - look + 1:i + 1].max() - l[i - look + 1:i + 1].min()) * chan_w / 100.0
        if not np.isfinite(cw) or cw <= 0:
            continue
        j0 = max(prd, i - loopback)
        # a pivot at j is only CONFIRMED at j+prd, so it may be used when j + prd <= i
        pv = []
        for j in range(j0, i - prd + 1):
            if ph[j]:
                pv.append(h[j])
            if pl[j]:
                pv.append(l[j])
        if not pv:
            continue
        pv = np.asarray(pv)
        cand = []
        for p in pv:
            lo, hi = p, p
            inn = pv[(pv >= p - cw) & (pv <= p + cw)]
            if len(inn) == 0:
                continue
            lo = min(p, inn.min()); hi = max(p, inn.max())
            if hi - lo > cw:
                hi = lo + cw
            cand.append((len(inn), lo, hi))
        cand.sort(key=lambda t: -t[0])
        kept = []
        for s, lo, hi in cand:
            if s < min_strength:
                continue
            if any(not (hi < klo or lo > khi) for _, klo, khi in kept):
                continue
            kept.append((s, lo, hi))
            if len(kept) >= maxnum:
                break
        for r, (_, lo, hi) in enumerate(kept):
            out_lo[q, r] = lo; out_hi[q, r] = hi
    return out_lo, out_hi


# ----------------------------------------------------------------------------- the event stream
def events(f, rhi, rlo, side="long", buf_atr=0.0, rs=RS, re_=RE, open_m=OPEN_M,
           end_m=960, touch=True, min_rn=1):
    """The FIRST bar at or after `open_m` whose high clears the range high (long) or whose low
    breaks the range low (short). One event per session per side. The fill is the NEXT bar's open,
    which is what a script can actually place."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    h = f["high"].to_numpy(); l = f["low"].to_numpy(); at = f["atr"].to_numpy()
    n = len(f)
    ok = (mod >= open_m) & (mod < end_m) & np.isfinite(rhi) & np.isfinite(rlo) & (at > 0)
    b = buf_atr * at
    up = ok & ((h >= rhi + b) if touch else (h > rhi + b))
    dn = ok & ((l <= rlo - b) if touch else (l < rlo - b))
    sig = []; sd = []
    seen_u = set(); seen_d = set()
    want_u = side in ("long", "both"); want_d = side in ("short", "both")
    for i in range(n):
        if not ok[i]:
            continue
        d = day[i]
        if want_u and up[i] and d not in seen_u:
            seen_u.add(d); sig.append(i); sd.append(1)
        if want_d and dn[i] and d not in seen_d:
            seen_d.add(d); sig.append(i); sd.append(-1)
    o = np.argsort(np.asarray(sig, np.int64), kind="stable")
    return np.asarray(sig, np.int64)[o], np.asarray(sd, np.int64)[o]


@njit(cache=True)
def _walk(o, h, l, c, at, mod, sig, side, stop_a, tgt_r, flat_m, cost, use_rng, rhi, rlo,
          stop_pts, tgt_pts, be_pts, be_off):
    """One live position. Entry at the NEXT bar's open. The stop is an ATR multiple at the SIGNAL
    bar (knowable when the order is written) or the opposite side of the range when use_rng. The
    target is in R. A bar touching both is resolved as the STOP and the ambiguous share is returned
    so the convention can be priced (`STUDY_VOLBO_BREAKOUT`: worth twice an edge once).

    `be_pts` arms an AUTO BREAKEVEN: once the bar's favourable extreme reaches `be_pts` from the
    fill, the stop moves to the fill (+ `be_off`). The ratchet can only BIND FROM THE NEXT BAR --
    within the trigger bar OHLC cannot say whether the move came before or after the pullback, so
    arming and filling the moved stop on the same bar invents information (`research/us30exit`).

    `stop_pts` / `tgt_pts` override with an ABSOLUTE distance in index points. Kept as a separate
    parameterisation rather than converted, because the two do not rank the same axis the same way:
    a fixed 100-point stop is 2.35 ATR on US30 and 4.36 on US100, and 4.23 ATR in 2016 against 1.10
    in 2025 on US30 alone, so a points grid confounds geometry with market and with era
    (`STUDY_DL50`, `STUDY_US30_SCALP_0711` sections 6-7). Both are run and both are printed."""
    n = len(c); m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); rr = np.zeros(m); risk = np.zeros(m)
    why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        a = at[i]
        if a <= 0 or not np.isfinite(a):
            continue
        s = side[q]
        e = o[i + 1]
        if use_rng == 1:
            rk = (e - rlo[i]) if s > 0 else (rhi[i] - e)
            if rk <= 0 or not np.isfinite(rk):
                continue
        elif stop_pts > 0:
            rk = stop_pts
        else:
            rk = stop_a * a
        stop = e - s * rk
        if tgt_pts > 0:
            tgt = e + s * tgt_pts
        elif tgt_r > 0:
            tgt = e + s * tgt_r * rk
        else:
            tgt = np.nan
        j = i + 1
        ex = np.nan; rsn = 0
        armed = False
        be_lvl = e + s * be_off
        while j < n:
            hit_s = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            hit_t = False
            if np.isfinite(tgt):
                hit_t = (h[j] >= tgt) if s > 0 else (l[j] <= tgt)
            if hit_s and hit_t:
                amb[q] = 1
            if hit_s:
                ex = stop; rsn = 1; break
            if hit_t:
                ex = tgt; rsn = 2; break
            if flat_m > 0 and j + 1 < n and mod[j + 1] >= flat_m and mod[j] < flat_m:
                ex = o[j + 1]; rsn = 3; j = j + 1; break
            if j + 1 < n and mod[j + 1] < mod[j] and flat_m > 0:
                ex = c[j]; rsn = 4; break
            # arm the breakeven on this bar; it binds from the NEXT one
            if be_pts > 0 and not armed:
                fav = (h[j] - e) if s > 0 else (e - l[j])
                if fav >= be_pts:
                    armed = True
                    if (s > 0 and be_lvl > stop) or (s < 0 and be_lvl < stop):
                        stop = be_lvl
            j += 1
        if not np.isfinite(ex):
            ex = c[n - 1]; rsn = 5; j = n - 1
        p = s * (ex - e) - cost
        eb[q] = i + 1; xb[q] = j; pts[q] = p; risk[q] = rk
        rr[q] = p / rk if rk > 0 else np.nan
        why[q] = rsn
        last = j
    return eb, xb, pts, rr, risk, why, amb


def run(f, sig, side, stop_a=1.0, tgt_r=0.0, flat_m=960, cost=1.72, use_rng=False,
        rhi=None, rlo=None, stop_pts=0.0, tgt_pts=0.0, be_pts=0.0, be_off=0.0):
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); at = f["atr"].to_numpy(); mod = f["mod"].to_numpy()
    if rhi is None:
        rhi = np.full(len(f), np.nan); rlo = np.full(len(f), np.nan)
    eb, xb, pts, rr, risk, why, amb = _walk(
        o, h, l, c, at, mod, sig, side, float(stop_a), float(tgt_r), int(flat_m),
        float(cost), 1 if use_rng else 0, rhi, rlo, float(stop_pts), float(tgt_pts),
        float(be_pts), float(be_off))
    k = eb >= 0
    ent = o[np.where(k, eb, 0)]
    return pd.DataFrame(dict(sig=sig[k], eb=eb[k], xb=xb[k], side=side[k], pts=pts[k],
                             R=rr[k], risk=risk[k], why=why[k], amb=amb[k],
                             ent=ent[k], atr=at[sig[k]],
                             pct=100.0 * pts[k] / ent[k],
                             ratr=pts[k] / at[sig[k]]))


# ----------------------------------------------------------------------------- nulls
def control_entries(f, tr, seed=0, n_draw=400, end_m=960, open_m=OPEN_M, **kw):
    """A RANDOM bar at or after the 09:30 open on the SAME sessions, the SAME side, with identical
    geometry, exits and cost. The drawn bars are SORTED before the walk, because the position lock
    rejects out-of-order signals and an unsorted control silently keeps a different fraction of its
    trades every draw (`STUDY_V59`)."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    ok = (mod >= open_m) & (mod < end_m)
    sig = tr["sig"].to_numpy(); sides = tr["side"].to_numpy()
    days = day[sig]
    # pool of eligible bars per session, as one padded matrix so the draw is vectorised
    uniq, inv = np.unique(days, return_inverse=True)
    pos = {d: k for k, d in enumerate(uniq)}
    elig = np.flatnonzero(ok & np.isin(day, uniq))
    ed = np.array([pos[d] for d in day[elig]], np.int64)
    order = np.argsort(ed, kind="stable")
    elig = elig[order]; ed = ed[order]
    cnt = np.bincount(ed, minlength=len(uniq))
    start = np.r_[0, np.cumsum(cnt)[:-1]]
    keep = cnt[inv] > 0
    inv_k = inv[keep]; sd_k = sides[keep]
    rng = np.random.default_rng(seed)
    out = np.zeros(n_draw)
    for s in range(n_draw):
        off = (rng.random(len(inv_k)) * cnt[inv_k]).astype(np.int64)
        pick = elig[start[inv_k] + off]
        o = np.argsort(pick, kind="stable")
        t = run(f, pick[o], sd_k[o], **kw)
        out[s] = t["pct"].mean() if len(t) else np.nan
    return out


def random_gate(f, sig, side, keep, seed=0, n_draw=400, **kw):
    """A same-selectivity random VETO, re-simulated end to end -- refusing a signal releases the
    position lock and admits a later one, which a subset of realised trades cannot represent
    (`STUDY_AUCTION`)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(n_draw)
    m = len(sig)
    for s in range(n_draw):
        k = rng.random(m) < keep
        if k.sum() < 5:
            out[s] = np.nan; continue
        t = run(f, sig[k], side[k], **kw)
        out[s] = t["pct"].mean() if len(t) else np.nan
    return out


# ----------------------------------------------------------------------------- statistics
def mde(sd, n, alpha_t=2.802):
    """The smallest per-trade effect this sample could resolve at 80% power, 5% two-sided."""
    return alpha_t * sd / np.sqrt(max(n, 1))


def e_max_normal(n, gamma=0.5772156649):
    """E[max t | pure noise] over n looks -- the bar the luckiest draw of a null search must clear
    before any survivor of a search that size can be believed."""
    from scipy.stats import norm
    if n <= 1:
        return 0.0
    return (1 - gamma) * norm.ppf(1 - 1.0 / n) + gamma * norm.ppf(1 - 1.0 / (n * np.e))


def pval(x, null):
    null = null[np.isfinite(null)]
    return float((null >= x).mean()) if len(null) else np.nan


def boot_edge(tr, n=2000, seed=0, col="pct"):
    """Day-block bootstrap: whole DAYS resampled WITH THEIR TRADES ATTACHED, then the trade-weighted
    mean (`research/edgelab`)."""
    d = f_day(tr)
    days = np.unique(d)
    rng = np.random.default_rng(seed)
    idx = {k: np.flatnonzero(d == k) for k in days}
    v = tr[col].to_numpy()
    out = np.zeros(n)
    for s in range(n):
        pick = rng.choice(days, len(days), replace=True)
        z = np.concatenate([idx[k] for k in pick])
        out[s] = v[z].mean()
    return out


def f_day(tr):
    return tr["_day"].to_numpy() if "_day" in tr else tr["sig"].to_numpy() // 1


def attach_day(f, tr):
    tr = tr.copy()
    tr["_day"] = f["day"].to_numpy()[tr["sig"].to_numpy()]
    return tr


# ----------------------------------------------------------------------------- the MA200 gate
def _pair_state(a, b):
    """(state, age since the most recent UP cross, age since the most recent DOWN cross) for two
    arbitrary series. `age` is a forward scan and never a fill-forward to the NEXT cross, which is
    `STUDY_DIVERGENCE_CONFIRM`'s leak. Written as a new helper rather than by parameterising
    `ema_state`, so no published result can silently inherit a change (CLAUDE.md: a frozen kernel
    is copied, never parameterised)."""
    n = len(a)
    st = np.zeros(n, bool)
    ok = np.isfinite(a) & np.isfinite(b)
    st[ok] = a[ok] > b[ok]
    up = np.zeros(n, bool); up[1:] = st[1:] & ~st[:-1]
    dn = np.zeros(n, bool); dn[1:] = (~st[1:]) & st[:-1]
    au = np.full(n, 10 ** 6, np.int64); ad = np.full(n, 10 ** 6, np.int64)
    lu = -10 ** 6; ld = -10 ** 6
    for i in range(n):
        if up[i]:
            lu = i
        if dn[i]:
            ld = i
        au[i] = i - lu; ad[i] = i - ld
    return st, au, ad


def ma200_ok(f, fast=13, slow=48, long_=200, kind="ema", mode="any", cross_bars=0,
             members="both"):
    """The LONG average as the direction REFERENCE, with the shorter averages read against it.
    Returns (ok_long, ok_short): whether a LONG break and whether a SHORT break is confirmed.

    The ask was "the 200 cross with ANY ema provided OR ALL". Each member of {fast, slow} is
    compared with the long average, and

      mode "any"   a long break is confirmed when AT LEAST ONE member sits above the 200
      mode "all"   a long break is confirmed when EVERY member sits above it

    with the short side mirrored. TWO MASKS RATHER THAN ONE DIRECTION LABEL, deliberately: under
    `any` a SPLIT reading (13 above the 200, 48 below) confirms BOTH sides, so the gate simply
    vetoes nothing that day. Collapsed into a single +1/-1/0 label a split has to abstain, and then
    `any` and `all` are THE SAME CONDITION -- any-above-with-none-below IS all-above -- which is an
    inert axis wearing two names. Measured on US30: the label form gives 0.5389 / 0.3810 / 0.0801
    for BOTH modes, identical to four decimals.

      members     "both" (13 and 48) / "fast" / "slow" -- which averages are read against the 200
      cross_bars  0 = the STATE form. >0 = the RECENCY form: the relevant cross must have happened
                  within that many BARS. Declared in bars here and converted from MINUTES in the
                  script, because a bar count is not a setting -- it is a setting times a timeframe
                  (`STUDY_V57`).

    Note what this is NOT: it is not `close > MA200`. `STUDY_V40` found the MA200 is priced by its
    DISTANCE and not by the state, and `STUDY_V51` found the FLOOR reading clears where the
    "support" reading does not. Both are about PRICE against the average; this is about the shorter
    AVERAGES against it, which is what was asked for and a different object.
    """
    c = f["close"].to_numpy()
    v = f["volume"].to_numpy()

    def _m(n):
        return vwma(c, v, n) if kind == "vwma" else ma(c, n, kind)

    L = _m(long_)
    mem = {"both": [fast, slow], "fast": [fast], "slow": [slow]}[members]
    ups = []; dns = []
    for p in mem:
        st, au, ad = _pair_state(_m(p), L)
        if cross_bars > 0:
            ups.append(st & (au <= cross_bars))
            dns.append((~st) & (ad <= cross_bars))
        else:
            ups.append(st)
            dns.append(~st)
    U = np.asarray(ups); D = np.asarray(dns)
    agg = (lambda A: A.all(axis=0)) if mode == "all" else (lambda A: A.any(axis=0))
    ok = np.isfinite(L)
    return ok & agg(U), ok & agg(D)


# ----------------------------------------------------------------------------- trend lines
def trendlines(f, prd=10, min_pts=2, tol_atr=0.25, max_age=200):
    """Causal trend lines through CONFIRMED pivots, returned as a per-bar LEVEL.

    A pivot high at bar j needs bars j-prd..j+prd, so it is knowable at j+prd and NEVER at j --
    the confirmation lag `STUDY_DIVERGENCE_CONFIRM` found, applied here rather than assumed away.
    At bar i the resistance line is drawn through the last TWO confirmed pivot highs and extended
    to i; the support line through the last two confirmed pivot lows. That is the "at least two
    points" definition.

      min_pts = 2   the line is the last two pivots and nothing else.
      min_pts >= 3  a THIRD (earlier) pivot must lie within `tol_atr` x ATR of the same line, so
                    the line has three touches. Fewer lines qualify; the check is on pivots the
                    line was NOT fitted to, which is the only version of "three points" that is
                    not automatically true.

    `max_age` refuses a line whose newer anchor is more than that many bars back -- an extended
    line from six months ago is a number, not a level.

    Returns (res, sup): the resistance and support level at every bar, NaN where no line exists.
    """
    h = f["high"].to_numpy(); l = f["low"].to_numpy(); at = f["atr"].to_numpy()
    n = len(h)
    ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for j in range(prd, n - prd):
        w = h[j - prd:j + prd + 1]
        if h[j] == w.max() and int(np.argmax(w)) == prd:
            ph[j] = True
        w = l[j - prd:j + prd + 1]
        if l[j] == w.min() and int(np.argmin(w)) == prd:
            pl[j] = True

    def _line(flags, px):
        out = np.full(n, np.nan)
        idx = []          # indices of pivots CONFIRMED so far, oldest first
        for i in range(n):
            j = i - prd   # a pivot at i-prd becomes knowable exactly now
            if j >= 0 and flags[j]:
                idx.append(j)
                if len(idx) > 40:
                    idx.pop(0)
            if len(idx) < 2:
                continue
            j1, j2 = idx[-2], idx[-1]
            if i - j2 > max_age or j2 == j1:
                continue
            slope = (px[j2] - px[j1]) / (j2 - j1)
            if min_pts >= 3:
                a = at[i]
                if not np.isfinite(a) or a <= 0:
                    continue
                ok = False
                for j0 in idx[:-2][::-1]:
                    if abs(px[j0] - (px[j2] + slope * (j0 - j2))) <= tol_atr * a:
                        ok = True
                        break
                if not ok:
                    continue
            out[i] = px[j2] + slope * (i - j2)
        return out

    return _line(ph, h), _line(pl, l)
