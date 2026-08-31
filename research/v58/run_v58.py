"""The 777,600-configuration Initial Balance sweep, run on the RESEARCH block only.

Nothing in this file may read the locked block. `v58judge.py` does that once.

TWO CORRECTIONS ARE BUILT IN, both of them traps this branch has already paid for once:

  * SCORING IS IN ATR UNITS, NOT IN R. In R a configuration can buy its own score by moving the
    stop closer to the entry -- retracement 0.50 against a 0.60 stop leaves a risk of a TENTH of
    the Initial Balance range, so the identical points move scores ten times higher and the
    ranking fills up with collapsed denominators (`STUDY_SWEEP_110K.md`). Profit factor is taken
    in POINTS for the same reason.

  * THE FILL BAR IS TESTED FOR THE STOP. When entry and stop sit a tenth of a range apart they
    are routinely inside one 15-minute bar, and a bar engine that skips the fill bar hands the
    configuration a free option. Both models are run and the gap between them is printed; where
    a result exists only in the optimistic one, it is an artifact of bar resolution.

Sharpe is over EVERY trading day in the block, zero-filled on days that did not trade, so a
filter is never paid for trading less. The SHARE of the grid that is profitable is printed
before any row of it.
"""
from __future__ import annotations

import numpy as np
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402

SPLIT = 0.65
MK = ["US30L", "US100L"]
MIN_N = 60


def blocks(D):
    k = int(D * SPLIT)
    return np.arange(k), np.arange(k, D)


def _planes(Az, Pz, ok, msk, ndays):
    """Sums over days for one side: ATR units, points, and the daily-total moments."""
    z = np.zeros((V.NF, V.NG))
    sA, sN, sPp, sPn, sA2 = z.copy(), z.copy(), z.copy(), z.copy(), z.copy()
    for li in range(len(V.IB_LEN)):
        sl = slice(li * 450, (li + 1) * 450)
        m = msk[:, :, li].astype(np.float64)
        sA[:, sl] = m.T @ Az[:, sl]
        sN[:, sl] = m.T @ ok[:, sl].astype(np.float64)
        sPp[:, sl] = m.T @ np.clip(Pz[:, sl], 0, None)
        sPn[:, sl] = m.T @ np.clip(Pz[:, sl], None, 0)
        sA2[:, sl] = m.T @ (Az[:, sl] ** 2)
    return sA, sN, sPp, sPn, sA2


def aggregate(A, P, mL, mS, idx, NGs=None):
    """A/P are (2, days, NG) ATR-unit and points outcomes for long and short."""
    n = len(idx)
    okL, okS = np.isfinite(A[0][idx]), np.isfinite(A[1][idx])
    AL, AS = np.nan_to_num(A[0][idx]), np.nan_to_num(A[1][idx])
    PL, PS = np.nan_to_num(P[0][idx]), np.nan_to_num(P[1][idx])
    fL, fS = mL[idx], mS[idx]
    pL = _planes(AL, PL, okL, fL, n)
    pS = _planes(AS, PS, okS, fS, n)
    cross = np.zeros((V.NF, V.NG))
    for li in range(len(V.IB_LEN)):
        sl = slice(li * 450, (li + 1) * 450)
        mm = (fL[:, :, li] & fS[:, :, li]).astype(np.float64)
        cross[:, sl] = mm.T @ (AL[:, sl] * AS[:, sl])
    out = {}
    for nm, p in (("long", pL), ("short", pS)):
        out[nm] = _metrics(*p, n)
    out["both"] = _metrics(pL[0] + pS[0], pL[1] + pS[1], pL[2] + pS[2], pL[3] + pS[3],
                           pL[4] + pS[4] + 2 * cross, n)
    return out


def _metrics(sA, sN, sPp, sPn, sA2, ndays):
    mean = sA / ndays
    var = np.maximum(sA2 / ndays - mean ** 2, 1e-12)
    return dict(n=sN, totA=sA,
                perTrade=np.where(sN > 0, sA / np.maximum(sN, 1), np.nan),
                pf=np.where(sPn < 0, sPp / np.maximum(-sPn, 1e-9), np.nan),
                sharpe=mean / np.sqrt(var) * np.sqrt(252.0))


def prep(mk, fillbar=1):
    F = V.build(mk)
    R, amb = V.outcomes(F, V.COST_PTS[mk], fillbar=fillbar)
    risk, atr = V.risk_atr(F)
    D = F["D"]
    R3 = R.reshape(D, len(V.IB_LEN), 2, 450)
    A, P = [], []
    for s in range(2):
        Rs = np.ascontiguousarray(R3[:, :, s, :].reshape(D, V.NG))
        pts = Rs * risk                              # points, net of cost
        A.append(pts / atr)                          # ATR units at the plan bar
        P.append(pts)
    return F, A, P, amb


def main():
    os.makedirs("results/v58", exist_ok=True)
    for mk in MK:
        t0 = time.time()
        F, A, P, amb = prep(mk, fillbar=1)
        _, A0, P0, _ = prep(mk, fillbar=0)
        mL, mS = V.filters(F)
        D = F["D"]
        res, lock = blocks(D)
        mr = aggregate(A, P, mL, mS, res)
        m0 = aggregate(A0, P0, mL, mS, res)
        print(f"\n=== {mk}: {D} sessions, {str(F['dates'][0])[:10]} .. {str(F['dates'][-1])[:10]} "
              f" research {len(res)} / locked {len(lock)}   ({time.time()-t0:.1f}s)")
        np.savez_compressed(f"results/v58/{mk}_research.npz",
                            **{f"{s}_{k}": v for s, d in mr.items() for k, v in d.items()},
                            **{f"opt_{s}_{k}": v for s, d in m0.items() for k, v in d.items()},
                            ndays=len(res), D=D)
        for s in ("long", "short"):
            np.save(f"results/v58/{mk}_A_{s}.npy", A[0 if s == "long" else 1].astype(np.float32))
            np.save(f"results/v58/{mk}_P_{s}.npy", P[0 if s == "long" else 1].astype(np.float32))
        np.savez_compressed(f"results/v58/{mk}_masks.npz", mL=mL, mS=mS, res=res, lock=lock)
        tot = prof = 0
        for s in ("long", "short", "both"):
            n, pt = mr[s]["n"], mr[s]["perTrade"]
            ok = n >= MIN_N
            tot += int(ok.sum()); prof += int(((pt > 0) & ok).sum())
            print(f"    {s:5s} scorable {int(ok.sum()):7,d}  profitable {(pt>0)[ok].mean()*100:5.1f}%"
                  f"  median ATR/trade {np.nanmedian(pt[ok]):+.4f}  median PF "
                  f"{np.nanmedian(mr[s]['pf'][ok]):.3f}")
        print(f"    GRID SHAPE: {prof:,}/{tot:,} = {prof/max(tot,1)*100:.1f}% of scorable "
              f"configurations are profitable on research.")
        okb = mr["both"]["n"] >= MIN_N
        gap = (m0["both"]["perTrade"][okb] - mr["both"]["perTrade"][okb])
        print(f"    EXIT-MODEL GAP (skip the fill bar minus test it): median "
              f"{np.nanmedian(gap):+.4f} ATR/trade, p90 {np.nanpercentile(gap,90):+.4f}. "
              f"{np.mean(gap>0.01)*100:.1f}% of configurations gain more than 0.01 from the "
              f"optimistic model.")


if __name__ == "__main__":
    main()
