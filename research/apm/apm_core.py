"""The APM session-VWAP strategy as a fast engine: one numba walk per configuration.

Everything the shipped Pine does (pine/apm/APM_SESSION_VWAP_strategy.pine) is here in the same
order -- the seeded EMA / Wilder ATR / EMA-of-phase recursions, the frozen MNQ calendar, the
decision-bar completeness gate, the 00:00 UTC reset, the session VWAP over bars opening inside the
window, the entry-window fill test, the control shadow, the opposite-cross exit and the cash close
-- with switches so each component can be removed, and a random-entry control that keeps the
identical exit machinery. The threshold and the ATR denominator are ONE axis: phase > 100 with a
denominator of 3 is `close - EMA > 3 ATR`, so the grid sweeps that distance directly.

Feeds: NQ_1m built into exact UTC buckets at 5 / 10 / 15 minutes (the source's decision bar is
10); US100 and US30 15-minute CFD files with TICK volume (the Volume column is zero); XAUUSD 15m.
Costs per side: half the session-tier spread plus entry slippage (research/scalp/core.COSTS), plus
commission on NQ; reported in points and, for NQ, in MNQ dollars.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "mrl"))

CACHE = os.path.join("/tmp/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad",
                     "apm_cache")

FROZEN = np.array(sorted({
    20200120, 20200217, 20200309, 20200312, 20200313, 20200316, 20200318, 20200525,
    20200611, 20200703, 20200907, 20200910, 20201126, 20201127, 20201224, 20210118,
    20210215, 20210402, 20210531, 20210705, 20210906, 20211125, 20211126, 20220117,
    20220221, 20220530, 20220620, 20220704, 20220905, 20221124, 20221125, 20230116,
    20230220, 20230407, 20230529, 20230619, 20230703, 20230704, 20230904, 20231123,
    20231124, 20240115, 20240219, 20240527, 20240619, 20240703, 20240704, 20240902,
    20241128, 20241129, 20241224, 20250109, 20250120, 20250217, 20250526, 20250619,
    20250703, 20250704, 20250901, 20251127, 20251128, 20251224, 20260119, 20260216,
    20260403, 20260525, 20260619, 20260703}), np.int64)
FROZEN_END = 20260817

# (entry start, entry end, vwap start, vwap end, cash close, eth start) in New York minutes.
# Gold's source clocks (08:20 / 09:50 / 13:30) do not sit on a 15-minute bar; 08:15 / 09:45 are
# the nearest that do, and the source's own Custom profile accepts them.
PROFILES = {
    "USIndex": (570, 660, 570, 960, 960, 1080),
    "ComexGold15": (495, 585, 495, 810, 810, 1080),
}
DEFAULT = dict(ema=21, atr=14, osc=3, dist=3.0, vwap=2.5, ent1=660, tf=10)

# per-side cost in points by fill-bar tier: (rth, pre, off) half-spread + entry slippage, + comm
COST = {
    "NQ": dict(rth=0.25 + 0.25, pre=0.50 + 0.25, off=0.75 + 0.25, comm=0.36, pv=2.0),   # MNQ $
    "US100": dict(rth=0.50 + 0.25, pre=1.00 + 0.25, off=1.50 + 0.25, comm=0.0, pv=1.0),
    "US30": dict(rth=1.00 + 0.50, pre=2.00 + 0.50, off=3.00 + 0.50, comm=0.0, pv=1.0),
    "XAUUSD": dict(rth=0.15 + 0.05, pre=0.225 + 0.05, off=0.35 + 0.05, comm=0.0, pv=1.0),
}
TICK = {"NQ": 0.25, "US100": 0.1, "US30": 0.1, "XAUUSD": 0.01}


# ---------------------------------------------------------------- feeds
def _finish(f, market, tf):
    ix = f.index
    out = dict(
        o=f["open"].to_numpy(float), h=f["high"].to_numpy(float), l=f["low"].to_numpy(float),
        c=f["close"].to_numpy(float), v=f["volume"].to_numpy(float),
        mod=(ix.hour * 60 + ix.minute).to_numpy().astype(np.int64),
        key=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy().astype(np.int64),
    )
    nxt = ix + pd.Timedelta(days=1)
    out["nkey"] = (nxt.year * 10000 + nxt.month * 100 + nxt.day).to_numpy().astype(np.int64)
    utc = ix.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    um = (utc.tz_convert("UTC").hour * 60 + utc.tz_convert("UTC").minute)
    out["utc_mod"] = np.where(pd.isna(um), -1, um).astype(np.int64)
    out["tsec"] = (ix.asi8 // 10**9).astype(np.int64)
    out["dates"] = ix
    out["market"] = market
    out["tf"] = tf
    cst = COST[market]
    tier = np.where((out["mod"] >= 570) & (out["mod"] < 960), cst["rth"],
                    np.where(((out["mod"] >= 420) & (out["mod"] < 570))
                             | ((out["mod"] >= 960) & (out["mod"] < 1080)), cst["pre"], cst["off"]))
    out["side_cost"] = tier + cst["comm"]
    out["pv"] = cst["pv"]
    return out


def load_nq(tf=10):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, f"nq_{tf}m.pkl")
    if os.path.exists(fn):
        f = pd.read_pickle(fn)
    else:
        d = pd.read_csv("data/NQ_1m.csv")
        ts = pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True))
        d.index = ts
        d = d[~d.index.duplicated()].sort_index()
        bucket = d.index.floor(f"{tf}min")
        slot = ((d.index - bucket).total_seconds() // 60).astype(int)
        g = d.groupby(bucket)
        n = g.size()
        ok = pd.Series(slot, index=d.index).groupby(bucket).agg(
            lambda s: sorted(s) == list(range(tf)))
        keep = (n == tf) & ok
        f = pd.DataFrame({"open": g["open"].first()[keep], "high": g["high"].max()[keep],
                          "low": g["low"].min()[keep], "close": g["close"].last()[keep],
                          "volume": g["volume"].sum()[keep]})
        f.index = f.index.tz_convert("America/New_York").tz_localize(None)
        f.to_pickle(fn)
    return _finish(f, "NQ", tf)


def load_cfd(market):
    fn = {"US100": "data/US100_LONG_15m.csv", "US30": "data/US30_LONG_15m.csv"}[market]
    d = pd.read_csv(fn, sep="\t")
    ix = pd.DatetimeIndex(pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S")) \
        - pd.Timedelta(hours=7)                       # file clock is New York + 7, DST-stable
    f = pd.DataFrame({"open": d["Open"].to_numpy(float), "high": d["High"].to_numpy(float),
                      "low": d["Low"].to_numpy(float), "close": d["Close"].to_numpy(float),
                      "volume": d["TickVolume"].to_numpy(float)}, index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    return _finish(f, market, 15)


def load_gold():
    import mrl_bar as MB
    f = MB.load("XAUUSD")
    return _finish(f, "XAUUSD", 15)


def load(market, tf=10):
    if market == "NQ":
        return load_nq(tf)
    if market == "XAUUSD":
        return load_gold()
    return load_cfd(market)


def blocks(D):
    """Named boolean masks over bars. NQ: first 65% of sessions research, the rest locked."""
    ts = D["dates"]
    if D["market"] == "NQ":
        sess = np.where(D["mod"] >= 1080, D["nkey"], D["key"])
        us = np.unique(sess)
        cut = us[int(0.65 * len(us))]
        return {"research": sess < cut, "locked": sess >= cut}
    if D["market"] == "XAUUSD":
        return {"research": np.asarray(ts < "2025-01-01"), "locked": np.asarray(ts >= "2025-01-01")}
    return {"research": np.asarray(ts < "2022-01-01"),
            "validation": np.asarray((ts >= "2022-01-01") & (ts < "2024-01-01")),
            "test": np.asarray(ts >= "2024-01-01")}


def frozen_flags(D, apply):
    if not apply:
        return np.zeros(len(D["c"]), np.bool_)
    sess = np.where(D["mod"] >= 1080, D["nkey"], D["key"])
    return np.isin(sess, FROZEN) & (sess <= FROZEN_END)


# ---------------------------------------------------------------- the walk
@njit(cache=True)
def walk(o, h, l, c, v, mod, key, nkey, utc_mod, tsec, frozen, side_cost,
         tf, ema_len, atr_len, osc_len, dist, vwap_mult, ent0, ent1, vw0, vw1, cash, eth,
         start_key, reset_pts, post_reset, admit_mode, u, opp_exit_on, side_mode,
         halt_on_anomaly):
    """One pass. admit_mode: 0 VWAP, 1 admit all, 2 random with u[intent] < vwap_mult (as p).
    side_mode: 0 rule, 1 always long, 2 always short, 3 inverted.
    Returns trade arrays (entry bar, exit bar, side, entry px, exit px, why) and counters.
    why: 1 cash, 2 opposite cross, 3 carry, 4 gap, 5 reset, 6 reversal, 7 end of data."""
    n = len(c)
    rel_first = min(vw0, ent0 - tf)
    required = (cash - rel_first) // tf
    aE = 2.0 / (ema_len + 1.0)
    aO = 2.0 / (osc_len + 1.0)
    thr = 100.0 * dist / 3.0            # phase threshold that gives `close - ema = dist x ATR`
    den = 3.0

    ei = np.empty(4096, np.int64); xi = np.empty(4096, np.int64); sd = np.empty(4096, np.int64)
    ep = np.empty(4096); xp = np.empty(4096); wy = np.empty(4096, np.int64)
    k = 0
    cnt = np.zeros(16, np.int64)  # 0 decision 1 blocked 2 resets 3 admit 4 reject 5 unavail
                                  # 6 rejrev 7 opp 8 cash 9 anom 10 long 11 short 12 rev 13 intents
    cur = -1; blocked = False; cash_done = False; expo = 0; req = 0; halted = False
    ema = np.nan; atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0
    osc = np.nan; oscinit = False; seg = 0; post = False; shadow = 0
    vday = -1; cpv = 0.0; cv = 0.0
    pos = 0; pend_kind = 0; pend_arg = 0; open_i = -1; open_px = 0.0
    iu = 0
    for i in range(n):
        # fill yesterday's order at this open
        if pend_kind != 0:
            px = o[i]
            if pend_kind == 2 and pos != 0:
                q = px - pos * side_cost[i]
                ei[k] = open_i; xi[k] = i; sd[k] = pos; ep[k] = open_px; xp[k] = q; wy[k] = pend_arg
                k += 1; pos = 0
            elif pend_kind == 1:
                s = pend_arg
                if pos == -s:
                    q = px - pos * side_cost[i]
                    ei[k] = open_i; xi[k] = i; sd[k] = pos; ep[k] = open_px; xp[k] = q; wy[k] = 6
                    k += 1; pos = 0
                if pos == 0:
                    pos = s; open_i = i; open_px = px + s * side_cost[i]
            pend_kind = 0
        if halted:
            continue
        sess = nkey[i] if mod[i] >= eth else key[i]
        if sess != cur:
            carried = pos != 0 or shadow != 0
            cur = sess
            blocked = frozen[i]
            if blocked:
                cnt[1] += 1
            cash_done = False; expo = rel_first; req = 0
            if carried:
                cnt[9] += 1; shadow = 0
                if pos != 0:
                    pend_kind = 2; pend_arg = 3
                if halt_on_anomaly:
                    halted = True
        if not blocked and not halted:
            if mod[i] >= rel_first and mod[i] < cash:
                if mod[i] != expo:
                    blocked = True; cnt[1] += 1; cnt[9] += 1
                else:
                    req += 1; expo += tf
            elif mod[i] >= cash and mod[i] < eth and req != required:
                blocked = True; cnt[1] += 1; cnt[9] += 1
            if blocked:
                shadow = 0
                if pos != 0:
                    pend_kind = 2; pend_arg = 4
                if halt_on_anomaly:
                    halted = True
        if blocked or halted:
            continue
        contiguous = i > 0 and tsec[i] - tsec[i - 1] == tf * 60
        if reset_pts > 0 and contiguous and utc_mod[i] == 0 and abs(o[i] - c[i - 1]) > reset_pts:
            if pos != 0 or shadow != 0:
                cnt[9] += 1
                if pos != 0:
                    pend_kind = 2; pend_arg = 5
                if halt_on_anomaly:
                    halted = True
            ema = np.nan; atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0
            osc = np.nan; oscinit = False; seg = 0; post = True; shadow = 0
            vday = -1; cpv = 0.0; cv = 0.0
            cnt[2] += 1
        osc_prev = osc; osc_prev_avail = oscinit
        ema = c[i] if np.isnan(ema) else aE * c[i] + (1.0 - aE) * ema
        if np.isnan(prevc):
            trng = h[i] - l[i]
        else:
            trng = max(h[i] - l[i], abs(h[i] - prevc), abs(l[i] - prevc))
        prevc = c[i]
        if np.isnan(atr):
            trn += 1; trsum += trng
            if trn == atr_len:
                atr = trsum / atr_len
        else:
            atr = ((atr_len - 1.0) * atr + trng) / atr_len
        osc_avail = False
        if not np.isnan(atr) and atr > 0:
            raw = 100.0 * (c[i] - ema) / (den * atr)
            osc = aO * raw + (1.0 - aO) * osc if oscinit else raw
            oscinit = True; osc_avail = True
        vwap_avail = False; admitted = False
        if mod[i] >= vw0 and mod[i] < vw1:
            if vday != key[i]:
                vday = key[i]; cpv = 0.0; cv = 0.0
            cpv += (h[i] + l[i] + c[i]) / 3.0 * v[i]
            cv += v[i]
            if cv > 0 and not np.isnan(atr) and atr > 0:
                vwap_avail = True
                admitted = abs(c[i] - cpv / cv) < vwap_mult * atr
        seg += 1; cnt[0] += 1
        close_mod = mod[i] + tf
        if close_mod == cash:
            shadow = 0
            if not cash_done:
                cash_done = True
                if pos != 0:
                    cnt[8] += 1; pend_kind = 2; pend_arg = 1
            continue
        if cash_done or sess < start_key or not osc_prev_avail or not osc_avail:
            continue
        if post and seg < post_reset:
            continue
        long_x = osc_prev <= thr and osc > thr
        short_x = osc_prev >= -thr and osc < -thr
        if not (long_x or short_x):
            continue
        side = 1 if long_x else -1
        if side_mode == 1:
            side = 1
        elif side_mode == 2:
            side = -1
        elif side_mode == 3:
            side = -side
        in_win = close_mod >= ent0 and close_mod < ent1
        prior = shadow
        if prior == side:
            continue
        if admit_mode == 1:
            adm = True
        elif admit_mode == 2:
            adm = u[iu % len(u)] < vwap_mult
        else:
            adm = admitted
        if prior == 0:
            if not in_win:
                continue
            cnt[13] += 1; iu += 1
            shadow = side
            if adm:
                cnt[3] += 1
                if side == 1:
                    cnt[10] += 1
                else:
                    cnt[11] += 1
                pend_kind = 1; pend_arg = side
            else:
                cnt[4] += 1
                if not vwap_avail:
                    cnt[5] += 1
            continue
        if not in_win:
            shadow = 0
            if pos == prior and opp_exit_on:
                cnt[7] += 1; pend_kind = 2; pend_arg = 2
            continue
        cnt[13] += 1; iu += 1
        shadow = side
        if adm:
            cnt[3] += 1
            if pos == prior:
                cnt[12] += 1
            if side == 1:
                cnt[10] += 1
            else:
                cnt[11] += 1
            pend_kind = 1; pend_arg = side
        else:
            cnt[4] += 1; cnt[6] += 1
            if not vwap_avail:
                cnt[5] += 1
            if pos == prior and opp_exit_on:
                cnt[7] += 1; pend_kind = 2; pend_arg = 2
    if pos != 0:
        ei[k] = open_i; xi[k] = n - 1; sd[k] = pos; ep[k] = open_px; xp[k] = c[n - 1]; wy[k] = 7
        k += 1
    return ei[:k], xi[:k], sd[:k], ep[:k], xp[:k], wy[:k], cnt


@njit(cache=True)
def oscillator(o, h, l, c, mod, key, nkey, utc_mod, tsec, frozen, tf, ema_len, atr_len, osc_len,
               eth, reset_pts):
    """The phase oscillator alone, on the same blocked/reset path, for the controls."""
    n = len(c)
    out = np.full(n, np.nan)
    rel_first = 0
    cur = -1; blocked = False
    ema = np.nan; atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0; osc = np.nan; oscinit = False
    for i in range(n):
        sess = nkey[i] if mod[i] >= eth else key[i]
        if sess != cur:
            cur = sess; blocked = frozen[i]
        if blocked:
            continue
        contiguous = i > 0 and tsec[i] - tsec[i - 1] == tf * 60
        if reset_pts > 0 and contiguous and utc_mod[i] == 0 and abs(o[i] - c[i - 1]) > reset_pts:
            ema = np.nan; atr = np.nan; prevc = np.nan; trn = 0; trsum = 0.0; osc = np.nan
            oscinit = False
        ema = c[i] if np.isnan(ema) else 2.0 / (ema_len + 1.0) * c[i] + (1 - 2.0 / (ema_len + 1.0)) * ema
        trng = h[i] - l[i] if np.isnan(prevc) else max(h[i] - l[i], abs(h[i] - prevc), abs(l[i] - prevc))
        prevc = c[i]
        if np.isnan(atr):
            trn += 1; trsum += trng
            if trn == atr_len:
                atr = trsum / atr_len
        else:
            atr = ((atr_len - 1.0) * atr + trng) / atr_len
        if not np.isnan(atr) and atr > 0:
            raw = 100.0 * (c[i] - ema) / (3.0 * atr)
            osc = 2.0 / (osc_len + 1.0) * raw + (1 - 2.0 / (osc_len + 1.0)) * osc if oscinit else raw
            oscinit = True
            out[i] = osc
    return out


@njit(cache=True)
def control_walk(o, c, mod, key, nkey, side_cost, osc, thr, fills, sides, tf, ent0, ent1, cash,
                 eth, opp_exit_on):
    """Random entries with the rule's exits: fill at the open of `fills` (sorted), exit on an
    opposite-side oscillator cross (order at that bar's close, fill next open) or the cash close.
    A draw that lands while a position is open is skipped, exactly like the rule's lock."""
    n = len(c)
    m = len(fills)
    pnl = np.empty(m); eb = np.empty(m, np.int64); sd = np.empty(m, np.int64); wy = np.empty(m, np.int64)
    k = 0
    j = 0
    pos = 0; open_px = 0.0; open_i = -1; pend = 0
    for i in range(n):
        if pend != 0 and pos != 0:
            q = o[i] - pos * side_cost[i]
            pnl[k] = pos * (q - open_px); eb[k] = open_i; sd[k] = pos; wy[k] = pend
            k += 1; pos = 0; pend = 0
        while j < m and fills[j] < i:
            j += 1
        if pos == 0 and j < m and fills[j] == i:
            pos = sides[j]; open_px = o[i] + pos * side_cost[i]; open_i = i
            j += 1
        if pos == 0:
            continue
        close_mod = mod[i] + tf
        if close_mod == cash:
            pend = 1
            continue
        if opp_exit_on and i > 0 and not np.isnan(osc[i]) and not np.isnan(osc[i - 1]):
            if pos == 1 and osc[i - 1] >= -thr and osc[i] < -thr:
                pend = 2
            elif pos == -1 and osc[i - 1] <= thr and osc[i] > thr:
                pend = 2
    return pnl[:k], eb[:k], sd[:k], wy[:k]


# ---------------------------------------------------------------- python wrappers
def run(D, cfg=None, profile="USIndex", frozen=None, start_key=0, reset_ticks=400,
        post_reset=21, admit_mode=0, seed=0, opp_exit_on=True, side_mode=0, halt=False,
        cost_mult=1.0, **over):
    cfg = dict(DEFAULT if cfg is None else cfg)
    cfg.update(over)
    e0, e1, v0, v1, cash, eth = PROFILES[profile]
    if "ent1" in cfg:
        e1 = int(cfg["ent1"])
    if "ent0" in cfg:
        e0 = int(cfg["ent0"])
    tf = D["tf"]
    if frozen is None:
        frozen = D["market"] == "NQ"
    fz = frozen_flags(D, frozen)
    u = np.random.default_rng(seed).random(4096) if admit_mode == 2 else np.zeros(1)
    res = walk(D["o"], D["h"], D["l"], D["c"], D["v"], D["mod"], D["key"], D["nkey"], D["utc_mod"],
               D["tsec"], fz, D["side_cost"] * cost_mult, tf, int(cfg["ema"]), int(cfg["atr"]),
               int(cfg["osc"]), float(cfg["dist"]), float(cfg["vwap"]), e0, e1, v0, v1, cash, eth,
               start_key, reset_ticks * TICK[D["market"]], post_reset, admit_mode, u,
               opp_exit_on, side_mode, halt)
    ei, xi, sd, ep, xp, wy, cnt = res
    tr = pd.DataFrame({"ei": ei, "xi": xi, "side": sd, "epx": ep, "xpx": xp, "why": wy})
    tr["pts"] = (tr["xpx"] - tr["epx"]) * tr["side"]
    tr["date"] = D["key"][ei] if len(tr) else np.zeros(0, np.int64)
    tr["fill_mod"] = D["mod"][ei] if len(tr) else np.zeros(0, np.int64)
    return tr, cnt


WHY = {1: "cash", 2: "opposite", 3: "carry", 4: "gap", 5: "reset", 6: "reversal", 7: "eod"}


def metrics(tr, D, mask=None, pv=None):
    """Per-block statistics. Sharpe is over EVERY session in the block, zero-filled."""
    pv = D["pv"] if pv is None else pv
    if mask is not None:
        tr = tr[mask[tr["ei"].to_numpy()]] if len(tr) else tr
    n = len(tr)
    if n == 0:
        return dict(n=0, net=0.0, mean=np.nan, win=np.nan, pf=np.nan, sharpe=np.nan, dd=np.nan,
                    ret_dd=np.nan, top5=np.nan, streak=0, usd=0.0)
    p = tr["pts"].to_numpy()
    w = p > 0
    pf = p[w].sum() / max(1e-9, -p[~w].sum())
    days = pd.Series(p).groupby(tr["date"].to_numpy()).sum()
    if mask is not None:
        sess_keys = np.unique(D["key"][mask & (D["mod"] >= 570) & (D["mod"] < 960)])
    else:
        sess_keys = np.unique(D["key"][(D["mod"] >= 570) & (D["mod"] < 960)])
    daily = pd.Series(0.0, index=sess_keys)
    daily.loc[days.index.intersection(daily.index)] = days.loc[days.index.intersection(daily.index)]
    sh = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else np.nan
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if n else 0.0
    ps = np.sort(p)[::-1]
    top5 = ps[: max(1, int(np.ceil(0.05 * n)))].sum() / p.sum() if p.sum() > 0 else np.nan
    streak = 0; cur = 0
    for x in p:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    return dict(n=n, net=float(p.sum()), mean=float(p.mean()), win=float(w.mean()), pf=float(pf),
                sharpe=float(sh), dd=dd, ret_dd=float(p.sum() / dd) if dd > 0 else np.nan,
                top5=float(top5), streak=streak, usd=float(p.sum() * pv))


def fmt(m, pv=1.0):
    if m["n"] == 0:
        return "n 0"
    return (f"n {m['n']:>4}  win {100*m['win']:5.1f}%  PF {m['pf']:5.2f}  mean {m['mean']:+7.2f} pts  "
            f"net {m['net']:+9.1f}  Sharpe {m['sharpe']:+5.2f}  DD {m['dd']:7.1f}  ret/DD {m['ret_dd']:5.2f}"
            + (f"  ${m['usd']:+,.0f}" if pv != 1.0 else ""))


def eligible_fills(D, profile="USIndex", ent1=None, start_key=0, frozen=None):
    """Bars whose OPEN is a legal fill minute for a fresh entry (the entry window), in sessions
    the rule could trade."""
    e0, e1, v0, v1, cash, eth = PROFILES[profile]
    if ent1 is not None:
        e1 = ent1
    if frozen is None:
        frozen = D["market"] == "NQ"
    fz = frozen_flags(D, frozen)
    sess = np.where(D["mod"] >= eth, D["nkey"], D["key"])
    # the rule's first possible VWAP-qualified fill is max(e0, v0 + tf)
    first = max(e0, v0 + D["tf"])
    ok = (D["mod"] >= first) & (D["mod"] < e1) & (~fz) & (sess >= start_key)
    return np.flatnonzero(ok)


def control(D, tr, cfg, block_mask, profile="USIndex", draws=2000, seed=0, mode="random",
            opp_exit_on=True):
    """Random-entry control matched on the block's trade count with the identical exits.
    mode 'random': random eligible fill bar, coin-flip side.
    mode 'days': the rule's own sessions, random fill bar in the window, the rule's side.
    mode 'side': the rule's own fill bars, coin-flip side.
    Returns the rule's mean, the control mean distribution, p (share >= rule), median count."""
    cfg = dict(DEFAULT, **cfg)
    e0, e1, v0, v1, cash, eth = PROFILES[profile]
    e1 = int(cfg.get("ent1", e1))
    fz = frozen_flags(D, D["market"] == "NQ")
    osc = oscillator(D["o"], D["h"], D["l"], D["c"], D["mod"], D["key"], D["nkey"], D["utc_mod"],
                     D["tsec"], fz, D["tf"], int(cfg["ema"]), int(cfg["atr"]), int(cfg["osc"]), eth,
                     400 * TICK[D["market"]])
    thr = 100.0 * float(cfg["dist"]) / 3.0
    trb = tr[block_mask[tr["ei"].to_numpy()]]
    n = len(trb)
    if n < 5:
        return None
    rule_mean = trb["pts"].mean()
    elig = eligible_fills(D, profile, e1)
    elig = elig[block_mask[elig]]
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    counts = np.empty(draws)
    keys = D["key"]
    if mode == "days":
        by_day = {}
        for b in elig:
            by_day.setdefault(keys[b], []).append(b)
        rule_days = trb["date"].to_numpy()
        rule_sides = trb["side"].to_numpy()
    for d in range(draws):
        if mode == "random":
            f = np.sort(rng.choice(elig, size=n, replace=False))
            s = rng.choice(np.array([-1, 1]), size=n)
        elif mode == "days":
            f = np.array([rng.choice(by_day[k]) if k in by_day else -1 for k in rule_days])
            keep = f >= 0
            f = f[keep]; s = rule_sides[keep]
            order = np.argsort(f); f = f[order]; s = s[order]
        else:
            f = trb["ei"].to_numpy().copy()
            s = rng.choice(np.array([-1, 1]), size=n)
        pnl, eb, sd, wy = control_walk(D["o"], D["c"], D["mod"], D["key"], D["nkey"], D["side_cost"],
                                       osc, thr, f, s, D["tf"], e0, e1, cash, eth, opp_exit_on)
        means[d] = pnl.mean() if len(pnl) else np.nan
        counts[d] = len(pnl)
    p = float(np.mean(means >= rule_mean))
    return dict(rule=float(rule_mean), ctl_median=float(np.nanmedian(means)),
                ctl_mean=float(np.nanmean(means)), p=p, n=n, ctl_n=float(np.median(counts)),
                excess=float(rule_mean - np.nanmedian(means)))
