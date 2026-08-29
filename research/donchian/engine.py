"""Donchian backtest engine: cached forward-walk tensors, geometry as an index.

Design
------
A trade's outcome depends only on its ENTRY bar and the exit geometry. So the
forward price walk is cached once per dataset as running extremes, and every
(stop, target, max-hold) triple becomes a vectorised lookup. That is what makes
a matched control affordable as a research GATE rather than a final check.

No-lookahead contract
---------------------
  * signals are evaluated on CLOSED bars only (index i)
  * the fill happens at the OPEN of bar i+1
  * every indicator at bar i uses bars <= i
  * Donchian channels EXCLUDE the current bar (rolling(L).shift(1)) so a bar
    cannot break out of a channel it is itself setting

Pessimism (deliberate, priced)
------------------------------
  * a bar containing BOTH stop and target is booked as a LOSS - the intrabar
    path is unknown. Frequency is reported as `ambig`.
  * costs are charged on both legs, in points, at the modelled round turn
  * a gap through the stop fills at the bar OPEN when that is worse
"""
import numpy as np, pandas as pd

MAXHOLD = 32                      # 8 hours of 15m bars - covers any intraday hold
STOP_EXIT, TARG_EXIT, TIME_EXIT, FLAT_EXIT, CHAN_EXIT = 0, 1, 2, 3, 4
REASONS = ["stop", "target", "time", "flatten", "channel"]


# ----------------------------------------------------------------- indicators
def ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty_like(x, dtype=np.float64)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def true_range(h, l, c):
    pc = np.roll(c, 1); pc[0] = c[0]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def atr(df, n=14, wilder=False):
    """House convention (see CLAUDE.md): ATR is ema(tr, n), NOT ta.atr, unless
    wilder is asked for explicitly."""
    tr = true_range(df.high.values, df.low.values, df.close.values)
    if wilder:
        a = 1.0 / n
        out = np.empty_like(tr); out[0] = tr[0]
        for i in range(1, len(tr)):
            out[i] = a * tr[i] + (1 - a) * out[i - 1]
        return out
    return ema(tr, n)


def donchian(df, n):
    """Upper/lower channel EXCLUDING the current bar. Breaking out of a channel
    the current bar helped set is the classic Donchian look-ahead."""
    hi = pd.Series(df.high.values).rolling(n).max().shift(1).values
    lo = pd.Series(df.low.values).rolling(n).min().shift(1).values
    return hi, lo


# ------------------------------------------------------------- forward tensors
def build_walk(df, maxhold=MAXHOLD):
    """Running extremes of the forward walk.

    runmax[i, h] = max(high[i+1 .. i+1+h]),  runmin[i, h] = min(low[i+1 .. i+1+h])
    opens[i, h]  = open[i+1+h],  closes[i, h] = close[i+1+h]
    Everything is indexed from the FILL bar (i+1), never the signal bar.
    """
    n = len(df)
    h_, l_, o_, c_ = (df.high.values.astype(np.float64), df.low.values.astype(np.float64),
                      df.open.values.astype(np.float64), df.close.values.astype(np.float64))
    H = maxhold
    runmax = np.full((n, H), np.nan); runmin = np.full((n, H), np.nan)
    opens = np.full((n, H), np.nan);  closes = np.full((n, H), np.nan)
    sess = df.sess.values; tod = df.tod.values
    sess_f = np.full((n, H), -1, dtype=np.int32); tod_f = np.full((n, H), -1, dtype=np.int32)
    for k in range(H):
        j = np.arange(n) + 1 + k
        ok = j < n
        jj = j[ok]
        opens[ok, k] = o_[jj]; closes[ok, k] = c_[jj]
        sess_f[ok, k] = sess[jj]; tod_f[ok, k] = tod[jj]
        if k == 0:
            runmax[ok, k] = h_[jj]; runmin[ok, k] = l_[jj]
        else:
            runmax[ok, k] = np.fmax(runmax[ok, k - 1], h_[jj])
            runmin[ok, k] = np.fmin(runmin[ok, k - 1], l_[jj])
    # highs/lows of the individual forward bar, needed for same-bar detection
    barhi = np.full((n, H), np.nan); barlo = np.full((n, H), np.nan)
    for k in range(H):
        j = np.arange(n) + 1 + k; ok = j < n; jj = j[ok]
        barhi[ok, k] = h_[jj]; barlo[ok, k] = l_[jj]
    return dict(runmax=runmax, runmin=runmin, opens=opens, closes=closes,
                barhi=barhi, barlo=barlo, sess_f=sess_f, tod_f=tod_f, n=n, H=H)


def simulate(walk, idx, side, entry_px, stop_px, targ_px,
             max_hold=16, flat_tod=660, cost_pts=2.0, slip_pts=0.0):
    """Resolve trades signalled at bars `idx`.

    idx       : signal-bar indices (fill is at walk.opens[i, 0] == open of i+1)
    side      : +1 long / -1 short, per trade
    entry_px  : realised fill price per trade (already slipped)
    stop_px   : absolute stop price per trade
    targ_px   : absolute target price per trade (np.inf/-inf disables)
    max_hold  : bars held before the time stop
    flat_tod  : minute-of-day (New York) at which any open trade is flattened
    cost_pts  : ROUND-TURN cost in index points, charged once per trade
    """
    H = min(max_hold, walk["H"])
    rmax = walk["runmax"][idx, :H]; rmin = walk["runmin"][idx, :H]
    opn = walk["opens"][idx, :H];   cls = walk["closes"][idx, :H]
    bhi = walk["barhi"][idx, :H];   blo = walk["barlo"][idx, :H]
    sf = walk["sess_f"][idx, :H];   tf = walk["tod_f"][idx, :H]
    m = len(idx)
    side = side.astype(np.float64)
    valid = ~np.isnan(opn[:, 0])

    sgn = side[:, None]
    # favourable / adverse running excursions, in signed price terms
    fav = np.where(sgn > 0, rmax, -rmin)          # best price reached
    adv = np.where(sgn > 0, rmin, -rmax)          # worst price reached
    tgt_s = np.where(side > 0, targ_px, -targ_px)[:, None]
    stp_s = np.where(side > 0, stop_px, -stop_px)[:, None]

    hit_t = fav >= tgt_s
    hit_s = adv <= stp_s
    # bar-local touches, to detect the same-bar ambiguity
    bar_fav = np.where(sgn > 0, bhi, -blo)
    bar_adv = np.where(sgn > 0, blo, -bhi)
    bar_t = bar_fav >= tgt_s
    bar_s = bar_adv <= stp_s

    # session boundary / flatten time -> forced exit
    sess0 = walk["sess_f"][idx, 0][:, None]
    dead = (sf != sess0) | (tf >= flat_tod) | (sf < 0)

    any_t = hit_t.any(1); any_s = hit_s.any(1); any_d = dead.any(1)
    f_t = np.where(any_t, hit_t.argmax(1), H + 9)
    f_s = np.where(any_s, hit_s.argmax(1), H + 9)
    f_d = np.where(any_d, dead.argmax(1), H + 9)

    first = np.minimum(np.minimum(f_t, f_s), np.minimum(f_d, H - 1))
    reason = np.full(m, TIME_EXIT, dtype=np.int8)
    ar = np.arange(m)

    # resolution order: forced flatten, then stop, then target; a bar holding
    # both stop and target is booked as the LOSS.
    ambig = (f_s == f_t) & any_t & any_s & (f_s <= f_d)
    reason[(f_t <= f_s) & (f_t <= f_d) & any_t] = TARG_EXIT
    reason[(f_s <= f_t) & (f_s <= f_d) & any_s] = STOP_EXIT
    reason[(f_d < f_s) & (f_d < f_t) & any_d] = FLAT_EXIT
    reason[ambig] = STOP_EXIT

    exit_px = np.empty(m)
    r_t = reason == TARG_EXIT; r_s = reason == STOP_EXIT
    r_d = reason == FLAT_EXIT; r_x = reason == TIME_EXIT
    exit_px[r_t] = targ_px[r_t]
    exit_px[r_s] = stop_px[r_s]
    # gap through the stop: the fill is the bar OPEN when that is worse
    if r_s.any():
        go = opn[ar[r_s], first[r_s]]
        worse = np.where(side[r_s] > 0, np.minimum(go, stop_px[r_s]),
                         np.maximum(go, stop_px[r_s]))
        exit_px[r_s] = worse
    if r_d.any():
        exit_px[r_d] = opn[ar[r_d], first[r_d]]      # flatten at the next open
    if r_x.any():
        exit_px[r_x] = cls[ar[r_x], first[r_x]]      # time stop at the close

    gross = side * (exit_px - entry_px)
    net = gross - cost_pts
    out = pd.DataFrame(dict(sig_bar=idx, side=side.astype(int), entry=entry_px,
                            exit=exit_px, stop=stop_px, targ=targ_px,
                            gross=gross, net=net, bars=first + 1,
                            reason=reason, ambig=ambig))
    return out[valid].reset_index(drop=True)


# ------------------------------------------------------------------- reporting
def stats(tr, cost_pts=None, pt_value=1.0):
    if len(tr) == 0:
        return dict(n=0, net=0.0, exp=0.0, pf=0.0, wr=0.0, sharpe=0.0, mdd=0.0)
    net = tr.net.values * pt_value
    wins = net[net > 0]; losses = net[net <= 0]
    eq = np.cumsum(net); peak = np.maximum.accumulate(eq)
    mdd = float((peak - eq).max()) if len(eq) else 0.0
    sd = net.std(ddof=1)
    return dict(
        n=len(tr), net=float(net.sum()), exp=float(net.mean()),
        pf=float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.inf,
        wr=float((net > 0).mean()),
        sharpe=float(net.mean() / sd * np.sqrt(252 * 6.5)) if sd > 0 else 0.0,
        t=float(net.mean() / (sd / np.sqrt(len(net)))) if sd > 0 else 0.0,
        mdd=mdd, ambig=float(tr.ambig.mean()),
        med_bars=float(np.median(tr.bars)),
    )


def fmt(s, label=""):
    if s["n"] == 0:
        return f"{label:<28} NO TRADES"
    return (f"{label:<28} n={s['n']:>6,}  net={s['net']:>11,.0f}  exp={s['exp']:>8.2f}"
            f"  pf={s['pf']:>5.2f}  wr={s['wr']:>5.1%}  t={s['t']:>6.2f}"
            f"  mdd={s['mdd']:>9,.0f}  hold={s['med_bars']:>4.1f}")
