"""The ATR-normalised phase momentum + session-VWAP strategy, as an executable order model.

This is the module the Pine header cites. It exists so that the Pine port, the NinjaScript source
and every test in this directory are scored against ONE definition of the strategy rather than
three, and so that the counts quoted in the Pine header are a regression test rather than a claim.

WHAT IS PORTED, AND WHY IT IS PORTED THIS WAY

  DECISION BAR   exact UTC-aligned 10-minute buckets built from ten CONTIGUOUS one-minute
                 components. The NinjaScript source omits any bucket missing a minute; that is
                 reproduced here and the drop count is reported rather than assumed to be zero.

  OSCILLATOR     phase = EMA3( 100 * (close - EMA21) / (3 * ATR14) ), with the source's seeds:
                 EMA21 seeded at the first close, ATR14 seeded as the mean of the first 14 true
                 ranges and then Wilder-smoothed, EMA3 seeded at the first raw value. These are
                 NOT ta.ema / ta.atr and NOT `indicators.ema` -- a different seed moves the first
                 few hundred bars and therefore moves which crosses exist at all.

  DECISION       the cross is read on the COMPLETED bar; the order fills at the NEXT decision
                 bar's open. Nothing in this file reads a value at the fill bar. See CLAUDE.md on
                 `ent_bar` -- that mistake produced a p=0.0005 holdout result here once already,
                 and section 1 of the battery re-checks it mechanically rather than trusting this
                 paragraph.

  ADMISSION      the completed signal bar's close must sit strictly within 2.5 x ATR14 of the
                 session HLC3-volume VWAP, which accumulates over decision bars OPENING inside the
                 VWAP window, the signal bar included.

  SHADOW         the unfiltered rule keeps its own position; the filtered position is that shadow
                 gated by VWAP admission at entry time. A cross to the side the shadow already
                 holds is a no-op even when the real position is flat.

Costs are MNQ: $2.00 a point, 0.25 tick, $0.72 per contract per side, one tick of slippage on each
fill, exactly as the Pine `strategy()` call declares them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NY = "America/New_York"
SRC = os.environ.get("APM_SRC", "data/NQ_1m.csv")

# MNQ, as declared in the Pine strategy() call.
PV = 2.0          # dollars per index point
TICK = 0.25       # minimum price increment
COMM = 0.72       # dollars per contract per side
SLIP_T = 1.0      # ticks of slippage per fill

# The source's frozen 68-date MNQ incomplete-session calendar, applied through 2026-08-17.
FROZEN = np.array([
    20200120, 20200217, 20200309, 20200312, 20200313, 20200316, 20200318, 20200525, 20200611,
    20200703, 20200907, 20200910, 20201126, 20201127, 20201224, 20210118, 20210215, 20210402,
    20210531, 20210705, 20210906, 20211125, 20211126, 20220117, 20220221, 20220530, 20220620,
    20220704, 20220905, 20221124, 20221125, 20230116, 20230220, 20230407, 20230529, 20230619,
    20230703, 20230704, 20230904, 20231123, 20231124, 20240115, 20240219, 20240527, 20240619,
    20240703, 20240704, 20240902, 20241128, 20241129, 20241224, 20250109, 20250120, 20250217,
    20250526, 20250619, 20250703, 20250704, 20250901, 20251127, 20251128, 20251224, 20260119,
    20260216, 20260403, 20260525, 20260619, 20260703], dtype=np.int64)
FROZEN_END = 20260817


@dataclass(frozen=True)
class Profile:
    """Session clocks in minutes since New York midnight, as the source defines them."""
    name: str = "USIndex"
    ent_start: int = 570      # 09:30 inclusive, on the FILL minute
    ent_end: int = 660        # 11:00 exclusive
    vwap_start: int = 570     # 09:30 inclusive, on the bar OPEN minute
    vwap_end: int = 960       # 16:00 exclusive
    cash: int = 960           # 16:00
    eth: int = 1080           # 18:00 -- the session date rolls here
    tf: int = 10

    @property
    def relevant_first(self) -> int:
        return min(self.vwap_start, self.ent_start - self.tf)

    @property
    def required(self) -> int:
        return (self.cash - self.relevant_first) // self.tf


US_INDEX = Profile()
COMEX_GOLD = Profile("ComexGold", 500, 590, 500, 810, 810, 1080, 10)


@dataclass
class Params:
    """Every knob the strategy has. The battery sweeps these; the ship setting is the default."""
    ema_len: int = 21
    atr_len: int = 14
    osc_len: int = 3
    atr_den: float = 3.0
    upper: float = 100.0
    lower: float = -100.0
    vwap_mult: float = 2.5
    reset_ticks: int = 400
    post_reset_bars: int = 21
    use_frozen: bool = False   # an MNQ-specific data-quality list; off for any other feed
    use_backstop: bool = True
    profile: Profile = field(default_factory=lambda: US_INDEX)


# --------------------------------------------------------------------------- data

def load_1m(path: str = SRC) -> dict:
    """The canonical export: timestamp,open,high,low,close,volume, UTC ISO-8601, ascending."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} is absent. Bar files are git-ignored (data/README.md); rebuild it with "
            f"scripts/quant-ingest.ts from the raw 1-minute source, or point APM_SRC at it.")
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    tcol = next(cols[k] for k in cols if "time" in k or k == "t" or "date" in k)
    ts = pd.to_datetime(df[tcol], utc=True)
    out = dict(
        ts=ts.to_numpy("datetime64[ns]").astype(np.int64),
        o=df[cols["open"]].to_numpy(float), h=df[cols["high"]].to_numpy(float),
        l=df[cols["low"]].to_numpy(float), c=df[cols["close"]].to_numpy(float),
        v=df[cols["volume"]].to_numpy(float))
    order = np.argsort(out["ts"], kind="stable")
    return {k: v[order] for k, v in out.items()}


def decision_bars(m1: dict, tf: int = 10, require_full: bool = True) -> dict:
    """Exact UTC-aligned `tf`-minute buckets from contiguous one-minute components.

    The source builds each bucket from ten consecutive one-minute bars and omits any bucket that
    is short one. `require_full=False` keeps partial buckets, which is what a TradingView chart
    bar actually is -- the difference between the two is measured, not assumed."""
    step = tf * 60_000_000_000
    key = m1["ts"] // step
    # Reduce over EVERY bucket boundary first, then drop: reduceat runs each segment to the next
    # start, so filtering the starts before reducing would silently merge a dropped bucket into
    # its neighbour.
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    ends = np.r_[starts[1:], len(key)]
    cnt = ends - starts
    o = m1["o"][starts]
    c = m1["c"][ends - 1]
    h = np.maximum.reduceat(m1["h"], starts)
    lo = np.minimum.reduceat(m1["l"], starts)
    vv = np.add.reduceat(m1["v"], starts)
    ts = key[starts] * step
    keep = np.ones(len(starts), bool) if not require_full else (cnt == tf)
    o, c, h, lo, vv, ts = o[keep], c[keep], h[keep], lo[keep], vv[keep], ts[keep]
    idx = pd.DatetimeIndex(pd.to_datetime(ts, utc=True)).tz_convert(NY)
    d = dict(ts=ts, o=o, h=h, l=lo, c=c, v=vv,
             mod=(idx.hour * 60 + idx.minute).to_numpy(np.int64),
             ymd=(idx.year * 10000 + idx.month * 100 + idx.day).to_numpy(np.int64),
             n=len(o), dropped=int((~keep).sum()), n_partial=int((cnt[keep] != tf).sum()))
    nxt = pd.DatetimeIndex(pd.to_datetime(ts + 86_400_000_000_000, utc=True)).tz_convert(NY)
    d["ymd_next"] = (nxt.year * 10000 + nxt.month * 100 + nxt.day).to_numpy(np.int64)
    return d


# --------------------------------------------------------------------------- the strategy

@dataclass
class Result:
    trades: pd.DataFrame
    diag: dict
    osc: np.ndarray          # the oscillator as of each bar's CLOSE (nan before it exists)
    vwap: np.ndarray         # session VWAP as of each bar's close, nan outside the window
    dist: np.ndarray         # |close - vwap| / ATR14 at the signal bar
    admit: np.ndarray        # the admission test, evaluated on every in-window bar
    atr: np.ndarray
    ema: np.ndarray
    blocked: np.ndarray      # per bar: was its session blocked
    intents: pd.DataFrame    # every cross, admitted or not -- the population the filter selects from


def simulate(d: dict, p: Params | None = None, start_date: int = 20200203,
             costs: bool = True, comm: float = COMM, slip_t: float = SLIP_T,
             pv: float = PV, tick: float = TICK,
             fill_shift: int = 1, seed_noise: np.ndarray | None = None,
             drop_p: float = 0.0, noise_seed: int = 0) -> Result:
    """Transliteration of the Pine, bar by bar, with the same fail-open anomaly handling.

    `fill_shift` is the number of decision bars between the completed signal bar and the fill.
    It is 1 -- the source's market order after the completed bar. Section 1 of the battery re-runs
    with 0 to show what same-bar execution would have been worth, which is the size of the
    look-ahead this design is exposed to if the order model is ever got wrong.

    `seed_noise` is a per-bar additive price perturbation in POINTS, used by the execution-noise
    and data-jitter tests; it is applied to the fill price only, never to the decision. `drop_p` is
    the probability that a submitted ENTRY never fills, which is what a rejected or unfilled order
    looks like to the strategy -- exits are never dropped, because a real desk keeps trying."""
    _nrng = np.random.default_rng(noise_seed)
    p = p or Params()
    pf = p.profile
    n = d["n"]
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    mod, ymd, ymd_next, ts = d["mod"], d["ymd"], d["ymd_next"], d["ts"]
    tf = pf.tf
    aE = 2.0 / (p.ema_len + 1.0)
    aO = 2.0 / (p.osc_len + 1.0)
    close_mod = mod + tf
    sess_key = np.where(mod >= pf.eth, ymd_next, ymd)
    in_vwap = (mod >= pf.vwap_start) & (mod < pf.vwap_end)
    in_fill = (close_mod >= pf.ent_start) & (close_mod < pf.ent_end)
    frozen = set(FROZEN[FROZEN <= FROZEN_END].tolist()) if p.use_frozen else set()

    osc_out = np.full(n, np.nan); vwap_out = np.full(n, np.nan)
    dist_out = np.full(n, np.nan); admit_out = np.zeros(n, bool)
    atr_out = np.full(n, np.nan); ema_out = np.full(n, np.nan)
    blocked_out = np.zeros(n, bool)

    cur_sess = None; sess_blocked = False; cash_done = False
    exp_open = 0; req_count = 0; halted = False
    ema = np.nan; atr = np.nan; prev_c = np.nan
    tr_n = 0; tr_sum = 0.0
    osc = np.nan; osc_init = False
    seg_bar = 0; post_reset = False
    shadow = 0
    vwap_day = None; cum_pv = 0.0; cum_v = 0.0

    pos = 0; entry_i = -1; entry_px = np.nan
    pending = None                      # ('entry', side) | ('exit', reason) resolved at a later open
    trades = []; intents = []
    diag = dict(decision=0, sessions=0, blocked=0, resets=0, longs=0, shorts=0, reversals=0,
                opp_exits=0, cash_exits=0, admitted=0, rejected=0, unavailable=0,
                reject_rev=0, anomalies=0, backstop_exits=0, carries=0, dropped_orders=0,
                last_anom="-")

    def fill_px(i, side, at_close=False):
        base = c[i] if at_close else o[i]
        px = base + (0.0 if seed_noise is None else seed_noise[i])
        return px + side * slip_t * tick if costs else px

    def close_trade(i, reason, at_close=False):
        nonlocal pos, entry_i, entry_px
        px = fill_px(i, -pos, at_close=at_close)
        gross = pos * (px - entry_px) * pv
        net = gross - (2.0 * comm if costs else 0.0)
        trades.append(dict(entry_i=entry_i, exit_i=i, side=pos,
                           entry_ts=ts[entry_i], exit_ts=ts[i],
                           entry_px=entry_px, exit_px=px, reason=reason,
                           gross=gross, net=net, bars=i - entry_i,
                           sess=int(sess_key[entry_i]), ymd=int(ymd[entry_i]),
                           mod_entry=int(mod[entry_i])))
        pos = 0; entry_i = -1; entry_px = np.nan

    def resolve(i, at_close=False):
        """Fill whatever is standing, at this bar's open (normal) or close (fill_shift=0)."""
        nonlocal pos, entry_i, entry_px, pending
        if pending is None or pending[2] > i:
            return
        kind, arg, _ = pending
        pending = None
        if kind == "exit":
            if pos != 0:
                close_trade(i, arg, at_close=at_close)
        else:
            if drop_p > 0.0 and _nrng.random() < drop_p:
                diag["dropped_orders"] += 1
                return
            if pos != 0:
                close_trade(i, "reverse", at_close=at_close)
            pos = arg; entry_i = i; entry_px = fill_px(i, arg, at_close=at_close)

    for i in range(n):
        # ---- resolve orders standing from an earlier bar, at THIS bar's open
        resolve(i)
        prev_pos = pos

        if halted:
            continue

        # ---- session boundary (the source's BeginSession)
        sk = int(sess_key[i])
        if cur_sess is None or sk != cur_sess:
            carried = pos != 0 or shadow != 0
            cur_sess = sk
            diag["sessions"] += 1
            sess_blocked = p.use_frozen and sk <= FROZEN_END and sk in frozen
            if sess_blocked:
                diag["blocked"] += 1
            cash_done = False
            exp_open = pf.relevant_first
            req_count = 0
            if carried:
                diag["anomalies"] += 1; diag["carries"] += 1
                diag["last_anom"] = f"session carry {sk}"
                shadow = 0
                if pos != 0:
                    pending = ("exit", "carry", i + fill_shift)

        # ---- cash-window completeness, at decision-bar level
        if not sess_blocked:
            m = int(mod[i])
            if pf.relevant_first <= m < pf.cash:
                if m != exp_open:
                    sess_blocked = True; diag["blocked"] += 1; diag["anomalies"] += 1
                    diag["last_anom"] = f"gap {sk} expected {exp_open} got {m}"
                else:
                    req_count += 1; exp_open += tf
            elif pf.cash <= m < pf.eth and req_count != pf.required:
                sess_blocked = True; diag["blocked"] += 1; diag["anomalies"] += 1
                diag["last_anom"] = f"short window {sk} {req_count}/{pf.required}"
            if sess_blocked:
                shadow = 0
                if pos != 0:
                    pending = ("exit", "data gap", i + fill_shift)
        blocked_out[i] = sess_blocked
        if sess_blocked:
            continue

        # ---- roll-like reset at the 00:00 UTC open
        if p.reset_ticks > 0 and i > 0 and (ts[i] - ts[i - 1]) == tf * 60_000_000_000 \
                and (ts[i] % 86_400_000_000_000) == 0 \
                and abs(o[i] - c[i - 1]) > p.reset_ticks * tick:
            if pos != 0 or shadow != 0:
                diag["anomalies"] += 1
                diag["last_anom"] = f"reset with exposure {sk}"
                if pos != 0:
                    pending = ("exit", "reset", i + fill_shift)
            ema = atr = prev_c = np.nan
            tr_n = 0; tr_sum = 0.0
            osc = np.nan; osc_init = False; seg_bar = 0
            post_reset = True; shadow = 0
            vwap_day = None; cum_pv = cum_v = 0.0
            diag["resets"] += 1

        # ---- the indicator, on every decision bar of a non-blocked session
        osc_prev = osc; osc_prev_avail = osc_init
        ema = c[i] if np.isnan(ema) else aE * c[i] + (1.0 - aE) * ema
        trng = (h[i] - l[i]) if np.isnan(prev_c) else max(
            h[i] - l[i], abs(h[i] - prev_c), abs(l[i] - prev_c))
        prev_c = c[i]
        if np.isnan(atr):
            tr_n += 1; tr_sum += trng
            if tr_n == p.atr_len:
                atr = tr_sum / p.atr_len
        else:
            atr = ((p.atr_len - 1.0) * atr + trng) / p.atr_len
        osc_avail = False
        if not np.isnan(atr) and atr > 0:
            raw = 100.0 * (c[i] - ema) / (p.atr_den * atr)
            osc = aO * raw + (1.0 - aO) * osc if osc_init else raw
            osc_init = True; osc_avail = True
        ema_out[i] = ema; atr_out[i] = atr
        if osc_avail:
            osc_out[i] = osc

        # ---- session HLC3-volume VWAP over bars OPENING inside the window
        vwap_avail = False; admitted = False
        if in_vwap[i]:
            if vwap_day is None or vwap_day != int(ymd[i]):
                vwap_day = int(ymd[i]); cum_pv = cum_v = 0.0
            hlc3 = (h[i] + l[i] + c[i]) / 3.0
            cum_pv += hlc3 * v[i]; cum_v += v[i]
            if cum_v > 0 and not np.isnan(atr) and atr > 0:
                vwap_avail = True
                vw = cum_pv / cum_v
                vwap_out[i] = vw
                dist_out[i] = abs(c[i] - vw) / atr
                admitted = abs(c[i] - vw) < p.vwap_mult * atr
        admit_out[i] = admitted
        seg_bar += 1
        diag["decision"] += 1

        # ---- cash close outranks a simultaneous cross
        if close_mod[i] == pf.cash:
            shadow = 0
            if not cash_done:
                cash_done = True
                if pos != 0:
                    diag["cash_exits"] += 1
                    pending = ("exit", "cash close", i + fill_shift)
        elif (not cash_done and sk >= start_date and osc_prev_avail and osc_avail
              and not (post_reset and seg_bar < p.post_reset_bars)):
            long_x = osc_prev <= p.upper and osc > p.upper
            short_x = osc_prev >= p.lower and osc < p.lower
            if long_x or short_x:
                side = 1 if long_x else -1
                prior = shadow
                if prior != side:
                    rec = dict(i=i, ts=ts[i], side=side, admitted=bool(admitted),
                               dist=dist_out[i], in_fill=bool(in_fill[i]), prior=prior,
                               mod=int(mod[i]), ymd=int(ymd[i]), sess=sk,
                               osc=osc, osc_prev=osc_prev, atr=atr, close=c[i],
                               pos_before=prev_pos)
                    if prior == 0:
                        if in_fill[i]:
                            shadow = side
                            intents.append(rec)
                            if admitted:
                                diag["admitted"] += 1
                                diag["longs" if side == 1 else "shorts"] += 1
                                pending = ("entry", side, i + fill_shift)
                            else:
                                diag["rejected"] += 1
                                if not vwap_avail:
                                    diag["unavailable"] += 1
                    elif not in_fill[i]:
                        shadow = 0
                        if pos == prior:
                            diag["opp_exits"] += 1
                            pending = ("exit", "opposite cross", i + fill_shift)
                    else:
                        shadow = side
                        intents.append(rec)
                        if admitted:
                            diag["admitted"] += 1
                            if pos == prior:
                                diag["reversals"] += 1
                            diag["longs" if side == 1 else "shorts"] += 1
                            pending = ("entry", side, i + fill_shift)
                        else:
                            diag["rejected"] += 1; diag["reject_rev"] += 1
                            if not vwap_avail:
                                diag["unavailable"] += 1
                            if pos == prior:
                                diag["opp_exits"] += 1
                                pending = ("exit", "opposite cross", i + fill_shift)

        # ---- fill_shift=0 is the look-ahead being tested for: the order fills at the CLOSE of
        # the bar whose close produced the signal. Never the live model; section 1.2 prices it.
        if fill_shift == 0:
            resolve(i, at_close=True)

        # ---- session-close backstop (the source's IsExitOnSessionCloseStrategy)
        if p.use_backstop and pos != 0 and (i + 1 >= n or sess_key[i + 1] != sk):
            if pending is None or pending[0] != "exit":
                shadow = 0
                diag["backstop_exits"] += 1
                close_trade(i, "session end", at_close=True)   # Pine's immediately=true
                pending = None

    tdf = pd.DataFrame(trades)
    if len(tdf):
        tdf["dt"] = pd.to_datetime(tdf["exit_ts"], utc=True).dt.tz_convert(NY)
        tdf["entry_dt"] = pd.to_datetime(tdf["entry_ts"], utc=True).dt.tz_convert(NY)
    return Result(tdf, diag, osc_out, vwap_out, dist_out, admit_out, atr_out, ema_out,
                  blocked_out, pd.DataFrame(intents))


# --------------------------------------------------------------------------- instruments

# Micro contracts, because the Pine declares MNQ's $0.72 per side. The Dow leg is priced as MYM.
# Both round-turn to the same $2.44, which is a coincidence of the two contract specs, not a
# simplification: 2 x 0.72 commission + 2 x 1 tick of slippage, at $0.50 a tick on either.
SPECS = {
    "NASDAQ_15m": dict(pv=2.0, tick=0.25, comm=0.72, slip_t=1.0, contract="MNQ"),
    "US30_15m": dict(pv=0.50, tick=1.0, comm=0.72, slip_t=1.0, contract="MYM"),
    "US30_ref_15m": dict(pv=0.50, tick=1.0, comm=0.72, slip_t=1.0, contract="MYM"),
}
P15 = Profile("USIndex", 570, 660, 570, 960, 960, 1080, 15)


def round_turn(spec: dict) -> float:
    return 2.0 * spec["comm"] + 2.0 * spec["slip_t"] * spec["tick"] * spec["pv"]


def load(name: str, tf: int = 15) -> tuple:
    """Decision bars, the instrument spec and the ship parameters for one dataset."""
    from apm_data import bars_from_csv
    d = bars_from_csv(f"data/{name}.csv", tf)
    return d, SPECS[name], Params(profile=Profile("USIndex", 570, 660, 570, 960, 960, 1080, tf))


def run(name: str, p: Params | None = None, tf: int = 15, **kw) -> Result:
    d, spec, ship = load(name, tf)
    return simulate(d, p or ship, start_date=kw.pop("start_date", 0),
                    pv=spec["pv"], tick=spec["tick"], comm=spec["comm"],
                    slip_t=spec["slip_t"], **kw)
