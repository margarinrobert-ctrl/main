"""V53 -- the deliberately small rule, swept whole, and read for UNDERFITTING rather than for a top
row. NQ 1-minute source, every trading timeframe resampled from it so the lower-timeframe
absorption and the trading bars come from one series and align exactly.

Research = the first 65% of bars, this branch's NQ convention. Locked = the last 35%, read once.
"""
from __future__ import annotations
import sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v53")
import v51tensor as T      # noqa: E402
import v53abs as A         # noqa: E402

COST, SLIP = 0.72, 0.25            # the real MNQ stack, not the broker-only figure
SPLIT = 0.65
MAX_HOLD = 480
ENT_N = (10, 20, 30, 55)
EXIT_N = (5, 10, 20, 30)
STOP_N = (1.5, 2.0, 2.5, 3.0)
MA_MODES = ("off", "above", "within 3.0 ATR", ">= 1.5 ATR above", ">= 3.0 ATR above")
CX_MODES = ("off", "13 > 48", "cross <= 20 bars")
REC = (1, 5)


def abs_modes():
    m = [("off", None, None, None)]
    for w in A.MEAN_W:
        for side in ("buyer", "seller"):
            for ltf in A.LTF:
                for k in REC:
                    m.append((f"{side} {ltf}m w{w} k{k}", side, ltf, (k, w)))
    return m


ABS_MODES = abs_modes()


def build(f1, tf):
    g = A.resample(f1, tf)
    o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    S = pd.Series(c)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    ema200 = S.ewm(span=200, adjust=False).mean().to_numpy()
    e13 = S.ewm(span=13, adjust=False).mean().to_numpy()
    e48 = S.ewm(span=48, adjust=False).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        mad = (c - ema200) / np.where(atr > 0, atr, np.nan)
    st = e13 > e48
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), ma_dist=mad, cx_state=st,
             cx_recent=A.recent(st & ~np.concatenate(([False], st[:-1])), 20),
             ent_hi={n: pd.Series(h).rolling(n).max().shift(1).to_numpy() for n in ENT_N},
             exit_lo={n: pd.Series(l).rolling(n).min().shift(1).to_numpy() for n in EXIT_N},
             flags={w: A.ltf_flags(f1, tf, w) for w in A.MEAN_W})
    return P


def entry_mask(P, n):
    m = np.asarray(P["h"] > P["ent_hi"][n], bool).copy()
    m[:1000] = False
    m[-(MAX_HOLD + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["ma_dist"])
    return m


def masks(P, sig, tf):
    d = P["ma_dist"][sig]
    MA = np.zeros((len(MA_MODES), len(sig)), bool)
    MA[0] = True; MA[1] = d > 0; MA[2] = (d > 0) & (d <= 3.0); MA[3] = d >= 1.5; MA[4] = d >= 3.0
    CX = np.zeros((len(CX_MODES), len(sig)), bool)
    CX[0] = True; CX[1] = P["cx_state"][sig]; CX[2] = P["cx_recent"][sig]
    AB = np.zeros((len(ABS_MODES), len(sig)), bool)
    for i, (_lab, side, ltf, kw) in enumerate(ABS_MODES):
        if side is None:
            AB[i] = True
            continue
        k, w = kw
        fl = P["flags"][w]
        if ltf not in fl:
            AB[i] = False                      # a lower timeframe above the chart's is undefined
            continue
        b, s = fl[ltf]
        AB[i] = A.recent(b if side == "buyer" else s, k)[sig]
    SS = np.ones((1, len(sig)), bool)
    return MA, CX, AB, SS


def sweep(f1, tf):
    P = build(f1, tf)
    cut = int(P["n"] * SPLIT)
    uni = np.flatnonzero(entry_mask(P, min(ENT_N)))
    pos = -np.ones(P["n"], np.int64); pos[uni] = np.arange(len(uni))
    tensor = {(xn, sn): T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], uni, P["exit_lo"][xn],
                               float(sn), -1, np.zeros(P["n"], np.int64), COST, SLIP, MAX_HOLD)
              for xn in EXIT_N for sn in STOP_N}
    rows = []
    ss_ids = np.zeros(1, np.int64)
    for en in ENT_N:
        bars = np.flatnonzero(entry_mask(P, en))
        sub = pos[bars]
        MA, CX, AB, SS = masks(P, bars, tf)
        for xn in EXIT_N:
            for sn in STOP_N:
                xb, R = tensor[(xn, sn)]
                tot = MA.shape[0] * CX.shape[0] * AB.shape[0]
                on = np.zeros(tot, np.int64); os_ = np.zeros(tot); ow = np.zeros(tot, np.int64)
                ogp = np.zeros(tot); ogl = np.zeros(tot)
                onl = np.zeros(tot, np.int64); osl = np.zeros(tot)
                T.score_all(sub, bars, xb, R, MA, CX, AB, SS, ss_ids, cut,
                            on, os_, ow, ogp, ogl, onl, osl)
                t = np.arange(tot)
                ia = t // (CX.shape[0] * AB.shape[0])
                ic = (t // AB.shape[0]) % CX.shape[0]
                ib = t % AB.shape[0]
                rows.append(pd.DataFrame(dict(tf=tf, entN=en, exitN=xn, stopN=sn,
                                              ma=ia.astype(np.int8), cx=ic.astype(np.int8),
                                              ab=ib.astype(np.int16), n=on, sumR=os_, win=ow,
                                              gp=ogp, gl=ogl, nlk=onl, sumRlk=osl)))
    D = pd.concat(rows, ignore_index=True)
    D["R"] = np.where(D.n > 0, D.sumR / np.maximum(D.n, 1), np.nan)
    D["Rlk"] = np.where(D.nlk > 0, D.sumRlk / np.maximum(D.nlk, 1), np.nan)
    D["pf"] = np.where(D.gl > 0, D.gp / np.maximum(D.gl, 1e-9), np.nan)
    return D


if __name__ == "__main__":
    f1 = A.load_1m()
    out = []
    for tf in A.TFS:
        t0 = time.time()
        D = sweep(f1, tf)
        print(f"  NQ {tf}m: {len(D):,} configurations in {time.time()-t0:6.1f}s")
        out.append(D)
    G = pd.concat(out, ignore_index=True)
    G.to_parquet("results/v53/v53_grid.parquet", index=False)
    print(f"\n  {len(G):,} configurations -> results/v53/v53_grid.parquet")
