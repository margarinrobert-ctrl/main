"""Phase 1 -- the declared grid, scored on RESEARCH ONLY, against a matched control.

THE GRID IS DECLARED BEFORE IT IS RUN and every cell is kept, including the losers, because the
reality check in phase 4 needs the return stream of everything that was tried and not just the
survivor (mechanism-first-alpha, phase 5). The reading taken from this table is its MARGINAL
AVERAGES -- what a timeframe is worth averaged over every other choice -- not its maximum, which
is the maximum of 960 looks and is not evidence of anything.

    tf      x6   1, 2, 3, 5, 15, 30 minutes           <- the user's "1 minute or others"
    window  x5   two 09:00 anchors (92 sessions), three 09:30 anchors (271)
    side    x2   long, both
    stop    x4   1.0 1.5 2.0 2.5 xATR
    target  x4   none, 1R, 2R, 3R
    = 960 cells
"""
from __future__ import annotations
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bars as B, sim as S, control as C

TFS = [1, 2, 3, 5, 15, 30]
WINDOWS = [(540, 555, 570, "09:00-09:15"), (540, 570, 570, "09:00-09:30"),
           (570, 585, 585, "09:30-09:45"), (570, 600, 600, "09:30-10:00"),
           (570, 630, 630, "09:30-10:30")]
SIDES = ["long", "both"]
STOPS = [1.0, 1.5, 2.0, 2.5]
TGTS = [("none", 0.0), ("r", 1.0), ("r", 2.0), ("r", 3.0)]
DRAWS = 120
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid.npz")


def main():
    rows = []; streams = {}
    t0 = time.time()
    for tf in TFS:
        b = B.bars(tf); a = B.atr(b, 14)
        for (r0, r1, arm, wname) in WINDOWS:
            # the split is computed on the sessions THIS window can produce
            hitU, hitD, _u, _d = S.triggers(b, r0, r1, arm, 960, a, 0.0, "both", True)
            sess = np.unique(b["si"][np.flatnonzero(hitU | hitD)])
            if len(sess) < 20:
                continue
            cut, nsess = B.split(b, sess)
            for side in SIDES:
                trig = S.triggers(b, r0, r1, arm, 960, a, 0.0, side, True)[:2]
                for sk in STOPS:
                    stopD = sk * a
                    for (tm, tk) in TGTS:
                        tgtD = (tk * stopD) if tm == "r" else np.zeros(b["n"])
                        r = S.run(b, a, r0=r0, r1=r1, arm=arm, last=960, flat=960,
                                  stop_k=sk, tgt_k=tk, tgt_mode=tm, side=side,
                                  trig=trig)
                        res = b["si"][r["eb"]] < cut
                        sc = S.score(r, res)
                        cell = f"{tf}m|{wname}|{side}|s{sk}|{tm}{tk}"
                        if sc["n"] >= 25:
                            ct = C.matched(b, r, stopD, tgtD, draws=DRAWS, block=res, seed=11)
                            p = ct["p"]; pct = ct["pct"]; cpf = ct["ctrl_pf"]
                        else:
                            p = pct = cpf = np.nan
                        m = control_mde(r["pnl"][res])
                        rows.append(dict(tf=tf, window=wname, side=side, stop=sk, tmode=tm, tk=tk,
                                         nsess=nsess, **sc, p=p, pct=pct, ctrl_pf=cpf, mde=m))
                        # keep the per-session stream for the reality check
                        if sc["n"] >= 25:
                            streams[cell] = daily(b, r, res)
        print(f"  tf={tf}m done  {len(rows)} cells  {time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(OUT, rows=json.dumps(rows, default=float),
                        **{f"s::{k}": v for k, v in streams.items()})
    print(f"\n{len(rows)} cells, {len(streams)} kept streams -> {OUT}  ({time.time()-t0:.0f}s)")


def control_mde(p):
    return C.mde(p) if len(p) >= 5 else np.nan


def daily(b, r, mask):
    """Per-session net P&L, which is the unit the reality check and PBO resample."""
    s = b["si"][r["eb"]][mask]; p = r["pnl"][mask]
    if len(s) == 0:
        return np.zeros(0)
    u = np.unique(s)
    return np.array([p[s == x].sum() for x in u])


if __name__ == "__main__":
    main()
