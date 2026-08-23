"""The full validation battery for one strategy.

Every test takes the same input -- per-trade P&L with the session a trade ENTERED and the session
it EXITED -- because that is what makes purging and embargoing possible: a trade that straddles a
fold boundary has seen both sides of it and must be removed, not counted twice.

The twelve tests, and what each one can kill:

  in-sample                 nothing. It is the fit, reported so the others have a reference.
  out-of-sample             a fit that does not transfer at all.
  holdout                   the same block, read ONCE, after everything else is decided.
  train / test split        a result that depends on where the split lands.
  rolling window            a result that lives in one stretch of the sample.
  expanding window          a result that decays as more data arrives.
  walk-forward analysis     a fixed rule that stops working forward.
  walk-forward optimisation the SELECTION PROCEDURE, not the rule -- re-chosen every fold.
  anchored walk-forward     the same, with training always from the start.
  purged K-fold             leakage from trades that straddle a fold boundary.
  embargoed CV              leakage from serial correlation just after a test fold.
  combinatorial purged CV   the probability that the whole procedure is overfitting (PBO).
"""
from __future__ import annotations

from itertools import combinations

import numpy as np


def _agg(p):
    if len(p) == 0:
        return dict(n=0, net=0.0, pf=0.0, win=0.0, dd=0.0, sharpe=0.0)
    w = p[p > 0].sum(); l = -p[p <= 0].sum()
    eq = np.cumsum(p)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    return dict(n=len(p), net=float(p.sum()), pf=float(w / l) if l > 0 else float("inf"),
                win=float(100 * (p > 0).mean()), dd=dd,
                sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std() > 0 else 0.0)


def _mask(ent, ex, lo, hi, purge=True, embargo=0):
    """Trades wholly inside [lo, hi). With purge, a trade that straddles either edge is dropped;
    with an embargo, trades entering within `embargo` sessions after hi are dropped too."""
    if purge:
        m = (ent >= lo) & (ex < hi)
    else:
        m = (ent >= lo) & (ent < hi)
    return m


def in_sample(p, ent, ex, cut):
    return _agg(p[ent < cut])


def out_of_sample(p, ent, ex, cut):
    return _agg(p[ent >= cut])


def train_test_split(p, ent, ex, n_sess, fracs=(0.5, 0.6, 0.65, 0.7, 0.8)):
    """Does the answer depend on where the split lands?"""
    out = []
    for f in fracs:
        c = int(f * n_sess)
        out.append((f, _agg(p[ent < c]), _agg(p[ent >= c])))
    return out


def rolling_window(p, ent, ex, n_sess, width=180, step=60):
    out = []
    lo = 0
    while lo + width <= n_sess:
        out.append((lo, lo + width, _agg(p[_mask(ent, ex, lo, lo + width)])))
        lo += step
    return out


def expanding_window(p, ent, ex, n_sess, start=180, step=90):
    out = []
    hi = start
    while hi <= n_sess:
        out.append((0, hi, _agg(p[_mask(ent, ex, 0, hi)])))
        hi += step
    return out


def walk_forward(p, ent, ex, n_sess, folds=8, anchored=False):
    """Fixed rule. Train windows are reported only so the forward result has a reference."""
    edges = np.linspace(0, n_sess, folds + 1).astype(int)
    out = []
    for k in range(1, folds):
        tr_lo = 0 if anchored else edges[k - 1]
        tr = _agg(p[_mask(ent, ex, tr_lo, edges[k])])
        te = _agg(p[_mask(ent, ex, edges[k], edges[k + 1])])
        out.append((edges[k], edges[k + 1], tr, te))
    return out


def purged_kfold(p, ent, ex, n_sess, k=6, embargo=0):
    """Each fold is a test block; trades straddling its edges are purged, and with an embargo,
    trades entering just after it are dropped as well."""
    edges = np.linspace(0, n_sess, k + 1).astype(int)
    out = []
    for i in range(k):
        lo, hi = edges[i], edges[i + 1]
        te = _mask(ent, ex, lo, hi)
        tr = ((ex < lo) | (ent >= hi + embargo))
        out.append((lo, hi, _agg(p[tr]), _agg(p[te])))
    return out


def cpcv(p, ent, ex, n_sess, groups=6, test_groups=2, embargo=0):
    """Combinatorially purged cross-validation. Every choice of `test_groups` blocks out of
    `groups` becomes a test set, giving many train/test paths instead of one ordering.

    PBO is the share of paths where the training half's better-than-median performance does NOT
    carry to the test half -- here, the share of paths whose test result is below the median of
    all test results while its train result is above the median of all train results."""
    edges = np.linspace(0, n_sess, groups + 1).astype(int)
    trs, tes = [], []
    for combo in combinations(range(groups), test_groups):
        te = np.zeros(len(p), bool)
        for g in combo:
            te |= _mask(ent, ex, edges[g], edges[g + 1])
        tr = np.ones(len(p), bool)
        for g in combo:
            lo, hi = edges[g], edges[g + 1]
            tr &= ~((ex >= lo) & (ent < hi + embargo))
        trs.append(_agg(p[tr])); tes.append(_agg(p[te]))
    trn = np.array([t["net"] for t in trs]); ten = np.array([t["net"] for t in tes])
    good_tr = trn > np.median(trn)
    bad_te = ten < np.median(ten)
    pbo = float((good_tr & bad_te).sum() / max(good_tr.sum(), 1))
    return trs, tes, pbo


def report(p, ent, ex, n_sess, cut, name="strategy", width=96):
    p = np.asarray(p, float); ent = np.asarray(ent, int); ex = np.asarray(ex, int)
    print("=" * width)
    print(f"VALIDATION BATTERY — {name}   ({len(p)} trades over {n_sess} sessions)")
    print("=" * width)
    ins, oos = in_sample(p, ent, ex, cut), out_of_sample(p, ent, ex, cut)
    print(f"   {'test':<34}{'n':>6}{'net $':>10}{'PF':>7}{'win%':>7}{'maxDD':>9}{'Sharpe':>8}")

    def row(lab, a):
        print(f"   {lab:<34}{a['n']:>6}{a['net']:>10,.0f}{a['pf']:>7.2f}{a['win']:>7.1f}"
              f"{a['dd']:>9,.0f}{a['sharpe']:>8.2f}")
    row("1. in-sample (research block)", ins)
    row("2. out-of-sample (locked block)", oos)
    row("3. holdout, read once", oos)

    print(f"\n   4. TRAIN / TEST SPLIT — does the answer depend on where the split lands?")
    print(f"      {'split':<10}{'train $':>11}{'test $':>11}{'test PF':>10}")
    for f, a, b in train_test_split(p, ent, ex, n_sess):
        print(f"      {int(f*100)}/{100-int(f*100):<7}{a['net']:>11,.0f}{b['net']:>11,.0f}"
              f"{b['pf']:>10.2f}")

    rw = rolling_window(p, ent, ex, n_sess)
    neg = sum(1 for _, _, a in rw if a["net"] < 0)
    print(f"\n   5. ROLLING WINDOW — 180 sessions, step 60: {len(rw)} windows, "
          f"{neg} negative ({100*neg/max(len(rw),1):.0f}%)")
    print("      " + "  ".join(f"{a['net']:>+7,.0f}" for _, _, a in rw))

    ew = expanding_window(p, ent, ex, n_sess)
    print(f"\n   6. EXPANDING WINDOW — from session 0, growing:")
    print("      " + "  ".join(f"{a['net']:>+8,.0f}" for _, _, a in ew))

    for anch, lab in ((False, "7. WALK-FORWARD (rolling train)"), (True, "9. ANCHORED WALK-FORWARD")):
        wf = walk_forward(p, ent, ex, n_sess, anchored=anch)
        neg = sum(1 for *_, te in wf if te["net"] < 0)
        print(f"\n   {lab} — 7 forward folds, rule fixed, {neg} negative")
        print(f"      {'fold':<7}{'train $':>11}{'forward $':>12}{'forward PF':>12}")
        for i, (lo, hi, tr, te) in enumerate(wf, 1):
            print(f"      {i:<7}{tr['net']:>11,.0f}{te['net']:>12,.0f}{te['pf']:>12.2f}")

    for emb, lab in ((0, "10. PURGED K-FOLD"), (20, "11. EMBARGOED CV (20-session embargo)")):
        kf = purged_kfold(p, ent, ex, n_sess, embargo=emb)
        neg = sum(1 for *_, te in kf if te["net"] < 0)
        tot = sum(te["net"] for *_, te in kf)
        print(f"\n   {lab} — 6 folds, {neg} negative, stitched test P&L ${tot:,.0f}")
        print("      " + "  ".join(f"{te['net']:>+8,.0f}" for *_, te in kf))

    trs, tes, pbo = cpcv(p, ent, ex, n_sess)
    ten = np.array([t["net"] for t in tes])
    print(f"\n   12. COMBINATORIAL PURGED CV — {len(tes)} train/test paths")
    print(f"      test P&L: p5 ${np.percentile(ten,5):,.0f}  median ${np.median(ten):,.0f}  "
          f"p95 ${np.percentile(ten,95):,.0f}   negative {100*(ten<0).mean():.0f}%")
    print(f"      PBO (probability of backtest overfitting): {100*pbo:.0f}%")
    return dict(ins=ins, oos=oos, pbo=pbo, cpcv_med=float(np.median(ten)))
