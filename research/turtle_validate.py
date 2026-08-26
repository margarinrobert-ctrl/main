"""Statistics for the sweep's survivors: is the best of K better than the best of K coin flips?

A sweep this size produces a maximum whether or not anything is there.  Everything in this module
exists to price that fact:

  * **the draw-based matched control** re-runs the whole scan on random triggers with the rule's own
    minute-of-day distribution, so it prices the no-overlap thinning the analytic screen cannot;
  * **the Deflated Sharpe Ratio** restates the winner's Sharpe as a probability given how many
    configurations were actually evaluated and how widely their Sharpes were spread;
  * **CSCV / PBO** asks the sharper question -- not "is this strategy good" but "does picking the
    in-sample best carry any information at all";
  * **walk-forward** pays the cost of having to choose parameters, which a single in-sample fit
    hides entirely;
  * **the neighbourhood** distinguishes a plateau from a spike, because a rule whose edge dies when
    a lookback moves from 8 to 9 never had one.

Everything here runs on the RESEARCH block.  `reveal()` is the only function that touches the
locked block; it prints the multiplicity before the result and flags the wrong shape -- a candidate
that does better on the holdout than on the block it was chosen from.
"""
from __future__ import annotations

import itertools
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_search as S
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P

EULER = 0.5772156649015329


# ================================================================= daily P&L matrix

def daily_series(s, p: P, spec: dict, n_sess: int, cost_mult: float = 1.0) -> np.ndarray:
    """Net dollars per session for one configuration, zero-filled, over [0, n_sess)."""
    ex = X.build(s, p)
    sc = X.scan(s, ex, T.signal_bars(s, p), p)
    net = sc.net(spec["cost_abs"] * cost_mult, spec["cost_bp"] * cost_mult,
                 spec["stop_slip"] * cost_mult, p.tp_rests)
    if len(sc):
        net = net * spec["point_value"] - sc.units * spec.get("comm", 0.0) * cost_mult
    out = np.zeros(n_sess)
    if len(sc):
        np.add.at(out, s.sess[sc.exit_bar], net)
    return out


def daily_matrix(s, rows: pd.DataFrame, spec: dict, n_sess: int,
                 cost_mult: float = 1.0) -> np.ndarray:
    """(n_sess, n_config) net dollars.  One pass; every downstream probe reads this."""
    out = np.zeros((n_sess, len(rows)))
    legs: dict = {}
    for j, (_, row) in enumerate(rows.iterrows()):
        p = S.to_params(row, spec, cost_mult)
        key = (p.atr_len, p.atr_mult, p.pyr_step, p.max_units, p.tp_r, p.use_chan_exit,
               p.chan_shift, p.armed_stop, p.max_hold, p.flatten_min, p.side)
        for e in (p.exit1, p.exit2):
            if (key, e) not in legs:
                legs[(key, e)] = X.build_leg(s, p, e)
        ex = X.pair(legs[(key, p.exit1)], legs[(key, p.exit2)], s.n, p.side)
        sc = X.scan(s, ex, T.signal_bars(s, p), p)
        if not len(sc):
            continue
        net = sc.net(spec["cost_abs"] * cost_mult, spec["cost_bp"] * cost_mult,
                     spec["stop_slip"] * cost_mult, p.tp_rests)
        net = net * spec["point_value"] - sc.units * spec.get("comm", 0.0) * cost_mult
        np.add.at(out[:, j], s.sess[sc.exit_bar], net)
        if len(legs) > 400:
            legs.clear()
    return out


# ================================================================= deflated Sharpe

def expected_max_sharpe(n_trials: int, trial_sd: float) -> float:
    """E[max Sharpe] over `n_trials` independent trials with dispersion `trial_sd`.

    Bailey & Lopez de Prado's approximation to the expected maximum of N standard normals.  This
    is the bar the winner has to clear: not zero, but what the best of N coin flips would score.
    """
    if n_trials < 2 or trial_sd <= 0:
        return 0.0
    a = sps.norm.ppf(1.0 - 1.0 / n_trials)
    b = sps.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return trial_sd * ((1.0 - EULER) * a + EULER * b)


def deflated_sharpe(daily: np.ndarray, n_trials: int, trial_sd_ann: float,
                    spy: float) -> dict:
    """DSR: the probability the true Sharpe is positive, given the size of the search.

    Sharpes are deflated in PER-OBSERVATION units.  Annualising both the estimate and the trial
    dispersion and comparing them would be arithmetically fine; mixing the two -- an annualised
    Sharpe against a per-observation threshold -- inflates the result by sqrt(252) and is the
    easiest way to report a deflated number that has not been deflated.
    """
    n = len(daily)
    sd = daily.std(ddof=1)
    if n < 20 or sd <= 0:
        return {"sr_ann": 0.0, "dsr": 0.0, "sr_star_ann": 0.0, "psr_vs_zero": 0.0, "mtrl": np.inf}
    sr = daily.mean() / sd                      # per session
    g3 = float(sps.skew(daily))
    g4 = float(sps.kurtosis(daily, fisher=False))
    sr_star = expected_max_sharpe(n_trials, trial_sd_ann / math.sqrt(spy))

    def psr(bench: float) -> float:
        denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
        if denom <= 0:
            return 0.0
        return float(sps.norm.cdf((sr - bench) * math.sqrt(n - 1) / math.sqrt(denom)))

    # Minimum track record length: sessions needed for PSR(0) to reach 95%.
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    mtrl = 1.0 + denom * (sps.norm.ppf(0.95) / sr) ** 2 if sr > 0 and denom > 0 else np.inf
    return {"sr_ann": sr * math.sqrt(spy), "sr_star_ann": sr_star * math.sqrt(spy),
            "dsr": psr(sr_star), "psr_vs_zero": psr(0.0), "mtrl": mtrl,
            "skew": g3, "kurtosis": g4}


# ================================================================= PBO / CSCV

def pbo_cscv(mat: np.ndarray, n_blocks: int = 10, rng_seed: int = 20250822) -> dict:
    """Probability of backtest overfitting, by combinatorially symmetric cross-validation.

    Splits the session axis into `n_blocks` contiguous blocks, and for every balanced train/test
    partition asks where the train-set winner lands in the test set's ranking.  PBO is the share of
    partitions where it falls below the test median.

    This tests the SELECTION PROCEDURE, not any single configuration.  Above 0.5 a better
    in-sample number is actively bad news.
    """
    t, k = mat.shape
    if k < 4 or t < n_blocks * 4:
        return {"pbo": np.nan, "n_splits": 0}
    edges = np.linspace(0, t, n_blocks + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(n_blocks)]
    half = n_blocks // 2
    logits = []
    for combo in itertools.combinations(range(n_blocks), half):
        tr = np.concatenate([blocks[i] for i in combo])
        te = np.concatenate([blocks[i] for i in range(n_blocks) if i not in combo])
        def sr(idx):
            m, s = mat[idx].mean(axis=0), mat[idx].std(axis=0, ddof=1)
            return np.where(s > 0, m / np.maximum(s, 1e-12), -np.inf)
        best = int(np.argmax(sr(tr)))
        oos = sr(te)
        rank = float((oos < oos[best]).sum() + 1) / (k + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1 - rank)))
    lg = np.array(logits)
    return {"pbo": float((lg <= 0).mean()), "n_splits": len(lg),
            "logit_mean": float(lg.mean())}


# ================================================================= walk-forward

def walk_forward(mat: np.ndarray, train: int = 250, test: int = 60,
                 min_sd: float = 1e-9) -> dict:
    """Rolling re-optimisation over the candidate matrix: fit on `train`, trade the next `test`.

    The stitched test windows include the cost of HAVING TO CHOOSE parameters, which no single
    in-sample fit shows.  Efficiency is reported as undefined when the in-sample median is not
    positive, because a ratio of two negatives looks like success.
    """
    t, k = mat.shape
    stitched: list[np.ndarray] = []
    picks: list[int] = []
    is_sr, oos_sr = [], []
    start = 0
    while start + train + test <= t:
        tr = mat[start:start + train]
        te = mat[start + train:start + train + test]
        m, s = tr.mean(axis=0), tr.std(axis=0, ddof=1)
        sr = np.where(s > min_sd, m / np.maximum(s, 1e-12), -np.inf)
        j = int(np.argmax(sr))
        picks.append(j)
        is_sr.append(float(sr[j]))
        sd = te[:, j].std(ddof=1)
        oos_sr.append(float(te[:, j].mean() / sd) if sd > min_sd else 0.0)
        stitched.append(te[:, j])
        start += test
    if not stitched:
        return {"folds": 0}
    st = np.concatenate(stitched)
    sd = st.std(ddof=1)
    med_is, med_oos = float(np.median(is_sr)), float(np.median(oos_sr))
    return {
        "folds": len(stitched),
        "oos_sessions": len(st),
        "oos_net": float(st.sum()),
        "oos_sharpe_per_sess": float(st.mean() / sd) if sd > 0 else 0.0,
        "median_is_sr": med_is, "median_oos_sr": med_oos,
        "efficiency": (med_oos / med_is) if med_is > 0 else float("nan"),
        "param_stability": float(pd.Series(picks).value_counts().iloc[0] / len(picks)),
        "unique_picks": len(set(picks)),
    }


# ================================================================= bootstrap

def stationary_bootstrap_ci(daily: np.ndarray, stat=None, reps: int = 2000,
                            mean_block: float = 10.0, seed: int = 20250822) -> tuple:
    """Politis-Romano stationary bootstrap CI, preserving short-range dependence."""
    if stat is None:
        def stat(x):
            sd = x.std(ddof=1)
            return x.mean() / sd if sd > 0 else 0.0
    rng = np.random.default_rng(seed)
    n = len(daily)
    p = 1.0 / mean_block
    vals = np.empty(reps)
    for r in range(reps):
        idx = np.empty(n, np.int64)
        i = rng.integers(n)
        for t in range(n):
            idx[t] = i
            if rng.random() < p:
                i = rng.integers(n)
            else:
                i = (i + 1) % n
        vals[r] = stat(daily[idx])
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)), vals


# ================================================================= neighbourhood

NEIGHBOUR_AXES = {
    "entry1": (4, 6, 8, 10, 14, 20, 28),
    "entry2": (8, 12, 16, 24, 40, 60),
    "exit1": (2, 3, 4, 6, 8, 12),
    "exit2": (2, 3, 4, 6, 8, 12),
    "atr_mult": (1.0, 1.5, 2.0, 2.5, 3.0),
    "tp_r": (0.0, 1.0, 2.0, 3.0),
    "atr_len": (14, 20),
}


def neighbourhood(df: pd.DataFrame, row: pd.Series, metric: str = "sharpe") -> dict:
    """Median objective of the winner's one-grid-step neighbours, divided by the winner's.

    Reported, never optimised.  `CLAUDE.md`: ranking by a minimum over a neighbourhood -- the
    obvious over-correction -- cost $18,970 on the holdout.  So this diagnoses the surface and
    does not choose on it.
    """
    keys = [k for k in NEIGHBOUR_AXES if k in df.columns]
    fixed = {k: row[k] for k in ("atr_len", "atr_mult", "pyr_step", "max_units", "tp_r",
                                 "use_chan_exit", "chan_shift", "armed_stop", "max_hold",
                                 "exit1", "exit2", "entry1", "entry2",
                                 "skip_win") if k in df.columns}
    vals = []
    for k in keys:
        grid = NEIGHBOUR_AXES[k]
        try:
            pos = grid.index(type(grid[0])(row[k]))
        except (ValueError, TypeError):
            continue
        for step in (-1, 1):
            q = pos + step
            if not (0 <= q < len(grid)):
                continue
            sel = df
            for kk, vv in fixed.items():
                sel = sel[sel[kk] == (grid[q] if kk == k else vv)]
            if len(sel):
                vals.append(float(sel[metric].iloc[0]))
    if not vals:
        return {"neighbours": 0, "stability": float("nan"), "verdict": "unknown"}
    base = float(row[metric])
    ratio = float(np.median(vals) / base) if base > 0 else float("nan")
    verdict = "spike" if (ratio < 0.5 or np.isnan(ratio)) else \
              ("ridge" if ratio < 0.8 else "plateau")
    return {"neighbours": len(vals), "stability": ratio, "verdict": verdict,
            "n_min": float(np.min(vals)), "n_max": float(np.max(vals))}


# ================================================================= draw-based control

def full_control(s, p: P, spec: dict, lo: int, hi: int, name: str, draws: int = 500,
                 seed: int = 20250822, cost_mult: float = 1.0) -> tuple[dict, dict]:
    ex = X.build(s, p)
    trig = T.signal_bars(s, p)
    sc = X.scan(s, ex, trig, p)
    st = M.summarise(s, sc, spec, lo, hi, name, cost_mult, p.tp_rests)
    block = np.where((s.sess >= lo) & (s.sess < hi), 0, 1).astype(np.int64)
    ctrl = X.Control(s, np.where(block == 0, trig, 0), block=block, seed=seed)
    bank = M.control_bank(s, ex, ctrl, p, spec, lo, hi, name, draws=draws, cost_mult=cost_mult)
    return st, M.excess(st, bank)


# ================================================================= the locked read

def reveal(s, p: P, spec: dict, name: str, cut: int, n_trials: int, trial_sd: float,
           draws: int = 500, label: str = "") -> dict:
    """Read the locked block.  Once.  Multiplicity first, then the number.

    Prints research and locked side by side and flags the wrong shape: a candidate chosen on
    research that does BETTER on the holdout.  `CLAUDE.md` records that seen twice, both times a
    defect rather than a result -- the holdout is where an edge decays, not where it appears.
    """
    n_sess = int(s.sess.max()) + 1
    spy = M.SESSIONS_PER_YEAR[name]
    print(f"\n{'=' * 96}\nLOCKED READ -- {label or name}")
    print(f"  configurations evaluated across the whole study: {n_trials:,}")
    print(f"  trial Sharpe dispersion (annualised): {trial_sd:.3f}")
    print(f"  expected best-of-{n_trials:,} Sharpe from noise alone: "
          f"{expected_max_sharpe(n_trials, trial_sd / math.sqrt(spy)) * math.sqrt(spy):.3f}")
    print("=" * 96)

    out = {}
    for tag, lo, hi in (("research", 0, cut), ("locked", cut, n_sess)):
        st, ex = full_control(s, p, spec, lo, hi, name, draws=draws)
        d = daily_series(s, p, spec, n_sess)[lo:hi]
        ds = deflated_sharpe(d, n_trials, trial_sd, spy)
        lo_ci, hi_ci, _ = stationary_bootstrap_ci(d, reps=1000)
        out[tag] = {**st, **ex, **ds, "ci_lo": lo_ci * math.sqrt(spy),
                    "ci_hi": hi_ci * math.sqrt(spy)}
        print(f"  {tag:<9} {M.fmt(st)}")
        print(f"  {'':<9} control /trade ${ex.get('ctrl_per_trade', 0):>8.2f}  "
              f"excess ${ex.get('ex_per_trade', 0):>8.2f}  p {ex.get('p_per_trade', 1):.4f}   "
              f"ctrl Sharpe {ex.get('ctrl_sharpe', 0):>5.2f}  excess {ex.get('ex_sharpe', 0):>5.2f}"
              f"  p {ex.get('p_sharpe', 1):.4f}")
        print(f"  {'':<9} DSR {ds['dsr']:.4f}  PSR>0 {ds['psr_vs_zero']:.4f}  "
              f"Sharpe 95% CI [{lo_ci * math.sqrt(spy):.2f}, {hi_ci * math.sqrt(spy):.2f}]  "
              f"MTRL {ds['mtrl']:.0f} sessions")
    if out["locked"]["sharpe"] > out["research"]["sharpe"]:
        print("\n  ** WRONG SHAPE ** locked Sharpe exceeds research Sharpe.  A rule selected on "
              "research\n     should look better there; treat this as a defect, not a result.")
    return out


__all__ = ["daily_series", "daily_matrix", "deflated_sharpe", "expected_max_sharpe", "pbo_cscv",
           "walk_forward", "stationary_bootstrap_ci", "neighbourhood", "full_control", "reveal"]
