"""ONE read of the locked block, on candidates declared from the research consensus alone.

The candidates are fixed here before the block is touched:

  A  CONSENSUS -- the marginal mode of every axis over the top 1000 (`CLAUDE.md`: read what the
     top 1000 AGREE on, never the top row, which is the maximum of ~430,000 draws).
  B  MOST UNDERFIT SURVIVOR -- the fewest conditions that still cleared the control on both
     markets, taken from the gate table.
  C  THE RULE AS THE USER TRADES IT -- 60-minute Initial Balance, 25% retracement, 60% stop,
     50% target, both sides, no filters. The baseline everything else has to beat.
  D  C PLUS ONE CONDITION -- the single most-agreed filter, so the value of the whole indicator
     stack can be separated from the value of its most popular member.

The locked block is the last 35% of sessions on each market and has never been scored.
"""
from __future__ import annotations

import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v58.run_v58 import MK, aggregate, MIN_N                   # noqa: E402
from research.v58.v58judge import load, control_p, gname, label         # noqa: E402


def fidx(adx, vol, cpos, ema):
    return ((V.ADX_MODE.index(adx) * len(V.VOL_MODE) + V.VOL_MODE.index(vol))
            * len(V.CPOS_MODE) + V.CPOS_MODE.index(cpos)) * len(V.EMA_MODE) + V.EMA_MODE.index(ema)


def gidx(ib, retr, stop, tgt, flat):
    li = int(np.flatnonzero(V.IB_LEN == ib)[0])
    ri = int(np.flatnonzero(V.RETR == retr)[0])
    si = int(np.flatnonzero(V.STOPF == stop)[0])
    ti = int(np.flatnonzero(V.TGT == tgt)[0])
    fi = int(np.flatnonzero(V.FLAT == flat)[0])
    return li * 450 + ri * 90 + si * 18 + ti * 3 + fi


CAND = {
    "A consensus": dict(side="long", g=gidx(30, 0.40, 1.30, 2.50, 955),
                        f=fidx("adx>=25", "ibr>=0.8x", "cpos>=0.5", "13 under 48")),
    "B underfit ": dict(side="both", g=gidx(30, 0.40, 0.80, 0.50, 955),
                        f=fidx("adx>=25", "ibr>=0.8x", "off", "13 under 48")),
    "C as-traded": dict(side="both", g=gidx(60, 0.25, 0.60, 0.50, 955),
                        f=fidx("off", "off", "off", "off")),
    "D C+ema    ": dict(side="both", g=gidx(60, 0.25, 0.60, 0.50, 955),
                        f=fidx("off", "off", "off", "13 under 48")),
}


def score(A, P, mL, mS, idx, f, g, side, ndays):
    li = g // 450
    r, pts = [], []
    for s2 in (["long", "short"] if side == "both" else [side]):
        si = 0 if s2 == "long" else 1
        msk = (mL if si == 0 else mS)[:, f, li]
        sel = idx[np.isfinite(A[si][idx, g]) & msk[idx]]
        r.append(A[si][sel, g]); pts.append(P[si][sel, g])
    r = np.concatenate(r); pts = np.concatenate(pts)
    if len(r) == 0:
        return None
    daily = np.zeros(ndays)
    win = pts > 0
    return dict(n=len(r), atr=r.mean(), pf=pts[win].sum() / max(-pts[~win].sum(), 1e-9),
                win=win.mean(), pts=pts.mean(), r=r, ptsv=pts)


def boot(x, n=5000, seed=7):
    g = np.random.default_rng(seed)
    m = g.choice(x, (n, len(x)), replace=True).mean(1)
    return (m <= 0).mean(), np.percentile(m, 5), np.percentile(m, 95)


def main():
    data = {mk: load(mk) for mk in MK}
    F = {mk: V.build(mk) for mk in MK}

    print("=" * 104)
    print("THE POPULATION DIAGNOSTIC  --  corr(research, locked) over every scorable configuration")
    print("=" * 104)
    for mk in MK:
        m, A, P, mL, mS, res, lock = data[mk]
        ml = aggregate(A, P, mL, mS, lock)
        for s in ("long", "short", "both"):
            ok = (m[s]["n"] >= MIN_N) & (ml[s]["n"] >= 30)
            a, b = m[s]["perTrade"][ok], ml[s]["perTrade"][ok]
            good = np.isfinite(a) & np.isfinite(b)
            print(f"  {mk:<7} {s:<5} n={int(good.sum()):7,d}   corr {np.corrcoef(a[good], b[good])[0,1]:+.4f}"
                  f"   research median {np.median(a[good]):+.4f} -> locked {np.median(b[good]):+.4f}")

    print("\n" + "=" * 104)
    print("THE SINGLE LOCKED READ   (candidates declared from research alone; ATR units at the plan bar)")
    print("=" * 104)
    hdr = f"{'candidate':<12} {'blk':<8} {'mkt':<7} {'n':>5} {'ATR/tr':>8} {'pts/tr':>9} {'PF':>6} {'win':>6} {'ctrl p':>7}"
    print(hdr)
    for nm, cd in CAND.items():
        print("-" * 104)
        print(f"  {label(cd['g'], cd['f'], cd['side'])}")
        pooled = {"research": [], "locked": []}
        for mk in MK:
            m, A, P, mL, mS, res, lock = data[mk]
            for bn, idx in (("research", res), ("locked", lock)):
                s = score(A, P, mL, mS, idx, cd["f"], cd["g"], cd["side"], len(idx))
                if s is None or s["n"] < 15:
                    print(f"{nm:<12} {bn:<8} {mk:<7} {'--- too few trades ---'}")
                    continue
                li = cd["g"] // 450
                ps = []
                for s2 in (["long", "short"] if cd["side"] == "both" else [cd["side"]]):
                    si = 0 if s2 == "long" else 1
                    msk = (mL if si == 0 else mS)[:, cd["f"], li]
                    d = idx[np.isfinite(A[si][idx, cd["g"]]) & msk[idx]]
                    if len(d) < 15:
                        continue
                    p, _, _ = control_p(F[mk], cd["g"], si, d, V.COST_PTS[mk], s["atr"])
                    ps.append(p)
                p = max(ps) if ps else float("nan")
                print(f"{nm:<12} {bn:<8} {mk:<7} {s['n']:>5d} {s['atr']:>+8.4f} {s['pts']:>+9.2f} "
                      f"{s['pf']:>6.3f} {s['win']*100:>5.1f}% {p:>7.3f}")
                pooled[bn].append(s["r"])
        for bn in ("research", "locked"):
            if pooled[bn]:
                x = np.concatenate(pooled[bn])
                p0, lo, hi = boot(x)
                print(f"{'':<12} {bn:<8} {'POOLED':<7} {len(x):>5d} {x.mean():>+8.4f} "
                      f"{'':>9} {'':>6} {'':>6}   bootstrap P(mean<=0) {p0:.3f}  "
                      f"90% CI [{lo:+.4f}, {hi:+.4f}]")


if __name__ == "__main__":
    main()
