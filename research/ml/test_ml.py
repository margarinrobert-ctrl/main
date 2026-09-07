"""Tests for the model layer. Run: python3 research/ml/test_ml.py

These check the properties that, when violated, silently produce a good-looking wrong answer. Every
one of them corresponds to a mistake actually made in this project.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from ml.metrics import auc, day_paired_lift, deflate, evaluate
from ml.splits import PurgedKFold, locked_split, session_folds

PASS = []


def check(name, cond):
    PASS.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    assert cond, name


def main() -> None:
    rng = np.random.default_rng(20250822)

    # ---- splits ----------------------------------------------------------------------------
    cv = PurgedKFold(n_splits=5, horizon=100, embargo=0.01)
    n = 20_000
    for tr, te in cv.split(n):
        check("train and test never intersect", not (set(tr) & set(te)))
        gap_lo = te.min() - tr[tr < te.min()].max() if (tr < te.min()).any() else 1e9
        gap_hi = tr[tr > te.max()].min() - te.max() if (tr > te.max()).any() else 1e9
        check("purge gap before test >= horizon", gap_lo >= 100)
        check("purge gap after test >= horizon + embargo", gap_hi >= 100)
        break

    sess = np.repeat(np.arange(500), 100)
    r, h = locked_split(sess, 0.2)
    check("locked split shares no session", not (set(sess[r]) & set(sess[h])))
    check("holdout is roughly the requested fraction", 0.15 < h.mean() < 0.25)
    for tr, te in session_folds(sess, 4):
        check("session folds share no session", not (set(sess[tr]) & set(sess[te])))
        break

    # ---- AUC -------------------------------------------------------------------------------
    d = rng.normal(0, 100, 5000)
    check("AUC of a perfect ranker is 1", abs(auc(d > 0, d) - 1.0) < 1e-9)
    check("AUC of an inverted ranker is 0", abs(auc(d > 0, -d)) < 1e-9)
    check("AUC of noise is near 0.5", abs(auc(d > 0, rng.random(5000)) - 0.5) < 0.05)
    check("AUC is NaN on a degenerate label", np.isnan(auc(np.ones(100, bool), rng.random(100))))

    # ---- the day-clustering property, which is the whole point -----------------------------
    n_days, per = 400, 100
    sess = np.repeat(np.arange(n_days), per)
    day_effect = np.repeat(rng.normal(0, 300, n_days), per)
    dollars = day_effect + rng.normal(0, 50, n_days * per)

    # A "signal" that knows WHICH DAY is good but nothing about when inside it. It must earn no
    # credit -- this is the discrimination that exposed MaxAI's CMF signal, which had the best raw
    # $/trade in its table and the worst within-session lift.
    #
    # Note the degenerate variant: a selector taking EVERY bar of its chosen days has a per-session
    # lift of exactly 0 and zero variance, so t is NaN -- correct, but it tests nothing. The
    # realistic case picks good days and then random bars inside them, which has within-day
    # variance and must still score ~0.
    good_day = np.repeat(rng.random(n_days) > 0.5, per)
    picked_day = good_day & (rng.random(len(dollars)) < 0.3)
    lift_day, t_day, _ = day_paired_lift(dollars, sess, picked_day)
    check("a pure day-selector earns ~zero within-session lift", abs(lift_day) < 15)
    check("a pure day-selector has an insignificant t", np.isfinite(t_day) and abs(t_day) < 2.5)

    # and the degenerate all-bars-of-a-day case is reported as NaN rather than as a result
    _, t_deg, _ = day_paired_lift(dollars, sess, good_day)
    check("an all-bars-of-the-day selector yields no t at all", not np.isfinite(t_deg))

    # a signal that knows WITHIN-DAY which bars pay
    picked_real = dollars > np.repeat(pd.Series(dollars).groupby(sess).mean().to_numpy(), per)
    lift_real, t_real, _ = day_paired_lift(dollars, sess, picked_real)
    check("a real within-day signal earns a large positive lift", lift_real > 20)
    check("a real within-day signal is significant", t_real > 5)

    # ---- evaluate() end to end -------------------------------------------------------------
    proba_noise = rng.random(len(dollars))
    s = evaluate(proba_noise, dollars, sess)
    check("noise scores ~zero lift", abs(s.best_lift) < 15)
    check("take_all equals the mean outcome", abs(s.take_all - dollars.mean()) < 1e-9)

    proba_good = 0.5 + 0.2 * (dollars > np.repeat(
        pd.Series(dollars).groupby(sess).mean().to_numpy(), per))
    s2 = evaluate(proba_good, dollars, sess)
    check("a real signal beats noise on lift", s2.best_lift > s.best_lift + 10)

    # ---- search-cost accounting ------------------------------------------------------------
    check("hurdle grows with trial count", deflate(2.0, 1000)["hurdle"] > deflate(2.0, 10)["hurdle"])
    check("t=2.0 clears a 1-trial hurdle", deflate(2.0, 1)["clears"])
    check("t=2.0 does NOT clear a 500-trial hurdle", not deflate(2.0, 500)["clears"])

    # ---- dataset: absence must not drop rows ----------------------------------------------
    from ml.dataset import build
    X, y, meta = build()
    check("dataset keeps ~all bars despite optional features", len(X) > 250_000)
    check("no NaN survives into the feature matrix", not X.isna().any().any())
    check("every optional feature has a presence flag",
          all(f"has_{c}" in X.columns for c in
              ["fvg_dist_up", "fvg_dist_dn", "or_pos", "range_pos"]))
    check("presence flags are not constant",
          all(0 < X[f"has_{c}"].mean() < 1 for c in ["fvg_dist_up", "or_pos"]))
    check("label carries costs (long mean below the gross drift)", y.mean() < 30)

    print(f"\n  {sum(PASS)}/{len(PASS)} CHECKS PASSED")


if __name__ == "__main__":
    main()
