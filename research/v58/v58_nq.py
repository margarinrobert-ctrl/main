"""ONE read of a cluster on NQ -- an instrument that had NO PART in the search.

The 0.63% of configurations profitable on all four US30/US100 cells were chosen BY LOOKING AT
THE LOCKED BLOCK, so their p-values there are decoration (`CLAUDE.md`, the first rule). What they
are good for is generating a hypothesis, and a hypothesis needs a block that chose nothing.

NQ is that block. It is a different feed, a different contract and a different span, and not one
of the 1,555,200 configurations swept in passes one and two was scored on it.

DECLARED BEFORE THE FILE IS OPENED -- the cluster that recurs in the survivor list:
    30-minute Initial Balance, LONG, entry 0.50 of the range back inside, stop 1.00 or 1.30 of
    the range from the broken edge, target none / 1.50 / 2.50, flat 15:55,
    ADX >= 20, IB range >= 0.8x its trailing 20-day median, last IB bar closing in the upper
    half, EMA 13 UNDER EMA 48.
plus candidate C, the as-traded configuration, as the baseline.

NQ's stored price LEVELS are synthetic (`STUDY_US100.md`); ATR-unit measurements are not affected.

NQ_1m IS STAMPED IN UTC and every other feed here is already on a New York clock, so the loader
must CONVERT. The first version of this file did not, which put the "Initial Balance" at 04:30
New York -- inside the pre-open block this branch has measured as the worst part of the day four
separate times. The registry states the clock; read it before loading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v58.v58judge import control_p                             # noqa: E402
from research.v58.v58lock import fidx, gidx, boot                       # noqa: E402

COST_NQ = 0.72          # MNQ $1.44 round turn at $2 a point


def load_nq():
    d = pd.read_csv("data/NQ_1m.csv")
    tc = [c for c in d.columns if "time" in c.lower() or "date" in c.lower()][0]
    ix = pd.DatetimeIndex(pd.to_datetime(d[tc], utc=True)) \
        .tz_convert("America/New_York").tz_localize(None)
    f = pd.DataFrame({k: d[[c for c in d.columns if c.lower().startswith(k)][0]].to_numpy(float)
                      for k in ("open", "high", "low", "close")}, index=ix)
    f = f.sort_index()
    f = f[~f.index.duplicated(keep="first")]
    return f.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last"}).dropna()


def main():
    f = load_nq()
    f["volume"] = 0.0
    print(f"NQ 15m: {len(f):,} bars, {f.index[0]} .. {f.index[-1]}")

    import research.v58.v58ib as M
    _load = M.load
    M.load = lambda name: f
    F = M.build("NQ")
    R, _ = M.outcomes(F, COST_NQ, fillbar=1)
    risk, atr = M.risk_atr(F)
    mL, mS = M.filters(F)
    D = F["D"]
    R3 = R.reshape(D, len(M.IB_LEN), 2, 450)
    A = [np.ascontiguousarray(R3[:, :, s, :].reshape(D, M.NG)) * risk / atr for s in (0, 1)]
    P = [np.ascontiguousarray(R3[:, :, s, :].reshape(D, M.NG)) * risk for s in (0, 1)]
    idx = np.arange(D)
    M.load = _load

    cl_f = fidx("adx>=20", "ibr>=0.8x", "cpos>=0.5", "13 under 48")
    cells = [("cluster", "long", gidx(30, 0.50, st, tg, 955), cl_f)
             for st in (1.00, 1.30) for tg in (99.0, 1.50, 2.50)]
    cells.append(("as-traded", "both", gidx(60, 0.25, 0.60, 0.50, 955),
                  fidx("off", "off", "off", "off")))

    print("\n" + "=" * 92)
    print("NQ, READ ONCE   (ATR units at the plan bar, net of a $1.44 MNQ round turn)")
    print("=" * 92)
    print(f"{'':<10} {'stop':>5} {'tgt':>5} {'n':>5} {'ATR/tr':>9} {'pts/tr':>9} {'PF':>6} "
          f"{'win':>6} {'ctrl p':>7}")
    pool = []
    for nm, side, g, ff in cells:
        li = g // 450
        rr, pp, ps = [], [], []
        for s2 in (["long", "short"] if side == "both" else [side]):
            si = 0 if s2 == "long" else 1
            msk = (mL if si == 0 else mS)[:, ff, li]
            sel = idx[np.isfinite(A[si][idx, g]) & msk[idx]]
            if len(sel) < 10:
                continue
            rr.append(A[si][sel, g]); pp.append(P[si][sel, g])
        if not rr:
            print(f"{nm:<10} -- too few trades --")
            continue
        r = np.concatenate(rr); pts = np.concatenate(pp)
        for s2 in (["long", "short"] if side == "both" else [side]):
            si = 0 if s2 == "long" else 1
            msk = (mL if si == 0 else mS)[:, ff, li]
            sel = idx[np.isfinite(A[si][idx, g]) & msk[idx]]
            if len(sel) >= 15:
                p, _, _ = control_p(F, g, si, sel, COST_NQ, r.mean())
                ps.append(p)
        gm = {"stop": (g // 18) % 5, "tgt": (g // 3) % 6}
        w = pts > 0
        if nm == "cluster":
            pool.append(r)
        print(f"{nm:<10} {M.STOPF[gm['stop']]:>5.2f} "
              f"{'none' if M.TGT[gm['tgt']] > 90 else f'{M.TGT[gm[chr(39)+chr(39)] if False else chr(116)+chr(103)+chr(116)]:.2f}':>5} "
              if False else
              f"{nm:<10} {M.STOPF[gm['stop']]:>5.2f} "
              f"{('none' if M.TGT[gm['tgt']] > 90 else f'{M.TGT[gm[chr(116)+chr(103)+chr(116)]]:.2f}'):>5} "
              , end="")
        print(f"{len(r):>5d} {r.mean():>+9.4f} {pts.mean():>+9.2f} "
              f"{pts[w].sum()/max(-pts[~w].sum(),1e-9):>6.3f} {w.mean()*100:>5.1f}% "
              f"{(max(ps) if ps else float('nan')):>7.3f}")
    if pool:
        x = np.concatenate(pool)
        p0, lo, hi = boot(x)
        print(f"\n  cluster pooled over its six cells: n {len(x)}, {x.mean():+.4f} ATR/trade, "
              f"bootstrap P(mean<=0) {p0:.3f}, 90% CI [{lo:+.4f}, {hi:+.4f}]")


if __name__ == "__main__":
    main()
