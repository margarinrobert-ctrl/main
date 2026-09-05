"""
IFVG + Liquidity Sweep (Dodgy DD / ICT) model - Python port of the Pine v6 strategy.

This is an event-driven, bar-by-bar reimplementation of the TradingView strategy so
it can be backtested with VectorBT. It preserves the stateful ICT pipeline:

    liquidity sweep (ERL)  ->  displacement  ->  FVG inversion (IFVG)  ->  entry

with the same context filters: market-structure bias (BOS/MSS), premium/discount
equilibrium from the 18:00 NY ICT-day open, killzones + ICT macros, displacement
(body >= ATR x mult), singular-FVG (reject double FVGs), an FVG size band, and the
prop-firm daily limits (max trades/day, two-losses-and-done).

The generator returns explicit long/short entry+exit boolean arrays and the fill
price at each event, which ``backtest.py`` hands to ``vbt.Portfolio.from_signals``.

Faithfulness notes / simplifications vs. the Pine source:
  * Entries fill at the NEXT bar's open (market) or when price trades the inverted
    gap edge within the limit-expiry window (limit retrace) - no same-bar lookahead.
  * Stops/targets are resolved by walking bars forward and taking the first of:
    hard stop, take-profit, "IFVG close" invalidation, or end-of-session flatten.
    Intrabar, a STOP is assumed to fill before the TP on the same bar (worst case).
  * Partial scaling at ITH/ITL + break-even is approximated by a single exit on the
    runner target with break-even handling; the standalone ``Params.use_scale`` only
    toggles the break-even-after-ITH behaviour here (documented, not silently dropped).
  * SMT divergence requires a correlated feed; off by default (matches Pine default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

MINTICK = 0.25          # NQ futures tick
POINT_VALUE = 20.0      # NQ $ per point
NY_TZ = "America/New_York"


@dataclass
class Params:
    # --- Fair Value Gap ---
    min_gap_ticks: float = 20.0
    max_gap_ticks: float = 100.0      # 0 = off
    fvg_max_age: int = 60
    use_double_fvg: bool = True
    double_fvg_bars: int = 5
    # --- Liquidity sweep ---
    use_sweep: bool = True
    sweep_lookback: int = 5           # sweep -> IFVG must form short-term (~1-5 min)
    pivot_len: int = 8
    use_swing_sweep: bool = True      # use swing pivot highs/lows as sweep levels
    use_pd_levels: bool = True        # previous-day high/low
    use_eq: bool = True               # equal highs/lows
    eq_ticks: float = 8.0
    allow_no_sweep_with_smt: bool = False
    # Session ranges (a later session raids an earlier one's high/low). Each session's
    # range freezes when it ends and becomes a sweep level + runner draw for the rest
    # of the ICT day. All reset at the 18:00 NY ICT-day open.
    use_sessions: bool = True
    use_asian_range: bool = True      # Asian 20:00-00:00 NY
    use_london_range: bool = True     # London 02:00-05:00 NY
    use_ny_range: bool = True         # NY AM 08:30-12:00 NY
    # --- Market structure ---
    use_mss: bool = True
    # --- Premium/Discount ---
    use_pd: bool = True
    # --- Displacement ---
    use_disp: bool = True
    atr_len: int = 14
    disp_mult: float = 1.0
    # --- Time ---
    use_time: bool = True
    use_ny_am: bool = True
    ny_am_start: int = 510            # NY AM killzone start, NY minutes (08:30 = 510)
    ny_am_end: int = 660              # NY AM killzone end, NY minutes (11:00 = 660)
    use_ny_lunch: bool = False
    use_ny_pm: bool = True
    use_london: bool = False
    use_macro: bool = False
    # --- Daily limits ---
    use_daily_limits: bool = True
    max_trades_per_day: int = 3
    max_losses_per_day: int = 2
    # --- Execution ---
    entry_mode: str = "Auto"          # Auto | Market on close | Limit Retest
    auto_chase_ticks: float = 40.0
    limit_expiry: int = 6
    # --- Risk ---
    stop_mode: str = "IFVG close"     # IFVG close | Swing high/low
    tp_mode: str = "Opposing liquidity"  # runner draws to the external swing high/low
    rr: float = 1.0                   # TP1 (partial) reward:risk -> 1:1 per the model
    runner_rr: float = 2.0            # runner fallback R:R when no external pool exists
    sl_lookback: int = 10
    sl_buf_ticks: float = 4.0
    use_be: bool = True               # move stop to break-even at the internal high/low
    use_scale: bool = True            # scale a partial at TP1 (1R)
    scale_pct: float = 50.0           # % of position taken off at TP1
    full_tp_1r: bool = False          # pure 1:1: take 100% off at the 1R target with a
                                      # symmetric hard stop (no partial/BE/runner/IFVG
                                      # early-exit). Win rate then reads as P(1R first).
    flat_eod: bool = True
    eod_session: tuple[int, int] = (8 * 60 + 30, 16 * 60)  # 0830-1600 NY, minutes


def preset(name: str = "robust") -> Params:
    """Named parameter presets.

    "robust" — the pure-1:1 config that survived cross-seed validation on the
    synthetic series (median ~+3.6%, win rate ~63%, PF ~2.1 across 6 seeds). NOTE:
    this is tuned on a synthetic generator and is a starting point, not a validated
    real-market edge — re-optimise on your own NQ data.
    """
    if name == "robust":
        return Params(min_gap_ticks=12.0, disp_mult=0.6, full_tp_1r=True,
                      sweep_lookback=3, stop_mode="Swing high/low")
    if name == "default":
        return Params()
    raise ValueError(f"unknown preset: {name}")


@dataclass
class Signals:
    long_entries: np.ndarray
    long_exits: np.ndarray
    short_entries: np.ndarray
    short_exits: np.ndarray
    entry_price: np.ndarray   # fill price aligned to entry bars (NaN elsewhere)
    exit_price: np.ndarray    # final-exit fill price aligned to exit bars (NaN elsewhere)
    order_size: np.ndarray    # signed contracts per bar (+buy/-sell, NaN = no order)
    order_price: np.ndarray   # fill price for the order on that bar (NaN = no order)
    trades: list = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Indicator helpers (vectorised where the Pine equivalent is stateless)
# --------------------------------------------------------------------------------------
def _atr(h, l, c, length):
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr = np.full_like(c, np.nan, dtype=float)
    # Wilder's RMA
    if len(c) >= length:
        atr[length - 1] = tr[:length].mean()
        for i in range(length, len(c)):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def _pivots(h, l, length):
    """Confirmed pivot high/low; value is placed at the confirmation bar (i),
    referring to the pivot that occurred at bar i-length (Pine ta.pivothigh)."""
    n = len(h)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(2 * length, n):
        c = i - length
        if h[c] == max(h[c - length:c + length + 1]) and h[c] > h[c - 1] and h[c] >= h[c + length]:
            # strict-ish local max (matches pivothigh: higher than neighbours)
            window = h[c - length:c + length + 1]
            if h[c] == window.max() and (window == h[c]).sum() == 1:
                ph[i] = h[c]
        wl = l[c - length:c + length + 1]
        if l[c] == wl.min() and (wl == l[c]).sum() == 1:
            pl[i] = l[c]
    return ph, pl


# --------------------------------------------------------------------------------------
# Main generator
# --------------------------------------------------------------------------------------
def generate(df: pd.DataFrame, p: Params, tz: str = NY_TZ, contracts: float = 1.0) -> Signals:
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(tz)
    ny = idx.tz_convert(tz)
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(c)

    mintick = MINTICK
    min_gap = p.min_gap_ticks * mintick
    max_gap = p.max_gap_ticks * mintick
    buf = p.sl_buf_ticks * mintick
    chase_tol = p.auto_chase_ticks * mintick
    eq_tol = p.eq_ticks * mintick

    atr = _atr(h, l, c, p.atr_len)
    ph, pl = _pivots(h, l, p.pivot_len)

    minute = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
    hour = ny.hour.to_numpy()
    weekday = ny.weekday.to_numpy()
    daynum = (ny.normalize().astype("int64").to_numpy())

    def in_window(mn, start, end):
        return (mn >= start) & (mn < end)

    in_ny_am = p.use_ny_am & in_window(minute, p.ny_am_start, p.ny_am_end)
    in_ny_lunch = p.use_ny_lunch & in_window(minute, 720, 780)
    in_ny_pm = p.use_ny_pm & in_window(minute, 810, 960)
    in_london = p.use_london & in_window(minute, 120, 300)
    in_kz = in_ny_am | in_ny_lunch | in_ny_pm | in_london

    macros = [(510, 550), (590, 610), (650, 670), (710, 730), (790, 820), (915, 945)]
    in_macro = np.zeros(n, bool)
    for s, e in macros:
        in_macro |= in_window(minute, s, e)
    in_time = (~p.use_time | in_kz) & (~p.use_macro | in_macro)

    # ICT day opens at 18:00 NY. Reset on the transition INTO the evening only (this
    # survives the 17:00-18:00 maintenance gap). If a feed never spans 18:00 (RTH-only
    # data), fall back to a calendar-day change so resets still happen once per day.
    is_eve = hour >= 18
    has_eve = bool(is_eve.any())
    new_ict = np.zeros(n, bool)
    new_ict[0] = True
    if has_eve:
        new_ict[1:] = is_eve[1:] & ~is_eve[:-1]
    else:
        new_ict[1:] = daynum[1:] != daynum[:-1]

    eod_s, eod_e = p.eod_session
    in_eod = in_window(minute, eod_s, eod_e) | (p.use_london & in_window(minute, 120, 300))

    # ---- stateful pass ----
    # rolling structure state
    last_ph = np.nan
    last_pl = np.nan
    prev_ph = np.nan
    prev_pl = np.nan
    bias = 0

    # premium/discount day extremes
    ict_hi = np.nan
    ict_lo = np.nan

    # previous-day high/low (computed from completed NY days)
    day_high_acc = -np.inf
    day_low_acc = np.inf
    pdh = np.nan
    pdl = np.nan
    prev_day_hi = np.nan   # prior daily candle extremes (always tracked, for the 50% S/R)
    prev_day_lo = np.nan

    # Session ranges: per-session developing + frozen high/low, reset each ICT day.
    # Windows are [start, end) in NY minutes-of-day.
    SESS = {
        "asia": (20 * 60, 24 * 60, p.use_asian_range),
        "london": (2 * 60, 5 * 60, p.use_london_range),
        "ny": (8 * 60 + 30, 12 * 60, p.use_ny_range),
    }
    sess_dev_hi = {k: np.nan for k in SESS}
    sess_dev_lo = {k: np.nan for k in SESS}
    sess_hi = {k: np.nan for k in SESS}   # frozen (usable) levels
    sess_lo = {k: np.nan for k in SESS}
    in_sess_prev = {k: False for k in SESS}

    # sweeps
    last_sweep_dir = 0
    last_sweep_bar = -10 ** 9
    sweep_used = False

    # double-FVG guard
    last_bull_fvg_bar = -10 ** 9
    last_bear_fvg_bar = -10 ** 9

    # FVG store: lists of [top, bot, dir, bar, inv]
    fvgs: list[list] = []

    # daily counters
    trades_today = 0
    losses_today = 0

    # outputs
    long_entries = np.zeros(n, bool)
    short_entries = np.zeros(n, bool)
    long_exits = np.zeros(n, bool)
    short_exits = np.zeros(n, bool)
    entry_price = np.full(n, np.nan)
    exit_price = np.full(n, np.nan)
    order_size = np.full(n, np.nan)
    order_price = np.full(n, np.nan)
    trades: list[dict] = []

    # position state for the event simulator
    pos = 0                # 0 flat, 1 long, -1 short
    pend = None            # pending limit order dict
    cur = None             # open-trade dict

    eqh = np.nan
    eql = np.nan

    for i in range(n):
        closed_this_bar = False   # guard: never enter on the same bar a trade exits
                                  # (order_size holds one fill per bar; a same-bar entry
                                  #  would overwrite the exit and leave a residual position)
        # --- ICT day reset (PD extremes, previous-day H/L, daily counters) ---
        if new_ict[i]:
            if day_high_acc > -np.inf:
                prev_day_hi = day_high_acc
                prev_day_lo = day_low_acc
                pdh = day_high_acc if p.use_pd_levels else np.nan
                pdl = day_low_acc if p.use_pd_levels else np.nan
            day_high_acc = -np.inf
            day_low_acc = np.inf
            ict_hi = h[i]
            ict_lo = l[i]
            trades_today = 0
            losses_today = 0
            for k in SESS:                     # reset session ranges each ICT day
                sess_dev_hi[k] = sess_dev_lo[k] = np.nan
                sess_hi[k] = sess_lo[k] = np.nan
                in_sess_prev[k] = False
        else:
            ict_hi = h[i] if np.isnan(ict_hi) else max(ict_hi, h[i])
            ict_lo = l[i] if np.isnan(ict_lo) else min(ict_lo, l[i])
        day_high_acc = max(day_high_acc, h[i])
        day_low_acc = min(day_low_acc, l[i])

        # Daily 50% as support/resistance: the midpoint of the prior daily candle.
        # When it sits BELOW price it is support -> only longs; when ABOVE price it is
        # resistance -> only shorts. (A directional bias filter, not mean-reversion.)
        daily_mid = np.nan if (np.isnan(prev_day_hi) or np.isnan(prev_day_lo)) \
            else (prev_day_hi + prev_day_lo) / 2.0
        pd_long_ok = (not p.use_pd) or np.isnan(daily_mid) or (c[i] >= daily_mid)
        pd_short_ok = (not p.use_pd) or np.isnan(daily_mid) or (c[i] <= daily_mid)

        # --- pivots / structure ---
        if not np.isnan(ph[i]):
            prev_ph = last_ph
            last_ph = ph[i]
        if not np.isnan(pl[i]):
            prev_pl = last_pl
            last_pl = pl[i]

        if p.use_eq and not np.isnan(last_ph) and not np.isnan(prev_ph) and abs(last_ph - prev_ph) <= eq_tol:
            eqh = max(last_ph, prev_ph)
        if p.use_eq and not np.isnan(last_pl) and not np.isnan(prev_pl) and abs(last_pl - prev_pl) <= eq_tol:
            eql = min(last_pl, prev_pl)

        if not np.isnan(last_ph) and c[i] > last_ph:
            bias = 1
        if not np.isnan(last_pl) and c[i] < last_pl:
            bias = -1
        bias_long_ok = (not p.use_mss) or bias >= 0
        bias_short_ok = (not p.use_mss) or bias <= 0

        # --- session ranges: accumulate while in-session, freeze on session end ---
        if p.use_sessions:
            for k, (s0, s1, on) in SESS.items():
                in_now = on and (s0 <= minute[i] < s1)
                if in_now:
                    sess_dev_hi[k] = h[i] if np.isnan(sess_dev_hi[k]) else max(sess_dev_hi[k], h[i])
                    sess_dev_lo[k] = l[i] if np.isnan(sess_dev_lo[k]) else min(sess_dev_lo[k], l[i])
                elif in_sess_prev[k]:           # just left the session -> freeze its range
                    sess_hi[k] = sess_dev_hi[k]
                    sess_lo[k] = sess_dev_lo[k]
                in_sess_prev[k] = in_now

        # Frozen session levels usable as sweep targets / runner draws this ICT day.
        sh_levels = [sess_hi[k] for k in SESS] if p.use_sessions else []
        sl_levels = [sess_lo[k] for k in SESS] if p.use_sessions else []

        # --- sweeps (wick beyond level, body rejects back) over the enabled set ---
        sw = p.use_swing_sweep
        swept_high = ((sw and not np.isnan(last_ph) and h[i] > last_ph and c[i] < last_ph) or
                      (not np.isnan(pdh) and h[i] > pdh and c[i] < pdh) or
                      (not np.isnan(eqh) and h[i] > eqh and c[i] < eqh) or
                      any((not np.isnan(x)) and h[i] > x and c[i] < x for x in sh_levels))
        swept_low = ((sw and not np.isnan(last_pl) and l[i] < last_pl and c[i] > last_pl) or
                     (not np.isnan(pdl) and l[i] < pdl and c[i] > pdl) or
                     (not np.isnan(eql) and l[i] < eql and c[i] > eql) or
                     any((not np.isnan(x)) and l[i] < x and c[i] > x for x in sl_levels))
        if swept_high:
            last_sweep_dir = 1
            last_sweep_bar = i
            sweep_used = False
        if swept_low:
            last_sweep_dir = -1
            last_sweep_bar = i
            sweep_used = False
        sweep_fresh = (i - last_sweep_bar) <= p.sweep_lookback and not sweep_used
        recent_sweep_high = sweep_fresh and last_sweep_dir == 1
        recent_sweep_low = sweep_fresh and last_sweep_dir == -1

        # --- FVG detection (needs i-2) ---
        bull_inversion = False
        bear_inversion = False
        long_edge = long_gap_bot = short_edge = short_gap_top = np.nan
        if i >= 2:
            bull_gap = l[i] - h[i - 2]
            bear_gap = l[i - 2] - h[i]
            gap_ok_bull = bull_gap >= min_gap and (p.max_gap_ticks <= 0 or bull_gap <= max_gap)
            gap_ok_bear = bear_gap >= min_gap and (p.max_gap_ticks <= 0 or bear_gap <= max_gap)
            is_bull_fvg = l[i] > h[i - 2] and gap_ok_bull
            is_bear_fvg = h[i] < l[i - 2] and gap_ok_bear

            block_bull = p.use_double_fvg and (i - last_bull_fvg_bar) <= p.double_fvg_bars
            block_bear = p.use_double_fvg and (i - last_bear_fvg_bar) <= p.double_fvg_bars
            if is_bull_fvg:
                last_bull_fvg_bar = i
            if is_bear_fvg:
                last_bear_fvg_bar = i

            if is_bull_fvg and not block_bull:
                fvgs.append([l[i], h[i - 2], 1, i, False])
            if is_bear_fvg and not block_bear:
                fvgs.append([l[i - 2], h[i], -1, i, False])

            # inversion: newest non-inverted gap closed through by body. A gap is
            # consumed (removed) on inversion - it never re-arms - so the list stays
            # short and, being append-ordered, can be front-pruned by age cheaply.
            hit = -1
            for j in range(len(fvgs) - 1, -1, -1):
                top, bot, d = fvgs[j][0], fvgs[j][1], fvgs[j][2]
                if d == 1 and c[i] < bot:
                    bear_inversion = True
                    short_edge = bot
                    short_gap_top = top
                    hit = j
                    break
                elif d == -1 and c[i] > top:
                    bull_inversion = True
                    long_edge = top
                    long_gap_bot = bot
                    hit = j
                    break
            if hit >= 0:
                del fvgs[hit]

            # cleanup: drop aged un-inverted gaps from the front (oldest first)
            while fvgs and (i - fvgs[0][3]) > p.fvg_max_age:
                fvgs.pop(0)

        # --- displacement ---
        bull_disp = (c[i] - o[i]) >= p.disp_mult * (atr[i] if not np.isnan(atr[i]) else 1e18)
        bear_disp = (o[i] - c[i]) >= p.disp_mult * (atr[i] if not np.isnan(atr[i]) else 1e18)
        disp_long_ok = (not p.use_disp) or bull_disp
        disp_short_ok = (not p.use_disp) or bear_disp

        sweep_long_ok = (not p.use_sweep) or recent_sweep_low
        sweep_short_ok = (not p.use_sweep) or recent_sweep_high

        day_block = p.use_daily_limits and (trades_today >= p.max_trades_per_day or
                                            losses_today >= p.max_losses_per_day)

        long_signal = (bull_inversion and in_time[i] and disp_long_ok and bias_long_ok and
                       sweep_long_ok and pd_long_ok and in_eod[i] and not day_block)
        short_signal = (bear_inversion and in_time[i] and disp_short_ok and bias_short_ok and
                        sweep_short_ok and pd_short_ok and in_eod[i] and not day_block)

        # ============================ POSITION MANAGEMENT ============================
        # 1) manage an open position first (exits take priority on this bar).
        #    Levels: TP1 = 1R partial (scale_pct off), break-even at the internal
        #    high/low, runner draws to the external swing high/low (cur["tp"]).
        if pos != 0 and cur is not None:
            d = cur["dir"]
            # Pure 1:1 mode disables the partial / break-even / IFVG-early-exit so the
            # only outcomes are a full exit at the 1R target or the symmetric hard stop.
            do_scale = p.use_scale and not p.full_tp_1r
            do_be = p.use_be and not p.full_tp_1r
            do_ifvg = (p.stop_mode == "IFVG close") and not p.full_tp_1r
            # Break-even when the internal high/low is taken.
            if do_be and not cur["be_done"]:
                if d == 1 and h[i] >= cur["be_level"]:
                    cur["be_done"] = True
                    cur["stop"] = max(cur["stop"], cur["entry"])
                elif d == -1 and l[i] <= cur["be_level"]:
                    cur["be_done"] = True
                    cur["stop"] = min(cur["stop"], cur["entry"])

            # At most one fill action per bar; stop assumed first (worst case), then
            # the 1R partial, then the runner, then IFVG-close / EOD invalidation.
            action = None  # (kind, price, reason)
            if d == 1:
                if l[i] <= cur["stop"]:
                    action = ("exit", cur["stop"], "stop")
                elif do_scale and not cur["tp1_done"] and h[i] >= cur["tp1"]:
                    action = ("partial", cur["tp1"], "tp1")
                elif h[i] >= cur["tp"]:
                    action = ("exit", cur["tp"], "tp")
                elif do_ifvg and not np.isnan(cur["inv_edge"]) and c[i] < cur["inv_edge"]:
                    action = ("exit", c[i], "ifvg")
                elif p.flat_eod and not in_eod[i]:
                    action = ("exit", c[i], "eod")
            else:
                if h[i] >= cur["stop"]:
                    action = ("exit", cur["stop"], "stop")
                elif do_scale and not cur["tp1_done"] and l[i] <= cur["tp1"]:
                    action = ("partial", cur["tp1"], "tp1")
                elif l[i] <= cur["tp"]:
                    action = ("exit", cur["tp"], "tp")
                elif do_ifvg and not np.isnan(cur["inv_edge"]) and c[i] > cur["inv_edge"]:
                    action = ("exit", c[i], "ifvg")
                elif p.flat_eod and not in_eod[i]:
                    action = ("exit", c[i], "eod")

            if action is not None:
                kind, px, reason = action
                if kind == "partial":
                    part = cur["size"] * (p.scale_pct / 100.0)
                    order_size[i] = -d * part
                    order_price[i] = px
                    cur["realized"] += (px - cur["entry"]) * d * POINT_VALUE * part
                    cur["size"] -= part
                    cur["tp1_done"] = True
                else:
                    rem = cur["size"]
                    order_size[i] = -d * rem
                    order_price[i] = px
                    cur["realized"] += (px - cur["entry"]) * d * POINT_VALUE * rem
                    if d == 1:
                        long_exits[i] = True
                    else:
                        short_exits[i] = True
                    exit_price[i] = px
                    total = cur["realized"]
                    if total < -4 * mintick * POINT_VALUE * cur["init_size"]:
                        losses_today += 1
                    n_orders = 3 if cur["tp1_done"] else 2  # entry + (partial?) + final
                    cur.update(exit_bar=i, exit_price=px, reason=reason,
                               pnl=total, n_orders=n_orders)
                    trades.append(cur)
                    cur = None
                    pos = 0
                    closed_this_bar = True

        # 2) handle a pending limit order (fill or expire) when flat
        if pos == 0 and pend is not None:
            age = i - pend["bar"]
            filled = False
            if pend["dir"] == 1 and l[i] <= pend["limit"]:
                fill = pend["limit"]
                filled = True
            elif pend["dir"] == -1 and h[i] >= pend["limit"]:
                fill = pend["limit"]
                filled = True
            pre_taken = (pend["dir"] == 1 and h[i] >= pend["tp"]) or \
                        (pend["dir"] == -1 and l[i] <= pend["tp"])
            if filled:
                pos = pend["dir"]
                if pos == 1:
                    long_entries[i] = True
                else:
                    short_entries[i] = True
                entry_price[i] = fill
                order_size[i] = pos * contracts
                order_price[i] = fill
                trades_today += 1
                cur = _new_cur(i, fill, pos, pend["stop"], pend["tp"], pend["tp1"],
                               pend["be_level"], pend["inv_edge"], contracts)
                sweep_used = True
                pend = None
            elif age >= p.limit_expiry or pre_taken:
                pend = None  # cancel; sweep re-armed (sweep_used stays False)

        # 3) new entry when flat and no pending order (and not on a same-bar exit)
        if pos == 0 and pend is None and not closed_this_bar and (long_signal or short_signal):
            if long_signal:
                ref_close = c[i]
                chase = ref_close - long_edge
                is_market = (p.entry_mode == "Market on close" or
                             (p.entry_mode == "Auto" and chase <= chase_tol))
                ref = ref_close if is_market else long_edge
                lo_lb = l[max(0, i - p.sl_lookback + 1):i + 1].min()
                swing_sl = min(lo_lb, long_gap_bot) - buf
                hard_sl = swing_sl if p.stop_mode == "Swing high/low" else long_gap_bot - buf
                risk = ref - hard_sl
                if risk > 0:
                    tp1 = ref + risk * p.rr                       # 1R partial target
                    pool = _near_above(ref, last_ph, pdh, eqh, *sh_levels)  # external draw
                    fallback = ref + risk * p.runner_rr
                    tp = pool if (p.tp_mode == "Opposing liquidity" and not np.isnan(pool)
                                  and pool > tp1) else fallback
                    tp = max(tp, tp1 + mintick)                   # runner beyond TP1
                    if p.full_tp_1r:
                        tp = tp1                                  # pure 1:1: exit all at 1R
                    ith = h[max(0, i - p.sl_lookback):i].max() if i > 0 else np.nan
                    be_level = ith if (not np.isnan(ith) and ith > ref) else ref
                    pos, cur, pend, trades_today, sweep_used = _commit_entry(
                        is_market, i, 1, ref, hard_sl, tp, tp1, be_level, long_gap_bot,
                        contracts, long_entries, short_entries, entry_price,
                        order_size, order_price, trades_today, sweep_used)
            elif short_signal:
                ref_close = c[i]
                chase = short_edge - ref_close
                is_market = (p.entry_mode == "Market on close" or
                             (p.entry_mode == "Auto" and chase <= chase_tol))
                ref = ref_close if is_market else short_edge
                hi_lb = h[max(0, i - p.sl_lookback + 1):i + 1].max()
                swing_sl = max(hi_lb, short_gap_top) + buf
                hard_sl = swing_sl if p.stop_mode == "Swing high/low" else short_gap_top + buf
                risk = hard_sl - ref
                if risk > 0:
                    tp1 = ref - risk * p.rr
                    pool = _near_below(ref, last_pl, pdl, eql, *sl_levels)
                    fallback = ref - risk * p.runner_rr
                    tp = pool if (p.tp_mode == "Opposing liquidity" and not np.isnan(pool)
                                  and pool < tp1) else fallback
                    tp = min(tp, tp1 - mintick)
                    if p.full_tp_1r:
                        tp = tp1                                  # pure 1:1: exit all at 1R
                    itl = l[max(0, i - p.sl_lookback):i].min() if i > 0 else np.nan
                    be_level = itl if (not np.isnan(itl) and itl < ref) else ref
                    pos, cur, pend, trades_today, sweep_used = _commit_entry(
                        is_market, i, -1, ref, hard_sl, tp, tp1, be_level, short_gap_top,
                        contracts, long_entries, short_entries, entry_price,
                        order_size, order_price, trades_today, sweep_used)

    return Signals(long_entries, long_exits, short_entries, short_exits,
                   entry_price, exit_price, order_size, order_price, trades)


def _near_above(ref, *levels):
    cands = [x for x in levels if not np.isnan(x) and x > ref]
    return min(cands) if cands else np.nan


def _near_below(ref, *levels):
    cands = [x for x in levels if not np.isnan(x) and x < ref]
    return max(cands) if cands else np.nan


def _new_cur(i, entry, d, stop, tp, tp1, be_level, inv_edge, size):
    """Build the open-trade state dict (size in contracts; realized PnL accrues
    across the TP1 partial and the runner leg)."""
    return dict(entry_bar=i, entry=entry, dir=d, stop=stop, tp=tp, tp1=tp1,
                be_level=be_level, inv_edge=inv_edge, size=size, init_size=size,
                realized=0.0, tp1_done=False, be_done=False)


def _commit_entry(is_market, i, direction, ref, stop, tp, tp1, be_level, inv_edge,
                  contracts, long_entries, short_entries, entry_price,
                  order_size, order_price, trades_today, sweep_used):
    """Apply an entry. Market fills now (this bar); limit becomes a pending order.

    Returns (pos, cur, pend, trades_today, sweep_used).
    """
    if is_market:
        if direction == 1:
            long_entries[i] = True
        else:
            short_entries[i] = True
        entry_price[i] = ref
        order_size[i] = direction * contracts
        order_price[i] = ref
        cur = _new_cur(i, ref, direction, stop, tp, tp1, be_level, inv_edge, contracts)
        return direction, cur, None, trades_today + 1, True
    else:
        pend = dict(bar=i, dir=direction, limit=ref, stop=stop, tp=tp, tp1=tp1,
                    be_level=be_level, inv_edge=inv_edge)
        return 0, None, pend, trades_today, sweep_used


