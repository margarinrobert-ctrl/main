"""IVB -- the CrackingMarkets intraday volatility breakout, built to spec and tested.

PHASE 0, WRITTEN BEFORE ANY CODE.

  The article names NO counterparty. It is a volatility breakout: "the strategy capitalizes on
  intraday trends by entering the market when momentum picks up." There is no constrained flow and
  no risk transfer identified, so under the mechanism-first architecture this is a FITTED PATTERN
  and carries the full deflation burden.

  What it has going FOR it, and this is unusual on this branch:
    * TWO parameters (ATR period 5, multiple 0.4), both stated to be unoptimised.
    * NO TAKE PROFIT -- exit is the stop or the close. This branch has now measured no-target
      beating every target roughly twenty-five times, so the geometry is on the right side.
    * The stop distance is 0.4 x a DAILY ATR, which is large: cost should be a small fraction of
      risk, unlike every scalping family that has died here.

  What it has AGAINST it:
    * It is an intraday session-bounded rule with a hard flatten at the close, and the intraday
      constraint has now failed fourteen separate times on this branch.
    * Both instruments available here rose ~150% and ~420% over the sample, so a long breakout
      that holds to the close is a drift exposure until proven otherwise.

THE RULE, VERBATIM FROM THE ARTICLE.
  1. Daily ATR(5).
  2. Long entry  = session open + 0.4 x ATR(5);  short entry = session open - 0.4 x ATR(5).
  3. Stop-loss at the SESSION OPEN ("exit if the market retraces to the opening price"), which
     makes the risk exactly 0.4 x ATR(5) and the stop fixed for the day.
  4. ONE long attempt and ONE short attempt per day. Both may be live at once -- the article is
     explicit that a single market can hold two trades in a day -- so there is NO position lock
     between the sides, and concurrency is reported rather than assumed.
  5. Exit at the stop or at the end of the trading day.

FOUR IMPLEMENTATION CHOICES THAT ARE NOT IN THE ARTICLE, DECLARED HERE.
  a. WHICH OPEN. The article trades ETFs (SPY, QQQ, DIA), which exist only in RTH, so "the opening
     price" is the 09:30 New York open. That is the faithful reading and the default. The author
     also says they trade futures, where the session opens at 18:00 the previous day, so the ETH
     open is carried as a declared alternative rather than substituted.
  b. THE ATR IS DAILY AND MUST BE CAUSAL. It is computed on RTH daily bars and read THROUGH
     YESTERDAY'S CLOSE, so it is known before today's open. A daily ATR that includes today is the
     single easiest leak in this family.
  c. THE FILL. A stop order at the level fills AT the level when the bar trades through it, and at
     the BAR'S OPEN when the bar gaps beyond it. Gapping through is not free.
  d. THE INTRABAR TIE-BREAK, AND A TRAP INSIDE IT. On the entry bar the stop can also be touched,
     and the sequence is unknowable from a 15-minute bar. The branch convention is to resolve as a
     STOP and report the share -- but ON THE SESSION'S FIRST BAR THAT CONVENTION IS FLATLY WRONG:
     the bar OPENS at O, so its low is <= O with probability 1, and the flag carries no information
     at all about the post-entry path. Measured, 100.0% of first-bar entries are "ambiguous" and
     they are 12.4-12.9% of ALL trades, so blanket pessimism converts an eighth of the sample into
     guaranteed maximum losses for a reason that is pure arithmetic. Excluding the first bar the
     genuine ambiguous share is 6.3-6.5%. Three modes are therefore carried and the choice is
     SETTLED ON TRUE 1-MINUTE DATA (`run_v2`) rather than asserted.

SCORED IN PERCENT OF ENTRY PRICE. R is reported as a diagnostic only: risk is 0.4 x ATR(5) and is
therefore well-behaved (it cannot collapse toward zero the way a structural stop can), but percent
is what survives a comparison across two instruments at different index levels.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from v38 import v38feeds as F  # noqa: E402

RTH0, RTH1 = 9 * 60 + 30, 16 * 60          # New York, [09:30, 16:00)
ETH0 = 18 * 60                              # the futures alternative

# Round turn in INDEX POINTS per feed, this branch's convention (STUDY_COSTS): broker commission
# plus the CME exchange fee plus the NFA line, plus slippage. US100 carries MNQ's 1.72 (the figure
# STUDY_V69_ORB charged on this same file); US30 carries YM's ~2.29.
RT = {"US100L": 1.72, "US30L": 2.29, "US30I": 2.29}


def load(name, eth=False):
    """15-minute bars in New York time, tagged with their session and that session's open."""
    try:
        f = F.load(name)
    except KeyError:
        # US30_ISO_15m on disk carries a LOWERCASE `volume` column; `v38feeds` was written against
        # a delivery that capitalised it. Read it directly rather than editing a loader four other
        # published studies import.
        d = pd.read_csv("data/US30_ISO_15m.csv", parse_dates=["ny"])
        f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                          "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                          "volume": d["volume"].to_numpy(float)}, index=d["ny"])
        f = f.sort_index()
        f = f[~f.index.duplicated(keep="first")]
    mod = f.index.hour * 60 + f.index.minute
    if eth:
        inw = (mod >= ETH0) | (mod < RTH1)
        # a bar at or after 18:00 belongs to the NEXT calendar day's session
        sess = (f.index.normalize() + pd.to_timedelta((mod >= ETH0).astype(int), unit="D")).values
    else:
        inw = (mod >= RTH0) & (mod < RTH1)
        sess = f.index.normalize().values
    d = f.loc[inw].copy()
    d["sess"] = sess[inw]
    d["mod"] = mod[inw]
    return d


def load_nq1m(tf=1):
    """NQ 1-minute, UTC-stamped -- the ONE feed here fine enough to settle an intrabar question.

    CLAUDE.md: `NQ_1m` is stamped in UTC while every other feed is already New York, and a loader
    that forgets to convert puts a 09:30 session window at 04:30. Converted here, then optionally
    resampled so the SAME bars can be read at 1m and at 15m.
    """
    d = pd.read_csv("data/NQ_1m.csv")
    ix = pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True)) \
        .tz_convert("America/New_York").tz_localize(None)
    f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                      "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                      "volume": d["volume"].to_numpy(float)}, index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    if tf > 1:
        f = f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                        "close": "last", "volume": "sum"}).dropna()
    mod = f.index.hour * 60 + f.index.minute
    inw = (mod >= RTH0) & (mod < RTH1)
    o = f.loc[inw].copy()
    o["sess"] = f.index.normalize().values[inw]
    o["mod"] = mod[inw]
    return o


def daily_atr(d, n=5):
    """ATR(5) on the SESSION's own daily bars, read THROUGH YESTERDAY -- causal by construction.

    Wilder's smoothing is not specified by the article; a simple mean of the last n true ranges is
    the plainest reading of "Average True Range with a period of 5 days" and is what is used. The
    ema variant is carried in `atr_mode` so the choice can be shown to be inert.
    """
    g = d.groupby("sess")
    day = pd.DataFrame({"h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(),
                        "o": g["open"].first()})
    pc = day["c"].shift(1)
    tr = np.maximum(day["h"] - day["l"],
                    np.maximum((day["h"] - pc).abs(), (day["l"] - pc).abs()))
    sma = tr.rolling(n).mean().shift(1)          # SHIFT: today may not see its own true range
    ema = tr.ewm(span=n, adjust=False).mean().shift(1)
    return day.assign(tr=tr, atr_sma=sma, atr_ema=ema)


def walk(d, day, k=0.4, cost_pts=0.0, atr_mode="sma", sides=("long", "short"),
         entry_mode="level", rng=None, amb_mode="stop", first_bar=None):
    """One long and one short attempt per session. No position lock between the two sides.

    entry_mode:
      'level'  -- the rule: a stop order at open +/- k*ATR(5)
      'random' -- THE MATCHED CONTROL: the same sessions and the same sides, entered at a RANDOM
                  bar of the session, with the stop placed k*ATR(5) away from THAT entry so the
                  risk distribution is matched trade for trade. `STUDY_TURTLE_YOUTUBE` is the
                  reason risk is matched and not just the exits: a control whose risk denominator
                  differs from the rule's flatters or damns it for the wrong reason.
    """
    acol = "atr_" + atr_mode
    atr = day[acol].to_dict()
    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    lo = d["low"].to_numpy(); c = d["close"].to_numpy()
    sess = d["sess"].to_numpy()
    rows = []
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    ends = np.r_[starts[1:], len(sess)]
    want_l, want_s = "long" in sides, "short" in sides
    for s0, s1 in zip(starts, ends):
        key = sess[s0]
        a = atr.get(key, np.nan)
        if not np.isfinite(a) or a <= 0 or s1 - s0 < 3:
            continue
        O = o[s0]
        up, dn = O + k * a, O - k * a
        for side, want, lvl in ((1, want_l, up), (-1, want_s, dn)):
            if not want:
                continue
            j = -1
            if entry_mode == "level":
                for t in range(s0, s1):
                    if (side > 0 and h[t] >= lvl) or (side < 0 and lo[t] <= dn):
                        j = t
                        break
                if j < 0:
                    continue
                # a stop order fills AT the level, or at the open if the bar gapped beyond it
                ent = max(lvl, o[j]) if side > 0 else min(lvl, o[j])
                stop = O
            else:
                j = int(rng.integers(s0, s1))
                ent = c[j]
                stop = ent - side * k * a
            risk = abs(ent - stop)
            if risk <= 0:
                continue
            amb = 0
            out, why = np.nan, ""
            # the ENTRY bar can also touch the stop; sequence is unknowable from a 15m bar
            if (side > 0 and lo[j] <= stop) or (side < 0 and h[j] >= stop):
                amb = 1
                structural = (j == s0)      # opens AT the stop, so low <= stop with probability 1
                if amb_mode == "stop" or (amb_mode == "skipfirst" and not structural):
                    out, why = stop, "stop"
            if not why:
                for e in range(j + 1, s1):
                    if (side > 0 and lo[e] <= stop) or (side < 0 and h[e] >= stop):
                        out, why = stop, "stop"
                        break
                else:
                    e = s1 - 1
                    out, why = c[e], "close"
            else:
                e = j
            gross = side * (out - ent)
            rows.append(dict(sess=key, side=side, ent=ent, stop=stop, risk=risk, atr=a,
                             out=out, why=why, amb=amb, barno=j - s0, bar=j, exbar=e,
                             gross_pct=100.0 * gross / ent,
                             pct=100.0 * (gross - cost_pts) / ent,
                             R=(gross - cost_pts) / risk,
                             cost_frac=cost_pts / risk))
    cols = ["sess", "side", "ent", "stop", "risk", "atr", "out", "why", "amb", "barno", "bar",
            "exbar", "gross_pct", "pct", "R", "cost_frac"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame({c: [] for c in cols})


def stats(t, col="pct"):
    if len(t) < 5:
        return dict(n=len(t), win=np.nan, pf=np.nan, mean=np.nan, total=np.nan,
                    sharpe=np.nan, dd=np.nan, rdd=np.nan)
    x = t[col].to_numpy()
    eq = np.cumsum(x)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else np.nan
    return dict(n=len(t), win=float((x > 0).mean()),
                pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)),
                mean=float(x.mean()), total=float(eq[-1]),
                sharpe=float(x.mean() / max(x.std(ddof=1), 1e-12)),
                dd=dd, rdd=float(eq[-1] / max(dd, 1e-9)))


def payoff_breakeven(t, col="pct"):
    """This rule has NO target, so the break-even win rate is not 1/(1+RR) -- it is set by the
    REALISED payoff ratio. Report both so a win rate can be read against something."""
    x = t[col].to_numpy()
    w, l = x[x > 0], x[x < 0]
    if len(w) < 2 or len(l) < 2:
        return np.nan, np.nan
    ratio = w.mean() / abs(l.mean())
    return float(ratio), float(1.0 / (1.0 + ratio))


def split(t, frac=0.65):
    ks = np.sort(t.sess.unique())
    cut = ks[int(frac * len(ks))]
    return t[t.sess < cut], t[t.sess >= cut], cut


def day_bootstrap(t, col="pct", n=2000, seed=0):
    """Resample whole SESSIONS with their trades attached -- the two sides of one day are not
    independent, and neither are the trades of adjacent days in a trending market."""
    rng = np.random.default_rng(seed)
    g = [v[col].to_numpy() for _, v in t.groupby("sess")]
    if len(g) < 10:
        return dict(mean=np.nan, lo=np.nan, hi=np.nan, p=np.nan)
    idx = rng.integers(0, len(g), size=(n, len(g)))
    ms = np.array([np.concatenate([g[i] for i in row]).mean() for row in idx])
    return dict(mean=float(np.mean(ms)), lo=float(np.percentile(ms, 2.5)),
                hi=float(np.percentile(ms, 97.5)), p=float((ms <= 0).mean()))
