"""V41 part 3 -- robustness to the maximum, cross-market, and vectorbt as a second engine.

Everything here is applied to the three candidates part 2 selected, and every one of them already
FAILED its locked read (PF 3.363 -> 0.647, 3.189 -> 0.957, 2.444 -> 0.691). Robustness is run
anyway, because the shape of HOW a candidate fails is the reusable part, and because the brief
asked for it explicitly.

WHAT IS RUN:
    perturbation      every axis at +/-1 rung; a real edge is a ridge, an artifact is a spike
    walk-forward      6 chronological folds, expanding-origin, each read once
    bootstrap         1,000 day-block draws for the edge; 1,000 permutations for the path
    cost stress       1x, 1.5x, 2x, 3x the assumed round turn
    deflated Sharpe   as a CURVE over assumed trial count, using the EFFECTIVE 62,208
    cross-market      US30 and US100, frozen, each charged its OWN tick and point value
    vectorbt          an independently written engine on the same signals

Usage: python3 research/v41/run_v41c.py
"""
from __future__ import annotations

import pickle
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
from run_v41 import blocks, hdr           # noqa: E402
from run_v41b import trades, tensors, line, KEYS   # noqa: E402

AXES = dict(ema_f=S.EMA_F, ema_s=S.EMA_S, win=S.WIN, don_e=S.DON_E, don_x=S.DON_X,
            stop=S.STOP, tp=S.TP)


def market_prep(mkt, tf):
    """A non-NQ feed put into the same shape S.prep produces, with WILDER ATR and its own pv."""
    d = F.frame(mkt, tf)
    h, l, c = d["h"], d["l"], d["c"]
    P = dict(o=d["o"], h=h, l=l, c=c, mod=d["mod"], n=len(c), pv=F.INSTR[mkt]["pv"],
             atr=I.rma(I.true_range(h, l, c), 20),
             day=pd.to_datetime(d["ts"]).normalize().astype("int64").to_numpy())
    adx, _p, _m = I.adx_di(h, l, c, 14)
    P["gate"] = {"off": np.ones(len(c), bool), "adx<22": adx < 22.0, "adx>=20": adx >= 20.0,
                 "chop<=45": S.chop(h, l, c, 14) <= 45.0}
    P["ema"] = {n: I.ema(c, n) for n in set(S.EMA_F) | set(S.EMA_S)}
    P["brk"] = {e: c > I.shift(I.rmax(h, e), 1) for e in S.DON_E}
    P["since"] = {}
    for a in S.EMA_F:
        for b in S.EMA_S:
            if a >= b:
                continue
            up = P["ema"][a] > P["ema"][b]
            cr = np.zeros(len(c), bool)
            cr[1:] = up[1:] & ~up[:-1]
            P["since"][(a, b)] = (S._since(cr), up)
    return P


def score_of(P, ten, cfg, blk=None):
    p, sb = trades(P, ten, cfg, blk)
    if len(p) < 10:
        return None
    days = np.unique(P["day"][blk]) if blk is not None else np.unique(P["day"])
    m = G.score(p, P["day"][sb], days)
    return None if m is None else (m, p, sb)      # a tuple whose [0] is None is the same as None


def main():
    t0 = time.perf_counter()
    with open("research/v41/v41_cands.pkl", "rb") as fh:
        cands = pickle.load(fh)

    hdr("8. PERTURBATION -- every axis at +/-1 rung. A ridge survives; a spike does not.")
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        res, lock = blocks(P)
        base = score_of(P, ten, c, res)
        if base is None:
            continue
        print(f"\n   {nm}   base research PF {base[0]['pf']:.3f}")
        print(f"      {'axis':<8}{'-1 rung':>22}{'centre':>12}{'+1 rung':>22}")
        keep = []
        for ax, rungs in AXES.items():
            rl = list(rungs)
            if c[ax] not in rl:
                continue
            i = rl.index(c[ax])
            cells = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(rl):
                    cc = dict(c)
                    cc[ax] = rl[j]
                    if cc["ema_f"] >= cc["ema_s"]:
                        cells.append(None)
                        continue
                    s = score_of(P, ten, cc, res)
                    cells.append(s[0]["pf"] if s else None)
                    if s:
                        keep.append(s[0]["pf"])
                else:
                    cells.append(None)
            lo = f"{cells[0]:.3f}" if cells[0] else "--"
            hi = f"{cells[1]:.3f}" if cells[1] else "--"
            print(f"      {ax:<8}{lo:>22}{base[0]['pf']:>12.3f}{hi:>22}")
        if keep:
            print(f"      neighbourhood mean PF {np.mean(keep):.3f} against centre "
                  f"{base[0]['pf']:.3f}   gap {base[0]['pf'] - np.mean(keep):+.3f}")

    hdr("9. WALK-FORWARD -- 6 chronological folds over the whole sample")
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        p, sb = trades(P, ten, c)
        if len(p) < 30:
            print(f"   {nm}: {len(p)} trades, too few to fold")
            continue
        d = P["day"][sb]
        edges = np.quantile(np.unique(P["day"]), np.linspace(0, 1, 7))
        print(f"\n   {nm}")
        pos = 0
        for i in range(6):
            m = (d >= edges[i]) & (d < edges[i + 1]) if i < 5 else (d >= edges[i])
            if m.sum() < 5:
                print(f"      fold {i + 1}   n {int(m.sum()):>4}   (too few)")
                continue
            w, lo = p[m][p[m] > 0], p[m][p[m] < 0]
            pf = w.sum() / abs(lo.sum()) if len(lo) else np.inf
            pos += int(p[m].sum() > 0)
            print(f"      fold {i + 1}   n {int(m.sum()):>4}   net ${p[m].sum():>+9,.0f}   "
                  f"$/t {p[m].mean():>+8.2f}   PF {pf:>6.3f}")
        print(f"      folds positive: {pos} of 6")

    hdr("10. BOOTSTRAP AND PATH -- 1,000 draws each, on the LOCKED block")
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        res, lock = blocks(P)
        s = score_of(P, ten, c, lock)
        if s is None:
            print(f"   {nm}: too few locked trades")
            continue
        m, p, sb = s
        b = MC.boot(p, P["day"][sb])
        pm = MC.perm(p)
        print(f"\n   {nm}   n {m['n']}")
        print(f"      bootstrap mean {b['mc_mean']:>+8.2f}  [{b['p5']:>+8.2f}, {b['p95']:>+8.2f}]"
              f"   P(mean <= 0) {b['p_le0']:.3f}")
        print(f"      realised DD ${pm['dd_real']:>8,.0f}   MC median ${pm['dd50']:>8,.0f}   "
              f"p95 ${pm['dd95']:>8,.0f}   p99 ${pm['dd99']:>8,.0f}")

    hdr("11. COST STRESS -- the spread is an assumption, so vary it")
    print(f"   {'candidate':<30}{'block':<10}{'1.0x':>10}{'1.5x':>10}{'2.0x':>10}{'3.0x':>10}")
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        res, lock = blocks(P)
        for bn, blk in (("research", res), ("LOCKED", lock)):
            out = []
            for mult in (1.0, 1.5, 2.0, 3.0):
                old = G.COST_MULT
                G.COST_MULT = 1.44 * mult
                ten = tensors(P)
                G.COST_MULT = old
                s = score_of(P, ten, c, blk)
                out.append(s[0]["pf"] if s else np.nan)
            print(f"   {nm[:28]:<30}{bn:<10}" + "".join(f"{v:>10.3f}" for v in out))

    hdr("12. CROSS-MARKET -- US30 and US100, frozen, each charged its OWN tick and point value")
    print("   These feeds had NO part in the search. Re-uploaded and verified byte-identical to")
    print("   the registry (US30_LONG sha 24dcf2e1c7ba398f, US100_LONG sha c449dddfbc06a943).")
    for mkt in ("US30L", "US100L"):
        print(f"\n   --- {mkt}  (${F.INSTR[mkt]['pv']:.0f}/point)")
        for nm, c in cands.items():
            Q = market_prep(mkt, int(c["tf"]))
            ten = tensors(Q)
            s = score_of(Q, ten, c)
            print(line(nm[:30], s[0] if s else None))

    hdr("13. DEFLATED SHARPE -- against the EFFECTIVE trial count, not the nominal one")
    import v33robust as RB
    for nm, c in cands.items():
        P = S.prep(int(c["tf"]))
        ten = tensors(P)
        res, lock = blocks(P)
        s = score_of(P, ten, c, lock)
        if s is None:
            continue
        m, p, sb = s
        dz = pd.Series(p).groupby(pd.Series(P["day"][sb])).sum()
        alld = np.unique(P["day"][lock])
        dz = dz.reindex(alld, fill_value=0.0).to_numpy()
        print(f"\n   {nm}")
        for N in (1, 100, 10000, S.N_EFFECTIVE, S.N_NOMINAL):
            r = RB.deflated_sharpe(dz, N)
            if r:
                print(f"      N = {N:>7,}   SR {r['sr_ann']:+.3f}   null SR "
                      f"{r['sr_null_ann']:+.3f}   DSR {r['dsr']:.4f}")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
