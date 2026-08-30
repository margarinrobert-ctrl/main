"""Donchian breakout trend-following on 07:00-11:00, over many independent synthetic 50-year worlds.

THE SPECIFICATION, AS ASKED
---------------------------
    trigger     Donchian breakout, channel EXCLUDING the current bar
    filters     EMA 13 > 48 > 200 stacked with the trade (mirrored for shorts), ADX(14) > 25
    stop        1.5 x ATR(14)
    session     07:00-11:00 New York, flat at 11:00
    model       a deep ensemble meta-label: it does not pick the side, it decides which of the
                rule's own signals to take (Lopez de Prado's meta-labelling, and the only use of a
                network here that is not a directional-forecast claim)
    evaluation  out-of-sample inside each world, then Monte Carlo ACROSS worlds

WHY THE MONTE CARLO IS THE POINT AND THE BACKTEST IS NOT
--------------------------------------------------------
A backtest on simulated bars measures the SIMULATOR. If the generator trends and the rule follows
trends, it prints money and that is arithmetic, not alpha. So every number here is reported three
ways:

  1. against a MATCHED CONTROL -- random entries with the same side, geometry and minute-of-day
     distribution, in the same world. This prices drift, costs, barrier width and session timing.
  2. across INDEPENDENT WORLDS, so a parameter's score is a mean with a confidence interval rather
     than one lucky path. This is what "the best mean on each parameter" has to mean if it is to
     mean anything.
  3. against the ABLATION `trend=0`, the same generator with the trend switched off. A trend
     follower that still earns there is measuring the drift or a bug, not trend.

And the selection is scored out of sample: pick on the first 65% of each world's sessions, read
the rest once. The gap between the in-sample winner and its own out-of-sample result is the cost
of having to choose parameters, which no single backtest can show you.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import synth50 as S
import donchian

# --- NQ contract and cost model (the user asked for Nasdaq; MNQ would triple the per-tick hurdle)
TICK = 0.25
PV = 20.0              # dollars per POINT (NQ: $5 a tick, four ticks to the point)
COMM = 4.0             # dollars per round turn
SPREAD_T = 1.0         # ticks crossed on each side
SLIP_T = 1.0           # extra ticks when the exit is a stop
WIN_OPEN, WIN_CLOSE = 420, 660          # 07:00 - 11:00 New York

STOP, TARGET, FLAT, HOLD = 1, 2, 3, 4


# ===================================================================== indicators
@njit(cache=True)
def _ema(x, n):
    k = 2.0 / (n + 1.0)
    out = np.empty(len(x))
    acc = x[0]
    for i in range(len(x)):
        acc = x[i] if i == 0 else k * x[i] + (1 - k) * acc
        out[i] = acc
    for i in range(min(n, len(x))):
        out[i] = np.nan
    return out


def ema(x, n):
    return _ema(np.ascontiguousarray(np.asarray(x, float)), int(n))


def true_range(h, l, c):
    pc = np.r_[c[0], c[:-1]]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def atr(h, l, c, n=14):
    """ema(true_range, n) -- this repository's definition, NOT Wilder's and NOT `ta.atr`."""
    return ema(true_range(h, l, c), n)


def adx(h, l, c, n=14):
    """Wilder's ADX. This one IS Wilder-smoothed, because that is what ADX means everywhere."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    up = np.r_[0.0, np.diff(h)]
    dn = np.r_[0.0, -np.diff(l)]
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(h, l, c)
    rma = lambda x: _rma(np.ascontiguousarray(np.asarray(x, float)), n)
    atr_ = rma(tr)
    pdi = 100.0 * rma(plus) / np.where(atr_ > 1e-12, atr_, np.nan)
    mdi = 100.0 * rma(minus) / np.where(atr_ > 1e-12, atr_, np.nan)
    dx = 100.0 * np.abs(pdi - mdi) / np.where(pdi + mdi > 1e-12, pdi + mdi, np.nan)
    out = _rma(np.ascontiguousarray(np.nan_to_num(dx)), n)
    out[:3 * n] = np.nan
    return out


@njit(cache=True)
def _rma(x, n):
    out = np.empty(len(x)); acc = x[0]
    a = 1.0 / n
    for i in range(len(x)):
        acc = x[i] if i == 0 else a * x[i] + (1 - a) * acc
        out[i] = acc
    return out


# ===================================================================== the exit tensor
@njit(cache=True)
def _tensor(o, h, l, c, mod, atr_s, stop_mult, targs, holds, flat_min, side, pv,
            xb, why, raw):
    n = len(c)
    ng = len(targs)
    for g in range(ng):
        tp_r = targs[g]; mh = holds[g]
        for i in range(n - 1):
            a = atr_s[i]
            if not (a > 0.0) or not (mod[i] >= WIN_OPEN and mod[i] < WIN_CLOSE):
                continue
            e = i + 1
            px = o[e]
            d = stop_mult * a
            sp = px - side * d
            tp = px + side * tp_r * d
            end = e + mh
            if end > n - 1:
                end = n - 1
            j = e
            done = False
            while j <= end:
                if side > 0:
                    hit_s = l[j] <= sp
                    hit_t = h[j] >= tp
                else:
                    hit_s = h[j] >= sp
                    hit_t = l[j] <= tp
                if hit_s:                       # pessimistic: a bar holding both books the loss
                    # A STOP IS A MARKET ORDER. If the bar opened beyond the level the fill is
                    # the open, not the level -- booking every stop at exactly -1R understates
                    # losses while targets stay correctly capped at +tp_r, and that asymmetry
                    # alone produced +0.09R per trade on a MARTINGALE in this file's Stage 0
                    # check. Targets keep the level because a target is a resting limit.
                    fill = sp
                    if side > 0:
                        if o[j] < fill:
                            fill = o[j]
                    else:
                        if o[j] > fill:
                            fill = o[j]
                    xb[g, i] = j; why[g, i] = STOP; raw[g, i] = side * (fill - px) * pv
                    done = True; break
                if hit_t:
                    xb[g, i] = j; why[g, i] = TARGET; raw[g, i] = side * (tp - px) * pv
                    done = True; break
                if mod[j] >= flat_min:
                    xb[g, i] = j; why[g, i] = FLAT; raw[g, i] = side * (c[j] - px) * pv
                    done = True; break
                j += 1
            if not done:
                xb[g, i] = end; why[g, i] = HOLD; raw[g, i] = side * (c[end] - px) * pv


@njit(cache=True)
def _book(trig, xb, why, raw, risk, se_pv, fixed, si, cut, out):
    """No-overlap walk, accumulating in R MULTIPLES as well as dollars.

    R is the primary metric here and dollars are secondary, because over fifty years the price
    level rises by a factor of six, so a 1.5 x ATR stop costs six times as many dollars at the end
    as at the start. A dollar mean would then be an average over incomparable bets, dominated by
    the last decade. R -- P&L divided by the risk actually taken on that trade -- is invariant to
    that, and it is also how the cost line correctly gets HARDER when ATR is small.

    out = [n, sumR, wins, n_is, sumR_is, n_oos, sumR_oos, stops, targets, net_dollars]
    """
    free = -1
    for k in range(len(trig)):
        i = trig[k]
        if xb[i] < 0 or i <= free or not (risk[i] > 0.0):
            continue
        net = raw[i] - fixed
        if why[i] == STOP:
            net -= se_pv
        r = net / risk[i]
        out[0] += 1.0; out[1] += r; out[9] += net
        if net > 0:
            out[2] += 1.0
        if si[i] < cut:
            out[3] += 1.0; out[4] += r
        else:
            out[5] += 1.0; out[6] += r
        if why[i] == STOP:
            out[7] += 1.0
        elif why[i] == TARGET:
            out[8] += 1.0
        free = xb[i]


@njit(cache=True)
def _control(mod_ptr, mod_idx, slot, trig, xb, why, raw, risk, se_pv, fixed, si, cut, draws,
             seed, per_is, per_oos):
    """Random entries with the SAME minute-of-day distribution, side and geometry."""
    np.random.seed(seed)
    nslots = len(mod_ptr) - 1
    want = np.zeros(nslots, np.int64)
    for k in range(len(trig)):
        s = slot[trig[k]]
        if s >= 0:
            want[s] += 1
    buf = np.empty(len(trig) + 8, np.int64)
    for d in range(draws):
        m = 0
        for s in range(nslots):
            lo = mod_ptr[s]; hi = mod_ptr[s + 1]
            cnt = want[s]
            avail = hi - lo
            if cnt == 0 or avail == 0:
                continue
            if cnt > avail:
                cnt = avail
            for _ in range(cnt):
                if m >= len(buf):
                    break
                buf[m] = mod_idx[lo + np.int64(np.random.random() * avail)]
                m += 1
        pick = np.sort(buf[:m])
        o = np.zeros(10)
        _book(pick, xb, why, raw, risk, se_pv, fixed, si, cut, o)
        per_is[d] = o[4] / o[3] if o[3] > 0 else 0.0
        per_oos[d] = o[6] / o[5] if o[5] > 0 else 0.0


# ===================================================================== one world
@dataclass
class World:
    d: dict
    ind: dict
    cut: int
    seed: int


DONS = (10, 20, 30, 40, 60)
TPRS = (1.0, 1.5, 2.0, 3.0)
HOLDS = (12, 24, 48)
ADXS = (20.0, 25.0, 30.0)
STOP_ATR = 1.5


def build_world(seed, years=50, trend=0.10, ann_drift=0.07, sub=24, verbose=False):
    """`sub` is the number of sub-steps each bar is built from, and it is not cosmetic.

    Judging barrier crossings from bar OHLC is optimistic for an ASYMMETRIC payoff: a bar whose
    range grazes a 3R target books the full +3R, while the same graze on the 1R stop is capped at
    -1R. `stage0()` measures the size of that on a driftless world: +0.084R per trade at one
    sub-step per bar, +0.053R at six, +0.011R at fifty. It is zero for a symmetric 1:1 geometry.
    Coarser bars make it worse, which is the opposite of the intuition that more sub-steps is a
    luxury.
    """
    t0 = time.time()
    d = S.synth(years=years, seed=seed, trend=trend, ann_drift=ann_drift, sub=sub)
    h, l, c = d["h"], d["l"], d["c"]
    ind = dict(ema13=ema(c, 13), ema48=ema(c, 48), ema200=ema(c, 200),
               atr=atr(h, l, c, 14), adx=adx(h, l, c, 14))
    for n in DONS:
        hi, lo, _, _ = donchian.channel(h, l, n)
        ind[f"dhi{n}"] = hi; ind[f"dlo{n}"] = lo
    us = np.unique(d["sess"])
    cut = int(np.searchsorted(d["sess"], us[int(0.65 * len(us))]))
    if verbose:
        print(f"    world {seed}: {d['n']:,} bars, cut at {cut:,} ({time.time()-t0:.1f}s)")
    return World(d=d, ind=ind, cut=cut, seed=seed)


def tensors(w: World, side):
    """Exit outcomes for every (tp_r, max_hold) geometry, every bar, one side."""
    d = w.d
    targs = np.array([t for t in TPRS for _ in HOLDS], float)
    holds = np.array([hh for _ in TPRS for hh in HOLDS], np.int64)
    ng = len(targs); n = d["n"]
    xb = np.full((ng, n), -1, np.int32)
    why = np.zeros((ng, n), np.int8)
    raw = np.zeros((ng, n), np.float32)
    _tensor(d["o"], d["h"], d["l"], d["c"], d["mod"], w.ind["atr"], STOP_ATR, targs, holds,
            np.int64(WIN_CLOSE), np.int64(side), PV, xb, why, raw)
    return dict(xb=xb, why=why, raw=raw, targs=targs, holds=holds,
                gi={(t, h): k for k, (t, h) in enumerate(zip(targs, holds))})


def triggers(w: World, don_n, adx_min, side, use_ema=True):
    d = w.d; ind = w.ind
    c = d["c"]; mod = d["mod"]
    band = ind[f"dhi{don_n}"] if side > 0 else ind[f"dlo{don_n}"]
    m = (c > band) if side > 0 else (c < band)
    m &= (mod >= WIN_OPEN) & (mod < WIN_CLOSE)
    m &= np.nan_to_num(ind["adx"], nan=0.0) > adx_min
    if use_ema:
        e13, e48, e200 = ind["ema13"], ind["ema48"], ind["ema200"]
        stack = (e13 > e48) & (e48 > e200) if side > 0 else (e13 < e48) & (e48 < e200)
        m &= np.nan_to_num(stack.astype(float)).astype(bool)
    m &= np.isfinite(ind["atr"]) & (ind["atr"] > 0)
    return np.flatnonzero(m).astype(np.int64)


def _fixed_cost(mult=1.0):
    return (COMM + 2.0 * SPREAD_T * TICK * PV) * mult


def _slip_cost(mult=1.0):
    return SLIP_T * TICK * PV * mult


def risk_per_bar(w: World):
    """Dollars at risk if a trade were taken from each bar: the stop distance times the multiplier."""
    return STOP_ATR * np.nan_to_num(w.ind["atr"], nan=0.0) * PV


def evaluate(w: World, T, trig, tp_r, hold, cost_mult=1.0, risk=None):
    g = T["gi"][(tp_r, hold)]
    risk = risk_per_bar(w) if risk is None else risk
    out = np.zeros(10)
    _book(trig, T["xb"][g], T["why"][g], T["raw"][g].astype(np.float64), risk,
          _slip_cost(cost_mult), _fixed_cost(cost_mult),
          w.d["sess"], np.int64(w.d["sess"][w.cut]), out)
    n, sumr, wins, n_is, r_is, n_oos, r_oos, stops, targets, dollars = out
    return dict(n=int(n), R=sumr, per=sumr / n if n else 0.0, dollars=dollars,
                win=100.0 * wins / n if n else 0.0,
                n_is=int(n_is), per_is=r_is / n_is if n_is else 0.0,
                n_oos=int(n_oos), per_oos=r_oos / n_oos if n_oos else 0.0,
                stop_share=100.0 * stops / n if n else 0.0,
                target_share=100.0 * targets / n if n else 0.0)


def control(w: World, T, trig, tp_r, hold, draws=200, seed=7):
    d = w.d
    g = T["gi"][(tp_r, hold)]
    elig = (d["mod"] >= WIN_OPEN) & (d["mod"] < WIN_CLOSE) & (T["xb"][g] >= 0)
    mods = np.unique(d["mod"][elig])
    slot = np.full(d["n"], -1, np.int64)
    order, ptr = [], [0]
    for s, mm in enumerate(mods):
        idx = np.flatnonzero(elig & (d["mod"] == mm))
        slot[idx] = s
        order.append(idx); ptr.append(ptr[-1] + len(idx))
    per_is = np.zeros(draws); per_oos = np.zeros(draws)
    _control(np.asarray(ptr, np.int64), np.concatenate(order).astype(np.int64), slot, trig,
             T["xb"][g], T["why"][g], T["raw"][g].astype(np.float64), risk_per_bar(w),
             _slip_cost(), _fixed_cost(), d["sess"], np.int64(d["sess"][w.cut]),
             np.int64(draws), np.int64(seed), per_is, per_oos)
    return per_is, per_oos


# ===================================================================== combining the two sides
@njit(cache=True)
def _merge_keep(sig, xb):
    """Indices surviving the no-overlap rule on an already-sorted merged trade list."""
    keep = np.empty(len(sig), np.int64)
    m = 0
    free = -1.0
    for k in range(len(sig)):
        if sig[k] > free:
            keep[m] = k; m += 1
            free = xb[k]
    return keep[:m]


def combined_book(w: World, Tl, Ts, trig_l, trig_s, tp_r, hold, cost_mult=1.0):
    """One book from both sides, with the no-overlap rule applied ACROSS them.

    Running the sides separately and adding the P&L would double-count the capital: at 07:00-11:00
    a long and a short signal can fire within bars of each other, and a single account cannot take
    both. The merge is a few thousand trades, so it stays in numpy.
    """
    risk = risk_per_bar(w)
    gl = Tl["gi"][(tp_r, hold)]; gs = Ts["gi"][(tp_r, hold)]
    rows = []
    for trig, T, g, side in ((trig_l, Tl, gl, 1), (trig_s, Ts, gs, -1)):
        xb = T["xb"][g]; why = T["why"][g]; raw = T["raw"][g]
        ok = trig[(xb[trig] >= 0) & (risk[trig] > 0)]
        rows.append(np.column_stack([ok, xb[ok], why[ok], np.full(len(ok), side),
                                     raw[ok].astype(np.float64)]))
    a = np.vstack(rows)
    a = a[np.argsort(a[:, 0], kind="mergesort")]
    fixed = _fixed_cost(cost_mult); slip = _slip_cost(cost_mult)
    a = a[_merge_keep(np.ascontiguousarray(a[:, 0]), np.ascontiguousarray(a[:, 1]))]
    sig = a[:, 0].astype(np.int64)
    net = a[:, 4] - fixed - np.where(a[:, 2] == STOP, slip, 0.0)
    R = net / risk[sig]
    is_m = w.d["sess"][sig] < w.d["sess"][w.cut]
    return dict(sig=sig, exit=a[:, 1].astype(np.int64), why=a[:, 2].astype(np.int8),
                side=a[:, 3].astype(np.int64), net=net, R=R, is_mask=is_m,
                n=len(sig), per=float(R.mean()) if len(R) else 0.0,
                per_is=float(R[is_m].mean()) if is_m.any() else 0.0,
                per_oos=float(R[~is_m].mean()) if (~is_m).any() else 0.0,
                n_is=int(is_m.sum()), n_oos=int((~is_m).sum()),
                dollars=float(net.sum()))


# ===================================================================== the deep meta-label
def meta_features(w: World, sig, side, don_n):
    """Signal-bar features for the meta-label. No calendar variables, by protocol.

    Minute-of-day is deliberately absent even though the session is fixed: with it, the network
    can express "only trade 09:30-10:00", which is a time-of-day filter dressed up as a model, and
    `CLAUDE.md` is explicit about what that does to a search. The matched control is minute-of-day
    matched precisely so that any such effect is priced rather than credited.
    """
    ind = w.ind; d = w.d
    a = ind["atr"]; c = d["c"]
    band = np.where(side > 0, ind[f"dhi{don_n}"], ind[f"dlo{don_n}"])
    rng5 = np.r_[np.zeros(5), c[5:] - c[:-5]]
    hl = np.where(d["h"] - d["l"] > 1e-9, d["h"] - d["l"], np.nan)
    cols = {
        "adx": ind["adx"],
        "natr": 100.0 * a / c,
        "atr_ratio": a / np.r_[np.full(240, np.nan), a[:-240]],
        "break_size": side * (c - band) / a,
        "chan_w": (ind[f"dhi{don_n}"] - ind[f"dlo{don_n}"]) / a,
        "e13_48": side * (ind["ema13"] - ind["ema48"]) / a,
        "e48_200": side * (ind["ema48"] - ind["ema200"]) / a,
        "px_vs_200": side * (c - ind["ema200"]) / a,
        "mom5": side * rng5 / a,
        "close_in_bar": (c - d["l"]) / hl,
        "vol_z": np.log(np.maximum(d["v"], 1.0)) - np.log(np.maximum(
            np.r_[np.full(240, np.nan), d["v"][:-240]], 1.0)),
    }
    names = list(cols)
    X = np.column_stack([np.asarray(cols[k], float)[sig] for k in names])
    return X, names


def meta_filter(w: World, bk, don_n, cfg=None, keep_q=0.5, verbose=False):
    """Train a deep ensemble on the IS trades, keep the top `1-keep_q` of OOS trades by P(win).

    This is META-LABELLING: the network never chooses a side or invents a trade, it only declines
    some of the rule's own signals. That keeps its failure mode bounded -- the worst it can do is
    remove good trades -- and it is the only use of a network on this data that this repository's
    own feature study does not already argue against.
    """
    import uq_net
    sig = bk["sig"]; side = bk["side"]
    X = np.empty((len(sig), 0)); names = []
    for s in (1, -1):
        m = side == s
        if not m.any():
            continue
        Xi, names = meta_features(w, sig[m], s, don_n)
        if X.shape[1] == 0:
            X = np.full((len(sig), Xi.shape[1]), np.nan)
        X[m] = Xi
    y = bk["R"]
    lab = (bk["R"] > 0).astype(float)
    is_m = bk["is_mask"]
    ok = np.isfinite(X).all(1)
    tr = np.flatnonzero(is_m & ok)
    te = np.flatnonzero((~is_m) & ok)
    if len(tr) < 500 or len(te) < 100:
        return None
    ens = uq_net.fit_ensemble(X[tr], y[tr], lab[tr], cfg or uq_net.UQCfg(members=3, mc=8,
                                                                        epochs=30))
    p_tr = uq_net.predict(ens, X[tr])["p_up"]
    thr = float(np.quantile(p_tr, keep_q))              # threshold from TRAINING rows only
    p_te = uq_net.predict(ens, X[te])["p_up"]
    take = te[p_te >= thr]
    base = float(y[te].mean())
    filt = float(y[take].mean()) if len(take) else float("nan")
    if verbose:
        print(f"      meta: train {len(tr):,} keep>{thr:.3f}  OOS {len(te):,} -> {len(take):,}"
              f"  {base:+.4f}R -> {filt:+.4f}R")
    return dict(n_train=len(tr), thr=thr, n_oos=len(te), n_kept=int(len(take)),
                oos_R=base, oos_R_filtered=filt, ece=uq_net.ece(p_tr, lab[tr]))


# ===================================================================== Stage 0
def stage0(years=15, seed=77, subs=(6, 24), tps=(1.0, 3.0), verbose=True):
    """Run the harness over a MARTINGALE world with costs off. Anything it earns is engine bias.

    `docs/RESEARCH_PROTOCOL.md` Stage 0. What it finds here is not a coding error but a modelling
    one, and it is worth stating precisely because it changes which geometries can be trusted:

        a 1:1 geometry is unbiased to within noise, on both sides
        a 3:1 geometry is OPTIMISTIC, by an amount that falls as the bar is built from more
        sub-steps -- it is bar discretisation, not drift

    The practical consequence is that no raw per-trade number from an asymmetric geometry means
    anything on its own. The matched control shares the geometry and therefore the bias, so the
    EXCESS over control is the only quantity that survives this.
    """
    import donchian as _don
    out = {}
    for sub in subs:
        d = S.synth(years=years, seed=seed, trend=0.0, ann_drift=0.0, sub=sub)
        h, l, c = d["h"], d["l"], d["c"]
        ind = dict(atr=atr(h, l, c, 14), adx=adx(h, l, c, 14), ema13=ema(c, 13),
                   ema48=ema(c, 48), ema200=ema(c, 200))
        for n in DONS:
            hi, lo, _, _ = _don.channel(h, l, n)
            ind[f"dhi{n}"] = hi; ind[f"dlo{n}"] = lo
        us = np.unique(d["sess"])
        w = World(d=d, ind=ind, cut=int(np.searchsorted(d["sess"], us[int(0.65 * len(us))])),
                  seed=seed)
        risk = risk_per_bar(w)
        mod = d["mod"]
        elig = np.flatnonzero((mod >= WIN_OPEN) & (mod < WIN_CLOSE) & (risk > 0))
        for tp in tps:
            vals = []
            for side in (1, -1):
                T = tensors(w, side)
                vals.append(evaluate(w, T, elig, tp, 24, cost_mult=0.0, risk=risk)["per"])
            out[(sub, tp)] = (float(np.mean(vals)), float(vals[0]), float(vals[1]))
            if verbose:
                print(f"  sub={sub:>2} tp={tp:g}R : mean {np.mean(vals):+.4f}R  "
                      f"(long {vals[0]:+.4f}, short {vals[1]:+.4f})")
    return out


def selftest():
    """Stage 0 plus the two properties the engine must have whatever the generator does."""
    s0 = stage0(years=12, subs=(24,), tps=(1.0, 3.0), verbose=False)
    sym = s0[(24, 1.0)][0]
    asym = s0[(24, 3.0)][0]
    assert abs(sym) < 0.02, f"a symmetric 1:1 geometry earns {sym:+.4f}R on a martingale -- bug"
    assert asym > sym, "the known discretisation optimism at 3:1 has vanished -- check stage0()"
    assert abs(asym) < 0.06, (f"3:1 optimism is {asym:+.4f}R, larger than measured at this "
                              "sub-step count -- do not trust asymmetric geometries here")
    return dict(sym_1R=round(sym, 4), asym_3R=round(asym, 4))


if __name__ == "__main__":
    if "--stage0" in sys.argv:
        print("Stage 0: martingale world, costs off")
        stage0(subs=(1, 6, 24, 50))
        print("selftest:", selftest())
        sys.exit(0)
    print("smoke test")
    w = build_world(0, years=5, verbose=True)
    T = tensors(w, 1)
    trig = triggers(w, 20, 25.0, 1)
    r = evaluate(w, T, trig, 2.0, 24)
    ci, co = control(w, T, trig, 2.0, 24, draws=100)
    print("  triggers %d -> n %d  %.4fR/trade  win %.1f%%  IS %.4fR  OOS %.4fR  $%.0f"
          % (len(trig), r["n"], r["per"], r["win"], r["per_is"], r["per_oos"], r["dollars"]))
    print("  matched control  IS %.4fR  OOS %.4fR" % (ci.mean(), co.mean()))
