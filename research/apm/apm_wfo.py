"""Walk-forward optimisation of the Saty-phase / ATR-normalised-momentum rule as configured.

THE CONFIGURATION AS GIVEN, and how each number maps onto the engine. Ten of the twelve map
cleanly; two do not and are flagged rather than guessed:

  21              pivot EMA length                     -> ema   = 21
  21              ATR length                           -> atr   = 21   (the port's default is 14)
  4               smoothing of the raw phase           -> osc   = 4    (default 3)
  100 / -100      the extended zones                   -> dist  = 3.0  -- the engine's threshold is
                                                          thr = 100 * dist / 3, so dist 3.0 IS the
                                                          +/-100 band. Same number, different unit.
  0930-1030       entry window                         -> ent0 = 570, ent1 = 630
  11              NOT MAPPED -- see below
  0               NOT MAPPED -- see below
  Opposing +/-100 exit at the opposite extreme         -> opp_exit_on = True
  61.8            the golden-ratio zone                -> NOT AN AXIS in this engine: the port
                                                          gates on the extended band only, so the
                                                          61.8 level is drawn and never traded on.
  0930-1600       cash session                         -> the USIndex profile, cash close 960
  2.5             VWAP band, in ATR                    -> vwap  = 2.5

THE TWO UNMAPPED NUMBERS. `11` and `0` sit between the entry window and the exit rule. In the
NinjaScript this port came from, the fields in that position are a bar/trade cap and an offset, and
the port does not implement either -- it takes one position at a time and never re-enters inside a
session, which is a cap of 1. If they mean something else, say so and I will re-run: they are the
only two numbers below that are assumed rather than read.

WHAT A WALK-FORWARD ANSWERS. Not "is this profitable" -- the block split answers that. It answers
whether the PARAMETERS are worth choosing: an optimiser picks them inside each training window and
is then read on the window it has never seen, against the same configuration held fixed. On this
branch that test has been run five times (`STUDY_IBS_SESSION`, `STUDY_APM_VWAP`,
`STUDY_TRENDDAY_EMA`, `STUDY_V60`, `STUDY_V63`) and the re-optimiser lost to the author's constants
every time. Sixth run.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apm_core as C  # noqa: E402

USER = dict(ema=21, atr=21, osc=4, dist=3.0, vwap=2.5, ent0=570, ent1=630)

# centred on the user's values so their own cell is inside the search
GRID = dict(ema=(13, 21, 34), atr=(14, 21, 28), osc=(2, 3, 4, 6),
            dist=(2.0, 2.5, 3.0, 3.5), vwap=(2.0, 2.5, 3.0, 99.0),
            ent1=(600, 630, 660, 720))
AXES = list(GRID)
MARKETS = (("NQ", 10, 12, 3), ("US100", 15, 24, 6), ("US30", 15, 24, 6))
MIN_TRAIN = 20


def cells():
    return [dict(zip(AXES, v)) for v in itertools.product(*[GRID[a] for a in AXES])]


def run_all(market, tf):
    """Every cell once over the whole history; keep the session key and the percent of price."""
    D = C.load(market, tf)
    out = []
    for cell in cells():
        cfg = dict(USER)
        cfg.update(cell)
        cfg["tf"] = tf
        tr, _ = C.run(D, cfg=cfg)
        if not len(tr):
            out.append((np.zeros(0, np.int64), np.zeros(0)))
            continue
        key = tr["date"].to_numpy()
        pct = 100.0 * tr["pts"].to_numpy() / tr["epx"].to_numpy()
        out.append((key, pct))
    return D, out


def user_index():
    for i, cell in enumerate(cells()):
        if all(cell[a] == USER[a] for a in AXES):
            return i
    return None


def folds_of(D, train_m, test_m, expanding):
    ts = pd.DatetimeIndex(D["dates"])
    d0 = pd.Timestamp(ts[0]).normalize()
    d0 = pd.Timestamp(year=d0.year, month=d0.month, day=1) + pd.DateOffset(months=1)
    dend = pd.Timestamp(ts[-1])
    k = lambda t: t.year * 10000 + t.month * 100 + t.day
    out, t = [], d0
    while t + pd.DateOffset(months=train_m + test_m) <= dend + pd.DateOffset(days=1):
        lo = d0 if expanding else t
        out.append((k(lo), k(t + pd.DateOffset(months=train_m)),
                    k(t + pd.DateOffset(months=train_m + test_m))))
        t = t + pd.DateOffset(months=test_m)
    return out


def main():
    print(__doc__)
    ui = user_index()
    print(f"  grid: {len(cells()):,} cells over {len(AXES)} axes; the given configuration is cell "
          f"#{ui} and is inside the search.\n")
    summary = []
    for market, tf, train_m, test_m in MARKETS:
        D, res = run_all(market, tf)
        B = C.blocks(D)
        ukey, upct = res[ui]

        print("=" * 116)
        print(f"{market} {tf}m -- the configuration AS GIVEN, on this branch's own block split")
        print("=" * 116)
        for b, m in B.items():
            sess = np.where(D["mod"] >= 1080, D["nkey"], D["key"])
            days = np.unique(sess[m])
            sel = np.isin(ukey, days)
            p = upct[sel]
            if len(p) < 3:
                print(f"  {b:11s} n {len(p)}")
                continue
            w = p > 0
            print(f"  {b:11s} n {len(p):4d}  {p.mean():+.4f} %/trade  total {p.sum():+7.2f}%  "
                  f"PF {p[w].sum()/max(1e-9,-p[~w].sum()):5.2f}  win {100*w.mean():5.1f}%")

        for expanding in (False, True):
            F = folds_of(D, train_m, test_m, expanding)
            mode = "expanding" if expanding else f"rolling {train_m}m"
            print(f"\n  WALK-FORWARD, {mode} train {train_m}m / test {test_m}m, "
                  f"{len(F)} candidate folds")
            print(f"    {'fold':<20}{'chosen':<44}{'IS':>8}{'OOS':>8}{'n':>5}{'WFE':>6} | "
                  f"{'given OOS':>10}{'n':>5}")
            tc = tn = tg = gn = 0.0
            pw = pg = nf = 0
            picks = []
            for a, b, c_ in F:
                best, bv = None, -np.inf
                for i, (kk, pp) in enumerate(res):
                    m = (kk >= a) & (kk < b)
                    if m.sum() < MIN_TRAIN:
                        continue
                    v = pp[m].sum()
                    if v > bv:
                        bv, best = v, i
                if best is None:
                    continue
                kk, pp = res[best]
                mi = (kk >= a) & (kk < b)
                mo = (kk >= b) & (kk < c_)
                gm = (ukey >= b) & (ukey < c_)
                if mo.sum() == 0 and gm.sum() == 0:
                    continue
                nf += 1
                picks.append(cells()[best])
                ism = pp[mi].mean() if mi.sum() else np.nan
                oos = pp[mo].mean() if mo.sum() else np.nan
                giv = upct[gm].mean() if gm.sum() else np.nan
                lab = " ".join(f"{x}={cells()[best][x]}" for x in AXES)
                print(f"    {a}-{c_:<11}{lab:<44}{ism:>+8.3f}{oos:>+8.3f}{mo.sum():>5}"
                      f"{(oos/ism if ism else np.nan):>6.2f} | {giv:>+10.3f}{gm.sum():>5}")
                if mo.sum():
                    tc += pp[mo].sum(); tn += mo.sum(); pw += int(pp[mo].mean() > 0)
                if gm.sum():
                    tg += upct[gm].sum(); gn += gm.sum(); pg += int(upct[gm].mean() > 0)
            if not nf:
                print("    no scorable fold")
                continue
            base = tg / max(gn, 1)
            # walk-forward efficiency is only defined against a POSITIVE baseline; dividing by a
            # negative one produces a number with the wrong sign and no meaning.
            wfe = (tc / max(tn, 1)) / base if base > 0 else np.nan
            wtxt = f"WFE {wfe:5.2f}" if np.isfinite(wfe) else "WFE n/a (given baseline <= 0)"
            print(f"    STITCHED: re-chosen {tc/max(tn,1):+.4f} %/trade on {int(tn)} trades "
                  f"({pw}/{nf} folds +)  |  given {base:+.4f} on {int(gn)} "
                  f"({pg}/{nf} folds +)  |  {wtxt}   difference "
                  f"{tc/max(tn,1) - base:+.4f}")
            kept = {a: sum(1 for p in picks if p[a] == USER[a]) for a in AXES}
            print("    the optimiser kept the given value in: "
                  + ", ".join(f"{a} {kept[a]}/{len(picks)}" for a in AXES))
            agree = np.mean([np.mean([p[a] == picks[0][a] for p in picks]) for a in AXES])
            print(f"    the optimiser's own choices agree with its FIRST fold's choice "
                  f"{100*agree:.0f}% of the time, averaged over the six axes")
            summary.append((market, mode, tc / max(tn, 1), base, wfe, pw, pg, nf, agree))

    print("\n" + "=" * 116)
    print("SUMMARY -- walk-forward efficiency is the re-chosen result over the given one")
    print("=" * 116)
    print(f"  {'market':8s}{'mode':14s}{'re-chosen':>11s}{'given':>10s}{'WFE':>7s}"
          f"{'folds + (re/given)':>22s}")
    for m, mo, c, g, w, pw, pg, nf, ag in summary:
        wt = f"{w:>7.2f}" if np.isfinite(w) else f"{'n/a':>7s}"
        print(f"  {m:8s}{mo:14s}{c:>+11.4f}{g:>+10.4f}{wt}{f'{pw}/{nf} vs {pg}/{nf}':>22s}")
    fin = [s[4] for s in summary if np.isfinite(s[4])]
    if fin:
        print(f"\n  mean WFE {np.mean(fin):.2f} over the {len(fin)} cells where the given"
              " configuration is profitable and the ratio is defined. Below 1.00 means")
        print("  re-optimising the parameters made it WORSE than leaving them alone.")
    beat = sum(1 for s in summary if s[2] > s[3])
    print(f"  the re-optimiser beat the given configuration in {beat} of {len(summary)} cells, and"
          f" on folds-positive in {sum(1 for s in summary if s[5] > s[6])} of {len(summary)}.")


if __name__ == "__main__":
    main()
