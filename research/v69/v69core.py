"""V69 -- the Loadish Starboard multi-session ORB, transliterated and tested.

FOUR THINGS ESTABLISHED BEFORE ANY OPTIMISATION, because they bound what the study can claim.

1. THE UPLOADED FILE IS ALREADY IN THE REGISTRY. sha256 prefix c449dddfbc06a943, 11,971,933 bytes,
   206,703 rows, 2016-11 to 2025-10 -- byte-identical to `US100_LONG_15m`, which `research/v13/*`,
   `research/v14/*`, `research/v15/*`, `STUDY_V38`, `STUDY_V41` and `STUDY_V60` have all read. THERE
   IS NO UNREAD BLOCK ON IT. Every out-of-sample figure here is a SECOND (or tenth) read and is
   descriptive; the only genuinely reserved thing available is the pre-2023 span that predates the
   NQ file, and even that has been read by `research/us100.py`.

2. THE CLOCK IS NEW YORK + 7, NOT NEW YORK. Re-derived here rather than trusted: mean bar range
   peaks at minute-of-day 990 = 16:30 file time, which is 09:30 New York. The Pine reads each
   session on its OWN local clock (JST, London, ET), so every session minute has to be converted.
   Taking the file stamps as New York would put the NY range candle at 02:30 -- the pre-open block
   this branch has measured as the worst part of the day four separate times.

3. THE VIX FILTER CANNOT BE REPRODUCED AND IT SHIPS ON. `useVixFilter` defaults true with a 17.00
   ceiling, gating every session at the range close. `data/VIX_daily.csv` ends 2021-12-31 while this
   feed runs to 2025-10, and CLAUDE.md records that the VIX cannot be joined to any futures feed on
   this branch. So the strategy is tested WITHOUT it, and every number here describes the rule minus
   its shipped volatility gate. That is a real gap, not a simplification.

4. IT IS US100, A CFD, NOT MNQ. Results are scored in PERCENT OF ENTRY PRICE so the contract spec
   does not confound them, with the MNQ conversion stated separately.

THE ARITHMETIC THAT FRAMES EVERYTHING. `riskReward` ships at 0.8, so the target is CLOSER than the
stop and the driftless break-even win rate is 1/(1+0.8) = 55.56%. Before any backtest, that is the
number the rule has to beat, and this branch has measured no-take-profit beating every target
roughly twenty-five times.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "data/US100_LONG_15m.csv")

# (name, tz, start minute-of-day, end minute-of-day) on that session's OWN clock
SESSIONS = (("asia", "Asia/Tokyo", 9 * 60, 15 * 60),
            ("london", "Europe/London", 8 * 60, 13 * 60),
            ("ny", "America/New_York", 9 * 60 + 30, 16 * 60))

# the shipped configuration, verbatim from the Pine defaults
SHIPPED = dict(rr=0.8, sessions=("asia", "london", "ny"),
               day=dict(Mon="Long", Tue="Both", Wed="Both", Thu="Both", Fri="Both"),
               rng_min=0.0, rng_max=0.0, pen_pct=0.0, close_loc=0.0,
               pct_max=0.0, pct_min=0.0, pct_look=20)

# THE PINE SETS commission_value = 0 AND slippage = 0, so its own Strategy Tester report is
# GROSS. This branch charges MNQ's all-in round turn of 1.72 index points (STUDY_COSTS:
# broker commission plus the CME exchange fee plus the NFA line, plus slippage scaled by
# bar speed). Every net figure here carries it; the gross variant is reported beside it.
RT_POINTS = 1.72


def load():
    """Ascending, with the NY+7 file clock converted to a real UTC instant.

    file wall-clock = New York wall-clock + 7h, and that offset is DST-STABLE (the registry
    identified it by measurement). So subtracting 7h gives New York local time, which is then
    localised WITH its DST rules and converted onward -- which is what lets each session be read on
    its own clock without any DST arithmetic in this file.
    """
    d = pd.read_csv(PATH, sep="\t")
    d["DateTime"] = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S")
    d = d.sort_values("DateTime").drop_duplicates("DateTime").reset_index(drop=True)
    ny_naive = d["DateTime"] - pd.Timedelta(hours=7)
    ny = ny_naive.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    keep = ny.notna()
    d, ny = d[keep].reset_index(drop=True), ny[keep].reset_index(drop=True)
    d["utc"] = ny.dt.tz_convert("UTC")
    d["ny"] = ny
    return d


def sessionize(d):
    """Per bar: which session it belongs to, that session's instance key, and its local weekday.

    Priority Asia -> London -> NY, exactly as the Pine's `f_sessionIdAt`. The instance key is the
    LOCAL DATE OF THE SHIFTED INSTANT (shifted so the session end lands on local midnight), which is
    the Pine's `f_dateKeyAt` -- bumping a YYYYMMDD by one would split every month boundary.
    """
    n = len(d)
    sid = np.full(n, -1, np.int8)
    key = np.zeros(n, np.int64)
    dow = np.full(n, -1, np.int8)
    is_open = np.zeros(n, bool)
    for k, (name, tz, s0, s1) in enumerate(SESSIONS):
        loc = d["utc"].dt.tz_convert(tz)
        m = loc.dt.hour * 60 + loc.dt.minute
        inw = (m >= s0) & (m < s1)
        take = inw & (sid < 0)                       # priority: first session wins
        shifted = loc + pd.Timedelta(minutes=1440 - s1)
        kk = (shifted.dt.year * 10000 + shifted.dt.month * 100 + shifted.dt.day) * 10 + k
        sid[take] = k
        key[take] = kk[take]
        dow[take] = shifted.dt.dayofweek[take]       # 0 = Monday
        is_open[take & (m == s0)] = True             # the RANGE CANDLE opens at the start minute
    d = d.assign(sid=sid, skey=key, sdow=dow, is_open=is_open)
    return d


def walk(d, rr=0.8, sessions=("asia", "london", "ny"), day=None, rng_min=0.0, rng_max=0.0,
         pen_pct=0.0, close_loc=0.0, pct_max=0.0, pct_min=0.0, pct_look=20,
         cost_pts=0.0, side_override=None):
    """The Pine's order model, statement for statement.

    `process_orders_on_close = true`, so the ENTRY FILLS AT THE CLOSE OF THE BREAKING BAR -- not at
    the next open, which is what almost every other engine on this branch does. The stop sits
    exactly on the opposite ORB edge (slBufferPts = 0) and the target at entry +/- risk * rr.
    Within one bar the STOP is taken first, the pessimistic reading this branch enforces.
    The first break LATCHES and consumes the session whichever side it fired on.
    """
    day = day or SHIPPED["day"]
    dmap = {0: day.get("Mon", "Both"), 1: day.get("Tue", "Both"), 2: day.get("Wed", "Both"),
            3: day.get("Thu", "Both"), 4: day.get("Fri", "Both")}
    want = {n for n in sessions}
    sidx = {i for i, (n, *_ ) in enumerate(SESSIONS) if n in want}

    o = d["Open"].to_numpy(); h = d["High"].to_numpy()
    lo = d["Low"].to_numpy(); c = d["Close"].to_numpy()
    sid = d["sid"].to_numpy(); skey = d["skey"].to_numpy()
    sdow = d["sdow"].to_numpy(); isopen = d["is_open"].to_numpy()
    n = len(d)

    hist = {0: [], 1: [], 2: []}
    rows = []
    i = 0
    while i < n:
        if sid[i] < 0 or sid[i] not in sidx or not isopen[i]:
            i += 1
            continue
        k = skey[i]
        # the range candle is THIS bar; the session runs while skey holds
        oh, ol = h[i], lo[i]
        rng = oh - ol
        dm = dmap.get(int(sdow[i]), "Off")
        # percentile gate: rank against PRIOR history, then push (never against itself)
        ok_pct = True
        H = hist[int(sid[i])]
        if pct_max > 0 or pct_min > 0:
            if len(H) < pct_look:
                ok_pct = False
            else:
                if pct_max > 0:
                    ok_pct &= rng <= np.percentile(H, pct_max)
                if pct_min > 0:
                    ok_pct &= rng >= np.percentile(H, pct_min)
        H.append(rng)
        if len(H) > pct_look:
            H.pop(0)
        ok_rng = (rng_min <= 0 or rng >= rng_min) and (rng_max <= 0 or rng <= rng_max)
        j = i + 1
        if dm == "Off" or not ok_rng or not ok_pct or rng <= 0:
            while j < n and skey[j] == k:
                j += 1
            i = j
            continue
        pen = rng * pen_pct / 100.0 if pen_pct > 0 else 0.0
        side = 0
        while j < n and skey[j] == k:
            br = h[j] - lo[j]
            up_loc = 100.0 if br <= 0 else (c[j] - lo[j]) / br * 100.0
            dn_loc = 100.0 if br <= 0 else (h[j] - c[j]) / br * 100.0
            if c[j] > oh + pen and (close_loc <= 0 or up_loc >= close_loc):
                side = 1
                break
            if c[j] < ol - pen and (close_loc <= 0 or dn_loc >= close_loc):
                side = -1
                break
            j += 1
        if side == 0:
            i = j
            continue
        allowed = (side > 0 and dm in ("Both", "Long")) or (side < 0 and dm in ("Both", "Short"))
        if side_override == "long" and side < 0:
            allowed = False
        if side_override == "short" and side > 0:
            allowed = False
        if not allowed:
            while j < n and skey[j] == k:
                j += 1
            i = j
            continue
        ent = c[j]                              # process_orders_on_close
        stop = ol if side > 0 else oh
        risk = abs(ent - stop)
        if risk <= 0:
            i = j + 1
            continue
        tgt = ent + side * risk * rr
        e = j + 1
        out, why = np.nan, ""
        while e < n and skey[e] == k:
            hit_s = (lo[e] <= stop) if side > 0 else (h[e] >= stop)
            hit_t = (h[e] >= tgt) if side > 0 else (lo[e] <= tgt)
            if hit_s:
                out, why = stop, "stop"
                break
            if hit_t:
                out, why = tgt, "target"
                break
            e += 1
        if not why:
            e = min(e, n - 1)
            out, why = c[e], "session flat"
        g = side * (out - ent) - cost_pts
        rows.append(dict(sig=j, ex=e, side=side, ent=ent, stop=stop, tgt=tgt,
                         risk_pct=100.0 * risk / ent, pct=100.0 * g / ent,
                         R=g / risk, why=why, sid=int(sid[i]), skey=k,
                         dow=int(sdow[i]), rng=rng, ts=d["ny"].iloc[j]))
        i = e + 1
    # A configuration that never trades must still return the right COLUMNS -- an empty frame with
    # no columns raises on the first `.skey` downstream, which is a crash where the honest answer is
    # "this cell has no trades".
    cols = ["sig", "ex", "side", "ent", "stop", "tgt", "risk_pct", "pct", "R", "why", "sid",
            "skey", "dow", "rng", "ts"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame({c: [] for c in cols})


def stats(t):
    if len(t) < 5:
        return dict(n=len(t), pct=np.nan, pf=np.nan, win=np.nan, sharpe=np.nan, dd=np.nan,
                    total=np.nan)
    x = t.pct.to_numpy()
    eq = np.cumsum(x)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(t), pct=float(x.mean()), pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)),
                win=float((x > 0).mean()), sharpe=float(x.mean() / max(x.std(ddof=1), 1e-12)),
                dd=dd, total=float(eq[-1]), rdd=float(eq[-1] / max(dd, 1e-9)))


def breakeven(rr, cost_pct=0.0, risk_pct=None):
    """The win rate the geometry demands with no drift. 1/(1+rr) before costs."""
    return 1.0 / (1.0 + rr)
