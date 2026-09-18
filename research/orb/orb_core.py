"""ORB v1 -- a one-trade-per-session opening-range breakout, built to the spec as given.

EVERY VALUE IS READ FROM COMPLETED BARS. The three places that decide whether this is a backtest
or a fiction:

  the HTF EMA        read from the last higher-timeframe bar that has CLOSED at or before the
                     trading bar's close. The HTF bar CONTAINING the current trading bar is still
                     forming and is never read. "rising" compares that closed bar to the one before
                     it, both closed.
  the volume SMA     the spec says "using bars before the current bar", so it is shifted by one.
                     Unshifted it would compare a bar's volume to an average containing itself.
  the session VWAP   accumulated from the session open through the CURRENT completed bar only.

THE EXITS ARE WALKED ON THE 1-MINUTE SERIES, not on the trading bars. A 1 ATR stop and a 1 ATR
target both sit inside a single 5-minute bar's range often enough that the bar-level answer is a
statement about the tie-break rule (`STUDY_V10_LIMIT`). The 1-minute path resolves most of them by
sequence; the residual 1-minute ambiguity is COUNTED and reported, and resolved as a STOP.

COSTS follow the branch's NQ stack so this is comparable with everything else here: 0.25 spread +
0.25 slippage charged as a price adjustment per side, plus 0.36 points of fees per side = 0.86 per
side, 1.72 the round turn, point value 2.0 (MNQ), tick 0.25.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "v63")):
    if p not in sys.path:
        sys.path.insert(0, p)

import v63feeds as FD  # noqa: E402
import orb_feeds as OF  # noqa: E402

# ---- the session, stated explicitly -------------------------------------------------------
SESS_OPEN = 9 * 60 + 30          # 09:30 New York
SESS_CLOSE = 16 * 60             # 16:00
# "flat by 16:00": the order goes on the last execution bar that starts before the close, and the
# fill is that bar's open. On a 1-minute path that is 15:55; on a 15-minute feed it is 15:45,
# because a 15-minute chart has no finer place to put it.
def liquidate_at(exec_tf):
    return SESS_CLOSE - max(exec_tf, 5)


LIQUIDATE = SESS_CLOSE - 5       # 15:55, the 1-minute default; kept so v1 reproduces exactly
RANGE_MIN = 15                   # the opening range is the first 15 completed minutes

# ---- instrument ---------------------------------------------------------------------------
TICK = 0.25
POINT_VALUE = 2.0                # MNQ
SPREAD = 0.25
SLIP = 0.25
FEE_PTS = 0.36                   # per side, expressed in points so it scales with point value

# ---- strategy defaults --------------------------------------------------------------------
TRADE_TF = 5
HTF = 15
EMA_FAST, EMA_SLOW = 20, 50
ATR_N = 14
VOL_N = 20
VOL_MULT = 1.2
RATIO_LO, RATIO_HI = 0.3, 1.5
BUF_ATR = 0.05
STOP_ATR = 1.0
RISK_PCT = 0.0025
EQUITY0 = 100_000.0


def _sess_key(ix):
    """RTH sessions only, so the calendar day IS the session."""
    return (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()


def _wilder(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def build(market="NQ", trade_tf=TRADE_TF, htf=HTF, ema_fast=EMA_FAST, ema_slow=EMA_SLOW,
          atr_n=ATR_N, vol_n=VOL_N, atr_tf=None, exec_tf=None):
    """Trading bars, the 1-minute execution path, and every indicator, all causal."""
    sp = OF.SPEC[market]
    exec_tf = sp["native"] if exec_tf is None else exec_tf
    m1 = OF.bars(market, exec_tf)
    tb = OF.bars(market, trade_tf)
    hb = OF.bars(market, htf)

    def rth(df):
        ix = pd.DatetimeIndex(df.index)
        mod = ix.hour * 60 + ix.minute
        return df[(mod >= SESS_OPEN) & (mod < SESS_CLOSE)]

    # the HTF EMA is computed on the CONTINUOUS series (an EMA restarted each session is a
    # different indicator), then sampled causally onto the RTH trading bars.
    hix = pd.DatetimeIndex(hb.index)
    h_close_time = hix + pd.Timedelta(minutes=htf)
    hc = hb["close"].to_numpy(float)
    ef, es = _ema(hc, ema_fast), _ema(hc, ema_slow)

    m1 = rth(m1)
    tb = rth(tb)
    tix = pd.DatetimeIndex(tb.index)
    t_close_time = tix + pd.Timedelta(minutes=trade_tf)
    # last HTF bar CLOSED at or before this trading bar's close
    j = np.searchsorted(h_close_time.to_numpy(), t_close_time.to_numpy(), side="right") - 1
    ok = j >= 1
    ema_f = np.where(ok, ef[np.clip(j, 1, None)], np.nan)
    ema_s = np.where(ok, es[np.clip(j, 1, None)], np.nan)
    ema_f_prev = np.where(ok, ef[np.clip(j - 1, 0, None)], np.nan)

    o, h, l, c, v = (tb[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    sess = _sess_key(tix)
    mod = (tix.hour * 60 + tix.minute).to_numpy()

    # ATR(14), Wilder, from completed bars only.
    # THE SPEC DOES NOT NAME THE ATR's TIMEFRAME and it is the most consequential unstated choice
    # in the whole rule, because `range_size / ATR` compares a 15-MINUTE range to an ATR measured
    # on whatever bar size you picked. `atr_tf=None` is the literal reading (the trading bars);
    # any other value is sampled from the last CLOSED bar of that timeframe.
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = _wilder(tr, atr_n)
    if atr_tf is not None and atr_tf != trade_tf:
        ab = OF.bars(market, atr_tf)
        aix = pd.DatetimeIndex(ab.index)
        ah, al, ac = (ab[k].to_numpy(float) for k in ("high", "low", "close"))
        apc = np.roll(ac, 1); apc[0] = ac[0]
        atr_o = _wilder(np.maximum(ah - al, np.maximum(np.abs(ah - apc), np.abs(al - apc))), atr_n)
        a_close = (aix + pd.Timedelta(minutes=atr_tf)).to_numpy()
        ja = np.searchsorted(a_close, t_close_time.to_numpy(), side="right") - 1
        atr = np.where(ja >= 0, atr_o[np.clip(ja, 0, None)], np.nan)

    # volume SMA(20) over the bars BEFORE the current bar
    vsma = pd.Series(v).rolling(vol_n).mean().shift(1).to_numpy()

    # session VWAP through the current completed bar
    tp = (h + l + c) / 3.0
    df = pd.DataFrame({"pv": tp * v, "v": v, "s": sess})
    g = df.groupby("s", sort=False)
    vwap = (g["pv"].cumsum() / g["v"].cumsum()).to_numpy()

    # opening range: the trading bars whose whole span sits inside the first RANGE_MIN minutes
    in_range = (mod >= SESS_OPEN) & (mod + trade_tf <= SESS_OPEN + RANGE_MIN)
    rr = pd.DataFrame({"s": sess, "h": np.where(in_range, h, np.nan),
                       "l": np.where(in_range, l, np.nan),
                       "a": np.where(in_range, atr, np.nan)})
    gg = rr.groupby("s", sort=False)
    rng = pd.DataFrame({"rh": gg["h"].max(), "rl": gg["l"].min(),
                        # ATR at range completion = the ATR of the LAST opening-range bar
                        "ra": gg["a"].last()})
    rh = rng["rh"].reindex(sess).to_numpy()
    rl = rng["rl"].reindex(sess).to_numpy()
    ra = rng["ra"].reindex(sess).to_numpy()

    m1ix = pd.DatetimeIndex(m1.index)
    return dict(
        market=market, trade_tf=trade_tf, htf=htf, atr_tf=atr_tf or trade_tf, exec_tf=exec_tf,
        tick=sp["tick"], pv=sp["pv"], spread=sp["spread"], slip=sp["slip"], fee=sp["fee"],
        vol_kind=sp["vol"], liquidate=liquidate_at(exec_tf),
        ts=tix.to_numpy(), o=o, h=h, l=l, c=c, v=v, sess=sess, mod=mod, atr=atr,
        vsma=vsma, vwap=vwap, ema_f=ema_f, ema_s=ema_s, ema_f_prev=ema_f_prev,
        rh=rh, rl=rl, ra=ra, in_range=in_range,
        m1_ts=m1ix.to_numpy(),
        m1_o=m1["open"].to_numpy(float), m1_h=m1["high"].to_numpy(float),
        m1_l=m1["low"].to_numpy(float), m1_c=m1["close"].to_numpy(float),
        m1_sess=_sess_key(m1ix), m1_mod=(m1ix.hour * 60 + m1ix.minute).to_numpy(),
        blocks=OF.blocks(market, tix))


def signals(D, vol_mult=VOL_MULT, ratio_lo=RATIO_LO, ratio_hi=RATIO_HI, buf_atr=BUF_ATR,
            allow_long=True, allow_short=True):
    """Every rule in the spec, vectorised. Returns the index of each qualifying breakout bar."""
    c, atr, rh, rl, ra = D["c"], D["atr"], D["rh"], D["rl"], D["ra"]
    n = len(c)
    prev_c = np.roll(c, 1); prev_c[0] = np.nan
    same_sess = np.r_[False, D["sess"][1:] == D["sess"][:-1]]

    ratio = (rh - rl) / ra
    tradeable = (ratio >= ratio_lo) & (ratio <= ratio_hi) & np.isfinite(ratio)
    # breakouts are only evaluated AFTER the opening range is complete
    after = (D["mod"] >= SESS_OPEN + RANGE_MIN) & ~D["in_range"]
    buf = np.maximum(buf_atr * atr, D["tick"])
    volok = D["v"] > vol_mult * D["vsma"]

    up = rh + buf
    dn = rl - buf
    long_t = (D["ema_f"] > D["ema_s"]) & (D["ema_f"] > D["ema_f_prev"]) & (c > D["vwap"])
    short_t = (D["ema_f"] < D["ema_s"]) & (D["ema_f"] < D["ema_f_prev"]) & (c < D["vwap"])

    base = after & tradeable & volok & same_sess & np.isfinite(atr) & np.isfinite(D["ema_f"])
    # allow_long / allow_short may be scalars or per-bar boolean arrays (the regime filter)
    lo = base & (c > up) & (prev_c <= up) & long_t & allow_long
    sh = base & (c < dn) & (prev_c >= dn) & short_t & allow_short
    side = np.where(lo, 1, np.where(sh, -1, 0)).astype(np.int64)
    return side, ratio


@njit(cache=True)
def _walk(sig_bar, sig_side, sig_atr, t_end_bar, m1_o, m1_h, m1_l, m1_c, m1_mod,
          equity0, risk_pct, point_value, spread, slip, fee_pts, stop_atr, liquidate,
          conservative):
    """One trade per session, exits walked on the 1-minute path, equity compounding.

    Returns per trade: entry bar, entry price, qty, stop, t1, t2, realised $ P&L, exit code
    (0 stop, 1 second target, 2 liquidation, 3 breakeven stop after T1), R multiple, qty scaled
    out at T1, whether the bar was AMBIGUOUS (stop and a target inside the same 1-minute bar).
    """
    n = len(sig_bar)
    e_bar = np.full(n, -1, np.int64)
    e_px = np.full(n, np.nan)
    qty = np.zeros(n, np.int64)
    q1 = np.zeros(n, np.int64)
    pnl = np.zeros(n)
    code = np.full(n, -1, np.int64)
    rmul = np.full(n, np.nan)
    amb = np.zeros(n, np.int64)
    eq = np.zeros(n)
    equity = equity0
    px_adj = spread + slip
    m = len(m1_c)

    for k in range(n):
        i0 = sig_bar[k]                 # first 1-minute bar AFTER the signal bar closes
        if i0 < 0 or i0 >= m - 1:
            continue
        s = sig_side[k]
        a = sig_atr[k]
        if a <= 0.0:
            continue
        fill = m1_o[i0] + s * px_adj    # the actual modeled fill, gaps included
        stop = fill - s * stop_atr * a
        risk_pu = abs(fill - stop) * point_value
        if risk_pu <= 0.0:
            continue
        q = int(np.floor(equity * risk_pct / risk_pu))
        if q < 1:
            continue                    # below the minimum lot -- the trade is skipped
        half = q // 2                   # 50% scale-out, rounded DOWN to a whole lot
        rest = q - half
        r = abs(fill - stop)
        t1 = fill + s * r
        t2 = fill + s * 2.0 * r

        cur_stop = stop
        live = q
        got1 = False
        cash = 0.0
        fees = fee_pts * point_value * q          # entry side
        ex = 2
        i = i0
        end = t_end_bar[k]
        while i <= end and i < m:
            hi, lo = m1_h[i], m1_l[i]
            hit_stop = (lo <= cur_stop) if s > 0 else (hi >= cur_stop)
            tgt = t1 if not got1 else t2
            hit_tgt = (hi >= tgt) if s > 0 else (lo <= tgt)
            if hit_stop and hit_tgt:
                amb[k] += 1
                if conservative == 1:
                    hit_tgt = False               # the stop is taken first, by assumption
            if hit_stop:
                px = cur_stop - s * px_adj
                if i == i0:
                    px = m1_o[i] - s * px_adj if (s > 0 and m1_o[i] < cur_stop) or \
                                                 (s < 0 and m1_o[i] > cur_stop) else px
                cash += s * (px - fill) * live * point_value
                fees += fee_pts * point_value * live
                ex = 3 if got1 else 0
                live = 0
                break
            if hit_tgt:
                if not got1:
                    got1 = True
                    if half > 0:
                        px = t1 - s * px_adj
                        cash += s * (px - fill) * half * point_value
                        fees += fee_pts * point_value * half
                        live -= half
                    cur_stop = fill                # breakeven on the remainder
                    if live == 0:
                        ex = 1
                        break
                else:
                    px = t2 - s * px_adj
                    cash += s * (px - fill) * live * point_value
                    fees += fee_pts * point_value * live
                    live = 0
                    ex = 1
                    break
            i += 1
        if live > 0:                              # session liquidation
            j = i if i < m else m - 1
            px = m1_o[min(j, m - 1)] - s * px_adj
            cash += s * (px - fill) * live * point_value
            fees += fee_pts * point_value * live
            ex = 2
        net = cash - fees
        equity += net
        e_bar[k] = i0; e_px[k] = fill; qty[k] = q; q1[k] = half
        pnl[k] = net; code[k] = ex; eq[k] = equity
        rmul[k] = net / (risk_pu * q) if risk_pu * q > 0 else np.nan
    return e_bar, e_px, qty, q1, pnl, code, rmul, amb, eq
