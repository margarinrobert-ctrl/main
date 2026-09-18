"""RTH VWAP Drift EVO 1 (Sierra Chart ACSIL) as a fast engine.

THE RULE, read out of the source rather than from its name. It is a TREND-CONTINUATION pullback,
not a mean reversion. On 1-minute bars, a VWAP is accumulated from the 09:30 RTH open as
cum(close x volume) / cum(volume) -- CLOSE times volume, not typical price, and reset every session.
An efficiency ratio runs on 1-minute closes, |C[i] - C[i-30]| / sum|C[j] - C[j-1]|, reset at the
18:00 ETH boundary and passed through an Ehlers super smoother of period 10. 15-minute buckets are
anchored to the RTH open, and at every completed bucket:

    LONG   the PREVIOUS bucket closed ABOVE VWAP, this bucket's LOW touched VWAP, this bucket
           CLOSED back above it, VWAP is RISING over `slope` buckets, the close is at least
           `drift` percent above its close `driftLB` buckets ago, and ER > 0.30.
    SHORT  the mirror.
    ENTRY  the bucket's close.
    STOP   the bucket's LOW (long) or HIGH (short), on the tick grid. TARGET entry +/- 2 x risk.
    LIMITS entries only between 09:45 and 13:45, flat at 15:55, at most 4 trades and 2 losses a day,
           one position at a time.

TWO FILL MODELS, because the source's own is not reachable. The study evaluates a bucket on the bar
that STARTS the next one, then records the entry at the bucket's CLOSE -- a price that has already
passed by the time the signal exists. `entry_at="close"` reproduces that (and its exit scan, which
skips the following bar as well); `entry_at="open"` fills at the open of the bar the signal actually
fires on and lets that bar resolve the trade. The gap between them is measured, not assumed.
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

RTH_OPEN, RTH_CLOSE, ETH_OPEN = 570, 960, 1080
DEFAULT = dict(bucket=15, drift_lb=3, drift_pct=0.10, slope_lb=1, er_n=30, er_smooth=10,
               er_min=0.30, rr=2.0, win_start=585, win_end=825, flat=955,
               max_trades=4, max_losses=2)
COST = {"NQ": dict(side=0.25 + 0.25 + 0.36, pv=2.0, tick=0.25),
        "US100": dict(side=0.50 + 0.25, pv=1.0, tick=0.1),
        "US30": dict(side=1.00 + 0.50, pv=1.0, tick=0.1),
        "US30_ISO": dict(side=1.00 + 0.50, pv=1.0, tick=0.1)}


def prep(market, tf_override=None):
    import ibs_core as IC
    f, tf = IC.load(market)
    vol = None
    if market in ("US30", "US100"):
        d = pd.read_csv(f"data/{market}_LONG_15m.csv", sep="\t")
        d.columns = [c.strip().lower() for c in d.columns]
        ix = pd.DatetimeIndex(pd.to_datetime(d["datetime"])) - pd.Timedelta(hours=7)
        vol = pd.Series(d["tickvolume"].to_numpy(float), index=ix).sort_index()
        vol = vol[~vol.index.duplicated(keep="first")].reindex(f.index)
    elif market == "US30_ISO":
        d = pd.read_csv("data/US30_ISO_15m.csv", parse_dates=["ny"])
        vol = pd.Series(d["volume"].to_numpy(float), index=pd.DatetimeIndex(d["ny"]))
        vol = vol[~vol.index.duplicated(keep="first")].reindex(f.index)
    else:
        d = pd.read_csv("data/NQ_1m.csv")
        ix = (pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True))
              .tz_convert("America/New_York").tz_localize(None))
        vol = pd.Series(d["volume"].to_numpy(float), index=ix).sort_index()
        vol = vol[~vol.index.duplicated(keep="first")].reindex(f.index)
    f = f.assign(volume=vol.fillna(0.0).to_numpy())
    if tf_override and tf_override != tf:
        f = f.resample(f"{tf_override}min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last",
             "volume": "sum"}).dropna()
        tf = tf_override
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    key = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy().astype(np.int64)
    nxt = ix + pd.Timedelta(days=1)
    nkey = (nxt.year * 10000 + nxt.month * 100 + nxt.day).to_numpy().astype(np.int64)
    cst = COST[market]
    return dict(o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
                l=f["low"].to_numpy(float), c=f["close"].to_numpy(float),
                v=f["volume"].to_numpy(float), mod=mod, key=key, nkey=nkey, tf=tf,
                dates=ix, market=market, pv=cst["pv"], side=cst["side"], tick=cst["tick"])


def blocks(D):
    ts = D["dates"]
    if D["market"] == "NQ":
        rth = (D["mod"] >= RTH_OPEN) & (D["mod"] < RTH_CLOSE)
        us = np.unique(D["key"][rth])
        cut = us[int(0.65 * len(us))]
        return {"research": D["key"] < cut, "locked": D["key"] >= cut}
    if D["market"] == "US30_ISO":
        return {"research": np.asarray(ts < "2026-01-01"), "locked": np.asarray(ts >= "2026-01-01")}
    return {"research": np.asarray(ts < "2022-01-01"),
            "validation": np.asarray((ts >= "2022-01-01") & (ts < "2024-01-01")),
            "test": np.asarray(ts >= "2024-01-01")}


@njit(cache=True)
def indicators(o, h, l, c, v, mod, key, nkey, tf, er_n, er_smooth):
    """The session VWAP and the super-smoothed efficiency ratio, both exactly as the source
    builds them: VWAP from close x volume since the RTH open, ER reset at the 18:00 ETH boundary."""
    n = len(c)
    vwap = np.full(n, np.nan)
    er = np.full(n, np.nan)
    raw = np.full(n, np.nan)
    cpv = 0.0; cv = 0.0; day = -1
    a = np.sqrt(2.0) * np.pi / er_smooth
    k2 = 2.0 * np.exp(-a) * np.cos(a)
    k3 = -np.exp(-2.0 * a)
    k1 = 1.0 - k2 - k3
    eth = -1
    cnt = 0
    for i in range(n):
        # ---- the ETH session the bar belongs to, for the ER reset
        e = nkey[i] if mod[i] >= ETH_OPEN else key[i]
        if e != eth:
            eth = e
            cnt = 0
        cnt += 1
        # ---- the RTH VWAP
        if mod[i] >= RTH_OPEN and mod[i] < RTH_CLOSE:
            if key[i] != day:
                day = key[i]
                cpv = 0.0; cv = 0.0
            cpv += c[i] * v[i]
            cv += v[i]
            vwap[i] = cpv / cv if cv > 0 else c[i]
        # ---- the efficiency ratio, on this timeframe's own bars
        lb = er_n // tf
        if lb >= 1 and cnt > lb and i >= lb:
            change = abs(c[i] - c[i - lb])
            vol_sum = 0.0
            for j in range(i - lb + 1, i + 1):
                vol_sum += abs(c[j] - c[j - 1])
            raw[i] = change / vol_sum if vol_sum > 0 else 0.0
            p1 = i >= 1 and not np.isnan(raw[i - 1]) and not np.isnan(er[i - 1])
            p2 = i >= 2 and not np.isnan(raw[i - 2]) and not np.isnan(er[i - 2])
            er[i] = raw[i] if not (p1 and p2) else k1 * raw[i] + k2 * er[i - 1] + k3 * er[i - 2]
    return vwap, er


@njit(cache=True)
def walk(o, h, l, c, mod, key, vwap, er, tf, bucket, drift_lb, drift_pct, slope_lb, er_min,
         rr, win_start, win_end, flat, max_trades, max_losses, side_cost, tick,
         entry_at, invert, use_er, use_slope, use_drift, use_touch, stop_mult, u, rand_side):
    """One pass. entry_at 0 = the bucket close as the source records it (and its exit scan skips
    the following bar), 1 = the open of the bar the signal fires on. why: 1 stop, 2 target, 3 flat."""
    n = len(c)
    per = bucket // tf
    ei = np.empty(20000, np.int64); xi = np.empty(20000, np.int64); sd = np.empty(20000, np.int64)
    ep = np.empty(20000); xp = np.empty(20000); wy = np.empty(20000, np.int64)
    rk = np.empty(20000)
    k = 0
    cnt = np.zeros(10, np.int64)   # 0 buckets 1 signals 2 window 3 capped 4 inpos
    # per-bucket history, rebuilt each session
    bo = np.zeros(64); bh = np.zeros(64); bl = np.zeros(64); bc = np.zeros(64)
    bv = np.zeros(64); bend = np.zeros(64, np.int64)
    nb = 0
    day = -1
    trades_today = 0; losses_today = 0
    pos = 0; e_bar = -1; e_px = 0.0; stop = 0.0; tgt = 0.0; scan_from = 0
    iu = 0
    for i in range(n):
        if key[i] != day:
            day = key[i]
            nb = 0
            trades_today = 0
            losses_today = 0
            if pos != 0:
                pos = 0
        inr = mod[i] >= RTH_OPEN and mod[i] < RTH_CLOSE
        # ---- manage an open position, from the bar the source starts scanning
        if pos != 0 and i >= scan_from:
            if mod[i] >= flat:
                ei[k] = e_bar; xi[k] = i; sd[k] = pos; ep[k] = e_px
                xp[k] = o[i] - pos * side_cost; wy[k] = 3; rk[k] = abs(e_px - stop)
                if (xp[k] - e_px) * pos <= 0:
                    losses_today += 1
                k += 1; pos = 0
            elif pos == 1:
                if l[i] <= stop:
                    ei[k] = e_bar; xi[k] = i; sd[k] = 1; ep[k] = e_px
                    xp[k] = stop - side_cost; wy[k] = 1; rk[k] = abs(e_px - stop)
                    losses_today += 1; k += 1; pos = 0
                elif h[i] >= tgt:
                    ei[k] = e_bar; xi[k] = i; sd[k] = 1; ep[k] = e_px
                    xp[k] = tgt - side_cost; wy[k] = 2; rk[k] = abs(e_px - stop)
                    k += 1; pos = 0
            else:
                if h[i] >= stop:
                    ei[k] = e_bar; xi[k] = i; sd[k] = -1; ep[k] = e_px
                    xp[k] = stop + side_cost; wy[k] = 1; rk[k] = abs(e_px - stop)
                    losses_today += 1; k += 1; pos = 0
                elif l[i] <= tgt:
                    ei[k] = e_bar; xi[k] = i; sd[k] = -1; ep[k] = e_px
                    xp[k] = tgt + side_cost; wy[k] = 2; rk[k] = abs(e_px - stop)
                    k += 1; pos = 0
        if not inr:
            continue
        off = mod[i] - RTH_OPEN
        # ---- accumulate the bucket this bar belongs to
        bi = off // bucket
        if bi >= 64:
            continue
        if bi >= nb:
            nb = bi + 1
            bo[bi] = o[i]; bh[bi] = h[i]; bl[bi] = l[i]
        else:
            if h[i] > bh[bi]:
                bh[bi] = h[i]
            if l[i] < bl[bi]:
                bl[bi] = l[i]
        bc[bi] = c[i]
        bv[bi] = vwap[i]
        bend[bi] = i
        # ---- the signal fires on the LAST bar of a bucket, using that bucket
        if (off % bucket) != (bucket - tf):
            continue
        cnt[0] += 1
        e1 = bi
        if e1 < 1 or e1 < drift_lb or e1 < slope_lb:
            continue
        vnow = bv[e1]
        if np.isnan(vnow) or vnow <= 0:
            continue
        pv = bv[e1 - 1]
        sv = bv[e1 - slope_lb]
        dc = bc[e1 - drift_lb]
        if np.isnan(pv) or pv <= 0 or np.isnan(sv) or sv <= 0 or dc == 0:
            continue
        e_now = er[bend[e1]]
        if np.isnan(e_now):
            continue
        was_above = bc[e1 - 1] > pv
        was_below = bc[e1 - 1] < pv
        t_dn = bl[e1] <= vnow
        t_up = bh[e1] >= vnow
        rising = vnow > sv
        falling = vnow < sv
        dpct = (bc[e1] - dc) / dc * 100.0
        er_ok = (e_now > er_min) if use_er == 1 else True
        if use_touch == 0:
            t_dn = True
            t_up = True
        if use_slope == 0:
            rising = True
            falling = True
        long_sig = was_above and t_dn and bc[e1] > vnow and rising and er_ok
        short_sig = was_below and t_up and bc[e1] < vnow and falling and er_ok
        if use_drift == 1:
            long_sig = long_sig and dpct >= drift_pct
            short_sig = short_sig and dpct <= -drift_pct
        if not (long_sig or short_sig):
            continue
        cnt[1] += 1
        # the window is tested on the bar that STARTS the next bucket, one bar later
        wtod = mod[i] + tf
        if wtod < win_start or wtod > win_end:
            continue
        cnt[2] += 1
        if trades_today >= max_trades or losses_today >= max_losses:
            cnt[3] += 1
            continue
        if pos != 0:
            cnt[4] += 1
            continue
        side = 1 if long_sig else -1
        if rand_side == 1:
            side = 1 if u[iu % len(u)] < 0.5 else -1
            iu += 1
        if invert == 1:
            side = -side
        if entry_at == 0:
            base = bc[e1]
            e_bar = i
            scan_from = i + 2
        else:
            if i + 1 >= n:
                continue
            base = o[i + 1]
            e_bar = i + 1
            scan_from = i + 1
        raw_stop = bl[e1] if side == 1 else bh[e1]
        raw_stop = base - side * stop_mult * abs(base - raw_stop)
        stop = np.round(raw_stop / tick) * tick
        risk = abs(base - stop)
        if risk <= 0:
            continue
        tgt = base + side * rr * risk
        e_px = base + side * side_cost
        pos = side
        trades_today += 1
    return ei[:k], xi[:k], sd[:k], ep[:k], xp[:k], wy[:k], rk[:k], cnt


WHY = {1: "stop", 2: "target", 3: "flat"}


_IND = {}


def get_ind(D, er_n, er_smooth):
    """The VWAP and ER depend only on the feed and the two ER parameters, so a sweep over the
    other axes computes them once. On a million 1-minute bars that is the whole cost."""
    k = (id(D), int(er_n), int(er_smooth))
    if k not in _IND:
        _IND[k] = indicators(D["o"], D["h"], D["l"], D["c"], D["v"], D["mod"], D["key"],
                             D["nkey"], D["tf"], int(er_n), int(er_smooth))
    return _IND[k]


def run(D, cfg=None, entry_at=0, invert=0, use_er=1, use_slope=1, use_drift=1, use_touch=1,
        stop_mult=1.0, cost_mult=1.0, rand_side=0, seed=0, **over):
    cfg = dict(DEFAULT if cfg is None else cfg)
    cfg.update(over)
    vwap, er = get_ind(D, cfg["er_n"], cfg["er_smooth"])
    u = np.random.default_rng(seed).random(8192)
    r = walk(D["o"], D["h"], D["l"], D["c"], D["mod"], D["key"], vwap, er, D["tf"],
             int(cfg["bucket"]), int(cfg["drift_lb"]), float(cfg["drift_pct"]),
             int(cfg["slope_lb"]), float(cfg["er_min"]), float(cfg["rr"]), int(cfg["win_start"]),
             int(cfg["win_end"]), int(cfg["flat"]), int(cfg["max_trades"]), int(cfg["max_losses"]),
             D["side"] * cost_mult, D["tick"], int(entry_at), int(invert), int(use_er),
             int(use_slope), int(use_drift), int(use_touch), float(stop_mult), u, int(rand_side))
    ei, xi, sd, ep, xp, wy, rk, cnt = r
    tr = pd.DataFrame({"ei": ei, "xi": xi, "side": sd, "epx": ep, "xpx": xp, "why": wy, "risk": rk})
    tr["pts"] = (tr["xpx"] - tr["epx"]) * tr["side"]
    tr["R"] = tr["pts"] / tr["risk"].replace(0, np.nan)
    tr["date"] = D["key"][ei] if len(tr) else np.zeros(0, np.int64)
    tr["pct"] = tr["pts"] / D["o"][ei] * 100 if len(tr) else np.zeros(0)
    tr["bars"] = tr["xi"] - tr["ei"]
    return tr, cnt


def metrics(tr, D, mask=None):
    if mask is not None and len(tr):
        tr = tr[mask[tr["ei"].to_numpy()]]
    n = len(tr)
    if n == 0:
        return dict(n=0, net=0.0, mean=np.nan, win=np.nan, pf=np.nan, sharpe=np.nan, dd=np.nan,
                    R=np.nan, usd=0.0, streak=0)
    p = tr["pts"].to_numpy()
    w = p > 0
    pf = p[w].sum() / max(1e-9, -p[~w].sum())
    rth = (D["mod"] >= RTH_OPEN) & (D["mod"] < RTH_CLOSE)
    if mask is not None:
        rth = rth & mask
    sess = np.unique(D["key"][rth])
    daily = pd.Series(0.0, index=sess)
    g = pd.Series(p).groupby(tr["date"].to_numpy()).sum()
    common = g.index.intersection(daily.index)
    daily.loc[common] = g.loc[common]
    sh = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else np.nan
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    streak = 0; cur = 0
    for x in p:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    return dict(n=n, net=float(p.sum()), mean=float(p.mean()), win=float(w.mean()), pf=float(pf),
                sharpe=float(sh), dd=dd, R=float(np.nanmean(tr["R"].to_numpy())),
                usd=float(p.sum() * D["pv"]), streak=streak)


def fmt(m, pv=1.0):
    if m["n"] == 0:
        return "n    0"
    return (f"n {m['n']:>4}  win {100*m['win']:5.1f}%  PF {m['pf']:5.2f}  mean {m['mean']:+7.2f}  "
            f"R {m['R']:+5.2f}  Sharpe {m['sharpe']:+5.2f}  DD {m['dd']:8.1f}"
            + (f"  ${m['usd']:+,.0f}" if pv != 1.0 else ""))


def line(tr, D, B, label, width=28):
    out = f"  {label:<{width}}"
    for b, m in B.items():
        mm = metrics(tr, D, m)
        out += (f" | {b[:4]} n {mm['n']:>4} {mm['R']:+5.2f}R PF {mm['pf']:4.2f} "
                f"Sh {mm['sharpe']:+4.1f}")
    return out
