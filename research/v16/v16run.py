"""The momentum sweep: 366 conditions x 3 timeframes x 2 sides, each against its own null.

THE TEST. A momentum filter is restrictive, so it will almost always raise R-per-trade and almost
always lower total R. Neither is evidence -- total dollars fails every restrictive condition and
per-trade edge passes every one. The question is whether the condition beats a RANDOM FILTER OF
THE SAME SELECTIVITY drawn from the same signal population and run through the same position lock.
If the unfiltered rule has 1,166 trades and the condition leaves 300, draw 300 of the same signals
at random, four hundred times, and see where the real 300 fall.

SELECTION HAPPENS ON THE RESEARCH BLOCK ONLY -- the first 65% of sessions. Any criterion that
touches the locked block puts the holdout inside the selection, which has happened twice on this
branch and both times the result looked better than it was.

MULTIPLICITY IS STATED, NOT HIDDEN. 2,196 tests at alpha 0.05 expect 110 passes by chance. The
Benjamini-Hochberg step-up is applied across the whole family and the expected-by-chance count is
printed beside the observed one, because a table of winners without it is decoration.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C     # noqa: E402
import v16mom as M      # noqa: E402

TFS = (5, 15, 30)
SIDES = (1, -1)


@njit(cache=True)
def _control(sig, xb, R, k, draws, seed):
    """`draws` random filters keeping exactly k signals, each run through the position lock.

    The null is drawn at the EXACT trade count, not a bucketed one: the whole comparison is
    "the same number of these breakouts, chosen at random", and rounding k would quietly change
    the question for the restrictive rungs where the answer matters most."""
    np.random.seed(seed)
    n = len(sig)
    out = np.empty(draws)
    order = np.arange(n)
    for d in range(draws):
        for q in range(k):                       # partial Fisher-Yates: k distinct indices
            j = q + np.int64(np.random.random() * (n - q))
            tmp = order[q]; order[q] = order[j]; order[j] = tmp
        sel = np.sort(order[:k])
        tot = 0.0
        last = -1
        for m in range(k):
            p = sel[m]
            if xb[p] < 0 or sig[p] <= last:
                continue
            tot += R[p]
            last = xb[p]
        out[d] = tot
    return out


def block_masks(P):
    """First 65% of SESSIONS is research. Sessions, not bars, so a day is never split."""
    u = np.unique(P["sess"])
    cut = u[int(len(u) * 0.65)]
    return P["sess"] < cut, P["sess"] >= cut, cut


def sweep(draws=400, seed=7):
    rows = []
    for tf in TFS:
        P = C.prep(tf)
        pool = M.build(P["b"])
        conds = M.conditions(pool)
        res_bar, lock_bar, _ = block_masks(P)
        for side in SIDES:
            sig_all = C.signals(P, side)
            sig = sig_all[res_bar[sig_all]]
            O = C.outcomes(P, side, sig)
            base_idx = C.take(O, np.ones(len(sig), bool))
            base = C.stats(O, base_idx, P["sess"])
            cache = {}
            for cname, score, center, off in conds:
                keep = M.mask_for(score[sig], center, off, side)
                idx = C.take(O, keep)
                if len(idx) < 25:
                    continue
                k = int(keep.sum())
                if k not in cache:
                    cache[k] = _control(O["sig"], O["xb"], O["R"], k, draws, seed + k)
                ctl = cache[k]
                s = C.stats(O, idx, P["sess"])
                rows.append(dict(tf=tf, side=side, cond=cname,
                                 feat=cname.split(">=")[0], off=off,
                                 n=s["n"], keepk=k, R=s["R"], perR=s["perR"], pf=s["pf"],
                                 win=s["win"], sharpe=s.get("sharpe", np.nan),
                                 base_n=base["n"], base_R=base["R"], base_per=base["perR"],
                                 ctl_med=float(np.median(ctl)),
                                 p=float((ctl >= s["R"]).mean())))
    return pd.DataFrame(rows)


def bh(p, q=0.10):
    """Benjamini-Hochberg step-up. Returns the boolean pass vector for the whole family."""
    p = np.asarray(p, float)
    o = np.argsort(p)
    m = len(p)
    thr = q * (np.arange(1, m + 1)) / m
    below = p[o] <= thr
    out = np.zeros(m, bool)
    if below.any():
        kmax = np.max(np.flatnonzero(below))
        out[o[:kmax + 1]] = True
    return out


def fam(name):
    """Group a score name into the family the paper cares about."""
    for pre, lab in (("tsmom", "tsmom  vol-scaled momentum"), ("roc", "roc    raw momentum"),
                     ("agree", "agree  multi-horizon"), ("emadist", "TREND  ema distance"),
                     ("slope", "TREND  price slope"), ("rsi", "osc    rsi"),
                     ("stoch", "osc    stoch"), ("willr", "osc    willr"), ("cci", "osc    cci"),
                     ("cmo", "osc    cmo"), ("aroon", "osc    aroon"), ("trix", "osc    trix"),
                     ("macdh", "osc    macd hist"), ("macd", "osc    macd line"),
                     ("tsi", "osc    tsi"), ("ao", "osc    awesome")):
        if name.startswith(pre):
            return lab
    return "other"


if __name__ == "__main__":
    df = sweep()
    df["family"] = df.cond.str.split(">=").str[0].map(fam)
    df.to_csv("results/v16/v16_sweep.csv", index=False)
    n = len(df)
    print(f"{n} conditions tested on the RESEARCH block "
          f"({len(TFS)} timeframes x {len(SIDES)} sides x {len(M.conditions(M.build(C.prep(15)['b'])))} rungs,"
          f" minus those leaving fewer than 25 trades)\n")

    print("=" * 100)
    print("A. THE BASELINE THE FILTERS HAVE TO BEAT -- Donchian 30/20, market order, no filter")
    print("=" * 100)
    b = df.groupby(["tf", "side"]).first()[["base_n", "base_R", "base_per"]]
    print(f"{'tf':>5}{'side':>7}{'trades':>9}{'net R':>10}{'R/trade':>10}")
    for (tf, side), r in b.iterrows():
        print(f"{tf:>4}m{('long' if side > 0 else 'short'):>7}{int(r.base_n):>9}"
              f"{r.base_R:>+10.1f}{r.base_per:>+10.4f}")

    print("\n" + "=" * 100)
    print("B. HOW MANY BEAT A RANDOM FILTER OF THE SAME SELECTIVITY, AND HOW MANY WERE EXPECTED TO")
    print("=" * 100)
    passed = df.p <= 0.05
    print(f"   observed p <= 0.05 : {int(passed.sum()):>5} of {n}   ({100*passed.mean():.1f}%)")
    print(f"   expected by chance : {0.05*n:>7.1f}")
    keep = bh(df.p.to_numpy(), 0.10)
    print(f"   surviving Benjamini-Hochberg at q = 0.10 : {int(keep.sum())}")
    df["bh"] = keep

    print("\n" + "=" * 100)
    print("C. READ THE FAMILIES BY MARGINAL AVERAGE, NOT BY THE BEST CELL")
    print("=" * 100)
    g = df.groupby("family").agg(tests=("p", "size"), med_p=("p", "median"),
                                 pass_rate=("p", lambda x: float((x <= 0.05).mean())),
                                 med_perR=("perR", "median"), best_p=("p", "min"),
                                 bh=("bh", "sum")).sort_values("pass_rate", ascending=False)
    print(f"{'family':<28}{'tests':>7}{'median p':>10}{'pass@.05':>10}{'med R/trade':>13}"
          f"{'best p':>9}{'BH':>5}")
    for k, r in g.iterrows():
        print(f"{k:<28}{int(r.tests):>7}{r.med_p:>10.3f}{r.pass_rate:>9.1%}"
              f"{r.med_perR:>+13.4f}{r.best_p:>9.3f}{int(r.bh):>5}")

    print("\n" + "=" * 100)
    print("D. THE SURVIVORS, RESEARCH BLOCK ONLY")
    print("=" * 100)
    top = df[df.bh].sort_values("p").head(25)
    if len(top) == 0:
        print("   none.")
    else:
        print(f"{'tf':>4}{'side':>6}  {'condition':<22}{'trades':>8}{'net R':>9}{'R/trade':>9}"
              f"{'PF':>7}{'win%':>7}{'ctl med':>9}{'p':>8}")
        for _, r in top.iterrows():
            print(f"{r.tf:>3}m{('long' if r.side > 0 else 'short'):>6}  {r.cond:<22}{int(r.n):>8}"
                  f"{r.R:>+9.1f}{r.perR:>+9.4f}{r.pf:>7.3f}{100*r.win:>7.2f}"
                  f"{r.ctl_med:>+9.1f}{r.p:>8.4f}")
    print(f"\n   wrote /tmp/v16_sweep.csv ({n} rows)")
