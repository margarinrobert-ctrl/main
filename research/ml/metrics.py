"""Cost-aware, day-clustered evaluation.

Three rules, each of which has already reversed a result in this repository:

  DOLLARS, NOT AUC. An AUC of 0.51 can be worth money or nothing depending on where the threshold
  sits and what a round turn costs. Every model here is scored by the dollars it would have made.

  LIFT, NOT LEVEL. On 2023-25 NQ the unconditional intraday long earns +$9.17 per barrier trade, so
  ANY long-biased rule clears zero. The benchmark is the unconditional take-every-bar policy, never
  zero. (RESEARCH_PROTOCOL 4a: an event study must difference out the cost, or it measures the cost.)

  DAY-CLUSTERED t. Bars inside a session share an outcome. Treating 8,541 of them as independent
  turned a -$95/trade effect at t = -2.70 into +$201/trade at t = +5.60 in the MaxAI study.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Score:
    n: int
    auc: float
    take_all: float           # $/trade of the unconditional policy on the same rows
    at_threshold: dict        # threshold -> (n, $/trade, total $, win%)
    best_lift: float          # within-session paired lift over take-everything, in $/trade
    t_day: float              # t on that paired lift, across sessions
    threshold: float

    def line(self, label: str) -> str:
        # A model that never clears any threshold has no selected bucket, so threshold is NaN and
        # there is nothing to index. That happens routinely to shuffled controls and must print,
        # not raise.
        if not np.isfinite(self.threshold):
            return (f"  {label:<28}{self.n:>9,}{self.auc:>8.4f}{self.take_all:>11.2f}"
                    f"{'--':>8}{'--':>9}{'--':>11}{'--':>9}{'--':>8}")
        return (f"  {label:<28}{self.n:>9,}{self.auc:>8.4f}{self.take_all:>11.2f}"
                f"{self.threshold:>8.2f}{self.at_threshold[self.threshold][0]:>9,}"
                f"{self.at_threshold[self.threshold][1]:>11.2f}{self.best_lift:>9.2f}{self.t_day:>8.2f}")


HEADER = (f"  {'':<28}{'rows':>9}{'AUC':>8}{'take-all':>11}{'thr':>8}{'picked':>9}"
          f"{'$/trade':>11}{'lift':>9}{'t(day)':>8}")


def auc(y_true, score) -> float:
    """Rank AUC without sklearn's import cost, and NaN-safe on a degenerate label."""
    y = np.asarray(y_true).astype(bool)
    if y.all() or (~y).all():
        return np.nan
    r = pd.Series(np.asarray(score, float)).rank().to_numpy()
    n1 = y.sum(); n0 = (~y).sum()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def day_paired_lift(dollars: np.ndarray, sess: np.ndarray, picked: np.ndarray):
    """Within-session lift: mean(picked in session) - mean(all bars in session), across sessions.

    This must be PAIRED inside the session. Comparing per-session means of the picked rows against a
    POOLED baseline mixes two different quantities and can report a positive lift with a negative t
    -- which is exactly what an earlier draft of this file did. The session is the unit of
    observation: a model firing on 40 bars of one day has one observation of that day, not 40.

    Returns (mean lift, t across sessions, n sessions).
    """
    df = pd.DataFrame({"d": dollars, "s": sess, "p": picked.astype(bool)})
    g = df.groupby("s")
    per = (g.apply(lambda x: x.loc[x.p, "d"].mean() - x["d"].mean(), include_groups=False)
             .to_numpy())
    per = per[np.isfinite(per)]
    if len(per) < 30:
        return (float(per.mean()) if len(per) else np.nan), np.nan, len(per)
    sd = per.std(ddof=1)
    t = np.nan if sd <= 0 else per.mean() / (sd / np.sqrt(len(per)))
    return float(per.mean()), float(t), len(per)


# A selected bucket has to be big enough for its mean to mean anything. At the old floor of 30 the
# "best threshold" could be chosen from a 34-row bucket, and the maximum over thresholds of a noisy
# mean is itself a search: shuffled-label controls duly reported lifts of +$450/trade at t = 2.70,
# beating every real model. The floor below is in ROWS, and a bucket must also span enough sessions
# for the day-clustered t to exist at all.
MIN_BUCKET_ROWS = 500
MIN_BUCKET_SESSIONS = 30


def evaluate(proba, dollars, sess, thresholds=(0.50, 0.52, 0.55, 0.60, 0.65)) -> Score:
    """Score a probability vector against the dollar outcome of acting on it."""
    proba = np.asarray(proba, float)
    dollars = np.asarray(dollars, float)
    sess = np.asarray(sess)
    ok = np.isfinite(proba) & np.isfinite(dollars)
    proba, dollars, sess = proba[ok], dollars[ok], sess[ok]

    take_all = dollars.mean() if len(dollars) else np.nan
    a = auc(dollars > 0, proba)

    at = {}
    for th in thresholds:
        m = proba >= th
        if m.sum() >= MIN_BUCKET_ROWS and len(np.unique(sess[m])) >= MIN_BUCKET_SESSIONS:
            at[th] = (int(m.sum()), float(dollars[m].mean()), float(dollars[m].sum()),
                      float(100 * (dollars[m] > 0).mean()))
        else:
            at[th] = (int(m.sum()), np.nan, np.nan, np.nan)

    usable = {th: v for th, v in at.items() if np.isfinite(v[1])}
    if usable:
        best_th = max(usable, key=lambda th: usable[th][1])
        best_lift, t, _ = day_paired_lift(dollars, sess, proba >= best_th)
    else:
        best_th, best_lift, t = np.nan, np.nan, np.nan

    return Score(n=len(dollars), auc=a, take_all=take_all, at_threshold=at,
                 best_lift=best_lift, t_day=t, threshold=best_th)


def deflate(t_observed: float, n_trials: int) -> dict:
    """What a t-statistic is worth once you say how many were looked at.

    E[max z] over n independent draws from the null is ~sqrt(2 ln n); a searched result has to clear
    that, not 2. This is reported next to every tuned number rather than left for the reader.
    """
    n_trials = max(int(n_trials), 1)
    hurdle = np.sqrt(2 * np.log(n_trials)) if n_trials > 1 else 1.96
    return dict(n_trials=n_trials, hurdle=float(hurdle), t=float(t_observed),
                clears=bool(np.isfinite(t_observed) and t_observed > hurdle))
