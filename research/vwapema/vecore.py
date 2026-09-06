"""VWAP-EMA REGIME-FILTERED INTRADAY XAU/USD -- the spec built literally, then tested.

SOURCE. Bhatti, "A Regime-Filtered Intraday Trading Framework for Gold" (SSRN 6650958), as
restated in the user's spec document. THE PAPER CONTAINS NO BACKTEST: its section 6.1 states the
outcome distribution was ASSUMED (full win 0.30 / partial 0.20 / breakeven 0.08 / loss 0.42) and
Monte Carlo sampled, so its 45.3% win rate, +0.414R expectancy, 3.99 Sharpe and +102.2% return are
arithmetic from that assumption and say nothing about gold. There is therefore nothing to
reproduce; this is the first measurement of the rules against XAU/USD bars.

THE DATA DECISION, made before any rule was coded.
  The uploaded `XAUUSD15.csv` (= registry `XAUUSD15_MT`, sha256 fdd173af1c92a768, 100,000 rows
  2022-06-07 .. 2026-08-28) CANNOT RUN THIS SPEC. Its sixth field is not volume: 99.62% of rows
  read exactly 15, the rest are smaller integers, sd 0.185, and its correlation with the bar's
  range is +0.0048 where a real tick-volume series scores +0.64. It is the bar's length in
  minutes. Two consequences are arithmetic:
    * C5 (`Volume > 1.1 x SMA20(Volume)`) fires on 33 of 100,000 bars = 0.033%, so the rule as
      specified takes essentially no trades;
    * VWAP = sum(P*V)/sum(V) with V constant IS the unweighted mean of the typical price, so the
      "volume-weighted" average price is not volume-weighted at all.
  `XAU_ISO_15m` (494,235 bars, 2004-06 .. 2026-01, semicolon ISO export) carries real broker TICK
  volume -- mean 988, corr with bar range +0.641, C5 firing 39.7% -- and is used instead. It is
  22 years against the paper's one, which is the point.

  THE VOLUME IS STILL A PROXY and the spec's own gap 3 says so: XAU/USD is OTC, so V is one
  broker's tick count, not traded volume. Every VWAP and C5 number here inherits that.

RESOLVING THE SPEC'S OPEN GAPS (its section 12), each decided once and recorded:
  1. VWAP MILESTONE CONTRADICTION. C2 requires `Close > VWAP` to enter long, while 7.3 treats VWAP
     as a milestone between entry and target -- which needs entry BELOW it. C2 is implemented as
     written (it is an entry condition and unambiguous); the milestone protocol is implemented as
     a re-touch of VWAP after entry, default OFF, and the re-touch RATE is reported so the size of
     the ambiguity is a number rather than an argument.
  2. WICK IMMUNITY IS PARTIAL -- implemented exactly so: the initial stop is a conventional
     intrabar order, the EMA trail is close-only.
  3. VOLUME PROXY -- above.
  4. FREE PARAMETERS -- ten, listed in `PARAMS`, every one counted as a trial.
  5/6. COST AND ATR -- measured, not assumed. The spec's 0.24R is carried as an arm beside gold's
     real cost floor (0.30 USD/oz round turn + 0.05 slippage a side, `research/xau/xau_core.py`),
     expressed as a FRACTION OF RISK because that is the only comparable unit (CLAUDE.md).

EXECUTION. Signal on a bar's CLOSE, fill at the NEXT bar's OPEN -- the spec's own checklist item 2.
One position at a time. Scored in R (safe here: risk = entry - low + 0.5*ATR has an ATR floor and
cannot collapse the way a channel stop does) AND in percent of entry price, both reported.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

NY_SHIFT_H = 7                       # XAU_ISO_15m broker stamp is New York + 7 (registry)
COST_RT, SLIP = 0.30, 0.05           # USD/oz round turn, USD/oz per side -- gold's floor
START = "2010-01-01"                 # pre-2010 excluded: 10% zero-range bars, tick volume ~14
SPLIT = 0.65
SESS_OPEN, SESS_CLOSE = 9 * 60 + 30, 16 * 60      # New York wall clock

# the ten free parameters the spec leaves unjustified; every sweep of one counts as a trial
PARAMS = dict(ema_slow=200, ema_pull=50, ema_tight=20, atr_len=14, atr_stop=0.5,
              vol_mult=1.1, range_mult=0.8, wick_body=2.0, ambig=0.001, tighten_R=2.5)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def load(path="data/XAU_ISO_15m.csv", start=START):
    d = pd.read_csv(path, sep=";")
    d.columns = [c.strip().lower() for c in d.columns]
    ix = pd.to_datetime(d["date"], format="%Y.%m.%d %H:%M") - pd.Timedelta(hours=NY_SHIFT_H)
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")},
                     index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    return f[f.index >= start]


def build(path="data/XAU_ISO_15m.csv", start=START, sess="ny"):
    """`sess` resolves an ambiguity in the paper's own words. Its 3.1 says the VWAP is "anchored to
    the New York session open (13:30 UTC)" and reset at "session close (20:00 UTC)". Those two
    readings are NOT the same thing: 13:30 UTC is 09:30 New York only under daylight saving, and
    08:30 New York in winter. `sess="ny"` uses the New York wall clock 09:30-16:00 (what "the New
    York session" means); `sess="utc"` uses the literal fixed 13:30-20:00 UTC. Both are run."""
    f = load(path, start)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    wd = ix.dayofweek.to_numpy()
    if sess == "utc":
        # ix is New York wall clock. A real tz conversion, not a fixed shift: UTC is NY+4 under
        # EDT and NY+5 under EST, which is exactly the ambiguity being tested.
        uix = ix.tz_localize("America/New_York", ambiguous="NaT",
                            nonexistent="NaT").tz_convert("UTC")
        umod = (uix.hour * 60 + uix.minute).to_numpy()
        rth = (umod >= 13 * 60 + 30) & (umod < 20 * 60) & (wd < 5) & ~uix.isna()
    else:
        rth = (mod >= SESS_OPEN) & (mod < SESS_CLOSE) & (wd < 5)

    p = PARAMS
    atr = _atr(h, l, c, p["atr_len"])
    e200, e50, e20 = _ema(c, p["ema_slow"]), _ema(c, p["ema_pull"]), _ema(c, p["ema_tight"])

    # ---- session VWAP, anchored at the New York open and reset at the close.
    # Accumulated on the strategy's OWN bars, through the current completed bar only.
    tp = (h + l + c) / 3.0
    g = pd.DataFrame({"pv": np.where(rth, tp * v, 0.0), "vv": np.where(rth, v, 0.0),
                      "tp": np.where(rth, tp, 0.0), "one": np.where(rth, 1.0, 0.0),
                      "s": day}).groupby("s", sort=False)
    vwap = (g["pv"].cumsum() / g["vv"].cumsum().replace(0, np.nan)).to_numpy()
    vwap_uw = (g["tp"].cumsum() / g["one"].cumsum().replace(0, np.nan)).to_numpy()   # the volume-free twin
    vwap[~rth] = np.nan
    vwap_uw[~rth] = np.nan

    vsma = pd.Series(v).rolling(20).mean().to_numpy()
    body = np.abs(c - o)
    lw = np.minimum(o, c) - l
    uw = h - np.maximum(o, c)

    D = dict(o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, day=day, rth=rth, atr=atr,
             e200=e200, e50=e50, e20=e20, vwap=vwap, vwap_uw=vwap_uw, vsma=vsma,
             body=body, lw=lw, uw=uw, n=len(c))
    us = np.unique(day[rth])
    D["cut_day"] = int(us[int(SPLIT * len(us))])
    D["blk"] = (day >= D["cut_day"]).astype(np.int64)
    D["cut_date"] = str(ix[np.argmax(day >= D["cut_day"])].date())
    # last bar of each RTH session, for the optional flatten
    D["sess_end"] = _session_end(rth, day)
    return D


def _session_end(rth, day):
    """For every bar, the index of the LAST rth bar of its own session (-1 if none)."""
    n = len(rth)
    out = np.full(n, -1, np.int64)
    idx = np.flatnonzero(rth)
    if len(idx) == 0:
        return out
    dd = day[idx]
    last = {}
    for k, i in zip(dd, idx):
        last[k] = i
    for i in range(n):
        out[i] = last.get(day[i], -1)
    return out


def periods(D, p):
    """Recompute the period-dependent series when a ladder moves one. `build()` caches the SPEC's
    values; sweeping a period without this returns the cached series and the ladder reads IDENTICAL
    at every rung -- a bug signature this branch has recorded before as a fake plateau."""
    p = {**PARAMS, **(p or {})}
    e200 = D["e200"] if p["ema_slow"] == PARAMS["ema_slow"] else _ema(D["c"], p["ema_slow"])
    e50 = D["e50"] if p["ema_pull"] == PARAMS["ema_pull"] else _ema(D["c"], p["ema_pull"])
    e20 = D["e20"] if p["ema_tight"] == PARAMS["ema_tight"] else _ema(D["c"], p["ema_tight"])
    atr = D["atr"] if p["atr_len"] == PARAMS["atr_len"] else _atr(D["h"], D["l"], D["c"], p["atr_len"])
    return e200, e50, e20, atr


def triggers(D, side=1, use_vwap_vol=True, p=None):
    """The six conditions, exactly as specified. `side` +1 long, -1 short (the exact mirror)."""
    p = {**PARAMS, **(p or {})}
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    e200, e50, _e20, atr = periods(D, p)
    vw = D["vwap"] if use_vwap_vol else D["vwap_uw"]
    lw, uw, body = D["lw"], D["uw"], D["body"]
    prev_l = np.concatenate(([np.nan], l[:-1]))
    prev_h = np.concatenate(([np.nan], h[:-1]))
    prev_o = np.concatenate(([np.nan], o[:-1]))
    prev_c = np.concatenate(([np.nan], c[:-1]))

    ambiguous = np.abs(c - e200) / np.maximum(e200, 1e-9) < p["ambig"]
    if side > 0:
        C1 = c > e200
        C2 = c > vw
        C3 = (np.minimum(l, prev_l) <= e50) & (e50 <= c)
        C4a = (lw >= p["wick_body"] * body) & (uw <= 0.5 * lw)
        C4b = (c > prev_o) & (o < prev_c)
    else:
        C1 = c < e200
        C2 = c < vw
        C3 = (np.maximum(h, prev_h) >= e50) & (e50 >= c)
        C4a = (uw >= p["wick_body"] * body) & (lw <= 0.5 * uw)
        C4b = (c < prev_o) & (o > prev_c)
    C5 = D["v"] > p["vol_mult"] * D["vsma"]
    C6 = (h - l) >= p["range_mult"] * atr
    parts = dict(C1=C1, C2=C2, C3=C3, C4=(C4a | C4b), C4a=C4a, C4b=C4b, C5=C5, C6=C6,
                 ambig=~ambiguous, rth=D["rth"])
    sig = C1 & C2 & C3 & (C4a | C4b) & C5 & C6 & ~ambiguous & D["rth"]
    sig = np.nan_to_num(sig, nan=False).astype(bool)
    return sig, parts


@njit(cache=True)
def _walk(o, h, l, c, atr, e50, e20, vwap, sess_end, sig, side, atr_stop, tgt_R, tighten_R,
          use_tighten, flatten, cost_rt, slip, first, last_bar,
          out_sig, out_x, out_R, out_pct, out_why, out_risk, out_touch):
    """Signal at bar i's close, fill at bar i+1's OPEN. Initial stop intrabar; EMA trail
    close-only; optional final-leg tightening to EMA20 above `tighten_R`; optional flatten at the
    session close. why: 0 initial stop, 1 target, 2 trail close, 3 session flatten."""
    n = 0
    busy = -1
    for i in range(first, last_bar):
        if i <= busy or not sig[i]:
            continue
        a = i + 1
        A = atr[i]
        if not (A > 0.0):
            continue
        px = o[a] + side * slip
        if side > 0:
            stp = l[i] - atr_stop * A
        else:
            stp = h[i] + atr_stop * A
        risk = (px - stp) if side > 0 else (stp - px)
        if risk <= 0.0:
            continue
        tgt = px + side * tgt_R * risk
        end = sess_end[a] if flatten == 1 else last_bar - 1
        if end < a:
            end = a
        if end > last_bar - 1:
            end = last_bar - 1
        out = np.nan
        why = 3
        j = a
        touched = 0
        while j <= end:
            # VWAP re-touch bookkeeping (the milestone protocol's precondition)
            if touched == 0 and not np.isnan(vwap[j]):
                if side > 0:
                    if l[j] <= vwap[j]:
                        touched = 1
                else:
                    if h[j] >= vwap[j]:
                        touched = 1
            # 1. initial stop -- a conventional intrabar order, live from the fill bar
            if side > 0:
                if l[j] <= stp:
                    out = stp if o[j] > stp else o[j]
                    why = 0
                    break
                if h[j] >= tgt:
                    out = tgt if o[j] < tgt else o[j]
                    why = 1
                    break
            else:
                if h[j] >= stp:
                    out = stp if o[j] < stp else o[j]
                    why = 0
                    break
                if l[j] <= tgt:
                    out = tgt if o[j] > tgt else o[j]
                    why = 1
                    break
            # 2. the trail -- CLOSE-ONLY, and only from the bar after the fill
            if j > a:
                fl = (c[j] - px) * side / risk
                trail = e50[j]
                if use_tighten == 1 and fl >= tighten_R:
                    trail = e20[j]
                if side > 0:
                    if c[j] < trail:
                        out = c[j]
                        why = 2
                        break
                else:
                    if c[j] > trail:
                        out = c[j]
                        why = 2
                        break
            j += 1
        if np.isnan(out):
            j = end
            out = c[j]
            why = 3
        out = out - side * slip
        pts = side * (out - px) - cost_rt
        out_sig[n] = i
        out_x[n] = j
        out_R[n] = pts / risk
        out_pct[n] = 100.0 * pts / px
        out_why[n] = why
        out_risk[n] = risk
        out_touch[n] = touched
        n += 1
        busy = j
    return n


def run(D, sig, side=1, tgt_R=3.0, atr_stop=None, tighten=True, flatten=False,
        cost_rt=COST_RT, slip=SLIP, p=None):
    p = {**PARAMS, **(p or {})}
    atr_stop = p["atr_stop"] if atr_stop is None else atr_stop
    _e200, e50p, e20p, atrp = periods(D, p)
    n = D["n"]
    cap = int(sig.sum()) + 8
    os_, ox = np.zeros(cap, np.int64), np.zeros(cap, np.int64)
    oR, opct, orisk = (np.full(cap, np.nan) for _ in range(3))
    owhy, otouch = np.zeros(cap, np.int64), np.zeros(cap, np.int64)
    k = _walk(D["o"], D["h"], D["l"], D["c"], atrp, e50p, e20p,
              np.nan_to_num(D["vwap"], nan=np.nan), D["sess_end"],
              np.asarray(sig, np.bool_), int(side), float(atr_stop), float(tgt_R),
              float(p["tighten_R"]), 1 if tighten else 0, 1 if flatten else 0,
              float(cost_rt), float(slip), 250, n - 2,
              os_, ox, oR, opct, owhy, orisk, otouch)
    t = pd.DataFrame(dict(sig=os_[:k], exit_bar=ox[:k], R=oR[:k], pct=opct[:k], why=owhy[:k],
                          risk=orisk[:k], vwap_touch=otouch[:k]))
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["ts"] = D["ix"][t.sig.to_numpy()]
    t["side"] = side
    return t


def stats(t):
    if len(t) == 0:
        return dict(n=0, R=np.nan, pct=np.nan, totR=np.nan, pf=np.nan, win=np.nan,
                    dd=np.nan, ret_dd=np.nan)
    r = t.R.to_numpy()
    cum = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    return dict(n=int(len(t)), R=float(r.mean()), pct=float(t.pct.mean()), totR=float(r.sum()),
                pf=float(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)),
                win=float(100 * (r > 0).mean()), dd=dd, ret_dd=float(r.sum() / max(dd, 1e-9)))
