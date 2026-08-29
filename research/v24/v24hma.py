"""HMA CROSS broken out in full, and then the one real signal V24 found: LAG.

PART A -- HMA CROSS, EVERY CELL. The Hull average was in the V24 grid (7 types x 9 pairs x 2 modes),
but the tables reported the marginal by TYPE (pooling STATE and CROSS) and the marginal by MODE
(pooling types). Nobody had seen HMA x CROSS on its own, so it is printed here cell by cell: 9 pairs
x 4 CHOP x 2 timeframes, against the no-MA baseline at the same timeframe and CHOP, and against a
same-selectivity control on the best cell.

PART B -- THE LAG TEST, which is the finding worth chasing. V24's one non-flat result was that
locked profit factor falls MONOTONICALLY with the average lag of the moving average:

    SMA 10.00 -> 1.208   EMA 10.00 -> 1.183   WMA 6.67 -> 1.161
    KAMA 1.25 -> 1.138   DEMA 0.00 -> 1.131   HMA 1.00 -> 1.115   TEMA 0.00 -> 1.114

Type spread was 0.093 PF and pair spread 0.135, both small, but that ordering is perfect. Two
readings fit it and they say opposite things:

  (a) LAG IS THE MECHANISM. A laggier average confirms later, so it only turns up after the move is
      established -- which on this branch's evidence is the safer side of a breakout.
  (b) IT IS AN ARTEFACT OF SELECTIVITY OR OF TYPE. The types differ in more than lag, and a
      per-type average pools nine different pairs.

The discriminating test is a LAG-MATCHED comparison: solve for the WINDOW that gives each type the
SAME average lag, and see whether the types converge. `STUDY_MA_LAG` says they must -- at matched
lag SMA, LMA and EMA correlate 0.9999+ and their trigger sets overlap 89.5-97.3%. If they converge
here too, TYPE is dead as an axis and LAG is the only thing the MA contributes. If the gradient
SURVIVES lag-matching, something other than lag is driving it and reading (a) is wrong.

NOTE WHICH TYPES CANNOT PLAY. DEMA and TEMA have exactly ZERO ramp lag at every window and KAMA is
flat at 1.25 regardless of window, so none of the three can be lag-matched to anything. That is not
a limitation of the test -- it IS the result `STUDY_MA_LAG` reports, and it means those three are a
separate axis rather than slower or faster versions of the first group.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v24")
import v16core as C           # noqa: E402
import v24ma as V             # noqa: E402

TARGET_LAGS = ((2.0, 5.0), (4.0, 10.0), (6.0, 15.0), (10.0, 25.0), (24.0, 60.0))
MATCHABLE = ("SMA", "EMA", "WMA", "HMA")


def window_for(kind, target, lo=2, hi=400, tol=0.25):
    """Smallest window whose average ramp lag is within tol of target, or None if unreachable."""
    best, bestd = None, 1e9
    for n in range(lo, hi + 1):
        d = abs(V.lag_of(kind, n) - target)
        if d < bestd:
            best, bestd = n, d
        if bestd <= tol:
            break
    return (best if bestd <= tol else None), bestd


if __name__ == "__main__":
    V.hdr("A. HMA CROSS, EVERY CELL -- against the no-MA baseline at the same timeframe and CHOP")
    print("   `edge` = locked PF minus that baseline. It is the only column that isolates what the")
    print("   Hull crossover contributed; a raw PF is mostly the base plus the CHOP filter.\n")
    rows = []
    for tf in (15, 30):
        P, sig, O, ch, res, lk = V.prep(tf)
        masks = V.ma_masks(P, sig)
        ok = O["xb"] >= 0
        base = {}
        for cc in V.CHOP_C:
            cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
            base[cc] = (V.stat(P, O, ok & cm & res), V.stat(P, O, ok & cm & lk))
        print(f"   NQ {tf}m")
        print(f"      {'pair':<9}{'CHOP':>7}{'n':>6}{'RES PF':>9}{'RES DD':>8}{'|':>3}{'n':>6}"
              f"{'LOCK PF':>9}{'LOCK R':>9}{'LOCK DD':>9}{'ret/DD':>8}{'baseline':>10}{'edge':>8}")
        for f, s in V.PAIRS:
            for cc in V.CHOP_C:
                cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
                keep = ok & masks[f"HMA {f}/{s} CROSS"] & cm
                a = V.stat(P, O, keep & res)
                b = V.stat(P, O, keep & lk)
                bl = base[cc][1]
                if a is None:
                    continue
                lab = "off" if cc is None else f"<={cc:g}"
                if b is None:
                    print(f"      {f'{f}/{s}':<9}{lab:>7}{a['n']:>6}{a['pf']:>9.3f}{a['dd']:>8.1f}"
                          f"{'|':>3}{'-- under 30 locked trades':>42}")
                    continue
                edge = b["pf"] - bl["pf"]
                rows.append(dict(tf=tf, pair=f"{f}/{s}", chop=lab, n=a["n"], pf=a["pf"],
                                 n_lk=b["n"], pf_lk=b["pf"], R_lk=b["R"], dd_lk=b["dd"],
                                 retdd_lk=b["retdd"], base=bl["pf"], edge=edge))
                print(f"      {f'{f}/{s}':<9}{lab:>7}{a['n']:>6}{a['pf']:>9.3f}{a['dd']:>8.1f}"
                      f"{'|':>3}{b['n']:>6}{b['pf']:>9.3f}{b['R']:>+9.4f}{b['dd']:>9.1f}"
                      f"{b['retdd']:>8.2f}{bl['pf']:>10.3f}{edge:>+8.3f}")
        print()
    h = pd.DataFrame(rows)
    print(f"   HMA CROSS cells that beat their own no-MA baseline on locked: "
          f"{int((h.edge > 0).sum())} of {len(h)} = {float((h.edge > 0).mean()):.0%}.  Chance is 50%.")
    print(f"   mean edge {h.edge.mean():+.3f} PF   |   mean locked drawdown {h.dd_lk.mean():.1f} R"
          f" against the baseline's {h.base.mean():.3f} PF")
    print(f"   best HMA CROSS cell on RESEARCH: "
          f"{h.sort_values('pf', ascending=False).iloc[0].to_dict()}")


def run_pair(P, sig, O, ch, res, lk, kind, fw, sw, mode, cc):
    import v24ma as _V
    c = P["c"]
    fa, sl = _V.ma(kind, c, fw), _V.ma(kind, c, sw)
    up = np.isfinite(fa) & np.isfinite(sl) & (fa > sl)
    if mode == "CROSS":
        crossed = up & ~np.r_[False, up[:-1]]
        up = pd.Series(crossed).rolling(_V.CROSS_WINDOW, min_periods=1).max().to_numpy() > 0
    m = up[sig]
    cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
    ok = O["xb"] >= 0
    return (_V.stat(P, O, ok & m & cm & res), _V.stat(P, O, ok & m & cm & lk))


if __name__ == "__main__":
    V.hdr("B1. SOLVING FOR THE WINDOW THAT GIVES EACH TYPE THE SAME LAG")
    print("   If two averages carry the same lag they are near-duplicates (STUDY_MA_LAG: trigger")
    print("   overlap 89.5-97.3%). Matching on lag is the only way to ask whether TYPE matters.\n")
    plan = {}
    print(f"   {'target lag':<14}" + "".join(f"{k:>22}" for k in MATCHABLE))
    for tl in TARGET_LAGS:
        cells = []
        for k in MATCHABLE:
            wf, df_ = window_for(k, tl[0])
            ws, ds = window_for(k, tl[1])
            if wf is None or ws is None:
                cells.append("unreachable")
                continue
            plan[(tl, k)] = (wf, ws)
            cells.append(f"{wf}/{ws}  (lag {V.lag_of(k,wf):.1f}/{V.lag_of(k,ws):.1f})")
        print(f"   {f'{tl[0]:g} / {tl[1]:g}':<14}" + "".join(f"{c:>22}" for c in cells))
    print("\n   DEMA and TEMA have ZERO ramp lag at EVERY window and KAMA is flat at 1.25 regardless")
    print("   of window, so none of the three can be lag-matched at all. They are a separate axis,")
    print("   not faster or slower members of this one -- which is the STUDY_MA_LAG result.")

    V.hdr("B2. AT MATCHED LAG, DO THE TYPES CONVERGE? -- CHOP <= 40, CROSS mode, both timeframes")
    print("   If TYPE were a real lever the rows would spread. If LAG is the only thing an MA")
    print("   contributes, each row collapses and the COLUMN (lag) is where the variation lives.\n")
    out = []
    for tf in (15, 30):
        P, sig, O, ch, res, lk = V.prep(tf)
        for mode in ("CROSS", "STATE"):
            print(f"   NQ {tf}m  {mode}  CHOP <= 40")
            print(f"      {'target lag':<14}" + "".join(f"{k:>20}" for k in MATCHABLE)
                  + f"{'row spread':>13}")
            for tl in TARGET_LAGS:
                cells, vals = [], []
                for k in MATCHABLE:
                    if (tl, k) not in plan:
                        cells.append("--")
                        continue
                    fw, sw = plan[(tl, k)]
                    a, b = run_pair(P, sig, O, ch, res, lk, k, fw, sw, mode, 40.0)
                    if b is None:
                        cells.append("n<30")
                        continue
                    cells.append(f"{b['pf']:.3f} (n {b['n']})")
                    vals.append(b["pf"])
                    out.append(dict(tf=tf, mode=mode, lag=tl[1], kind=k, pf_lk=b["pf"],
                                    R_lk=b["R"], dd_lk=b["dd"], n_lk=b["n"],
                                    pf_res=(a["pf"] if a else np.nan)))
                spread = (max(vals) - min(vals)) if len(vals) > 1 else np.nan
                print(f"      {f'{tl[0]:g} / {tl[1]:g}':<14}"
                      + "".join(f"{c:>20}" for c in cells)
                      + (f"{spread:>13.3f}" if np.isfinite(spread) else f"{'--':>13}"))
            print()
    L = pd.DataFrame(out)
    L.to_csv("results/v24/v24_lag.csv", index=False)

    V.hdr("B3. THE VERDICT -- is the variation in the TYPE or in the LAG?")
    within = L.groupby(["tf", "mode", "lag"]).pf_lk.agg(lambda x: x.max() - x.min())
    across = L.groupby(["tf", "mode"]).apply(
        lambda g: g.groupby("lag").pf_lk.mean().pipe(lambda s: s.max() - s.min()),
        include_groups=False)
    print(f"   mean spread WITHIN a matched-lag row (across the four TYPES):   {within.mean():.3f} PF")
    print(f"   mean spread ACROSS the lag rows (the LAG axis itself):          {across.mean():.3f} PF")
    print(f"   ratio: the lag axis is {across.mean()/max(within.mean(),1e-9):.2f}x the type axis")
    print()
    g = L.groupby("lag").agg(cells=("pf_lk", "size"), pf_lk=("pf_lk", "mean"),
                             R_lk=("R_lk", "mean"), dd_lk=("dd_lk", "mean"),
                             n_lk=("n_lk", "mean"), pf_res=("pf_res", "mean"))
    print(f"   {'slow-leg lag':<14}{'cells':>7}{'research PF':>13}{'LOCKED PF':>11}{'LOCKED R':>10}"
          f"{'LOCK DD(R)':>12}{'avg n':>8}")
    for k, r in g.iterrows():
        print(f"   {k:<14.0f}{int(r.cells):>7}{r.pf_res:>13.3f}{r.pf_lk:>11.3f}{r.R_lk:>+10.4f}"
              f"{r.dd_lk:>12.1f}{r.n_lk:>8.0f}")
    print(f"\n   monotone in lag on LOCKED? "
          f"{'YES' if list(g.pf_lk) == sorted(g.pf_lk) else 'NO -- the V24 gradient does not survive lag-matching'}")
