"""V41 part 2 -- correlations, selection, the single locked read, robustness, cross-market.

Part 1 established the shape: research-to-locked profit-factor correlation -0.391 Pearson, the
top 100 going 2.781 research -> 0.733 locked, and a matched pairwise ablation in which the EMA
condition helps in 42.0% of pairs on research and 50.0% on locked. This part asks whether any
selection rule survives that, and what the components actually correlate with each other.

TWO CORRELATION MATRICES, because they answer different questions:
  SIGNAL LEVEL      do the EMA condition and the Donchian breakout fire on the same bars? A
                    confirmation that is already implied by the trigger removes signals and adds
                    nothing -- `STUDY_V16_MOMENTUM` measured 94.7% of breakout bars already
                    passing an RSI>=55 filter.
  STRATEGY LEVEL    do the top cells produce correlated DAILY RETURNS? `CLAUDE.md`: a hypothesis
                    count is not a diversification count -- eight US30 breakout hypotheses
                    correlated 0.87-0.96 and combining them cut Sharpe from 0.30 to 0.11.

Usage: python3 research/v41/run_v41b.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v33")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
sys.path.insert(0, "research/v41")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v39mc as MC           # noqa: E402
import v41seq as S           # noqa: E402
from run_v41 import blocks, hdr    # noqa: E402

KEYS = ("tf", "ema_f", "ema_s", "mode", "win", "don_e", "don_x", "stop", "tp", "gate")
CTRL = 400


def trades(P, ten, cfg, block=None):
    sig = S.signal(P, cfg["ema_f"], cfg["ema_s"], cfg["mode"], cfg["win"], cfg["don_e"],
                   cfg["gate"])
    xb, pnl, _w = ten[(cfg["don_x"], cfg["stop"], cfg["tp"])]
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    k = G._lock(sig, xb, pnl, bp, bs)
    p, sb = bp[:k].copy(), bs[:k].copy()
    if block is not None:
        m = block[sb]
        p, sb = p[m], sb[m]
    return p, sb


def tensors(P):
    return {(x, sn, tp): G.tensor_stop(P, x, sn, tp, 0)
            for x in S.DON_X for sn in S.STOP for tp in S.TP}


def line(tag, m):
    if m is None:
        return f"      {tag:<34} fewer than 20 trades"
    return (f"      {tag:<34} n {m['n']:>5}  PF {m['pf']:>6.3f}  $/t {m['usd']:>+8.2f}  "
            f"win {m['win']:.3f}  Sh {m['sharpe']:>+5.2f}  DD ${m['dd']:>8,.0f}  "
            f"ret/DD {m['retdd']:>5.2f}")


def main():
    t0 = time.perf_counter()
    T = pd.read_pickle("research/v41/v41_grid.pkl")
    E = T[~T.inert].dropna(subset=["l_pf"])

    hdr("5. SIGNAL-LEVEL CORRELATION -- does the EMA condition already live inside the breakout?")
    for tf in S.TFS:
        P = S.prep(tf)
        res, _lock = blocks(P)
        print(f"\n   {tf}m, research block, {int(res.sum()):,} bars")
        print(f"      {'condition':<28}{'% of ALL bars':>15}{'% of BREAKOUT bars':>22}"
              f"{'lift':>8}")
        brk = P["brk"][20] & res
        base = float((brk).sum())
        for (a, b) in [(13, 48)]:
            since, up = P["since"][(a, b)]
            for nm, m in (("EMA13 > EMA48 (state)", up),
                          ("cross within 5 bars", (since >= 0) & (since <= 5)),
                          ("cross within 10 bars", (since >= 0) & (since <= 10)),
                          ("cross within 40 bars", (since >= 0) & (since <= 40))):
                allb = float((m & res).mean())
                onbrk = float((m & brk).sum() / max(base, 1))
                print(f"      {nm:<28}{allb:>15.1%}{onbrk:>22.1%}"
                      f"{(onbrk / max(allb, 1e-9)):>8.2f}")

    hdr("6. SELECTION -- three rules, all read ONCE on the locked block")
    cands = {}
    top = E.sort_values("r_pf", ascending=False).iloc[0]
    cands["TOP (best research PF)"] = {k: top[k] for k in KEYS}
    t100 = E.sort_values("r_pf", ascending=False).head(100)
    cons = {k: t100[k].mode().iloc[0] for k in KEYS}
    cands["CONSENSUS (top-100 mode)"] = cons
    brief = E[(E.ema_f == 13) & (E.ema_s == 48) & (E["mode"] == "cross") & (E.win > 0)]
    bb = brief.sort_values("r_pf", ascending=False).iloc[0]
    cands["THE BRIEF (EMA 13/48 fixed)"] = {k: bb[k] for k in KEYS}
    for nm, c in cands.items():
        print(f"   {nm:<30} " + "  ".join(f"{k}={c[k]}" for k in KEYS))

    store = {}
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        res, lock = blocks(P)
        print(f"\n   {nm}")
        for bn, blk in (("NQ research", res), ("NQ LOCKED", lock)):
            p, sb = trades(P, ten, c, blk)
            m = G.score(p, P["day"][sb], np.unique(P["day"][blk])) if len(p) else None
            print(line(bn, m))
            if bn == "NQ LOCKED":
                store[nm] = (c, p, sb, P, ten, res, lock, m)

    hdr("7. STRATEGY-RETURN CORRELATION AMONG THE TOP CELLS")
    print("   Daily P&L of the 12 highest research-PF cells, correlated pairwise. A hypothesis")
    print("   count is not a diversification count.")
    T12 = E.sort_values("r_pf", ascending=False).head(12)
    ser = {}
    for i, (_ix, r) in enumerate(T12.iterrows()):
        c = {k: r[k] for k in KEYS}
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        p, sb = trades(P, ten, c)
        ser[f"#{i + 1}"] = pd.Series(p).groupby(P["day"][sb]).sum()
    D = pd.DataFrame(ser).fillna(0.0)
    C = D.corr()
    names = list(C.columns)
    print("\n   " + " " * 5 + "".join(f"{n:>7}" for n in names))
    for a in names:
        print(f"   {a:<5}" + "".join(f"{C.loc[a, b]:>7.2f}" if a != b else f"{'--':>7}"
                                     for b in names))
    off = C.to_numpy()[np.triu_indices(len(C), 1)]
    print(f"\n   median |rho| {np.median(np.abs(off)):.3f}   max {np.max(np.abs(off)):.3f}   "
          f"pairs above 0.7: {int((np.abs(off) > 0.7).sum())} of {len(off)}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
    import pickle
    with open("research/v41/v41_cands.pkl", "wb") as fh:
        pickle.dump({k: v[0] for k, v in store.items()}, fh)


if __name__ == "__main__":
    main()
