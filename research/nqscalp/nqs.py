"""Faithful replication of the "NQ Scalping System" Pine v6 strategy.

Every indicator is the Pine definition, not the pandas near-equivalent:
  ta.ema  = SMA-seeded, alpha 2/(n+1)
  ta.rma  = SMA-seeded, alpha 1/n          (Wilder)
  ta.atr  = ta.rma(ta.tr(true), n)         <- RMA, not EMA. The Pine uses ta.atr.
  ta.rsi  = rma(gain,n) / rma(loss,n)
  ta.stoch(r,r,r,n) = 100*(r - lowest(r,n)) / (highest(r,n) - lowest(r,n))
  ta.highest/lowest INCLUDE the current bar.

Execution model, matching the strategy's declaration
(calc_on_every_tick=false, process_orders_on_close=false):
  * every rule is read at the CLOSE of the signal bar;
  * strategy.entry fills at the NEXT bar's open, plus slippage;
  * stop/target distances are the SIGNAL bar's ATR (Pine stores them in
    pending* vars), applied to the realised fill price;
  * strategy.exit is live from the fill bar onward, so a same-bar stop or target
    is possible;
  * the trailing stop arms once price has run `trail_arm` points in favour, then
    follows the running extreme by `trail_offset`, and never loosens the fixed
    stop (Pine keeps both orders; the binding one wins);
  * ENTRIES are gated by the session window. EXITS ARE NOT. The Pine has no
    session flatten, so a position opened at the end of the window runs until a
    barrier is hit - possibly days later. `flat_at` reproduces the code as
    written (None) or adds the flatten the description implies.

Intrabar ambiguity on a 15m bar is a modelling choice, not a fact, so it is a
knob: `order="adverse"` resolves the unfavourable level first (stop before
target, trail-stop using this bar's own extreme), `order="favorable"` the other
way. Every headline number is reported under BOTH.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/user/main/research/donchian")
import data as D

TICK = 0.25          # NQ/MNQ tick
NY_MINUS_CHICAGO = 60  # New York is 60 minutes ahead of Chicago, year-round


# ------------------------------------------------------------------ Pine TA
def _seeded(x, alpha, n):
    """Pine's recursive smoothers: SMA seed at bar n-1, then alpha-blend."""
    x = np.asarray(x, float)
    out = np.full(x.shape, np.nan)
    fin = np.flatnonzero(np.isfinite(x))
    if len(fin) < n:
        return out
    b = fin[0]                      # Pine treats leading na as "series not started"
    x = x[b:]
    out = np.full(x.shape, np.nan)
    s = x[:n].mean()
    out[n - 1] = s
    for i in range(n, len(x)):
        s = alpha * x[i] + (1 - alpha) * s
        out[i] = s
    return np.concatenate([np.full(b, np.nan), out])


def ema(x, n):   return _seeded(x, 2.0 / (n + 1.0), n)
def rma(x, n):   return _seeded(x, 1.0 / n, n)
def sma(x, n):   return pd.Series(x).rolling(n).mean().values


def true_range(h, l, c):
    pc = np.roll(c, 1); pc[0] = np.nan
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]                      # ta.tr(true) on the first bar
    return tr


def rsi(c, n):
    d = np.diff(c, prepend=np.nan)
    up = rma(np.where(np.isnan(d), np.nan, np.maximum(d, 0.0)), n)
    dn = rma(np.where(np.isnan(d), np.nan, np.maximum(-d, 0.0)), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dn == 0, 100.0, np.where(up == 0, 0.0, 100 - 100 / (1 + up / dn)))


def hh(x, n): return pd.Series(x).rolling(n).max().values
def ll(x, n): return pd.Series(x).rolling(n).min().values


# ------------------------------------------------------------- the strategy
DEFAULTS = dict(
    trend_ema=89, fast_ema=8, slow_ema=21, use_fallback=True,
    min_pullback=15.0, pullback_lookback=10,
    rsi_len=14, stoch_len=14, k_smooth=3, d_smooth=3,
    oversold=20.0, overbought=80.0, reset_lookback=8,
    use_volume=False, vol_len=20, vol_mult=1.2,
    use_macd=False, macd_fast=12, macd_slow=26, macd_signal=9,
    sess_start_h=6, sess_start_m=0, sess_end_h=11, sess_end_m=30, warmup=1,
    atr_len=14, atr_stop=1.5, atr_target=2.5,
    use_trail=True, trail_arm=15.0, trail_offset=8.0,
    qty=5, point_value=2.0, commission=1.24, slippage_ticks=1.0,
)


def indicators(df, **kw):
    p = {**DEFAULTS, **kw}
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    v = df["tickvol"].values.astype(float)
    I = {}
    I["trend"] = ema(c, p["trend_ema"])
    I["fast"] = ema(c, p["fast_ema"])
    I["slow"] = ema(c, p["slow_ema"])
    I["atr"] = rma(true_range(h, l, c), p["atr_len"])
    r = rsi(c, p["rsi_len"])
    lo, hi = ll(r, p["stoch_len"]), hh(r, p["stoch_len"])
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(hi - lo == 0, 0.0, 100 * (r - lo) / (hi - lo))
    I["k"] = sma(raw, p["k_smooth"])
    I["d"] = sma(I["k"], p["d_smooth"])
    I["swing_hi"] = hh(h, p["pullback_lookback"])
    I["swing_lo"] = ll(l, p["pullback_lookback"])
    I["vol_avg"] = sma(v, p["vol_len"])
    mf, ms = ema(c, p["macd_fast"]), ema(c, p["macd_slow"])
    I["macd"] = mf - ms
    I["macd_sig"] = ema(np.nan_to_num(I["macd"], nan=0.0), p["macd_signal"])
    I["o"], I["h"], I["l"], I["c"], I["v"] = o, h, l, c, v
    return I, p


def conditions(df, I, p):
    """Long/short trigger booleans, all read at the signal bar's close."""
    o, h, l, c = I["o"], I["h"], I["l"], I["c"]
    up, dn = c > I["trend"], c < I["trend"]
    touch_l = (l <= I["fast"]) | (p["use_fallback"] & (l <= I["slow"]))
    touch_s = (h >= I["fast"]) | (p["use_fallback"] & (h >= I["slow"]))
    pull_l = up & ((I["swing_hi"] - l) >= p["min_pullback"]) & touch_l
    pull_s = dn & ((h - I["swing_lo"]) >= p["min_pullback"]) & touch_s

    k, d = I["k"], I["d"]
    kp, dp = np.roll(k, 1), np.roll(d, 1); kp[0] = dp[0] = np.nan
    reset_os = ll(k, p["reset_lookback"]) <= p["oversold"]
    reset_ob = hh(k, p["reset_lookback"]) >= p["overbought"]
    xover = (k > d) & (kp <= dp)
    xunder = (k < d) & (kp >= dp)
    stoch_l, stoch_s = reset_os & xover, reset_ob & xunder

    vol_ok = np.ones(len(c), bool) if not p["use_volume"] else I["v"] >= I["vol_avg"] * p["vol_mult"]
    macd_l = np.ones(len(c), bool) if not p["use_macd"] else I["macd"] > I["macd_sig"]
    macd_s = np.ones(len(c), bool) if not p["use_macd"] else I["macd"] < I["macd_sig"]

    # session in CHICAGO time; the bars are New York, Chicago = NY - 60 min
    chi = (df.tod.values - NY_MINUS_CHICAGO) % 1440
    start = p["sess_start_h"] * 60 + p["sess_start_m"] + p["warmup"]
    end = p["sess_end_h"] * 60 + p["sess_end_m"]
    in_sess = (chi >= start) & (chi < end)

    fin = ~np.isnan(I["trend"]) & ~np.isnan(I["d"]) & ~np.isnan(I["atr"]) & ~np.isnan(I["swing_hi"])
    return (pull_l & stoch_l & vol_ok & macd_l & in_sess & fin,
            pull_s & stoch_s & vol_ok & macd_s & in_sess & fin), in_sess


def simulate(df, I, p, long_ok, short_ok, order="adverse", flat_at=None,
             max_bars=4000, cost_mult=1.0, trail_mode="intrabar"):
    """Sequential one-position-at-a-time walk. Returns a book in POINTS and USD.

    A 15m bar gives O/H/L/C but not the path between them, and this strategy's
    trailing stop is path-dependent, so the result is BRACKETED rather than
    asserted. Two orderings are simulated end to end:

      order="adverse"   O -> adverse extreme -> favourable extreme -> C
                        the initial stop gets first refusal, so a bar that both
                        dips and runs is booked as a full stop-out.
      order="favorable" O -> favourable extreme -> adverse extreme -> C
                        price runs first, arming and tightening the trail, which
                        then gets hit on the way back - a small locked profit.

    The truth is between them. Anything that only works under "favorable" is a
    statement about tick paths this data cannot see.

    flat_at: minutes past Chicago midnight to force flat, or None to reproduce
    the Pine as written, which has NO session exit at all.
    """
    o, h, l, c = I["o"], I["h"], I["l"], I["c"]
    atr = I["atr"]
    n = len(c)
    chi = (df.tod.values - NY_MINUS_CHICAGO) % 1440
    sess = df.sess.values
    slip = p["slippage_ticks"] * TICK * cost_mult
    comm_pts = (p["commission"] * cost_mult) / p["point_value"]
    adverse = order == "adverse"
    trail_on = p["use_trail"]
    # trail_mode="barclose": the trail may only be armed or tightened from bars
    # that have CLOSED, and the level it sets is live from the next bar onward.
    # No claim is then made about the order of prices inside any bar, which is
    # the one thing a 15m OHLC file cannot tell you.
    live_trail = trail_mode == "intrabar"

    rows = []
    i = 0
    while i < n - 1:
        side = 1 if long_ok[i] else (-1 if short_ok[i] else 0)
        if side == 0:
            i += 1
            continue
        sig, fb = i, i + 1
        sd, td = p["atr_stop"] * atr[sig], p["atr_target"] * atr[sig]
        if not np.isfinite(sd) or sd <= 0:
            i += 1
            continue
        fill = o[fb] + side * slip
        stop, targ = fill - side * sd, fill + side * td
        init_stop = stop
        peak, armed = fill, False
        exit_px = exit_bar = reason = None

        for j in range(fb, min(fb + max_bars, n)):
            oj, hj, lj, cj = o[j], h[j], l[j], c[j]
            fav, adv = (hj, lj) if side > 0 else (lj, hj)

            def beyond(px, lvl, is_stop):
                # True when px is at or past lvl in the losing (stop) / winning
                # (target) direction for this side
                d = side * (px - lvl)
                return d <= 0 if is_stop else d >= 0

            # a gap at the open fills at the open, whichever ordering
            if beyond(oj, stop, True):
                exit_px, exit_bar, reason = oj, j, ("trail" if armed else "stop")
                break
            if beyond(oj, targ, False):
                exit_px, exit_bar, reason = oj, j, "target"
                break

            def arm_and_tighten(ext):
                nonlocal peak, armed, stop
                peak = max(peak, ext) if side > 0 else min(peak, ext)
                if trail_on:
                    if not armed and side * (peak - fill) >= p["trail_arm"]:
                        armed = True
                    if armed:
                        ts = peak - side * p["trail_offset"]
                        stop = max(stop, ts) if side > 0 else min(stop, ts)

            if adverse:
                if beyond(adv, stop, True):                       # adverse leg first
                    exit_px, exit_bar, reason = stop, j, ("trail" if armed else "stop")
                    break
                if live_trail:
                    arm_and_tighten(fav)
                if beyond(fav, targ, False):
                    exit_px, exit_bar, reason = targ, j, "target"
                    break
                if live_trail and beyond(cj, stop, True):         # trail hit on the way to C
                    exit_px, exit_bar, reason = stop, j, "trail"
                    break
            else:
                if live_trail:
                    arm_and_tighten(fav)
                if beyond(fav, targ, False):
                    exit_px, exit_bar, reason = targ, j, "target"
                    break
                if beyond(adv, stop, True):
                    exit_px, exit_bar, reason = stop, j, ("trail" if armed else "stop")
                    break
            if not live_trail:
                arm_and_tighten(fav)      # takes effect from the NEXT bar

            if flat_at is not None and (chi[j] >= flat_at or sess[j] != sess[fb]):
                exit_px, exit_bar, reason = cj, j, "flat"
                break
        if exit_bar is None:
            exit_bar = min(fb + max_bars, n) - 1
            exit_px, reason = c[exit_bar], "maxbars"

        gross = side * (exit_px - fill) - slip
        net = gross - 2 * comm_pts
        rows.append(dict(sig_bar=sig, fill_bar=fb, exit_bar=exit_bar, side=side,
                         sess=sess[sig], tod_chi=chi[sig], fill=fill, exit=exit_px,
                         stop_dist=sd, targ_dist=td, atr=atr[sig], reason=reason,
                         armed=armed, bars_held=exit_bar - fb,
                         gross_pts=gross, net_pts=net,
                         net_usd=net * p["point_value"] * p["qty"]))
        i = exit_bar
    tr = pd.DataFrame(rows)
    if len(tr):
        tr["ts"] = df.ts.values[tr.sig_bar.values]
    return tr


def run(df, order="adverse", flat_at=None, cost_mult=1.0, trail_mode="intrabar", **kw):
    I, p = indicators(df, **kw)
    (lo, sh), _ = conditions(df, I, p)
    return simulate(df, I, p, lo, sh, order=order, flat_at=flat_at,
                    cost_mult=cost_mult, trail_mode=trail_mode), I, p


def stats(tr, point_value=2.0, qty=5):
    if not len(tr):
        return dict(n=0)
    net = tr.net_pts.values
    usd = tr.net_usd.values
    eq = np.cumsum(usd)
    dd = eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    wins, losses = net[net > 0], net[net <= 0]
    return dict(n=len(tr), exp_pts=float(net.mean()), exp_usd=float(usd.mean()),
                net_usd=float(usd.sum()), wr=float((net > 0).mean()),
                pf=float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
                mdd_usd=float(-dd.min()), med_bars=float(np.median(tr.bars_held)),
                sharpe=float(net.mean() / net.std(ddof=1) * np.sqrt(252 * len(tr) / max(tr.sess.nunique(), 1)))
                if net.std(ddof=1) > 0 else 0.0,
                long_frac=float((tr.side > 0).mean()))
