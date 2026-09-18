"""The 1,290,240-cell grid: masks x geometries, both sides, entries only inside 07:00-11:00 NY.

THE SPLIT IS DECIDED HERE AND NOWHERE ELSE. Train is everything before 2026-01-01 on BOTH
instruments; 2026 is read once at the end. A configuration only counts as a survivor if it holds on
US30 AND US100 independently -- the check that has repeatedly separated real from fitted here.

RANKED ON RETURN OVER MAX DRAWDOWN, which is the one ranking criterion on this branch whose
in-sample ordering has survived out of sample. Sharpe and profit factor are carried on every row
but do not drive the ordering.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/v14"); sys.path.insert(0,"research/v8opt")
import mirror, indicators as I, fastbars, v14tensor as T  # noqa: E402

WIN_LO, WIN_HI = 420, 660          # 07:00-11:00 New York; ENTRIES ONLY, exits run free
DON_E = 30                          # the Donchian anchor, fixed by the brief
JUDGE = pd.Timestamp("2026-01-01")

MA_F   = [6, 8, 10, 12, 13, 15, 18, 21]
MA_S   = [34, 48, 55, 89, 100, 144, 200]
MA_MODE= [0, 1, 2]                  # 0 off, 1 state, 2 fresh cross within 8 bars
ADX    = [0, 15, 20, 22, 25, 30]
CHOP   = [0, 50, 55, 61.8]          # 0 = off
LIM    = [0.0, 0.25, 0.5, 0.75]     # 0 = market at next open; else a limit N x ATR(5) in our favour
STOP   = [1.0, 1.5, 2.0, 2.5, 3.0]
TPR    = [0.0, 1.5, 2.0, 3.0]       # 0 = no target
EXIT_L = [10, 15, 20, 25]

def geoms():
    return [(lm, sm, tp, xi) for lm in LIM for sm in STOP for tp in TPR for xi in range(len(EXIT_L))]

def load(path):
    df = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    ix = df.index
    d = dict(o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
             l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             mod=(ix.hour*60+ix.minute).to_numpy(np.int64),
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64))
    return d, ix

def prep(d):
    h,l,c = d["h"],d["l"],d["c"]
    atr  = mirror.wilder_atr(h,l,c,20)
    atr5 = I.ema(I.true_range(h,l,c), 5)
    C = dict(lo=[I.shift(I.rmin(l,n),1) for n in EXIT_L],
             hi=[I.shift(I.rmax(h,n),1) for n in EXIT_L])
    ent_hi = I.shift(I.rmax(h,DON_E),1); ent_lo = I.shift(I.rmin(l,DON_E),1)
    adx,pdi,mdi = I.adx_di(h,l,c,14)
    tr = I.true_range(h,l,c)
    s14 = pd.Series(tr).rolling(14).sum().to_numpy()
    r14 = pd.Series(h).rolling(14).max().to_numpy() - pd.Series(l).rolling(14).min().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        chop = 100*np.log10(s14/np.maximum(r14,1e-9))/np.log10(14)
    return atr, atr5, C, ent_hi, ent_lo, adx, chop

def signal_bars(d, ent_hi, ent_lo, atr, side, block):
    mod = d["mod"]
    inwin = (mod >= WIN_LO) & (mod < WIN_HI)
    fin = np.isfinite(atr) & (atr > 0)
    if side > 0:
        trig = np.isfinite(ent_hi) & (d["h"] > np.nan_to_num(ent_hi, nan=np.inf))
    else:
        trig = np.isfinite(ent_lo) & (d["l"] < np.nan_to_num(ent_lo, nan=-np.inf))
    return np.flatnonzero(inwin & fin & trig & block)

def masks_for(d, sig, adx, chop, side):
    """4,032 masks over the signal bars: MA pair x mode x ADX floor x CHOP ceiling."""
    c = d["c"]
    rows = []
    meta = []
    ema = {n: I.ema(c, n) for n in set(MA_F) | set(MA_S)}
    a_s = adx[sig]; ch_s = chop[sig]
    for f in MA_F:
        for s_ in MA_S:
            if s_ <= f:
                st = np.zeros(len(c), bool); fr = np.zeros(len(c), bool)
            else:
                up = ema[f] > ema[s_]
                st = up if side > 0 else ~up
                sw = np.r_[False, np.diff(up.astype(np.int8)) != 0]
                bs = np.zeros(len(c), np.int64); k = 0
                for i in range(len(c)):
                    k = 0 if sw[i] else k+1
                    bs[i] = k
                fr = st & (bs <= 8)
            st_s, fr_s = st[sig], fr[sig]
            for mm in MA_MODE:
                base = np.ones(len(sig), bool) if mm == 0 else (st_s if mm == 1 else fr_s)
                for ax in ADX:
                    ba = base if ax == 0 else (base & np.nan_to_num(a_s >= ax, nan=False))
                    for cp in CHOP:
                        m = ba if cp == 0 else (ba & np.nan_to_num(ch_s <= cp, nan=False))
                        rows.append(m.astype(np.int8))
                        meta.append((f, s_, mm, ax, cp))
    return np.ascontiguousarray(np.array(rows, np.int8)), meta
