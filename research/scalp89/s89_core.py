"""The "NQ Scalping System" Pine, transcribed with its ORDER MODEL, not just its rules.

THE RULE. EMA89 trend (close above = up). Pullback: over the last 10 bars the swing high minus this
bar's low is at least 15 points AND this bar's low touched EMA8 (or EMA21 as a fallback). Trigger:
StochRSI %K was at or below 20 within the last 8 bars (inclusive) and %K crosses over %D this bar.
Shorts mirror. Entries only inside 06:00-11:30 Chicago = 07:00-12:30 New York, skipping the first
minute. Stop 1.5 x ATR(14) and target 2.5 x ATR(14), both measured at the SIGNAL bar and anchored
to the FILL price. A trailing stop that arms once price is 15 points in favour and then trails the
best price by 8 points. NO SESSION FLATTEN -- the script restricts entries to the window and lets
a position run on stop / target / trail alone, so a trade can carry overnight.

THREE THINGS ABOUT THE SCRIPT THAT ARE NOT RULES AND CHANGE THE ANSWER:

  THE ENTRY BAR IS NAKED. `strategy.exit` is called after the `justEnteredLong` block sets the
  stop, on the fill bar's close -- so the bracket is live from the bar AFTER the fill. On the fill
  bar itself nothing protects the position. `STUDY_PINE_PARITY` measured this at 4-13% of trades.
  Modelled both ways (`protect_fill=0/1`) and the gap is reported.

  PINE'S INTRABAR PATH. When a stop and a target (or a trail) both fall inside one bar, the
  broker emulator assumes open -> the NEARER extreme -> the farther extreme -> close. That is not
  "stop first" and it is not "target first". Modelled as the emulator does it (`path=1`) and as
  the branch's conservative rule (`path=0`); the gap is the size of the assumption.

  `strategy.entry` WITHOUT `barstate.isconfirmed`. In a bar-close backtest that is harmless. Live,
  the entry fires on the first tick that satisfies the rule mid-bar, and `STUDY_TICK_RECALC`
  measured that at 5.1x the signals with 80% on bars that never satisfied the rule at the close.
  The research here is the bar-close run, which is the correct one; the shipped script is guarded.

Indicators match Pine's built-ins: `ta.atr` is Wilder's RMA of true range (NOT the ema(tr) this
branch's research layer uses elsewhere), `ta.rsi` is Wilder, `ta.stoch(rsi, rsi, rsi, n)` is the
plain StochRSI, `ta.highest/lowest` include the current bar, `ta.crossover` is `a[1] <= b[1] and
a > b`.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import v63feeds as FD  # noqa: E402

# the screenshot's values, which override the code's defaults
CFG = dict(trend=89, fast=8, slow=21, fallback=1, min_pb=15.0, pb_look=10,
           rsi_n=14, stoch_n=14, k_s=3, d_s=3, os_lvl=20.0, ob_lvl=80.0, reset_look=8,
           sess_start=7 * 60 + 1, sess_end=12 * 60 + 30,      # 06:01-11:30 Chicago in NY minutes
           atr_n=14, stop_mult=1.5, tgt_mult=2.5,
           trail_on=1, trail_arm=15.0, trail_off=8.0,
           qty=5, pv=2.0, tick=0.25)
COST = {"NQ": (0.86, 2.0, 0.25), "US100": (0.75, 1.0, 0.1)}


def _rma(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    au, ad = _rma(up, n), _rma(dn, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = au / ad
        out = 100.0 - 100.0 / (1.0 + rs)
    out[ad == 0] = 100.0
    return out


def build(market="NQ", tf=5, cfg=CFG):
    f = FD.bars(market, tf)
    ix = pd.DatetimeIndex(f.index)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    cost, pv, tick = COST[market]
    return indicators(o, h, l, c, ix, cfg, market=market, tf=tf, cost=cost, pv=pv, tick=tick)


def indicators(o, h, l, c, ix, cfg=CFG, market="NQ", tf=5, cost=0.86, pv=2.0, tick=0.25):
    """Everything the rule reads, from bar arrays -- so a perturbation can rebuild it."""
    n = len(c)
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = _rma(tr, cfg["atr_n"])
    e_tr, e_f, e_s = _ema(c, cfg["trend"]), _ema(c, cfg["fast"]), _ema(c, cfg["slow"])
    rsi = _rsi(c, cfg["rsi_n"])
    rs = pd.Series(rsi)
    lo_r = rs.rolling(cfg["stoch_n"]).min().to_numpy()
    hi_r = rs.rolling(cfg["stoch_n"]).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = 100.0 * (rsi - lo_r) / (hi_r - lo_r)
    raw = np.nan_to_num(raw, nan=50.0)
    k = pd.Series(raw).rolling(cfg["k_s"]).mean().to_numpy()
    d = pd.Series(k).rolling(cfg["d_s"]).mean().to_numpy()
    sw_hi = pd.Series(h).rolling(cfg["pb_look"]).max().to_numpy()
    sw_lo = pd.Series(l).rolling(cfg["pb_look"]).min().to_numpy()
    k_lo = pd.Series(k).rolling(cfg["reset_look"]).min().to_numpy()
    k_hi = pd.Series(k).rolling(cfg["reset_look"]).max().to_numpy()
    us = np.unique(sess)
    cut = us[int(0.65 * len(us))]
    return dict(market=market, tf=tf, ts=ix.to_numpy(), o=o, h=h, l=l, c=c, n=n, mod=mod,
                sess=sess, atr=atr, e_tr=e_tr, e_f=e_f, e_s=e_s, k=k, d=d, sw_hi=sw_hi,
                sw_lo=sw_lo, k_lo=k_lo, k_hi=k_hi, cut=int(cut), cost=cost, pv=pv, tick=tick,
                blocks={"research": sess < cut, "locked": sess >= cut})


def signals(D, cfg=CFG):
    c, h, l = D["c"], D["h"], D["l"]
    k, d = D["k"], D["d"]
    pk, pd_ = np.roll(k, 1), np.roll(d, 1)
    up = c > D["e_tr"]
    dn = c < D["e_tr"]
    touch_lo = (l <= D["e_f"]) | ((cfg["fallback"] == 1) & (l <= D["e_s"]))
    touch_hi = (h >= D["e_f"]) | ((cfg["fallback"] == 1) & (h >= D["e_s"]))
    pb_l = up & ((D["sw_hi"] - l) >= cfg["min_pb"]) & touch_lo
    pb_s = dn & ((h - D["sw_lo"]) >= cfg["min_pb"]) & touch_hi
    x_up = (pk <= pd_) & (k > d)
    x_dn = (pk >= pd_) & (k < d)
    st_l = (D["k_lo"] <= cfg["os_lvl"]) & x_up
    st_s = (D["k_hi"] >= cfg["ob_lvl"]) & x_dn
    ins = (D["mod"] >= cfg["sess_start"]) & (D["mod"] < cfg["sess_end"])
    ok = np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(k) & np.isfinite(d)
    ok[:max(cfg["trend"], 200)] = False
    long = pb_l & st_l & ins & ok
    short = pb_s & st_s & ins & ok
    return np.where(long, 1, np.where(short, -1, 0)).astype(np.int64)


@njit(cache=True)
def walk(o, h, l, c, atr, side, stop_mult, tgt_mult, trail_on, trail_arm, trail_off,
         cost, slip, protect_fill, path, flat_mod, mod, use_flat, max_hold):
    """The script's order model. Fill at the next open. Stop/target from the SIGNAL bar's ATR,
    anchored to the fill. Trail arms at `trail_arm` points in favour and trails the running
    extreme by `trail_off`. `protect_fill`=0 leaves the fill bar naked as the script does.
    `path`=1 uses Pine's open -> nearer extreme -> farther extreme ordering; 0 is stop-first.
    Returns per-trade arrays. A position lock: no new trade while one is open."""
    n = len(c)
    mx = 20000
    e_bar = np.full(mx, -1, np.int64)
    x_bar = np.full(mx, -1, np.int64)
    s_arr = np.zeros(mx, np.int64)
    e_px = np.full(mx, np.nan)
    x_px = np.full(mx, np.nan)
    code = np.full(mx, -1, np.int64)   # 0 stop, 1 target, 2 trail, 3 flat, 4 end of data
    risk = np.full(mx, np.nan)
    cnt = 0
    i = 200
    while i < n - 2:
        s = side[i]
        if s == 0:
            i += 1
            continue
        a = i + 1
        px = o[a] + s * slip
        A = atr[i]
        stp = px - s * stop_mult * A
        tgt = px + s * tgt_mult * A
        rk = stop_mult * A
        armed = 0
        tstop = 0.0
        best = px
        out = np.nan
        xb = -1
        cd = -1
        j = a
        while j < n:
            if j == a and protect_fill == 0:
                # naked fill bar: only the running extreme is tracked
                if s > 0:
                    if h[j] > best:
                        best = h[j]
                else:
                    if l[j] < best:
                        best = l[j]
                j += 1
                continue
            # the bar's path: which extreme comes first
            if path == 1:
                lo_first = (o[j] - l[j]) < (h[j] - o[j])
            else:
                lo_first = True if s > 0 else False   # adverse extreme first = stop first
            # current trailing stop, arming on this bar's favourable extreme if reached
            fav = h[j] if s > 0 else l[j]
            adv = l[j] if s > 0 else h[j]
            if trail_on == 1:
                if armed == 0 and s * (fav - px) >= trail_arm:
                    armed = 1
                if armed == 1:
                    cand = fav - s * trail_off
                    if s > 0:
                        if cand > tstop or tstop == 0.0:
                            tstop = cand
                    else:
                        if cand < tstop or tstop == 0.0:
                            tstop = cand
            eff_stop = stp
            if armed == 1:
                if s > 0 and tstop > eff_stop:
                    eff_stop = tstop
                if s < 0 and tstop < eff_stop:
                    eff_stop = tstop
            hit_stop = (adv <= eff_stop) if s > 0 else (adv >= eff_stop)
            hit_tgt = (fav >= tgt) if s > 0 else (fav <= tgt)
            # gap through the stop at the open
            if (s > 0 and o[j] <= eff_stop) or (s < 0 and o[j] >= eff_stop):
                out = o[j] - s * slip; xb = j; cd = 0 if armed == 0 or eff_stop == stp else 2
                break
            if hit_stop and hit_tgt:
                # both inside one bar: the path decides
                adverse_first = (lo_first if s > 0 else (not lo_first))
                if adverse_first:
                    out = eff_stop - s * slip; xb = j; cd = 0 if eff_stop == stp else 2
                else:
                    out = tgt - s * slip; xb = j; cd = 1
                break
            if hit_stop:
                out = eff_stop - s * slip; xb = j; cd = 0 if eff_stop == stp else 2
                break
            if hit_tgt:
                out = tgt - s * slip; xb = j; cd = 1
                break
            if use_flat == 1 and mod[j] >= flat_mod:
                out = c[j] - s * slip; xb = j; cd = 3
                break
            if max_hold > 0 and (j - a) >= max_hold:
                out = c[j] - s * slip; xb = j; cd = 5
                break
            j += 1
        if xb < 0:
            xb = n - 1; out = c[xb] - s * slip; cd = 4
        if cnt < mx:
            e_bar[cnt] = a; x_bar[cnt] = xb; s_arr[cnt] = s; e_px[cnt] = px; x_px[cnt] = out
            code[cnt] = cd; risk[cnt] = rk
            cnt += 1
        i = xb + 1
    return e_bar[:cnt], x_bar[:cnt], s_arr[:cnt], e_px[:cnt], x_px[:cnt], code[:cnt], risk[:cnt]


def run(D, cfg=CFG, protect_fill=0, path=1, use_flat=0, flat_mod=15 * 60 + 55,
        slip=None, cost=None, side_override=None, max_hold=0):
    side = signals(D, cfg) if side_override is None else side_override
    slip = D["tick"] if slip is None else slip
    cost = D["cost"] if cost is None else cost
    eb, xb, s, ep, xp, cd, rk = walk(D["o"], D["h"], D["l"], D["c"], D["atr"], side,
                                     float(cfg["stop_mult"]), float(cfg["tgt_mult"]),
                                     int(cfg["trail_on"]), float(cfg["trail_arm"]),
                                     float(cfg["trail_off"]), float(cost), float(slip),
                                     int(protect_fill), int(path), int(flat_mod), D["mod"],
                                     int(use_flat), int(max_hold))
    if len(eb) == 0:
        return pd.DataFrame()
    gross = s * (xp - ep)
    net = gross - 2 * cost
    t = pd.DataFrame(dict(entry_bar=eb, exit_bar=xb, side=s, entry_px=ep, exit_px=xp, code=cd,
                          risk=rk, net_pts=net, pct=100.0 * net / ep, R=net / np.maximum(rk, 1e-9),
                          hold=xb - eb, usd=net * cfg["pv"] * cfg["qty"]))
    t["ts"] = D["ts"][eb]
    t["sess"] = D["sess"][eb]
    t["block"] = np.where(t["sess"] < D["cut"], "research", "locked")
    t["exit"] = t["code"].map({0: "stop", 1: "target", 2: "trail", 3: "flat", 4: "eod", 5: "hold"})
    return t


def stats(t, cfg=CFG):
    if len(t) == 0:
        return dict(n=0, pct=np.nan, tot=np.nan, pf=np.nan, win=np.nan, dd=np.nan, pts=np.nan,
                    R=np.nan, usd=np.nan, usd_tot=np.nan, hold=np.nan, sharpe=np.nan)
    v = t["pct"].to_numpy()
    g, b = v[v > 0].sum(), -v[v <= 0].sum()
    eq = np.cumsum(v)
    u = t["usd"].to_numpy()
    d = pd.Series(v, index=pd.DatetimeIndex(t["ts"]).normalize()).groupby(level=0).sum()
    sh = np.sqrt(252) * d.mean() / d.std(ddof=1) if len(d) > 2 and d.std(ddof=1) > 0 else np.nan
    return dict(n=len(v), pct=float(v.mean()), tot=float(v.sum()),
                pf=float(g / b) if b > 0 else np.nan, win=100.0 * float((v > 0).mean()),
                dd=float((eq - np.maximum.accumulate(eq)).min()), pts=float(t["net_pts"].mean()),
                R=float(t["R"].mean()), usd=float(u.mean()), usd_tot=float(u.sum()),
                hold=float(t["hold"].median()), sharpe=float(sh))
