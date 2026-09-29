"""PASS TWO. The retracement ridge ran off the grid, so the grid is extended along it.

Pass one's marginal read is monotone in the retracement depth and it replicates in ALL FOUR
columns -- US30 research -0.2624 -> -0.1185, US30 locked -0.2432 -> -0.0838, US100 research
-0.2790 -> -0.0805, US100 locked -0.1794 -> +0.0333 as the entry moves from the broken edge to
the middle of the Initial Balance. A gradient that reproduces on a block it was not chosen on is
the standard of evidence `STUDY_V17_FEATURES.md` shipped on, and `STUDY_TURTLE_15M.md` records
the matching caution: a ridge that runs off the grid means the grid was drawn in the wrong place.

So pass two moves the entry from the middle of the range to the FAR EDGE -- 0.50 to 1.20 of the
range back inside -- which at 1.00 is no longer a retracement into a breakout at all but a FADE
of it, entered where the break started.

MULTIPLICITY IS NOW TWO PASSES OF 777,600. Pass two is a second look at the same two markets and
nothing here can be read as if it were the first.
"""
from __future__ import annotations

import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402

V.RETR = np.array([0.50, 0.60, 0.75, 0.90, 1.00], np.float64)
V.STOPF = np.array([0.80, 1.00, 1.30, 1.60, 2.00], np.float64)

from research.v58 import run_v58 as R                                   # noqa: E402
R.V = V


def main():
    os.makedirs("results/v58b", exist_ok=True)
    orig = "results/v58"
    R.__dict__["MK"] = ["US30L", "US100L"]
    import research.v58.run_v58 as rr
    # redirect the output directory
    src = rr.main.__globals__
    for mk in R.MK:
        F, A, P, amb = R.prep(mk, fillbar=1)
        mL, mS = V.filters(F)
        D = F["D"]
        res, lock = R.blocks(D)
        mr = R.aggregate(A, P, mL, mS, res)
        np.savez_compressed(f"results/v58b/{mk}_research.npz",
                            **{f"{s}_{k}": v for s, d in mr.items() for k, v in d.items()},
                            ndays=len(res), D=D)
        for i, s in enumerate(("long", "short")):
            np.save(f"results/v58b/{mk}_A_{s}.npy", A[i].astype(np.float32))
            np.save(f"results/v58b/{mk}_P_{s}.npy", P[i].astype(np.float32))
        np.savez_compressed(f"results/v58b/{mk}_masks.npz", mL=mL, mS=mS, res=res, lock=lock)
        tot = prof = 0
        for s in ("long", "short", "both"):
            n, pt = mr[s]["n"], mr[s]["perTrade"]
            ok = n >= R.MIN_N
            tot += int(ok.sum()); prof += int(((pt > 0) & ok).sum())
        print(f"=== {mk}  PASS TWO: {prof:,}/{tot:,} = {prof/max(tot,1)*100:.1f}% of scorable "
              f"configurations profitable on research")

    # the marginal read, the only thing pass two is allowed to answer
    print("\n" + "=" * 96)
    print("RETRACEMENT DEPTH, marginal over the whole extended grid (ATR units per trade)")
    print("=" * 96)
    print(f"{'entry, fraction of range back inside':<38} " +
          "".join(f"{mk[:-1]+' '+b:>15}" for mk in R.MK for b in ("res", "lock")))
    data = {}
    for mk in R.MK:
        z = np.load(f"results/v58b/{mk}_research.npz")
        m = {s: {k: z[f"{s}_{k}"] for k in ("n", "perTrade", "pf")} for s in ("long", "short", "both")}
        A = [np.load(f"results/v58b/{mk}_A_{s}.npy").astype(np.float64) for s in ("long", "short")]
        P = [np.load(f"results/v58b/{mk}_P_{s}.npy").astype(np.float64) for s in ("long", "short")]
        mm = np.load(f"results/v58b/{mk}_masks.npz")
        data[mk] = (m, R.aggregate(A, P, mm["mL"], mm["mS"], mm["lock"]))
    gi = np.arange(V.NG)
    depth = np.array([V.RETR[(g // 90) % 5] for g in gi])
    for d in V.RETR:
        sel = depth == d
        cells = []
        for mk in R.MK:
            for blk, src in (("res", data[mk][0]), ("lock", data[mk][1])):
                v = []
                for s in ("long", "short", "both"):
                    pt = src[s]["perTrade"][:, sel]
                    n = src[s]["n"][:, sel]
                    v.append(np.where(n >= (R.MIN_N if blk == "res" else 30), pt, np.nan))
                cells.append(np.nanmean(np.concatenate([x.ravel() for x in v])))
        tag = "  <- a FADE of the break" if d >= 1.0 else ""
        print(f"{d:<38.2f} " + "".join(f"{c:>+15.4f}" for c in cells) + tag)


if __name__ == "__main__":
    main()
