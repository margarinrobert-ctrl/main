"""The Zeta FX IBS New York session EA (MQL5, v2.00), re-implemented at the order-model level.

THE STRATEGY AS SHIPPED. Over the 09:30-16:00 New York cash session accumulate high, low and
close from M1 bars; IBS = (close - low) / (high - low) * 100. On the bar that opens at 15:59 the
session is complete: if flat and IBS < entry threshold, BUY at the ask on the first tick of the
16:00 bar with a broker-side stop `session range x multiplier` below the bid. On every later
completed session the held count increments; exit (at the 16:00 open) when IBS > exit threshold
or the held count reaches the maximum. A session with fewer than 75% of its expected M1 bars is
skipped entirely -- no signal, no exit, no count -- and so is a session whose high equals its low.
An exit and an entry never share a session (the EA returns after the exit branch).

HOW IT IS SIMULATED HERE. A trade's outcome depends only on its ENTRY SESSION and the geometry
(stop multiple, exit threshold, maximum hold), never on which other trades were taken -- so the
price walk is done once per (session, stop multiple) and once per (session, exit threshold,
hold), and every grid cell is an array lookup plus a position-lock loop over the sessions. This
is the same cached-tensor idea as `research/tune.py`, and it is what makes a 2,352-cell grid with
a matched control per cell cost seconds.

CLOCK AND FEEDS. NQ_1m is stamped UTC; both LONG 15m feeds are New York + 7 (registry); the ISO
feed carries its own offset. On a 15-minute feed the session high, low and close are identical
to the M1 construction (the 09:30-15:45 bars tile 09:30-16:00 exactly), so only the STOP fill
is coarser: a 15m bar whose low crosses the stop fills at the stop, or at the open if the bar
opened through it. That is the same resolution the EA itself would get from a 15m-only tester.

COSTS. Retail CFD assumptions in index points from `research/scalp/core.py` (US30 2.0/4.0/6.0
spread RTH/pre/off, US100 1.0/2.0/3.0, NQ 0.5/1.0/1.5 plus commission), charged BY THE SESSION
OF THE FILL BAR: the 16:00 entry and exit pay the post-close tier, a stop pays its bar's tier
plus stop slippage. Bid/ask is not in any feed, so every cost here is an assumption and the
sweep is re-read at 0x, 1.5x and 2x.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from scalp.core import COSTS  # noqa: E402

RTH = (570, 960)               # 09:30-16:00 New York, the EA's defaults
MIN_PCT = 75.0
H_MAX = 10                     # the longest maximum-hold in the grid

# The EA's own defaults sit inside every axis of the grid.
GRID = dict(entry=(10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0),
            exit=(50.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0),
            hold=(1, 2, 3, 4, 5, 7, 10),
            mult=(0.5, 0.75, 1.0, 1.5, 2.0, 3.0))
DEFAULT = dict(entry=20.0, exit=80.0, hold=5, mult=1.0)

# Research / validation / test for the two long feeds; the same dates as `scalp.core.SPLITS`.
SPLITS = {"US30": ("2022-01-01", "2024-01-01"), "US100": ("2022-01-01", "2024-01-01")}
NQ_SPLIT = 0.65
ISO_FINAL = "2026-01-01"        # US30_ISO from here on has never been seen by anything


# ------------------------------------------------------------------------------------------
# feeds
# ------------------------------------------------------------------------------------------
def _unwrap_rtf(path):
    raw = open(path, "r", errors="ignore").read()
    body = raw.split("\\par")
    rx = re.compile(r"\\[a-zA-Z]+-?\d* ?")
    lines = []
    for chunk in body:
        s = rx.sub("", chunk).replace("{", "").replace("}", "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
            lines.append(s)
    return lines


def load(market):
    """Bars on a NEW YORK clock (tz-naive), ascending, de-duplicated. Returns (df, tf_minutes)."""
    if market == "NQ":
        d = pd.read_csv("data/NQ_1m.csv")
        tc = [c for c in d.columns if "time" in c.lower() or "date" in c.lower()][0]
        ix = (pd.DatetimeIndex(pd.to_datetime(d[tc], utc=True))
              .tz_convert("America/New_York").tz_localize(None))
        cols = {k: d[[c for c in d.columns if c.lower().startswith(k)][0]].to_numpy(float)
                for k in ("open", "high", "low", "close")}
        f, tf = pd.DataFrame(cols, index=ix), 1
    elif market in ("US30", "US100"):
        d = pd.read_csv(f"data/{market}_LONG_15m.csv", sep="\t")
        d.columns = [c.strip().lower() for c in d.columns]
        tc = [c for c in d.columns if "date" in c or "time" in c][0]
        ix = pd.DatetimeIndex(pd.to_datetime(d[tc])) - pd.Timedelta(hours=7)
        f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")},
                         index=ix)
        tf = 15
    elif market == "US30_ISO":
        path = "data/US30_ISO_15m.csv"
        if not os.path.exists(path):
            lines = _unwrap_rtf("data/us30_2_year_data.rtf")
            rows = [ln.split(",") for ln in lines]
            d = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
            ny = (pd.DatetimeIndex(pd.to_datetime(d["ts"], utc=True))
                  .tz_convert("America/New_York").tz_localize(None))
            d.insert(0, "ny", ny)
            d = d.drop(columns="ts")
            for k in ("open", "high", "low", "close", "volume"):
                d[k] = d[k].astype(float)
            d = d.sort_values("ny")
            d.to_csv(path, index=False)
        d = pd.read_csv(path, parse_dates=["ny"])
        f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")},
                         index=pd.DatetimeIndex(d["ny"]))
        tf = 15
    else:
        raise ValueError(market)
    f = f.sort_index()
    f = f[~f.index.duplicated(keep="first")]
    return f, tf


def cost_of(market):
    return COSTS["US30" if market.startswith("US30") else market]


# ------------------------------------------------------------------------------------------
# sessions
# ------------------------------------------------------------------------------------------
def sessions(f, tf, start=RTH[0], end=RTH[1], min_pct=MIN_PCT):
    """One row per VALID cash session. Columns: date, ibs, rng, hi, lo, cl, close_bar (index of
    the last session bar), fill_bar (index of the first bar at/after `end` on that date, where
    the 16:00 order fills at the OPEN), px16 (that open)."""
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    day = ix.normalize()
    in_s = (mod >= start) & (mod < end)
    expected = (end - start) // tf
    need = max(1, int(np.ceil(expected * min_pct / 100.0)))
    g = f[in_s].groupby(day[in_s])
    agg = g.agg(hi=("high", "max"), lo=("low", "min"), cl=("close", "last"), n=("close", "size"))
    # The EA fires only on the bar that opens one minute before the end; if that bar is missing
    # the session is silently skipped even when the count passes. On a 15m feed the equivalent
    # is the bar opening at end - tf.
    last_mod = pd.Series(mod[in_s], index=day[in_s]).groupby(level=0).max()
    agg["last_mod"] = last_mod
    last_pos = pd.Series(np.arange(len(f))[in_s], index=day[in_s]).groupby(level=0).max()
    agg["close_bar"] = last_pos
    # The EA sends its order on the first tick AFTER the last session bar closes. On NQ that is
    # the 16:00 bar; on the CFD feeds the broker is closed after 16:00 and the first tick is
    # the re-open, which the fill has to wait for. Either way: the NEXT BAR IN THE FILE.
    agg["fill_bar"] = agg["close_bar"] + 1
    ok = ((agg["n"] >= need) & (agg["hi"] > agg["lo"]) & (agg["fill_bar"] < len(f))
          & (agg["last_mod"] == end - tf))
    s = agg[ok].copy()
    s["fill_bar"] = s["fill_bar"].astype(int)
    s["ibs"] = (s["cl"] - s["lo"]) / (s["hi"] - s["lo"]) * 100.0
    s["rng"] = s["hi"] - s["lo"]
    s["px16"] = f["open"].to_numpy()[s["fill_bar"].to_numpy()]
    s["fill_mod"] = mod[s["fill_bar"].to_numpy()]
    s.index.name = "date"
    return s.reset_index()


# ------------------------------------------------------------------------------------------
# the cached tensor
# ------------------------------------------------------------------------------------------
@njit(cache=True)
def _stop_walk(o, h, l, mod, fill_bar, close_bar, px16, rng, mults, half_spread,
               slip_stop, sp_rth, sp_pre, sp_off, hmax):  # half_spread: per-session array
    """For every session j and stop multiple m: the slot (1..hmax) in which the stop fills, or
    hmax+1 if it never does inside hmax sessions; the fill price; and the spread tier charged on
    that bar. Slot k spans (close_bar[j+k-1], close_bar[j+k]] in bar index terms."""
    S = len(fill_bar)
    M = len(mults)
    slot = np.full((S, M), hmax + 1, np.int64)
    px = np.zeros((S, M))
    tier = np.zeros((S, M))
    nb = len(o)
    for j in range(S):
        bid0 = px16[j]
        last_j = min(j + hmax, S - 1)
        end_bar = close_bar[last_j]
        for mi in range(M):
            lvl = bid0 - rng[j] * mults[mi]
            k = 1
            b = fill_bar[j]
            while b <= end_bar and b < nb:
                while k <= hmax and j + k <= S - 1 and b > close_bar[j + k]:
                    k += 1
                if k > hmax or j + k > S - 1:
                    break
                if l[b] <= lvl:
                    fill = lvl if o[b] >= lvl else o[b]
                    slot[j, mi] = k
                    px[j, mi] = fill
                    m = mod[b]
                    if m >= 570 and m < 960:
                        tier[j, mi] = sp_rth
                    elif m >= 240 and m < 1080:
                        tier[j, mi] = sp_pre
                    else:
                        tier[j, mi] = sp_off
                    break
                b += 1
    return slot, px, tier


def build(f, tf, s, market, cost_mult=1.0, hmax=H_MAX, grid=GRID):
    """Everything a cell needs, indexed by session. Returns a dict of arrays."""
    c = cost_of(market)
    fm = s["fill_mod"].to_numpy()
    tier_fill = np.where((fm >= 570) & (fm < 960), c.spread_rth,
                         np.where((fm >= 240) & (fm < 1080), c.spread_pre, c.spread_off))
    half = tier_fill / 2.0 * cost_mult         # each 16:00-side fill pays its own bar's tier
    slip_e = c.slip_entry * cost_mult
    slip_s = c.slip_stop * cost_mult
    comm = getattr(c, "commission", 0.0) * cost_mult
    o, h, l = (f[k].to_numpy() for k in ("open", "high", "low"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    mults = np.asarray(grid["mult"], float)
    slot_s, px_s, tier_s = _stop_walk(
        o, h, l, mod, s["fill_bar"].to_numpy(np.int64), s["close_bar"].to_numpy(np.int64),
        s["px16"].to_numpy(), s["rng"].to_numpy(), mults, half.astype(float), slip_s,
        c.spread_rth * cost_mult, c.spread_pre * cost_mult, c.spread_off * cost_mult, hmax)
    S = len(s)
    ibs = s["ibs"].to_numpy()
    px16 = s["px16"].to_numpy()
    rng = s["rng"].to_numpy()
    entry_px = px16 + half + slip_e
    # stop outcome in points, all-in: fill - entry - stop slippage - half the fill bar's spread
    stop_pnl = px_s - entry_px[:, None] - slip_s - tier_s / 2.0 - comm
    # exit-by-rule: for each exit threshold e, the first k in 1..hmax with ibs[j+k] > e
    exits = np.asarray(grid["exit"], float)
    first_k = np.full((S, len(exits)), hmax + 1, np.int64)
    for k in range(hmax, 0, -1):
        cond = np.zeros((S, len(exits)), bool)
        cond[: S - k] = ibs[k:, None] > exits[None, :]
        first_k = np.where(cond, k, first_k)
    holds = np.asarray(grid["hold"], np.int64)
    # exit slot per (j, e, h) = min(first_k, h); an exit beyond the last session is not tradeable
    exit_slot = np.minimum(first_k[:, :, None], holds[None, None, :])
    j_idx = np.arange(S)[:, None, None]
    tgt = j_idx + exit_slot
    valid = tgt <= S - 1
    tgt_c = np.minimum(tgt, S - 1)
    exit_pnl = px16[tgt_c] - half[tgt_c] - slip_e - entry_px[:, None, None] - comm
    exit_pnl = np.where(valid, exit_pnl, np.nan)
    return dict(S=S, ibs=ibs, rng=rng, entry_px=entry_px, date=s["date"].to_numpy(),
                slot_s=slot_s, stop_pnl=stop_pnl, exit_slot=exit_slot, exit_pnl=exit_pnl,
                exits=exits, holds=holds, mults=mults, entries=np.asarray(grid["entry"], float),
                close_px=s["cl"].to_numpy())


@njit(cache=True)
def _lock(ibs, thr, mask, slot_s, stop_pnl, exit_slot, exit_pnl, mults_rng, S):
    """Position lock over sessions. `mask[j]` is 1 where an entry is allowed (the block). Returns
    per-trade arrays: entry session, exit session, pnl in points, R, and whether it stopped."""
    ent = np.empty(S, np.int64)
    ex = np.empty(S, np.int64)
    pnl = np.empty(S)
    r = np.empty(S)
    stopped = np.empty(S, np.int64)
    n = 0
    j = 0
    while j < S:
        if mask[j] == 1 and ibs[j] < thr:
            es = exit_slot[j]
            if np.isnan(exit_pnl[j]):
                break
            if slot_s[j] <= es:
                p = stop_pnl[j]
                k = slot_s[j]
                st = 1
            else:
                p = exit_pnl[j]
                k = es
                st = 0
            ent[n] = j
            ex[n] = j + k
            pnl[n] = p
            r[n] = p / mults_rng[j]
            stopped[n] = st
            n += 1
            # a rule exit and an entry never share a session; a STOP leaves the EA flat at that
            # session's close, so it can re-enter on the same session (found by the parity walk)
            j = j + k + (0 if st == 1 else 1)
        else:
            j += 1
    return ent[:n], ex[:n], pnl[:n], r[:n], stopped[:n]


def run_cell(B, entry, exit_i, hold_i, mult_i, mask):
    """One grid cell; `mask` is a 0/1 array over sessions (the block). Returns a DataFrame."""
    ent, ex, pnl, r, st = _lock(
        B["ibs"], float(entry), mask.astype(np.int64), B["slot_s"][:, mult_i],
        B["stop_pnl"][:, mult_i], B["exit_slot"][:, exit_i, hold_i],
        B["exit_pnl"][:, exit_i, hold_i], B["rng"] * B["mults"][mult_i], B["S"])
    return pd.DataFrame(dict(ent=ent, ex=ex, pnl=pnl, r=r, stopped=st))


def block_masks(market, dates):
    """0/1 masks over sessions for each block of the feed."""
    d = pd.DatetimeIndex(dates)
    if market == "NQ":
        cut = int(len(d) * NQ_SPLIT)
        m = np.zeros(len(d), np.int64)
        res = m.copy()
        res[:cut] = 1
        lock = m.copy()
        lock[cut:] = 1
        return {"research": res, "locked": lock}
    if market == "US30_ISO":
        pre = (d < ISO_FINAL).astype(np.int64)
        fin = (d >= ISO_FINAL).astype(np.int64)
        return {"iso_pre2026": pre, "iso_2026": fin}
    a, b = SPLITS[market]
    return {"research": (d < a).astype(np.int64),
            "validation": ((d >= a) & (d < b)).astype(np.int64),
            "test": (d >= b).astype(np.int64)}


def metrics(t, n_days):
    """Trade-level metrics plus a Sharpe over EVERY session in the block (zero-filled)."""
    if len(t) == 0:
        return dict(n=0, pts=np.nan, R=np.nan, pf=np.nan, win=np.nan, sharpe=np.nan,
                    dd=np.nan, sumR=0.0, stop_share=np.nan)
    r = t["r"].to_numpy()
    g = r[r > 0].sum()
    l = -r[r <= 0].sum()
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    daily = np.zeros(n_days)
    np.add.at(daily, np.clip(t["ex"].to_numpy() - t["ex"].min(), 0, n_days - 1), r)
    sh = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan
    return dict(n=int(len(t)), pts=float(t["pnl"].mean()), R=float(r.mean()),
                pf=float(g / l) if l > 0 else np.inf, win=float((r > 0).mean()), sharpe=sh,
                dd=dd, sumR=float(r.sum()), stop_share=float(t["stopped"].mean()))


def sweep(B, mask, grid=GRID):
    """Every cell on one block. Returns a DataFrame with one row per cell."""
    rows = []
    n_days = int(mask.sum())
    for ei, e in enumerate(grid["entry"]):
        for xi, x in enumerate(grid["exit"]):
            for hi, hd in enumerate(grid["hold"]):
                for mi, m in enumerate(grid["mult"]):
                    t = run_cell(B, e, xi, hi, mi, mask)
                    row = dict(entry=e, exit=x, hold=hd, mult=m)
                    row.update(metrics(t, n_days))
                    rows.append(row)
    return pd.DataFrame(rows)


def cell_trades(B, mask, cell, grid=GRID):
    xi = list(grid["exit"]).index(cell["exit"])
    hi = list(grid["hold"]).index(cell["hold"])
    mi = list(grid["mult"]).index(cell["mult"])
    return run_cell(B, cell["entry"], xi, hi, mi, mask)


# ------------------------------------------------------------------------------------------
# the matched control: a random session with the identical geometry
# ------------------------------------------------------------------------------------------
@njit(cache=True)
def _control_draws(order_pool, n_take, slot_s, stop_pnl, exit_slot, exit_pnl, mults_rng,
                   n_draws, seed):
    """Random entry sessions from the block with the same stop, exit rule and hold, position
    lock included. Returns the mean R of each draw."""
    np.random.seed(seed)
    out = np.empty(n_draws)
    P = len(order_pool)
    for d in range(n_draws):
        perm = np.random.permutation(P)
        taken = 0
        busy_until = -1
        tot = 0.0
        # walk the pool in random order but respect the lock by sorting the chosen few
        chosen = np.empty(n_take, np.int64)
        for i in range(P):
            if taken >= n_take:
                break
            j = order_pool[perm[i]]
            chosen[taken] = j
            taken += 1
        chosen = np.sort(chosen[:taken])
        cnt = 0
        for i in range(taken):
            j = chosen[i]
            if j <= busy_until:
                continue
            if np.isnan(exit_pnl[j]):
                continue
            if slot_s[j] <= exit_slot[j]:
                p = stop_pnl[j]
                k = slot_s[j] - 1
            else:
                p = exit_pnl[j]
                k = exit_slot[j]
            tot += p / mults_rng[j]
            cnt += 1
            busy_until = j + k
        out[d] = tot / cnt if cnt > 0 else 0.0
    return out


def matched_control(B, mask, cell, n_draws=1000, seed=0, grid=GRID):
    """p-value of the cell's mean R against random sessions with the same geometry. The pool is
    every tradeable session in the block; the draw takes the same number of entries."""
    t = cell_trades(B, mask, cell, grid)
    if len(t) < 5:
        return dict(ctrl_mean=np.nan, p=np.nan)
    xi = list(grid["exit"]).index(cell["exit"])
    hi = list(grid["hold"]).index(cell["hold"])
    mi = list(grid["mult"]).index(cell["mult"])
    pool = np.where(mask == 1)[0].astype(np.int64)
    draws = _control_draws(pool, len(t) * 2, B["slot_s"][:, mi], B["stop_pnl"][:, mi],
                           B["exit_slot"][:, xi, hi], B["exit_pnl"][:, xi, hi],
                           B["rng"] * B["mults"][mi], n_draws, seed)
    obs = float(t["r"].mean())
    return dict(ctrl_mean=float(np.mean(draws)), p=float(np.mean(draws >= obs)))
