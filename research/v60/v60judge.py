"""V60 part one: does each indicator carry information, and are any of them the same indicator?

Two reads, in this order, because the second only means something if the first says the pool is
not already duplicated:

  1. CORRELATION MATRIX of the condition masks themselves. `STUDY_RULE_ANATOMY.md` found eight
     literal duplicates in this branch's own pool and `STUDY_SCALP_TREND.md` found ADX and the
     efficiency ratio at rho 0.642 -- "stacking them cut the edge, sample halved, no information
     added". Aroon is a channel-position indicator and Donchian is a channel breakout, so the
     first thing to ask is whether the new indicator is the old one wearing a hat.

  2. THE MARGINAL EFFECT OF EVERY SETTING, averaged over the WHOLE grid rather than at its top
     row. `CLAUDE.md`: read a grid by its marginal average per axis, because the top cell is the
     maximum of the draws. A setting earns its place only by beating `off` in every
     market-block column.
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))

import v60core as V             # noqa: E402
from run_v60 import MARKETS      # noqa: E402

MIN_N = 30


def load(mk, tf=60):
    z = np.load(f"results/v60/{mk}_{tf}.npz")
    with open(f"results/v60/{mk}_{tf}_keys.pkl", "rb") as fh:
        K = pickle.load(fh)
    M = {k: z[k] for k in ("n", "net", "usd", "atru", "pf", "sharpe")}
    return M, K["keys"], K["geoms"], int(z["nres"]), int(z["nlock"])


def correlation_matrix():
    print("=" * 100)
    print("1. CORRELATION MATRIX OF THE CONDITION MASKS -- is the new indicator a new indicator?")
    print("=" * 100)
    for mk in MARKETS:
        P = V.prep(60, mk)
        c = P["c"]
        cols = {}
        cols["donchian brk 30"] = P["brk"][30]
        cols["adx>=20"] = P["gate"]["adx>=20"]
        cols["chop<=45"] = P["gate"]["chop<=45"]
        since, up = P["since"][(13, 48)]
        cols["ema13>ema48"] = up
        cols["ema cross<=40"] = (since >= 0) & (since <= 40)
        for ar in ("osc>=0", "osc>=50", "up>=70"):
            cols[f"aroon25 {ar}"] = P["aroon"][25][ar]
        ok = np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["aroon"][25]["osc>=0"])
        names = list(cols)
        X = np.array([cols[k][ok].astype(float) for k in names])
        C = np.corrcoef(X)
        print(f"\n  {mk} 60m, {int(ok.sum()):,} bars")
        w = max(len(n) for n in names) + 1
        print(" " * (w + 2) + "".join(f"{i:>7d}" for i in range(len(names))))
        for i, nm in enumerate(names):
            print(f"  {nm:<{w}}" + "".join(f"{C[i, j]:>7.3f}" for j in range(len(names))))
        hi = [(names[i], names[j], C[i, j]) for i in range(len(names))
              for j in range(i + 1, len(names)) if abs(C[i, j]) >= 0.5]
        if hi:
            for a, b, r in sorted(hi, key=lambda t: -abs(t[2])):
                print(f"    |rho| >= 0.5:  {a} vs {b} = {r:+.3f}")
        else:
            print("    no pair reaches |rho| 0.5 -- the pool is not duplicated on this market")
        # how often does each condition fire, and how often on a breakout bar?
        brk = P["brk"][30] & ok
        print(f"    base rate on ALL bars vs on BREAKOUT bars (the lift a filter can actually add)")
        for nm in names[1:]:
            m = cols[nm] & ok
            print(f"      {nm:<18} all {m.mean()*100:5.1f}%   on breakouts "
                  f"{(m & brk).sum() / max(brk.sum(), 1) * 100:5.1f}%")


def axis_index(keys, geoms):
    """Per-configuration axis values, as arrays aligned to (signal set, geometry)."""
    md = np.array([k[0] for k in keys])
    ef = np.array([k[1] for k in keys])
    es = np.array([k[2] for k in keys])
    wn = np.array([k[3] for k in keys])
    de = np.array([k[4] for k in keys])
    gt = np.array([k[5] for k in keys])
    an = np.array([k[6] for k in keys])
    ar = np.array([k[7] for k in keys])
    dx = np.array([g[0] for g in geoms])
    sn = np.array([g[1] for g in geoms])
    tp = np.array([g[2] for g in geoms])
    return dict(mode=md, ema_f=ef, ema_s=es, win=wn, don_e=de, gate=gt, aroon_n=an, aroon=ar), \
        dict(don_x=dx, stop=sn, tp=tp)


def marginals():
    print("\n" + "=" * 100)
    print("2. MARGINAL EFFECT OF EVERY SETTING over the WHOLE grid ($ per trade)")
    print("=" * 100)
    D = {mk: load(mk) for mk in MARKETS}
    hdr = f"{'axis':<10} {'setting':<12}"
    for mk in MARKETS:
        hdr += f"{mk[:5] + ' res':>12}{mk[:5] + ' lock':>12}"
    print(hdr)
    rows = []
    for mk in MARKETS:
        M, keys, geoms, nres, nlock = D[mk]
        sig_ax, geo_ax = axis_index(keys, geoms)
        ok = M["n"][:, :, 0] >= MIN_N
        rows.append((mk, M, sig_ax, geo_ax, ok))

    def emit(axis, values, is_sig):
        for v in values:
            cells = []
            for mk, M, sig_ax, geo_ax, ok in rows:
                sel = (sig_ax[axis] == v)[:, None] if is_sig else (geo_ax[axis] == v)[None, :]
                m = ok & sel
                for blk in (0, 1):
                    u = M["usd"][:, :, blk]
                    nn = M["n"][:, :, blk]
                    cells.append(np.nanmean(np.where(m & (nn >= MIN_N), u, np.nan)))
            print(f"{axis:<10} {str(v):<12}" + "".join(f"{c:>12.2f}" for c in cells))
    emit("mode", V.EMA_MODE, True)
    emit("win", V.WIN, True)
    emit("don_e", V.DON_E, True)
    emit("gate", V.GATE, True)
    emit("aroon", V.AROON, True)
    emit("aroon_n", (0,) + V.AROON_N, True)
    emit("stop", V.STOP, False)
    emit("tp", V.TP, False)
    emit("don_x", V.DON_X, False)
    print("\n  A setting earns its place only by beating `off` in ALL SIX columns.")


if __name__ == "__main__":
    correlation_matrix()
    marginals()
