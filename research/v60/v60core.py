"""V60 -- the complete quant test on the V41 family, with the AROON OSCILLATOR added.

THE QUESTION: of the indicators this strategy stacks -- the EMA cross, the Donchian breakout, the
ADX/CHOP regime gate, and now the Aroon oscillator -- which ones earn their place and which are
decoration?

THE METHOD, and every part of it is the branch's standing discipline rather than a fresh idea:

  * A CACHED EXIT TENSOR. A trade's outcome depends only on its SIGNAL BAR and its GEOMETRY, never
    on which indicator fired, so the price is walked once per (bar, geometry) and every filtered
    configuration is an array lookup plus a position-lock pass.
  * INERT CELLS ARE COUNTED ONCE. With the EMA condition off, `ema_f`, `ema_s` and `win` change
    nothing; with it in `state` mode, `win` changes nothing. The nominal grid is 1,166,400 cells
    and only 475,200 are DISTINCT. `STUDY_RULE_ANATOMY.md` caught this branch overstating a
    configuration count by 24% once already.
  * SHARPE OVER EVERY TRADING DAY IN THE BLOCK, zero-filled on days that did not trade. Over
    traded days only, a filter is PAID for trading less.
  * SCORING IS PER TRADE IN DOLLARS AND IN ATR UNITS AT THE SIGNAL BAR. The stop is a swept ATR
    multiple, so ranking in R would pay a configuration for tightening its own denominator
    (`STUDY_V58_INITIAL_BALANCE.md`).
  * ATR IS WILDER'S rma(TR, 20), matching the shipped Pine and the Turtle definition the brief
    started from -- NOT this branch's usual ema(TR, n).

The exit walk, the position lock and the cost stack are `research/v38/v38grid.py`'s, unchanged, so
this study and V38/V41 cannot drift apart.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))

import indicators as I          # noqa: E402
import fastbars as FB           # noqa: E402
import v38grid as G             # noqa: E402

SPLIT = 0.65

TFS = (30, 60, 120)
EMA_F = (8, 13, 21)
EMA_S = (34, 48, 62)
EMA_MODE = ("off", "cross", "state")
WIN = (0, 5, 10, 20, 40)
DON_E = (10, 20, 30, 55)
DON_X = (10, 20)
STOP = (1.5, 2.0, 2.5, 3.0)
TP = (0.0, 2.0, 3.0)
GATE = ("off", "adx>=20", "chop<=45")
AROON_N = (14, 25)
AROON = ("off", "osc>=0", "osc>=50", "osc>=-50", "up>=70")

N_NOMINAL = (len(TFS) * len(EMA_F) * len(EMA_S) * len(EMA_MODE) * len(WIN) * len(DON_E)
             * len(DON_X) * len(STOP) * len(TP) * len(GATE) * len(AROON_N) * len(AROON))
N_GEOM = len(DON_X) * len(STOP) * len(TP)


@njit(cache=True)
def _aroon(h, l, n, up, dn):
    """Aroon up/down. Up is 100 when the window's high is the newest bar, 0 when it is the oldest.

    Written out rather than taken from `trendind.aroon` because that one is a Python loop over
    every bar and this is called once per timeframe per period.
    """
    for i in range(n, len(h)):
        hi_at = 0
        lo_at = 0
        hv = h[i - n]
        lv = l[i - n]
        for k in range(1, n + 1):
            if h[i - n + k] >= hv:
                hv = h[i - n + k]
                hi_at = k
            if l[i - n + k] <= lv:
                lv = l[i - n + k]
                lo_at = k
        up[i] = 100.0 * hi_at / n
        dn[i] = 100.0 * lo_at / n


def aroon(h, l, n):
    up = np.full(len(h), np.nan)
    dn = np.full(len(h), np.nan)
    _aroon(h, l, int(n), up, dn)
    return up, dn


def _since(flag):
    """Bars since the last True, -1 before the first. The confirmation window reads this."""
    out = np.full(len(flag), -1, np.int64)
    last = -1
    for i in range(len(flag)):
        if flag[i]:
            last = i
        out[i] = i - last if last >= 0 else -1
    return out


def chop(h, l, c, n=14):
    tr = I.true_range(h, l, c)
    rng = np.maximum(I.rmax(h, n) - I.rmin(l, n), 1e-9)
    return 100.0 * np.log10(I.rsum(tr, n) / rng) / np.log10(n)


MARKETS = ("NQ", "US100L", "US30L")


def load_market(market, tf):
    """NQ comes from the cached 1-minute file; the two LONG feeds from `v38feeds`, which carries
    their New York + 7 clock. Point value follows the instrument so dollars are not NQ's."""
    if market == "NQ":
        d = FB.bars(tf)
        return d, G.PV
    sys.path.insert(0, os.path.join(HERE, "..", "v38"))
    import v38feeds as FE
    f = FE.frame(market, tf)
    return f, FE.INSTR[market]["pv"]


def prep(tf, market="NQ"):
    """Bars plus every series any configuration can ask for, computed once per timeframe."""
    d, pv = load_market(market, tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = I.rma(I.true_range(h, l, c), 20)          # WILDER, as the shipped Pine uses ta.atr(20)
    ts = d["ts"]
    idx = pd.to_datetime(ts)
    mod = d["mod"] if "mod" in d else (idx.hour * 60 + idx.minute).to_numpy(np.int64)
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), pv=pv, ts=ts,
             mod=np.asarray(mod, np.int64),
             day=idx.normalize().astype("int64").to_numpy())
    adx, _pdi, _mdi = I.adx_di(h, l, c, 14)
    P["gate"] = {"off": np.ones(len(c), bool), "adx>=20": adx >= 20.0,
                 "chop<=45": chop(h, l, c, 14) <= 45.0}
    P["brk"] = {e: c > I.shift(I.rmax(h, e), 1) for e in DON_E}
    P["ex_lo"] = {x: I.shift(I.rmin(l, x), 1) for x in DON_X}
    emas = {}
    for a in set(EMA_F) | set(EMA_S):
        emas[a] = I.ema(c, a)
    P["since"] = {}
    for a in EMA_F:
        for b in EMA_S:
            up = emas[a] > emas[b]
            cross = np.zeros(len(c), bool)
            cross[1:] = up[1:] & ~up[:-1]
            P["since"][(a, b)] = (_since(cross), up)
    P["aroon"] = {}
    for n in AROON_N:
        u, dd = aroon(h, l, n)
        osc = u - dd
        P["aroon"][n] = {"off": np.ones(len(c), bool),
                         "osc>=0": osc >= 0.0, "osc>=50": osc >= 50.0,
                         "osc>=-50": osc >= -50.0, "up>=70": u >= 70.0}
    return P


def signal_keys():
    """The DISTINCT signal sets. `off` collapses the EMA axes; `state` collapses the window."""
    seen = set()
    for md in EMA_MODE:
        for a in EMA_F:
            for b in EMA_S:
                for w in WIN:
                    ka = 0 if md == "off" else a
                    kb = 0 if md == "off" else b
                    kw = 0 if md != "cross" else w
                    for e in DON_E:
                        for g in GATE:
                            for an in AROON_N:
                                for ar in AROON:
                                    kan = 0 if ar == "off" else an
                                    k = (md, ka, kb, kw, e, g, kan, ar)
                                    if k not in seen:
                                        seen.add(k)
                                        yield k


def signal_mask(P, key):
    md, a, b, w, e, g, an, ar = key
    if md == "off":
        ema_ok = np.ones(P["n"], bool)
    else:
        since, up = P["since"][(a, b)]
        if md == "state":
            ema_ok = up
        elif w <= 0:
            ema_ok = since >= 0
        else:
            ema_ok = (since >= 0) & (since <= w)
    aro = P["aroon"][an if an else AROON_N[0]][ar]
    m = P["brk"][e] & ema_ok & P["gate"][g] & aro
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    return m


@njit(cache=True, parallel=True)
def sweep(sig_flat, sig_off, sig_len, xb_all, pnl_all, atr, day_id, n_days_res, n_days_lock,
          cut, out):
    """For every (signal set, geometry): lock the positions and score both blocks in one pass.

    Daily totals are accumulated as the walk goes, so Sharpe is over EVERY trading day in the
    block and not only the days that traded. out columns, per block:
      0 n, 1 sum usd, 2 gross win, 3 gross loss, 4 sum of squared DAILY totals, 5 sum ATR units
    """
    n_sig = len(sig_off)
    n_geo = xb_all.shape[0]
    for s in prange(n_sig):
        a0 = sig_off[s]
        a1 = a0 + sig_len[s]
        for g in range(n_geo):
            xb = xb_all[g]
            pnl = pnl_all[g]
            for blk in range(2):
                nn = 0.0
                sm = 0.0
                gw = 0.0
                gl = 0.0
                sq = 0.0
                sa = 0.0
                cur_day = -1
                cur_tot = 0.0
                free = -1
                for t in range(a0, a1):
                    i = sig_flat[t]
                    if blk == 0 and i >= cut:
                        break
                    if blk == 1 and i < cut:
                        continue
                    if i < free:
                        continue
                    x = xb[i]
                    if x < 0:
                        continue
                    free = x
                    v = pnl[i]
                    d = day_id[i]
                    if d != cur_day:
                        if cur_day >= 0:
                            sq += cur_tot * cur_tot
                        cur_day = d
                        cur_tot = 0.0
                    cur_tot += v
                    sm += v
                    nn += 1.0
                    if v > 0:
                        gw += v
                    else:
                        gl += v
                    if atr[i] > 0:
                        sa += v / atr[i]
                if cur_day >= 0:
                    sq += cur_tot * cur_tot
                base = s * n_geo * 12 + g * 12 + blk * 6
                out[base + 0] = nn
                out[base + 1] = sm
                out[base + 2] = gw
                out[base + 3] = gl
                out[base + 4] = sq
                out[base + 5] = sa


def build(tf, market="NQ"):
    """Everything the sweep needs for one timeframe."""
    P = prep(tf, market)
    keys = list(signal_keys())
    flat = []
    off = np.zeros(len(keys), np.int64)
    ln = np.zeros(len(keys), np.int64)
    pos = 0
    for i, k in enumerate(keys):
        idx = np.flatnonzero(signal_mask(P, k)).astype(np.int64)
        off[i] = pos
        ln[i] = len(idx)
        pos += len(idx)
        flat.append(idx)
    sig_flat = np.concatenate(flat) if flat else np.zeros(0, np.int64)

    geoms = [(x, sn, tp) for x in DON_X for sn in STOP for tp in TP]
    xb_all = np.zeros((len(geoms), P["n"]), np.int64)
    pnl_all = np.zeros((len(geoms), P["n"]))
    for gi, (x, sn, tp) in enumerate(geoms):
        xb, pnl, _why = G.tensor_stop(P, x, sn, tp, 0)
        xb_all[gi] = xb
        pnl_all[gi] = pnl

    days, day_id = np.unique(P["day"], return_inverse=True)
    cut = int(P["n"] * SPLIT)
    n_res = len(np.unique(day_id[:cut]))
    n_lock = len(np.unique(day_id[cut:]))
    return P, keys, geoms, sig_flat, off, ln, xb_all, pnl_all, day_id.astype(np.int64), \
        cut, n_res, n_lock


def metrics(out, n_sig, n_geo, n_days_res, n_days_lock):
    """(n_sig, n_geo, 2) frames of the scored blocks."""
    a = out.reshape(n_sig, n_geo, 2, 6)
    nd = np.array([n_days_res, n_days_lock], float)[None, None, :]
    n = a[..., 0]
    sm = a[..., 1]
    gw = a[..., 2]
    gl = a[..., 3]
    sq = a[..., 4]
    sa = a[..., 5]
    mean_d = sm / nd
    var_d = np.maximum(sq / nd - mean_d ** 2, 1e-12)
    with np.errstate(invalid="ignore", divide="ignore"):
        return dict(n=n, net=sm,
                    usd=np.where(n > 0, sm / np.maximum(n, 1), np.nan),
                    atru=np.where(n > 0, sa / np.maximum(n, 1), np.nan),
                    pf=np.where(gl < 0, gw / np.maximum(-gl, 1e-9), np.nan),
                    sharpe=mean_d / np.sqrt(var_d) * np.sqrt(252.0))
