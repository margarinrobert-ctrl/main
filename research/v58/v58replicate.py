"""Two reads that decide the family, and neither is a single cell.

  1. REPLICATION. The 25 configurations that headed the research ranking, read once on locked.
     Chance says half of them beat zero. `STUDY_V16_MOMENTUM.md` used exactly this test to kill a
     2,167-condition pool.

  2. THE MARGINAL EFFECT OF EACH CONDITION, averaged over the WHOLE grid rather than at its top
     row -- `CLAUDE.md`: read a grid by its marginal average per axis, because the top cell is the
     maximum of the draws. A condition worth having is positive on BOTH blocks and BOTH markets.
"""
from __future__ import annotations

import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v58.run_v58 import MK, aggregate, MIN_N                   # noqa: E402
from research.v58.v58judge import load, control_p, gname, label         # noqa: E402


def main():
    data = {mk: load(mk) for mk in MK}
    F = {mk: V.build(mk) for mk in MK}
    lockm = {}
    for mk in MK:
        m, A, P, mL, mS, res, lock = data[mk]
        lockm[mk] = aggregate(A, P, mL, mS, lock)

    gate = np.load("results/v58/gate.npy")
    print("=" * 96)
    print("REPLICATION -- the 25 research leaders, read once on locked")
    print("=" * 96)
    print(f"{'#':>3} {'research p':>10} {'US30 lock':>10} {'US100 lock':>11} {'lock ctrl p':>12}  verdict")
    beat0 = ctrl = 0
    for r, row in enumerate(gate):
        side, f, g = str(row["side"]), int(row["f"]), int(row["g"])
        li = g // 450
        vals, ps = [], []
        for mk in MK:
            m, A, P, mL, mS, res, lock = data[mk]
            n = lockm[mk][side]["n"][f, g]
            v = lockm[mk][side]["perTrade"][f, g] if n >= 15 else np.nan
            vals.append(v)
            if np.isfinite(v):
                pp = []
                for s2 in (["long", "short"] if side == "both" else [side]):
                    si = 0 if s2 == "long" else 1
                    msk = (mL if si == 0 else mS)[:, f, li]
                    d = lock[np.isfinite(A[si][lock, g]) & msk[lock]]
                    if len(d) >= 15:
                        p, _, _ = control_p(F[mk], g, si, d, V.COST_PTS[mk], v)
                        pp.append(p)
                ps.append(max(pp) if pp else np.nan)
            else:
                ps.append(np.nan)
        ok = np.isfinite(vals).all()
        pos = ok and min(vals) > 0
        cp = np.nanmax(ps) if ok else np.nan
        beat0 += int(pos)
        ctrl += int(pos and np.isfinite(cp) and cp <= 0.05)
        print(f"{r+1:>3} {row['p']:>10.3f} {vals[0]:>+10.4f} {vals[1]:>+11.4f} {cp:>12.3f}"
              f"  {'positive both' if pos else 'fails'}")
    print(f"\n  {beat0}/25 positive on locked on BOTH markets  (chance ~6/25 for two independent"
          f" coin flips, ~12/25 if the markets moved together)")
    print(f"  {ctrl}/25 also beat their risk-matched control on locked at p <= 0.05")

    print("\n" + "=" * 96)
    print("MARGINAL EFFECT OF EACH CONDITION, averaged over the WHOLE grid (ATR units per trade)")
    print("=" * 96)
    print(f"{'axis':<12} {'setting':<14} " +
          "".join(f"{mk[:-1]+' '+b:>16}" for mk in MK for b in ("res", "lock")))
    axes = [("adx", V.ADX_MODE, lambda f: V.filter_name(f)["adx"]),
            ("vol", V.VOL_MODE, lambda f: V.filter_name(f)["vol"]),
            ("close pos", V.CPOS_MODE, lambda f: V.filter_name(f)["cpos"]),
            ("ema 13/48", V.EMA_MODE, lambda f: V.filter_name(f)["ema"])]
    fidx = np.arange(V.NF)
    for nm, modes, get in axes:
        for md in modes:
            sel = np.array([get(f) == md for f in fidx])
            cells = []
            for mk in MK:
                for blk, src in (("res", data[mk][0]), ("lock", lockm[mk])):
                    v = []
                    for s in ("long", "short", "both"):
                        pt = src[s]["perTrade"][sel]
                        n = src[s]["n"][sel]
                        pt = np.where(n >= (MIN_N if blk == "res" else 30), pt, np.nan)
                        v.append(pt)
                    cells.append(np.nanmean(np.concatenate([x.ravel() for x in v])))
            print(f"{nm:<12} {md:<14} " + "".join(f"{c:>+16.4f}" for c in cells))
    print("\n  A condition is only worth its place if it is BETTER THAN `off` in all four columns.")

    print("\n" + "=" * 96)
    print("GEOMETRY AXES, same marginal read")
    print("=" * 96)
    gi = np.arange(V.NG)
    gax = [("IB length", [f"{x}m" for x in V.IB_LEN], lambda g: f"{gname(g)['ib']}m"),
           ("retrace", [f"{x:.2f}" for x in V.RETR], lambda g: f"{gname(g)['retr']:.2f}"),
           ("stop", [f"{x:.2f}" for x in V.STOPF], lambda g: f"{gname(g)['stop']:.2f}"),
           ("target", ["none"] + [f"{x:.2f}" for x in V.TGT[:-1]],
            lambda g: "none" if gname(g)['tgt'] > 90 else f"{gname(g)['tgt']:.2f}"),
           ("flatten", [f"{x//60:02d}:{x%60:02d}" for x in V.FLAT],
            lambda g: f"{gname(g)['flat']//60:02d}:{gname(g)['flat']%60:02d}")]
    print(f"{'axis':<12} {'setting':<14} " +
          "".join(f"{mk[:-1]+' '+b:>16}" for mk in MK for b in ("res", "lock")))
    for nm, modes, get in gax:
        for md in modes:
            sel = np.array([get(g) == md for g in gi])
            cells = []
            for mk in MK:
                for blk, src in (("res", data[mk][0]), ("lock", lockm[mk])):
                    v = []
                    for s in ("long", "short", "both"):
                        pt = src[s]["perTrade"][:, sel]
                        n = src[s]["n"][:, sel]
                        v.append(np.where(n >= (MIN_N if blk == "res" else 30), pt, np.nan))
                    cells.append(np.nanmean(np.concatenate([x.ravel() for x in v])))
            print(f"{nm:<12} {md:<14} " + "".join(f"{c:>+16.4f}" for c in cells))


if __name__ == "__main__":
    main()
