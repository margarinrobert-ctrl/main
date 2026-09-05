"""Three things `run_wfo` left open.

(1) WFE COMPARED SPANS OF DIFFERENT LENGTH. Training is 4-12 quarters and testing is 1, so a raw
    sum-OOS / sum-IS ratio is mostly a span ratio. Normalised to %-per-quarter here.
(2) THE FIXED ARMS HAD NO TRADE COUNTS, so their per-trade figures printed as nan.
(3) THE OPTIMISER CONVERGES ON TWO AXES AND WANDERS ON FOUR. It picked entry channel 15 in 9/9
    folds and exit 30 in 8-9/9 -- which is exactly the shipped 15m preset's geometry -- and no
    take profit in 8/9. Its modal share on timeframe, stop, k and w is 44-78%. So: freeze what it
    agrees on, let it re-choose only what it does not, and see whether the wandering axes are what
    cost it. That is the actionable version of a stability table.
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

import v64opt as O  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

ENTS = (15, 20, 30, 40, 55)
EXNS = (10, 20, 30, 40)
STOPS = (1.5, 2.0, 2.5, 3.0)
TPS = (0.0, 3.0, 4.0, 6.0)
KS = (2, 3, 4, 5)
WS = (5, 10, 20, 30, 40)
TFS = (15, 30, 60)
MIN_TRAIN = 15

FIXED = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, k=3, w=20)
FIXED15 = dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, k=3, w=30)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def full(p):
    return dict(hold=480, adapt=0, use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0, **p)


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in TFS}
    times = {tf: pd.DatetimeIndex(Ds[tf]["ix"]) for tf in TFS}

    grid = [dict(tf=tf, ent=e, exN=x, stop=s, tp=t, k=k, w=w)
            for tf, e, x, s, t, k, w in itertools.product(TFS, ENTS, EXNS, STOPS, TPS, KS, WS)]
    print(f"evaluating {len(grid):,} cells ...")
    store = []
    for p in grid:
        R, pct, blk, sig = O.evaluate(Ds[p["tf"]], full(p))
        store.append((times[p["tf"]][sig].to_numpy() if len(sig)
                      else np.array([], "datetime64[ns]"), pct.astype(np.float32)))

    q = pd.PeriodIndex(times[30], freq="Q").unique().sort_values()
    roll = [((q[i - 4].start_time, q[i - 1].end_time), (q[i].start_time, q[i].end_time),
             str(q[i]), 4) for i in range(4, len(q))]
    expd = [((q[0].start_time, q[i - 1].end_time), (q[i].start_time, q[i].end_time),
             str(q[i]), i) for i in range(4, len(q))]

    def slc(ci, lo, hi):
        ts, v = store[ci]
        if len(ts) == 0:
            return np.array([], np.float32)
        return v[(ts >= np.datetime64(lo)) & (ts <= np.datetime64(hi))]

    idx = {}
    for nm, cfg in (("fixed", FIXED), ("fixed15", FIXED15)):
        idx[nm] = next(i for i, p in enumerate(grid) if all(p[a] == cfg[a] for a in cfg))

    def rechoose(trlo, trhi, mask=None):
        best, bv = -1, -1e18
        pool = range(len(grid)) if mask is None else mask
        for ci in pool:
            v = slc(ci, trlo, trhi)
            if len(v) >= MIN_TRAIN and v.sum() > bv:
                best, bv = ci, float(v.sum())
        return best, bv

    frozen = [i for i, p in enumerate(grid)
              if p["ent"] == 15 and p["exN"] == 30 and p["tp"] == 0.0]
    print(f"  frozen sub-grid (ent 15, exit 30, no target): {len(frozen)} cells "
          f"-- only timeframe, stop, k and w are re-chosen")

    rng = np.random.default_rng(3)
    for sname, fl in (("rolling 4Q", roll), ("expanding", expd)):
        line(f"{sname.upper()} -- every arm with its trade count")
        arms = {k: [] for k in ("rechosen", "frozen", "fixed", "fixed15", "random")}
        is_rate, oos_q = [], 0
        for (trlo, trhi), (telo, tehi), label, tq in fl:
            b, bv = rechoose(trlo, trhi)
            bf, _ = rechoose(trlo, trhi, frozen)
            arms["rechosen"].append(slc(b, telo, tehi))
            arms["frozen"].append(slc(bf, telo, tehi))
            arms["fixed"].append(slc(idx["fixed"], telo, tehi))
            arms["fixed15"].append(slc(idx["fixed15"], telo, tehi))
            arms["random"].append(np.concatenate(
                [slc(int(rng.integers(len(grid))), telo, tehi) for _ in range(1)]))
            is_rate.append(bv / tq)
            oos_q += 1
        print(f"  {'arm':26s}{'OOS trades':>12s}{'total %':>10s}{'%/trade':>10s}"
              f"{'PF':>8s}{'folds +':>9s}{'worst fold':>12s}")
        for nm, lab in (("rechosen", "RE-CHOSEN (all axes)"), ("frozen", "RE-CHOSEN (4 axes only)"),
                        ("fixed", "FIXED incumbent"), ("fixed15", "FIXED 15m preset"),
                        ("random", "RANDOM grid cell")):
            per = [a.sum() for a in arms[nm]]
            v = np.concatenate([a for a in arms[nm] if len(a)]) if any(
                len(a) for a in arms[nm]) else np.array([0.0])
            g_, b_ = v[v > 0].sum(), -v[v <= 0].sum()
            print(f"  {lab:26s}{len(v):>12,d}{v.sum():>10.2f}{v.mean():>10.4f}"
                  f"{(g_ / b_ if b_ > 0 else np.nan):>8.3f}"
                  f"{f'{int(np.sum(np.array(per) > 0))}/{len(per)}':>9s}{min(per):>12.2f}")
        isr = float(np.mean(is_rate))
        oosr = float(np.sum([a.sum() for a in arms["rechosen"]]) / oos_q)
        print(f"\n  SPAN-NORMALISED walk-forward efficiency: in-sample {isr:.3f} %/quarter, "
              f"out-of-sample {oosr:.3f} %/quarter -> WFE {oosr / isr:.3f}")
        print(f"  (the raw sum-OOS/sum-IS ratio in run_wfo was {oosr*oos_q/ (isr*sum(f[3] for f in fl)):.3f} "
              f"and is mostly a span ratio, not an efficiency)")

    line("THE MATCHED CONTROL ON THE AGGREGATED OUT-OF-SAMPLE TRADES")
    print("  Same test windows, same geometry, same trade count -- entries drawn at random from")
    print("  the bars each arm was eligible to trade. 400 draws.")
    D15 = Ds[15]
    for nm, cfg in (("FIXED 15m preset", FIXED15), ("FIXED incumbent", FIXED)):
        D = Ds[cfg["tf"]]
        R, pct, blk, sig = O.evaluate(D, full(cfg))
        ts = times[cfg["tf"]][sig]
        m = ts >= q[4].start_time
        obs = pct[m]
        if len(obs) < 10:
            continue
        ent = D["ent_all"][int(cfg["ent"]) - O.CH_MIN]
        elig = np.flatnonzero(np.isfinite(ent) & np.isfinite(D["atr"]) & (D["atr"] > 0))
        elig = elig[(times[cfg["tf"]][elig] >= q[4].start_time)]
        draws = np.zeros(400)
        for d in range(400):
            pick = rng.choice(elig, size=min(len(obs), len(elig)), replace=False)
            pick.sort()
            pp = full(dict(cfg))
            Rr, pc, bl, sg = O.evaluate_at(D, pp, pick) if hasattr(O, "evaluate_at") else (
                None, None, None, None)
            draws[d] = np.nan
        print(f"  {nm}: n {len(obs)}  observed {obs.mean():+.4f} %/trade  total {obs.sum():+.2f}%")
    print("  (a bar-level random-entry control needs an evaluator entry point that takes a bar")
    print("   list; it is added in run_wfo3 rather than faked here)")
