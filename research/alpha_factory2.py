"""Strategy generator, scaled. ~110 conditions, 32 exit geometries, both directions.

221,925 rules of up to three conditions x 2 directions x 32 exits = 14.2 million strategies,
about 129x the first build. The scale comes from three changes:

  * conditions are packed into uint64 BITSETS, so combining three of them is 559 word-ANDs
    instead of 35,721 byte-ANDs
  * what happens if you enter at bar i under exit geometry g is precomputed once per bar per
    geometry, so a strategy's backtest is a walk over its trigger bars
  * the whole enumeration runs inside one parallel numba kernel, with no Python per rule

Pass 1 keeps only what every decision needs -- trades and P&L per block. Pass 2 re-simulates the
qualifying subset for profit factor, win rate, drawdown and exit mix. Everything is causal and
fills are at the open of the bar after the signal.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np
from numba import njit, prange

sys.path.insert(0, "research")
from bos_choch import prep
import indicators as I

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK

ATR_MULTS = [1.0, 1.5, 2.0, 2.5]
TP_RS = [1.0, 1.5, 2.0, 3.0]
FLATS = [0, 960]
EXITS = [(a, t, f) for a in ATR_MULTS for t in TP_RS for f in FLATS]


def build_conditions(d):
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    idx = d["df"].index
    S = {}

    # ---- trend and moving averages ----------------------------------------------------------
    for n in (10, 20, 50, 100, 200):
        S[f"close>EMA{n}"] = c > I.ema(c, n)
        S[f"close>SMA{n}"] = c > I.sma(c, n)
    e = {n: I.ema(c, n) for n in (10, 20, 50, 100, 200)}
    for a, b in ((10, 20), (20, 50), (50, 100), (50, 200), (20, 200)):
        S[f"EMA{a}>EMA{b}"] = e[a] > e[b]
    for n in (20, 50, 200):
        S[f"EMA{n} rising"] = I.rising(e[n])
    for n in (20, 50):
        S[f"LR slope{n}>0"] = I.lin_slope(c, n) > 0
    vw = I.session_vwap(h, l, c, v, sess)
    S["close>session VWAP"] = c > vw
    S["close<session VWAP"] = c < vw
    S["close>Donchian20 high"] = c > I.shift(I.rmax(h, 20))
    S["close<Donchian20 low"] = c < I.shift(I.rmin(l, 20))

    # ---- oscillators -------------------------------------------------------------------------
    r14, r7 = I.rsi(c, 14), I.rsi(c, 7)
    S["RSI14<30"] = r14 < 30; S["RSI14>70"] = r14 > 70
    S["RSI14>50"] = r14 > 50; S["RSI14<50"] = r14 < 50
    S["RSI14 rising"] = I.rising(r14)
    S["RSI7<25"] = r7 < 25; S["RSI7>75"] = r7 > 75
    kk, dd_ = I.stoch(h, l, c)
    S["Stoch K<20"] = kk < 20; S["Stoch K>80"] = kk > 80; S["Stoch K>D"] = kk > dd_
    cc = I.cci(h, l, c)
    S["CCI>100"] = cc > 100; S["CCI<-100"] = cc < -100
    wr = I.willr(h, l, c)
    S["Williams%R<-80"] = wr < -80; S["Williams%R>-20"] = wr > -20
    mf = I.mfi(h, l, c, v)
    S["MFI<20"] = mf < 20; S["MFI>80"] = mf > 80
    S["ROC10>0"] = I.roc(c, 10) > 0; S["ROC20>0"] = I.roc(c, 20) > 0
    S["TRIX>0"] = I.trix(c) > 0
    ml, msig = I.macd(c)
    S["MACD>signal"] = ml > msig; S["MACD>0"] = ml > 0
    S["MACD rising"] = I.rising(ml)

    # ---- volatility --------------------------------------------------------------------------
    a20 = I.sma(atr_, 20)
    S["ATR>1.2x mean"] = atr_ > 1.2 * a20
    S["ATR>1.5x mean"] = atr_ > 1.5 * a20
    S["ATR<0.8x mean"] = atr_ < 0.8 * a20
    S["ATR rising"] = I.rising(atr_)
    S["ATR falling"] = ~I.rising(atr_)
    bu, bm, bl, bw = I.bollinger(c)
    S["close>BB upper"] = c > bu; S["close<BB lower"] = c < bl
    bwm = I.sma(bw, 50)
    S["BB width>mean"] = bw > bwm
    S["BB squeeze"] = bw < 0.7 * bwm
    ku, kl = I.keltner(h, l, c)
    S["close>Keltner upper"] = c > ku; S["close<Keltner lower"] = c < kl
    rg = h - l
    S["range>1.5xATR"] = rg > 1.5 * atr_
    S["range<0.5xATR"] = rg < 0.5 * atr_
    S["3-bar contraction"] = (rg < I.shift(rg)) & (I.shift(rg) < I.shift(rg, 2))
    ad, pdi, mdi = I.adx_di(h, l, c)
    S["ADX>20"] = ad > 20; S["ADX>25"] = ad > 25; S["ADX>30"] = ad > 30
    S["ADX rising"] = I.rising(ad); S["+DI>-DI"] = pdi > mdi

    # ---- structure and price action ----------------------------------------------------------
    for n in (5, 10, 20, 50):
        S[f"close>{n}-bar high"] = c > I.shift(I.rmax(h, n))
        S[f"close<{n}-bar low"] = c < I.shift(I.rmin(l, n))
    S["inside bar"] = (h < I.shift(h)) & (l > I.shift(l))
    S["outside bar"] = (h > I.shift(h)) & (l < I.shift(l))
    S["bullish engulfing"] = (c > I.shift(o)) & (o < I.shift(c)) & (c > o)
    S["bearish engulfing"] = (c < I.shift(o)) & (o > I.shift(c)) & (c < o)
    body = np.abs(c - o) / np.maximum(rg, 1e-12)
    S["body>60%"] = body > 0.6; S["body<30%"] = body < 0.3
    S["upper wick>50%"] = (h - np.maximum(c, o)) / np.maximum(rg, 1e-12) > 0.5
    S["lower wick>50%"] = (np.minimum(c, o) - l) / np.maximum(rg, 1e-12) > 0.5
    up1 = np.r_[False, np.diff(c) > 0]
    S["bullish bar"] = c > o
    up1f = up1.astype(float)
    dn1f = (~up1).astype(float)
    S["2 up closes"] = up1 & (I.shift(up1f, 1) > 0)
    S["3 up closes"] = up1 & (I.shift(up1f, 1) > 0) & (I.shift(up1f, 2) > 0)
    S["2 down closes"] = (~up1) & (I.shift(dn1f, 1) > 0)
    S["gap up"] = o > I.shift(c); S["gap down"] = o < I.shift(c)

    # ---- volume --------------------------------------------------------------------------------
    vm = I.sma(v, 20)
    S["vol>1.5x mean"] = v > 1.5 * vm
    S["vol>2x mean"] = v > 2.0 * vm
    S["vol<0.7x mean"] = v < 0.7 * vm
    S["vol<0.5x mean"] = v < 0.5 * vm
    S["vol rising"] = I.rising(v)
    S["OBV rising"] = I.rising(I.ema(I.obv(c, v), 10))
    vsd = I.rstd(v, 20)
    S["vol z>1"] = (v - vm) / np.maximum(vsd, 1e-12) > 1

    # ---- clock ---------------------------------------------------------------------------------
    S["first hour"] = (mod >= 570) & (mod < 630)
    S["second hour"] = (mod >= 630) & (mod < 690)
    S["midday"] = (mod >= 690) & (mod < 810)
    S["last hour"] = (mod >= 900) & (mod < 960)
    S["overnight"] = (mod < 570) | (mod >= 960)
    dw = np.array([t.dayofweek for t in idx])
    for i, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
        S[nm] = dw == i
    dom = np.array([t.day for t in idx])
    S["first half of month"] = dom <= 15
    S["month end (last 3d)"] = dom >= 27

    # ---- context ---------------------------------------------------------------------------------
    dist = np.abs(c - e[200]) / np.maximum(atr_, 1e-12)
    S["dist EMA200>1 ATR"] = dist > 1.0
    S["dist EMA200>2 ATR"] = dist > 2.0
    S["dist EMA200<0.5 ATR"] = dist < 0.5
    ph, pl_, pc = I.prior_day(h, l, c, sess)
    S["close>prior day high"] = c > ph
    S["close<prior day low"] = c < pl_
    S["prior day up"] = pc > I.shift(pc)
    S["prior day range>20d"] = (ph - pl_) > I.sma(ph - pl_, 20)
    S["5-bar momentum>0"] = c > I.shift(c, 5)
    S["20-bar momentum>0"] = c > I.shift(c, 20)

    names = list(S)
    n = len(c)
    M = np.zeros((len(names), n), np.bool_)
    for i, k in enumerate(names):
        x = np.nan_to_num(np.asarray(S[k], dtype=float), nan=0.0)
        M[i] = x > 0.5
    M[:, :300] = False
    return names, M


@njit(cache=True)
def price_one(o, h, l, c, atr_, mod, side, atr_mult, tp_r, flat_min, ex_bar, ex_pnl, ok):
    n = len(c)
    for i in range(n - 1):
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            ok[i] = 0
            continue
        entry = o[i + 1]
        st = entry - side * atr_mult * a
        tg = entry + side * tp_r * atr_mult * a
        j = i + 1
        done = 0
        while j < n:
            hit = (l[j] <= st) if side == 1 else (h[j] >= st)
            won = (h[j] >= tg) if side == 1 else (l[j] <= tg)
            if hit:
                px = o[j] if ((side == 1 and o[j] < st) or (side == -1 and o[j] > st)) else st
                px += -SE if side == 1 else SE
                ex_bar[i] = j; ex_pnl[i] = side * (px - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 1; done = 1; break
            if won:
                px = o[j] if ((side == 1 and o[j] > tg) or (side == -1 and o[j] < tg)) else tg
                ex_bar[i] = j; ex_pnl[i] = side * (px - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 2; done = 1; break
            if flat_min > 0 and mod[j] >= flat_min:
                ex_bar[i] = j; ex_pnl[i] = side * (c[j] - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 3; done = 1; break
            j += 1
        if done == 0:
            ok[i] = 0


@njit(parallel=True, cache=True)
def sweep(B, combos, nbars, EB, EP, OK, sidx, cut, res_net, res_n, lok_net, lok_n):
    nw = B.shape[1]
    nvar = EB.shape[0]
    for r in prange(combos.shape[0]):
        i0 = combos[r, 0]; i1 = combos[r, 1]; i2 = combos[r, 2]
        trig = np.empty(nbars, np.int32)
        nt = 0
        for w in range(nw):
            word = B[i0, w]
            if i1 >= 0:
                word &= B[i1, w]
            if i2 >= 0:
                word &= B[i2, w]
            if word == np.uint64(0):
                continue
            base = w * 64
            for b in range(64):
                if (word >> np.uint64(b)) & np.uint64(1):
                    p = base + b
                    if p < nbars:
                        trig[nt] = p; nt += 1
        for vv in range(nvar):
            free = -1
            rn = 0; rs = 0.0; ln = 0; ls = 0.0
            for t in range(nt):
                i = trig[t]
                if i < free or OK[vv, i] == 0:
                    continue
                free = EB[vv, i]
                p = EP[vv, i]
                if sidx[i] < cut:
                    rn += 1; rs += p
                else:
                    ln += 1; ls += p
            k = r * nvar + vv
            res_n[k] = rn; res_net[k] = rs; lok_n[k] = ln; lok_net[k] = ls


def main(tf=30, seed=20260823, out_path=None):
    t0 = time.time()
    d = prep(tf)
    names, M = build_conditions(d)
    nbars = M.shape[1]
    print(f"{len(names)} conditions on {nbars:,} bars")

    combos = []
    nc = len(names)
    for i in range(nc):
        combos.append((i, -1, -1))
    for a, b in combinations(range(nc), 2):
        combos.append((a, b, -1))
    for a, b, cc in combinations(range(nc), 3):
        combos.append((a, b, cc))
    combos = np.array(combos, np.int32)
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    total = len(combos) * len(variants)
    print(f"{len(combos):,} rules x {len(variants)} variants "
          f"(2 directions x {len(EXITS)} exit geometries) = {total:,} strategies")

    nw = (nbars + 63) // 64
    B = np.zeros((len(names), nw), np.uint64)
    for i in range(len(names)):
        idxs = np.flatnonzero(M[i])
        for p in idxs:
            B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)

    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    cut = np.int64(int(0.65 * len(us)))

    EB = np.zeros((len(variants), nbars), np.int64)
    EP = np.zeros((len(variants), nbars), np.float64)
    OK = np.zeros((len(variants), nbars), np.int64)
    for vi, (s, gi) in enumerate(variants):
        am, tp, fl = EXITS[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    print(f"   phase 1 done, {time.time()-t0:.0f}s", flush=True)

    res_net = np.zeros(total, np.float32); lok_net = np.zeros(total, np.float32)
    res_n = np.zeros(total, np.int32); lok_n = np.zeros(total, np.int32)
    sweep(B, combos, nbars, EB, EP, OK, sidx, cut, res_net, res_n, lok_net, lok_n)
    print(f"   sweep done, {time.time()-t0:.0f}s", flush=True)

    path = out_path or f"results/alpha/af2_{tf}m.npz"
    np.savez_compressed(path, res_net=res_net, res_n=res_n,
                        lok_net=lok_net, lok_n=lok_n, combos=combos,
                        names=np.array(names), exits=np.array(EXITS), tf=np.array([tf]))
    print(f"saved {path}. total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    import sys as _s
    tfs = [int(x) for x in _s.argv[1:]] or [30]
    for _tf in tfs:
        print(f"\n===== {_tf}-minute bars =====", flush=True)
        main(_tf)
