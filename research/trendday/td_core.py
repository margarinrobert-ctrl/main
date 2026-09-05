"""The ZetaFX Raschke Trend-Day / Untouched-EMA EA as a fast engine.

THE RULE, restated from the MQL5 source. Over the 390-minute RTH session an EMA(20) is built from
COMPLETE, clock-aligned 15-minute RTH closes only (seeded with the SMA of the first 20). Each
15-minute bucket is tested against the EMA value known BEFORE that bucket closed; if no bucket's
range contained the EMA all day the session is UNTOUCHED. A session also qualifies as a TREND DAY
when |close - open| / range >= 75%. After a qualified session, the NEXT full NYSE session is faded:
open above the EMA -> short, open below -> long, filled ONE MINUTE after the session open. The exit
is a resting target at the most recently completed RTH 15-minute EMA, replaced after every bucket,
and a hard flatten one minute before the close. No stop, one contract.

WHAT THIS ENGINE REPRODUCES, and the one place bar data cannot. Everything above is implemented in
the same order the EA evaluates it, including: the continuous cross-session EMA and its reset on an
incomplete session or a calendar gap, the EA's own 2010-2027 XNYS non-full-session calendar, the
390-minute / 26-bucket completeness test, the skip when the session-open bar has already reached the
target, and the skip when the fill price is no longer on the entry side of it. The ONE thing a
15-minute file cannot supply is the one-minute fill: `run(entry_off=1)` on NQ_1m is the exact model,
`entry_off=0` is what a 15-minute feed can do, and `parity()` measures the gap between them.

A target-only exit needs no intrabar ordering -- there is no stop competing with it -- so the exit
is identical at 1-minute and 15-minute resolution. The entry is the only approximation.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "ibs"))

RTH_START, RTH_END, RTH_MIN, BUCKET = 570, 960, 390, 15
DEFAULT = dict(ema=20, trend_pct=75.0, untouched=1, trend=1)

# per-side cost in points: half the RTH spread + entry slippage, + commission; and the point value
COST = {
    "NQ": dict(side=0.25 + 0.25 + 0.36, pv=2.0, tick=0.25),      # MNQ dollars
    "US100": dict(side=0.50 + 0.25, pv=1.0, tick=0.1),
    "US30": dict(side=1.00 + 0.50, pv=1.0, tick=0.1),
    "US30_ISO": dict(side=1.00 + 0.50, pv=1.0, tick=0.1),
}

# The EA's embedded XNYS non-full-session calendar (holidays, early closes, exceptional closures).
NON_FULL = np.array([
    20100101, 20100118, 20100215, 20100402, 20100531, 20100705, 20100906, 20101125,
    20101126, 20101224, 20110117, 20110221, 20110422, 20110530, 20110704, 20110905,
    20111124, 20111125, 20111226, 20120102, 20120116, 20120220, 20120406, 20120528,
    20120703, 20120704, 20120903, 20121029, 20121030, 20121122, 20121123, 20121224,
    20121225, 20130101, 20130121, 20130218, 20130329, 20130527, 20130703, 20130704,
    20130902, 20131128, 20131129, 20131224, 20131225, 20140101, 20140120, 20140217,
    20140418, 20140526, 20140703, 20140704, 20140901, 20141127, 20141128, 20141224,
    20141225, 20150101, 20150119, 20150216, 20150403, 20150525, 20150703, 20150907,
    20151126, 20151127, 20151224, 20151225, 20160101, 20160118, 20160215, 20160325,
    20160530, 20160704, 20160905, 20161124, 20161125, 20161226, 20170102, 20170116,
    20170220, 20170414, 20170529, 20170703, 20170704, 20170904, 20171123, 20171124,
    20171225, 20180101, 20180115, 20180219, 20180330, 20180528, 20180703, 20180704,
    20180903, 20181122, 20181123, 20181205, 20181224, 20181225, 20190101, 20190121,
    20190218, 20190419, 20190527, 20190703, 20190704, 20190902, 20191128, 20191129,
    20191224, 20191225, 20200101, 20200120, 20200217, 20200410, 20200525, 20200703,
    20200907, 20201126, 20201127, 20201224, 20201225, 20210101, 20210118, 20210215,
    20210402, 20210531, 20210705, 20210906, 20211125, 20211126, 20211224, 20220117,
    20220221, 20220415, 20220530, 20220620, 20220704, 20220905, 20221124, 20221125,
    20221226, 20230102, 20230116, 20230220, 20230407, 20230529, 20230619, 20230703,
    20230704, 20230904, 20231123, 20231124, 20231225, 20240101, 20240115, 20240219,
    20240329, 20240527, 20240619, 20240703, 20240704, 20240902, 20241128, 20241129,
    20241224, 20241225, 20250101, 20250109, 20250120, 20250217, 20250418, 20250526,
    20250619, 20250703, 20250704, 20250901, 20251127, 20251128, 20251224, 20251225,
    20260101, 20260119, 20260216, 20260403, 20260525, 20260619, 20260703, 20260907,
    20261126, 20261127, 20261224, 20261225, 20270101, 20270118, 20270215, 20270326,
    20270531, 20270618, 20270705], dtype=np.int64)
CAL_LO, CAL_HI = 20100101, 20270902


# ---------------------------------------------------------------- feed preparation
def full_sessions(days):
    """The EA's zfxIsFullNyseSession, vectorised over a DatetimeIndex of calendar days."""
    key = (days.year * 10000 + days.month * 100 + days.day).to_numpy().astype(np.int64)
    weekday = days.weekday.to_numpy()
    ok = weekday < 5
    inside = (key >= CAL_LO) & (key <= CAL_HI)
    ok &= ~(inside & np.isin(key, NON_FULL))
    return key, ok


def prep(market, tf_override=None):
    """Bars on a New York clock plus the per-bar session index the walk needs."""
    import ibs_core as IC
    f, tf = IC.load(market)
    if tf_override and tf_override != tf:
        r = f.resample(f"{tf_override}min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        f, tf = r, tf_override
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    days = ix.normalize()
    key, full = full_sessions(days)
    in_s = (mod >= RTH_START) & (mod < RTH_END)

    # session list: full NYSE days carrying at least one RTH bar, and whether each is the
    # IMMEDIATELY following full session of the one before it (the EA's gap-aware EMA reset)
    live = in_s & full
    sess_keys = np.unique(key[live])
    all_days = pd.date_range(ix[0].normalize(), ix[-1].normalize(), freq="D")
    ak, af = full_sessions(all_days)
    cal = ak[af]                                       # every full NYSE session in the span
    pos = np.searchsorted(cal, sess_keys)
    contiguous = np.zeros(len(sess_keys), np.bool_)
    contiguous[1:] = (pos[1:] - pos[:-1]) == 1         # no full session skipped in between
    si = np.full(len(f), -1, np.int64)
    si[live] = np.searchsorted(sess_keys, key[live])
    return dict(
        o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
        l=f["low"].to_numpy(float), c=f["close"].to_numpy(float),
        mod=mod, key=key, si=si, off=(mod - RTH_START), tf=tf,
        sess_keys=sess_keys, contiguous=contiguous, dates=ix, market=market,
        pv=COST[market]["pv"], side=COST[market]["side"], n_sess=len(sess_keys))


def blocks(D):
    """Named bar masks. NQ: first 65% of sessions research, the rest locked (the branch split).
    US100/US30: research < 2022, validation 2022-23, test 2024+. US30_ISO: pre-2026 / 2026."""
    ts = D["dates"]
    if D["market"] == "NQ":
        cut = D["sess_keys"][int(0.65 * D["n_sess"])]
        return {"research": D["key"] < cut, "locked": D["key"] >= cut}
    if D["market"] == "US30_ISO":
        return {"research": np.asarray(ts < "2026-01-01"), "locked": np.asarray(ts >= "2026-01-01")}
    return {"research": np.asarray(ts < "2022-01-01"),
            "validation": np.asarray((ts >= "2022-01-01") & (ts < "2024-01-01")),
            "test": np.asarray(ts >= "2024-01-01")}


# ---------------------------------------------------------------- the walk
@njit(cache=True)
def walk(o, h, l, c, off, si, contiguous, tf, ema_n, req_untouched, req_trend, trend_pct,
         entry_off, side_cost, day_mode, side_mode, use_target, skip_open_bar, hold_buckets,
         u, ema_lag):
    """One pass over the bars. Returns the trade table and the session diagnostics.

    day_mode  0 only the qualified sessions (the rule); 1 EVERY full session (the filter control).
    side_mode 0 the rule's fade (open vs EMA); 1 a coin flip; 2 inverted; 3 always long;
              4 always short.
    ema_lag   extra completed buckets to hold the target stale (0 = the rule).
    why: 1 target, 2 flatten, 3 max hold."""
    n = len(c)
    n_bar = RTH_MIN // tf
    n_bkt = RTH_MIN // BUCKET
    per_bkt = BUCKET // tf

    ei = np.empty(8192, np.int64); xi = np.empty(8192, np.int64); sd = np.empty(8192, np.int64)
    ep = np.empty(8192); xp = np.empty(8192); wy = np.empty(8192, np.int64)
    sk = np.empty(8192, np.int64); tg = np.empty(8192)
    k = 0
    # counters: 0 sessions 1 complete 2 untouched 3 trendday 4 qualified 5 signals
    #           6 skip_openbar 7 skip_side 8 skip_flat 9 ema_resets 10 skip_notready
    cnt = np.zeros(16, np.int64)

    ema = np.nan; seed_sum = 0.0; seed_k = 0; ema_ready = False
    prev_qual = False; prev_sess = -1
    iu = 0
    i = 0
    while i < n:
        s = si[i]
        if s < 0:
            i += 1
            continue
        # ---- collect this session's bars
        j = i
        while j < n and si[j] == s:
            j += 1
        m = j - i
        cnt[0] += 1
        # the EA drops a pending signal and resets the EMA when a full session was skipped
        if prev_sess >= 0 and not contiguous[s]:
            ema = np.nan; seed_k = 0; seed_sum = 0.0; ema_ready = False
            prev_qual = False
            cnt[9] += 1

        # ---- the signal for THIS session, decided from the prior session and the prior EMA
        take = False; side = 0; target0 = 0.0; fade_side = 0
        eligible = ema_ready and (prev_qual if day_mode == 0 else True)
        if eligible:
            if o[i] > ema:
                side = -1
            elif o[i] < ema:
                side = 1
            if side != 0:
                take = True
                target0 = ema
                cnt[5] += 1
        if take:
            fade = side
            fade_side = side
            if side_mode == 1:
                side = 1 if u[iu % len(u)] < 0.5 else -1
                iu += 1
            elif side_mode == 2:
                side = -side
            elif side_mode == 3:
                side = 1
            elif side_mode == 4:
                side = -1
            # A side that is not the fade has the EMA on the WRONG side of price, so it is not a
            # tradeable target at all. MIRROR it across the session open instead: same distance,
            # same flatten, opposite direction -- the control that isolates the direction.
            if side != fade:
                target0 = 2.0 * o[i] - target0
                cnt[11] += 1

        # ---- session completeness, buckets, EMA, touch -- and the trade, in one bar walk
        complete = (m == n_bar)
        s_open = o[i]; s_hi = h[i]; s_lo = l[i]; s_cl = c[i]
        touch_free = True; observable = True
        bkt_bars = 0; bkt_hi = -1e18; bkt_lo = 1e18; bkt_cl = 0.0; n_bkt_done = 0
        pos = 0; e_bar = -1; e_px = 0.0; target = target0; x_bar = -1; x_px = 0.0; why = 0
        entered_bkt = 0
        mirrored = 1 if (take and side_mode != 0 and side != fade_side) else 0

        # the entry bar: `entry_off` minutes after the session open, if such a bar exists
        fill_b = -1
        for t in range(m):
            if off[i + t] == entry_off:
                fill_b = i + t
                break
        if take and fill_b < 0:
            take = False
            cnt[10] += 1
        # the EA skips when the bars BEFORE the fill already reached the target
        if take and skip_open_bar == 1:
            for t in range(m):
                if off[i + t] >= entry_off:
                    break
                if (side == 1 and h[i + t] >= target0) or (side == -1 and l[i + t] <= target0):
                    take = False
                    cnt[6] += 1
                    break

        for t in range(m):
            b = i + t
            if h[b] > s_hi:
                s_hi = h[b]
            if l[b] < s_lo:
                s_lo = l[b]
            s_cl = c[b]
            # ---- enter
            if take and b == fill_b and pos == 0:
                px = o[b]
                on_side = (side == 1 and px < target0) or (side == -1 and px > target0)
                if not on_side:
                    cnt[7] += 1
                    take = False
                else:
                    pos = side; e_bar = b; e_px = px + side * side_cost
                    entered_bkt = n_bkt_done
            # ---- the resting target, live from the fill
            if pos != 0 and use_target == 1:
                if (pos == 1 and h[b] >= target) or (pos == -1 and l[b] <= target):
                    x_bar = b; x_px = target - pos * side_cost; why = 1; pos = 0
            if pos != 0 and hold_buckets > 0 and (n_bkt_done - entered_bkt) >= hold_buckets:
                x_bar = b; x_px = c[b] - pos * side_cost; why = 3; pos = 0
            # ---- bucket accounting, then the causal touch test, then the EMA update
            if h[b] > bkt_hi:
                bkt_hi = h[b]
            if l[b] < bkt_lo:
                bkt_lo = l[b]
            bkt_cl = c[b]
            bkt_bars += 1
            if (off[b] % BUCKET) == (BUCKET - tf):
                if bkt_bars == per_bkt:
                    if not ema_ready:
                        observable = False
                    elif bkt_lo <= ema and ema <= bkt_hi:
                        touch_free = False
                    # EMA update on the completed bucket close
                    if not ema_ready:
                        if seed_k < ema_n:
                            seed_sum += bkt_cl
                            seed_k += 1
                        if seed_k == ema_n:
                            ema = seed_sum / ema_n
                            ema_ready = True
                    else:
                        a = 2.0 / (ema_n + 1.0)
                        ema = a * bkt_cl + (1.0 - a) * ema
                    n_bkt_done += 1
                    if pos != 0 and use_target == 1 and (n_bkt_done - entered_bkt) > ema_lag:
                        target = ema if mirrored == 0 else 2.0 * o[i] - ema
                else:
                    complete = False
                bkt_bars = 0; bkt_hi = -1e18; bkt_lo = 1e18
        # ---- flatten one bar before the session end
        if pos != 0:
            b = i + m - 1
            x_bar = b; x_px = c[b] - pos * side_cost; why = 2; pos = 0
            cnt[8] += 1
        if e_bar >= 0 and x_bar >= 0 and k < 8192:
            ei[k] = e_bar; xi[k] = x_bar; sd[k] = side; ep[k] = e_px; xp[k] = x_px
            wy[k] = why; sk[k] = s; tg[k] = target0
            k += 1

        # ---- qualify this session for tomorrow
        if not complete:
            ema = np.nan; seed_k = 0; seed_sum = 0.0; ema_ready = False
            cnt[9] += 1
        else:
            cnt[1] += 1
        rng = s_hi - s_lo
        ratio = 100.0 * abs(s_cl - s_open) / rng if rng > 0 else 0.0
        if complete and touch_free:
            cnt[2] += 1
        if complete and ratio >= trend_pct:
            cnt[3] += 1
        q = (complete and observable and rng > 0.0
             and (req_untouched == 0 or touch_free)
             and (req_trend == 0 or ratio >= trend_pct))
        if q:
            cnt[4] += 1
        prev_qual = q
        prev_sess = s
        i = j
    return ei[:k], xi[:k], sd[:k], ep[:k], xp[:k], wy[:k], sk[:k], tg[:k], cnt


WHY = {1: "target", 2: "flatten", 3: "maxhold"}


def run(D, cfg=None, entry_off=None, day_mode=0, side_mode=0, use_target=1, skip_open_bar=1,
        hold_buckets=0, seed=0, cost_mult=1.0, ema_lag=0, **over):
    cfg = dict(DEFAULT if cfg is None else cfg)
    cfg.update(over)
    if entry_off is None:
        entry_off = 1 if D["tf"] == 1 else 0
    u = np.random.default_rng(seed).random(8192)
    r = walk(D["o"], D["h"], D["l"], D["c"], D["off"], D["si"], D["contiguous"], D["tf"],
             int(cfg["ema"]), int(cfg["untouched"]), int(cfg["trend"]), float(cfg["trend_pct"]),
             int(entry_off), D["side"] * cost_mult, int(day_mode), int(side_mode),
             int(use_target), int(skip_open_bar), int(hold_buckets), u, int(ema_lag))
    ei, xi, sd, ep, xp, wy, sk, tg, cnt = r
    tr = pd.DataFrame({"ei": ei, "xi": xi, "side": sd, "epx": ep, "xpx": xp, "why": wy,
                       "sess": sk, "target": tg})
    tr["pts"] = (tr["xpx"] - tr["epx"]) * tr["side"]
    tr["date"] = D["key"][ei] if len(tr) else np.zeros(0, np.int64)
    tr["bars"] = tr["xi"] - tr["ei"]
    return tr, cnt


def metrics(tr, D, mask=None):
    """Sharpe is over EVERY session in the block, zero-filled -- a filter is never paid for
    trading less."""
    if mask is not None and len(tr):
        tr = tr[mask[tr["ei"].to_numpy()]]
    n = len(tr)
    if n == 0:
        return dict(n=0, net=0.0, mean=np.nan, win=np.nan, pf=np.nan, sharpe=np.nan,
                    dd=np.nan, ret_dd=np.nan, top5=np.nan, streak=0, usd=0.0)
    p = tr["pts"].to_numpy()
    w = p > 0
    pf = p[w].sum() / max(1e-9, -p[~w].sum())
    live = D["si"] >= 0
    if mask is not None:
        live &= mask
    sess_keys = np.unique(D["key"][live])
    daily = pd.Series(0.0, index=sess_keys)
    g = pd.Series(p).groupby(tr["date"].to_numpy()).sum()
    common = g.index.intersection(daily.index)
    daily.loc[common] = g.loc[common]
    sh = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else np.nan
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    ps = np.sort(p)[::-1]
    top5 = ps[: max(1, int(np.ceil(0.05 * n)))].sum() / p.sum() if p.sum() > 0 else np.nan
    streak = 0; cur = 0
    for x in p:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    return dict(n=n, net=float(p.sum()), mean=float(p.mean()), win=float(w.mean()), pf=float(pf),
                sharpe=float(sh), dd=dd, ret_dd=float(p.sum() / dd) if dd > 0 else np.nan,
                top5=float(top5), streak=streak, usd=float(p.sum() * D["pv"]))


def fmt(m, pv=1.0):
    if m["n"] == 0:
        return "n    0"
    return (f"n {m['n']:>4}  win {100*m['win']:5.1f}%  PF {m['pf']:5.2f}  mean {m['mean']:+7.2f}  "
            f"net {m['net']:+9.1f}  Sharpe {m['sharpe']:+5.2f}  DD {m['dd']:7.1f}  "
            f"ret/DD {m['ret_dd']:5.2f}" + (f"  ${m['usd']:+,.0f}" if pv != 1.0 else ""))


def line(tr, D, B, label, width=30):
    out = f"  {label:<{width}}"
    for b, m in B.items():
        mm = metrics(tr, D, m)
        out += (f" | {b[:4]} n {mm['n']:>3} {mm['mean']:+7.1f} PF {mm['pf']:4.2f} "
                f"Sh {mm['sharpe']:+4.1f}")
    return out
