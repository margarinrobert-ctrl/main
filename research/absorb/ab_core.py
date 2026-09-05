"""The three submitted indicators combined into one reversal strategy, built causally.

COMPONENTS, each transcribed from the posted source:

1. THE 50% LEVEL (`50% level` by kijunkun/milly). Session is `1600-1500` in EXCHANGE time; for
   CME that is Chicago, so 17:00 -> 16:00 New York -- exactly the futures trading day. The script
   accumulates the session's running high and low from the first bar of the session and plots
   `low + (high - low) / 2`. It is a RUNNING midpoint, so it moves whenever the session extends its
   range. Causal as written; reproduced bar for bar here.

2. SWING HIGH / LOW MTF (ICT 3-candle pattern) on 1H and 4H, plus previous day / week / month
   high and low. A swing high sits at HTF bar j when high[j] > high[j-1] and high[j] > high[j+1],
   so it CANNOT be known until HTF bar j+1 has closed. The source publishes it on the open of HTF
   bar j+2 (`new1h` fires when the HTF bar changes) and uses `lookahead_on` only to reach values
   that are already complete. Here the level becomes visible to a trading bar strictly AFTER the
   close of HTF bar j+1 -- `STUDY_DIVERGENCE_CONFIRM`'s confirmed-only rule, applied to swings.

3. ABSORPTION BUBBLES (`Absorption Bubbles` by profitprotrading). `scaledVol = volume /
   stdev(volume, 100)`; the bubble sits at the bar's MIDPOINT and is drawn only when that midpoint
   falls inside a wick:
       upper zone: (h+l)/2 >= max(o,c) and <= h   -- body in the lower part, long UPPER wick
                   the script alerts this as SELLING absorption (sellers absorbed the buying)
       lower zone: (h+l)/2 <= min(o,c) and >= l   -- body in the upper part, long LOWER wick
                   alerted as BUYING absorption
   The published threshold is `scaledVol >= limitFactor` with limitFactor = 0.1, which is nearly
   unconditional -- the buckets A-E only change the DOT SIZE. The threshold is a parameter here so
   its base rate can be measured rather than assumed.

THE STRATEGY: price reaches a level and shows absorption against the move into it -> take the
reversal. Long at support with buying absorption, short at resistance with selling absorption.
Stop 1.5 ATR, optional ATR trailing stop, both swept.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63", "research/scalp89"):
    q = os.path.join(ROOT, p)
    if q not in sys.path: sys.path.insert(0, q)
import v63feeds as FD
import s89_core as M
import s89_pine as P

# per side, in POINTS, split the way the walker charges them: `slip` moves the fill price
# (spread + slippage) and `fee` is subtracted as cash (exchange + broker). The two sum to this
# branch's standard round-turn assumption for each feed.
COST = {"NQ": (0.86, 2.0, 0.25), "US100": (0.75, 1.0, 0.1), "US30": (1.50, 1.0, 0.1)}
SPLIT = {"NQ": dict(slip=0.50, fee=0.36), "US100": dict(slip=0.45, fee=0.30),
         "US30": dict(slip=0.90, fee=0.60)}
SESS_START_NY = 17 * 60          # the futures day opens 17:00 New York = 16:00 Chicago


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _swing_levels(hh, ll, tt, n_trade, idx_map):
    """ICT 3-bar swings on an HTF series, published with ONE HTF bar of confirmation lag.

    A swing high at HTF bar j needs bar j+1 to exist, so the earliest trading bar that may use it
    is the first one after HTF bar j+1 CLOSES. Returns two arrays over trading bars carrying the
    most recent confirmed swing high / low level (NaN before the first)."""
    n = len(hh)
    sh_lvl = np.full(n, np.nan); sl_lvl = np.full(n, np.nan)
    cur_h = np.nan; cur_l = np.nan
    for j in range(1, n - 1):
        # decided once bar j+1 has closed; recorded AT j+1 so the map below lags it correctly
        if hh[j] > hh[j - 1] and hh[j] > hh[j + 1]:
            cur_h = hh[j]
        if ll[j] < ll[j - 1] and ll[j] < ll[j + 1]:
            cur_l = ll[j]
        sh_lvl[j + 1] = cur_h
        sl_lvl[j + 1] = cur_l
    # map HTF bar -> trading bars that begin strictly AFTER that HTF bar closes
    out_h = np.full(n_trade, np.nan); out_l = np.full(n_trade, np.nan)
    out_h[idx_map >= 0] = sh_lvl[idx_map[idx_map >= 0]]
    out_l[idx_map >= 0] = sl_lvl[idx_map[idx_map >= 0]]
    return out_h, out_l


def _htf(ix, o, h, l, c, v, rule):
    """Resample to an HTF and return, for every trading bar, the index of the last HTF bar that
    has ALREADY CLOSED (so nothing can read a forming HTF bar)."""
    df = pd.DataFrame(dict(open=o, high=h, low=l, close=c, volume=v), index=ix)
    g = df.resample(rule, label="left", closed="left").agg(
        dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()
    close_ts = g.index + pd.Timedelta(rule)
    # a trading bar stamped t may use HTF bar k only if close_ts[k] <= t
    pos = np.searchsorted(close_ts.to_numpy(), ix.to_numpy(), side="right") - 1
    return g, pos


def build(market="NQ", tf=15, atr_n=14, vol_look=100, swing_tfs=("1h", "4h")):
    f = FD.bars(market, tf); ix = pd.DatetimeIndex(f.index)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c); mod = (ix.hour * 60 + ix.minute).to_numpy()

    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_n, adjust=False).mean().to_numpy()

    # --- 1. the 50% level: running midpoint of the 17:00 NY -> 16:00 NY session ---
    fut_day = (ix - pd.Timedelta(hours=SESS_START_NY // 60)).normalize()
    fd = fut_day.astype("int64").to_numpy()
    d = pd.DataFrame({"h": h, "l": l, "d": fd})
    g = d.groupby("d", sort=False)
    sess_hi = g["h"].cummax().to_numpy()
    sess_lo = g["l"].cummin().to_numpy()
    mid = sess_lo + (sess_hi - sess_lo) / 2.0
    # the running midline includes THIS bar's own high/low, exactly as the source plots it; for a
    # decision taken at this bar's close that is legal (both are known), but the level a trade
    # reacts to should be the one that existed BEFORE the bar, so shift it by one
    mid_prev = np.roll(mid, 1); mid_prev[0] = np.nan
    new_sess = np.concatenate([[True], fd[1:] != fd[:-1]])
    mid_prev[new_sess] = np.nan

    # --- 2. swing levels on each requested HTF, confirmed-only ---
    lv_h = {}; lv_l = {}
    for rule in swing_tfs:
        g2, pos = _htf(ix, o, h, l, c, v, rule)
        a, b = _swing_levels(g2["high"].to_numpy(), g2["low"].to_numpy(), g2.index, n, pos)
        lv_h[rule] = a; lv_l[rule] = b
    # previous day / week / month extremes (completed periods only)
    for nm, rule in (("D", "1D"), ("W", "1W"), ("M", "1MS")):
        g2, pos = _htf(ix, o, h, l, c, v, rule)
        ph = g2["high"].shift(1).to_numpy(); pl = g2["low"].shift(1).to_numpy()
        a = np.full(n, np.nan); b = np.full(n, np.nan)
        a[pos >= 0] = ph[pos[pos >= 0]]; b[pos >= 0] = pl[pos[pos >= 0]]
        lv_h[nm] = a; lv_l[nm] = b

    # --- 3. absorption ---
    sd = pd.Series(v).rolling(vol_look).std().to_numpy()
    scaled = np.where(sd > 0, v / sd, np.nan)
    midp = (h + l) / 2.0
    body_hi = np.maximum(o, c); body_lo = np.minimum(o, c)
    upper_zone = (midp >= body_hi) & (midp <= h)   # long UPPER wick  -> SELLING absorption
    lower_zone = (midp <= body_lo) & (midp >= l)   # long LOWER wick  -> BUYING absorption

    us = np.unique(fd); cut = us[int(0.65 * len(us))]
    cost, pv, tick = COST[market]
    return dict(market=market, tf=tf, ts=ix.to_numpy(), o=o, h=h, l=l, c=c, v=v, n=n, mod=mod,
                sess=fd, atr=atr, mid=mid, mid_prev=mid_prev, lv_h=lv_h, lv_l=lv_l,
                scaled=scaled, upper_zone=upper_zone, lower_zone=lower_zone,
                cut=int(cut), cost=cost, pv=pv, tick=tick,
                blocks={"research": fd < cut, "locked": fd >= cut},
                vol_kind="true contract volume" if market == "NQ" else "TICK volume (a proxy)")


def signals(D, levels=("mid", "1h", "4h"), vol_min=0.1, touch_atr=0.10, need_absorb=True,
            side="both", sess0=None, sess1=None):
    """A reversal at a level with absorption against the move into it.

    `touch_atr` is how close the bar must come to the level, in ATR -- 0 means the bar's range must
    contain it. `vol_min` is the published `limitFactor` (0.1 by default, which is why its base
    rate is measured before anything else)."""
    n = D["n"]; h, l, c = D["h"], D["l"], D["c"]; atr = D["atr"]
    tol = touch_atr * atr
    res = np.zeros(n, bool)   # touched a level from below -> candidate SHORT
    sup = np.zeros(n, bool)   # touched a level from above -> candidate LONG
    for k in levels:
        if k == "mid":
            lv = D["mid_prev"]
            ok = np.isfinite(lv)
            # the midline is both: approached from below it is resistance, from above support
            res |= ok & (h >= lv - tol) & (c <= lv + tol)
            sup |= ok & (l <= lv + tol) & (c >= lv - tol)
        else:
            hi = D["lv_h"].get(k); lo = D["lv_l"].get(k)
            if hi is not None:
                ok = np.isfinite(hi)
                res |= ok & (h >= hi - tol) & (c <= hi + tol)
            if lo is not None:
                ok = np.isfinite(lo)
                sup |= ok & (l <= lo + tol) & (c >= lo - tol)
    ab_s = (D["scaled"] >= vol_min) & D["upper_zone"]    # selling absorption
    ab_b = (D["scaled"] >= vol_min) & D["lower_zone"]    # buying  absorption
    lo_sig = sup & (ab_b if need_absorb else True)
    sh_sig = res & (ab_s if need_absorb else True)
    if side == "long":
        sh_sig = np.zeros(n, bool)
    elif side == "short":
        lo_sig = np.zeros(n, bool)
    ok = np.isfinite(atr) & (atr > 0)
    ok[:max(300, 120)] = False
    if sess0 is not None:
        ny = D["mod"]
        ok &= (ny >= sess0) & (ny < sess1)
    lo_sig &= ok; sh_sig &= ok
    both = lo_sig & sh_sig
    lo_sig &= ~both; sh_sig &= ~both     # a bar cannot be both
    return np.where(lo_sig, 1, np.where(sh_sig, -1, 0)).astype(np.int64)


def run(D, side_arr, stop=1.5, trail=True, t_arm=1.0, t_off=1.0, tgt=99.0, flat=False,
        flat_mod=15 * 60 + 55, fill_mode=2, fee=None, slip=None, max_hold=0, cost_mult=1.0):
    """`fill_mode=2` = the stop and target are live on the fill bar, which is what a script can
    actually achieve by placing a fill-relative bracket with the entry (STUDY_V56_PARITY)."""
    sp = SPLIT[D["market"]]
    fee = sp["fee"] * cost_mult if fee is None else fee
    slip = sp["slip"] * cost_mult if slip is None else slip
    cfg = dict(M.CFG, stop_mult=stop, tgt_mult=tgt, trail_on=1 if trail else 0,
               trail_arm=t_arm, trail_off=t_off, pv=D["pv"], qty=1)
    return P.run(D, cfg=cfg, side_override=side_arr, fill_mode=fill_mode, trail_atr=1,
                 use_flat=1 if flat else 0, flat_mod=flat_mod, fee=fee, slip=slip,
                 max_hold=max_hold)


def stats(t):
    return M.stats(t)
