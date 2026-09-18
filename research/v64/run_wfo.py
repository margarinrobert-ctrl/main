"""V64 walk-forward on the V61 CVD rule.

THE ONLY HONEST FORM. `STUDY_EDGELAB` recorded that a walk-forward is CONTAMINATED if the
parameters were chosen on the whole training span -- rolling folds inside a discovery block showed
5/6 positive and meant nothing. So the selection is re-run INSIDE every training window here and
only the test window is read. Nothing outside a fold's training data touches that fold's choice.

THE COMPARISON THAT MATTERS IS NOT "IS THE WALK-FORWARD POSITIVE". Six re-optimisers on this
branch have now lost to the author's fixed constants (`STUDY_APM_WFO`, `STUDY_IBS_SESSION`,
`STUDY_V63_TREND_VWAP`, `STUDY_TRENDDAY_EMA`, `STUDY_V33_OPTIMIZER`, `STUDY_APM_VWAP`), so every
fold carries four arms:

  RE-CHOSEN   the best training cell of a declared grid, re-picked every fold
  FIXED       the shipped incumbent, never re-chosen
  FIXED-15m   the shipped high-activity preset, never re-chosen
  RANDOM      a cell drawn uniformly from the SAME grid each fold -- the null that asks whether
              selecting from this family beats picking from it arbitrarily

WHY THIS IS CHEAP. A configuration's trades depend only on its own parameters, not on the fold, so
every cell is evaluated ONCE over the whole series and a fold's score is a slice of its trades by
signal bar. 19,200 evaluations answer 2 schemes x 8 folds x 4 arms.
"""
from __future__ import annotations

import itertools
import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "v61"))

import v64opt as O   # noqa: E402
import v61core as V  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

# the declared grid -- centred on the shipped family, with the four axes fANOVA called noise
# (adaptive stop, prior-session-high, MA200 floor, max hold) held at the shipped value
ENTS = (15, 20, 30, 40, 55)
EXNS = (10, 20, 30, 40)
STOPS = (1.5, 2.0, 2.5, 3.0)
TPS = (0.0, 3.0, 4.0, 6.0)
KS = (2, 3, 4, 5)
WS = (5, 10, 20, 30, 40)
TFS = (15, 30, 60)
MIN_TRAIN, MIN_TEST = 15, 5

FIXED = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20,
             use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)
FIXED15 = dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30,
               use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def cells():
    for tf, e, x, s, t, k, w in itertools.product(TFS, ENTS, EXNS, STOPS, TPS, KS, WS):
        yield dict(tf=tf, ent=e, exN=x, stop=s, tp=t, hold=480, adapt=0, k=k, w=w,
                   use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)


def folds(dates, train_q, test_q=1):
    """Calendar-quarter folds. Returns (train_mask_fn, test_mask_fn) as timestamp bounds."""
    q = pd.PeriodIndex(dates, freq="Q").unique().sort_values()
    out = []
    for i in range(train_q, len(q) - test_q + 1):
        tr = (q[max(0, i - train_q)].start_time, q[i - 1].end_time)
        te = (q[i].start_time, q[i + test_q - 1].end_time)
        out.append((tr, te, str(q[i])))
    return out


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in TFS}
    times = {tf: pd.DatetimeIndex(Ds[tf]["ix"]) for tf in TFS}

    grid = list(cells())
    print(f"evaluating {len(grid):,} declared cells once each over the whole series ...")
    store = []
    for p in grid:
        R, pct, blk, sig = O.evaluate(Ds[p["tf"]], p)
        store.append((times[p["tf"]][sig].to_numpy() if len(sig) else np.array([], "datetime64[ns]"),
                      pct.astype(np.float32)))
    print(f"  done. median trades per cell {np.median([len(s[1]) for s in store]):.0f}")

    all_dates = times[30]
    schemes = {"rolling 4Q train / 1Q test": folds(all_dates, 4),
               "expanding train / 1Q test": None}
    q = pd.PeriodIndex(all_dates, freq="Q").unique().sort_values()
    exp = []
    for i in range(4, len(q)):
        exp.append(((q[0].start_time, q[i - 1].end_time), (q[i].start_time, q[i].end_time),
                    str(q[i])))
    schemes["expanding train / 1Q test"] = exp

    def score(ci, lo, hi):
        ts, v = store[ci]
        if len(ts) == 0:
            return 0, 0.0, np.nan
        m = (ts >= np.datetime64(lo)) & (ts <= np.datetime64(hi))
        if not m.any():
            return 0, 0.0, np.nan
        vv = v[m]
        return int(m.sum()), float(vv.sum()), float(vv.mean())

    rng = np.random.default_rng(3)
    summary = []
    for sname, fl in schemes.items():
        line(f"WALK-FORWARD -- {sname}")
        print(f"  {'test fold':10s}{'chosen (tf/ent/ex/stop/tp/k/w)':34s}"
              f"{'IS tot%':>9s}{'IS n':>6s}{'OOS n':>7s}{'OOS tot%':>10s}"
              f"{'FIXED':>9s}{'FIXED15':>9s}{'RANDOM':>9s}")
        rows = []
        idx_fixed = next(i for i, p in enumerate(grid)
                         if all(p[a] == FIXED[a] for a in ("tf", "ent", "exN", "stop", "tp", "k", "w")))
        idx_f15 = next(i for i, p in enumerate(grid)
                       if all(p[a] == FIXED15[a] for a in ("tf", "ent", "exN", "stop", "tp", "k", "w")))
        for (trlo, trhi), (telo, tehi), label in fl:
            best, bv, bn = -1, -1e18, 0
            for ci in range(len(grid)):
                n, tot, _ = score(ci, trlo, trhi)
                if n >= MIN_TRAIN and tot > bv:
                    best, bv, bn = ci, tot, n
            if best < 0:
                continue
            n_o, tot_o, _ = score(best, telo, tehi)
            _, f_o, _ = score(idx_fixed, telo, tehi)
            _, f15_o, _ = score(idx_f15, telo, tehi)
            rnd = [score(rng.integers(len(grid)), telo, tehi)[1] for _ in range(200)]
            p = grid[best]
            rows.append(dict(fold=label, ci=best, is_tot=bv, is_n=bn, oos_n=n_o, oos_tot=tot_o,
                             fixed=f_o, fixed15=f15_o, rnd=float(np.mean(rnd)),
                             **{a: p[a] for a in ("tf", "ent", "exN", "stop", "tp", "k", "w")}))
            tag = "{}/{}/{}/{}/{}/{}/{}".format(p["tf"], p["ent"], p["exN"], p["stop"],
                                                 p["tp"], p["k"], p["w"])
            print(f"  {label:10s}{tag:34s}"
                  f"{bv:>9.2f}{bn:>6d}{n_o:>7d}{tot_o:>10.2f}{f_o:>9.2f}{f15_o:>9.2f}"
                  f"{np.mean(rnd):>9.2f}")
        R = pd.DataFrame(rows)
        R.to_parquet(f"results/v64/wfo_{sname.split()[0]}.parquet")
        print(f"\n  {'arm':22s}{'total OOS %':>13s}{'mean/fold':>11s}{'folds positive':>16s}"
              f"{'median/fold':>13s}")
        for arm, col in (("RE-CHOSEN per fold", "oos_tot"), ("FIXED incumbent", "fixed"),
                         ("FIXED 15m preset", "fixed15"), ("RANDOM from the grid", "rnd")):
            v = R[col]
            print(f"  {arm:22s}{v.sum():>13.2f}{v.mean():>11.2f}"
                  f"{f'{int((v>0).sum())}/{len(v)}':>16s}{v.median():>13.2f}")
        base_is = R["is_tot"].sum()
        wfe = R["oos_tot"].sum() / base_is if base_is > 0 else np.nan
        print(f"\n  walk-forward efficiency (sum OOS / sum IS) {wfe:.3f}   "
              f"-- IS totals cover {R['is_n'].sum():,} trades against {R['oos_n'].sum():,} OOS")
        print(f"  RE-CHOSEN beats FIXED in {int((R['oos_tot'] > R['fixed']).sum())}/{len(R)} folds, "
              f"FIXED-15m in {int((R['oos_tot'] > R['fixed15']).sum())}/{len(R)}, "
              f"and a RANDOM grid cell in {int((R['oos_tot'] > R['rnd']).sum())}/{len(R)}")
        summary.append((sname, R, wfe))

        print(f"\n  PARAMETER STABILITY -- does the optimiser settle?")
        for a in ("tf", "ent", "exN", "stop", "tp", "k", "w"):
            vc = R[a].value_counts()
            agree = 100 * vc.iloc[0] / len(R)
            print(f"    {a:6s} chosen values {dict(vc)}   modal share {agree:.0f}%"
                  f"   agrees with the shipped value in "
                  f"{int((R[a] == FIXED[a]).sum())}/{len(R)} folds")

    line("THE AGGREGATE READ")
    print(f"  {'scheme':30s}{'arm':22s}{'OOS total %':>13s}{'OOS trades':>12s}"
          f"{'%/trade':>10s}{'PF':>8s}")
    for sname, R, _ in summary:
        for arm, col in (("RE-CHOSEN per fold", "oos_tot"), ("FIXED incumbent", "fixed"),
                         ("FIXED 15m preset", "fixed15")):
            tot = R[col].sum()
            n = R["oos_n"].sum() if col == "oos_tot" else np.nan
            print(f"  {sname:30s}{arm:22s}{tot:>13.2f}"
                  f"{(f'{int(n):,}' if col == 'oos_tot' else '-'):>12s}"
                  f"{(tot / n if col == 'oos_tot' and n else float('nan')):>10.4f}{'-':>8s}")
    print("\n  Six re-optimisers on this branch have lost to the author's fixed constants.")
    print("  The table above is the seventh test of that, on the one rule that works.")
