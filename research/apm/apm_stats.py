"""Statistical primitives for the validation battery.

Everything here operates on a RETURN SERIES (per trade, or per session), never on prices, so the
same function serves the strategy, a control and a bootstrap replicate without special-casing.

Two conventions that matter and are easy to get wrong:

  * Sharpe is computed PER OBSERVATION and annualised only at the point of display, with the
    observation frequency stated. A per-trade Sharpe annualised by sqrt(252) when the strategy
    trades 36 times a year is the single most common way a thin strategy is made to look thick.
  * The moment-based tests (PSR, DSR, MinTRL) need NON-EXCESS kurtosis (3.0 for a normal), because
    that is the convention in Bailey & Lopez de Prado's derivation. `scipy.stats.kurtosis` returns
    excess by default; every call here passes `fisher=False`.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

EULER = 0.5772156649015329


# --------------------------------------------------------------------------- basics

def sharpe(x: np.ndarray, ddof: int = 1) -> float:
    x = np.asarray(x, float)
    if len(x) < 2:
        return np.nan
    s = x.std(ddof=ddof)
    return np.nan if s <= 0 else float(x.mean() / s)


def ann_sharpe(x: np.ndarray, per_year: float) -> float:
    sr = sharpe(x)
    return np.nan if np.isnan(sr) else sr * np.sqrt(per_year)


def moments(x: np.ndarray) -> tuple:
    x = np.asarray(x, float)
    return (float(stats.skew(x, bias=False)),
            float(stats.kurtosis(x, fisher=False, bias=False)))


def newey_west_t(x: np.ndarray, lag: int | None = None) -> float:
    """HAC t-statistic on the mean. Trades cluster by session, so the iid t overstates."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 5:
        return np.nan
    if lag is None:
        lag = max(1, int(round(4 * (n / 100) ** (2 / 9))))
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else float(x.mean() / np.sqrt(s / n))


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * m / (rank + 1))
        q[i] = prev
    return q


def max_drawdown(equity: np.ndarray) -> float:
    e = np.asarray(equity, float)
    return float((np.maximum.accumulate(e) - e).max()) if len(e) else 0.0


# --------------------------------------------------------------------------- section 3

def psr(x: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(true per-observation Sharpe > benchmark), fat tails included."""
    x = np.asarray(x, float)
    n = len(x)
    sr = sharpe(x)
    if n < 3 or np.isnan(sr):
        return np.nan
    g3, g4 = moments(x)
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return np.nan
    return float(stats.norm.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / np.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """E[max SR] over `n_trials` independent trials whose Sharpes have variance `var_trials`."""
    if n_trials < 2 or var_trials <= 0:
        return 0.0
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_trials) * ((1.0 - EULER) * z1 + EULER * z2))


def dsr(x: np.ndarray, n_trials: int, var_trials: float) -> tuple:
    """Deflated Sharpe: PSR against the Sharpe a search of this size produces from noise alone."""
    sr_star = expected_max_sharpe(n_trials, var_trials)
    return psr(x, sr_star), sr_star


def min_trl(x: np.ndarray, sr_benchmark: float = 0.0, alpha: float = 0.05) -> float:
    """Observations needed before the Sharpe is distinguishable from the benchmark at `alpha`."""
    sr = sharpe(x)
    if np.isnan(sr) or sr <= sr_benchmark:
        return np.inf
    g3, g4 = moments(x)
    z = stats.norm.ppf(1.0 - alpha)
    return float(1.0 + (1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr) * (z / (sr - sr_benchmark)) ** 2)


def pbo(mat: np.ndarray, n_blocks: int = 12, max_combos: int = 2000, seed: int = 7) -> dict:
    """Probability of Backtest Overfitting by CSCV (Bailey, Borwein, Lopez de Prado, Zhu).

    `mat` is observations x strategies. The sample is cut into `n_blocks` blocks; every way of
    choosing half of them as in-sample gives one train/test pair. PBO is how often the strategy
    that wins in-sample lands below the MEDIAN out-of-sample -- i.e. how often selection is
    actively harmful rather than merely useless."""
    from itertools import combinations
    mat = np.asarray(mat, float)
    T, N = mat.shape
    if N < 2 or T < n_blocks * 2:
        return dict(pbo=np.nan, n_splits=0, logits=np.array([]))
    n_blocks -= n_blocks % 2
    blocks = np.array_split(np.arange(T), n_blocks)
    combos = list(combinations(range(n_blocks), n_blocks // 2))
    rng = np.random.default_rng(seed)
    if len(combos) > max_combos:
        combos = [combos[i] for i in rng.choice(len(combos), max_combos, replace=False)]
    logits = []
    for cin in combos:
        cin = set(cin)
        tr = np.concatenate([blocks[b] for b in range(n_blocks) if b in cin])
        te = np.concatenate([blocks[b] for b in range(n_blocks) if b not in cin])
        sr_in = np.array([sharpe(mat[tr, k]) for k in range(N)])
        sr_out = np.array([sharpe(mat[te, k]) for k in range(N)])
        if not np.isfinite(sr_in).any() or not np.isfinite(sr_out).any():
            continue
        best = int(np.nanargmax(sr_in))
        ok = np.isfinite(sr_out)
        # relative rank of the in-sample winner among the out-of-sample results
        rank = (np.sum(sr_out[ok] < sr_out[best]) + 1) / (ok.sum() + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(rank / (1 - rank)))
    logits = np.array(logits)
    return dict(pbo=float((logits < 0).mean()) if len(logits) else np.nan,
                n_splits=len(logits), logits=logits)


# --------------------------------------------------------------------------- bootstraps

def stationary_bootstrap_idx(n: int, mean_block: float, rng) -> np.ndarray:
    """Politis-Romano: geometric block lengths, wrapping. Preserves autocorrelation."""
    p = 1.0 / max(mean_block, 1.0)
    idx = np.empty(n, np.int64)
    i = rng.integers(0, n)
    for t in range(n):
        idx[t] = i
        if rng.random() < p:
            i = rng.integers(0, n)
        else:
            i = (i + 1) % n
    return idx


def circular_bootstrap_idx(n: int, block: int, rng) -> np.ndarray:
    block = max(1, int(block))
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, nb)
    return np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]


def block_bootstrap_ci(x: np.ndarray, stat, reps: int = 5000, mean_block: float = 5.0,
                       kind: str = "stationary", seed: int = 7, alpha: float = 0.05) -> dict:
    x = np.asarray(x, float)
    n = len(x)
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    for b in range(reps):
        idx = (stationary_bootstrap_idx(n, mean_block, rng) if kind == "stationary"
               else circular_bootstrap_idx(n, int(mean_block), rng))
        out[b] = stat(x[idx])
    out = out[np.isfinite(out)]
    return dict(point=float(stat(x)), lo=float(np.quantile(out, alpha / 2)),
                hi=float(np.quantile(out, 1 - alpha / 2)),
                p_le_zero=float((out <= 0).mean()), reps=len(out))


def whites_reality_check(f: np.ndarray, reps: int = 5000, mean_block: float = 5.0,
                         seed: int = 7) -> dict:
    """White's Reality Check. `f` is observations x models of performance RELATIVE to the benchmark.

    H0: the best model in the universe is no better than the benchmark. The null is imposed by
    recentring each bootstrap mean on the observed mean, so a universe of pure noise reproduces the
    same maximum by construction."""
    f = np.asarray(f, float)
    n, N = f.shape
    mu = f.mean(0)
    V = np.sqrt(n) * mu.max()
    rng = np.random.default_rng(seed)
    boot = np.empty(reps)
    for b in range(reps):
        idx = stationary_bootstrap_idx(n, mean_block, rng)
        boot[b] = (np.sqrt(n) * (f[idx].mean(0) - mu)).max()
    return dict(stat=float(V), p=float((boot >= V).mean()), n_models=N, reps=reps)


def hansen_spa(f: np.ndarray, reps: int = 5000, mean_block: float = 5.0, seed: int = 7) -> dict:
    """Hansen's SPA: studentised, and recentres only models that are not hopeless.

    White's RC is dragged down by bad models -- adding rules that lose money makes the best rule
    look more significant. SPA studentises by each model's own standard error and drops models
    below the threshold A_k from the recentring, which is why it is the more powerful test and the
    one to read when the universe is a parameter sweep containing obvious losers."""
    f = np.asarray(f, float)
    n, N = f.shape
    mu = f.mean(0)
    rng = np.random.default_rng(seed)
    # HAC-ish scale via the bootstrap itself, per Hansen: use the sample sd of the block means
    om = np.array([max(f[:, k].std(ddof=1), 1e-12) for k in range(N)])
    T = max(0.0, float((np.sqrt(n) * mu / om).max()))
    A = om * np.sqrt(2.0 * np.log(np.log(max(n, 3))) / n)
    g = np.where(mu >= -A, mu, 0.0)          # consistent recentring
    boot = np.empty(reps)
    for b in range(reps):
        idx = stationary_bootstrap_idx(n, mean_block, rng)
        z = np.sqrt(n) * (f[idx].mean(0) - g) / om
        boot[b] = max(0.0, z.max())
    return dict(stat=T, p=float((boot >= T).mean()), n_models=N, reps=reps)


def permutation_pvalue(observed: float, null: np.ndarray, higher_is_better: bool = True) -> float:
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    if not len(null):
        return np.nan
    k = (null >= observed).sum() if higher_is_better else (null <= observed).sum()
    return float((k + 1) / (len(null) + 1))


def risk_of_ruin(x: np.ndarray, start_equity: float, floor: float, n_trades: int,
                 reps: int = 20000, seed: int = 7, mean_block: float = 1.0) -> dict:
    """P(equity ever touches `floor`) over `n_trades`, resampling the observed trade distribution.

    `mean_block` > 1 uses a stationary bootstrap, so a strategy whose losses cluster is not given
    the free pass that iid resampling would hand it."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    ruined = 0
    finals = np.empty(reps)
    worst = np.empty(reps)
    for b in range(reps):
        idx = (rng.integers(0, len(x), n_trades) if mean_block <= 1
               else stationary_bootstrap_idx(n_trades, mean_block, rng) % len(x))
        eq = start_equity + np.cumsum(x[idx])
        finals[b] = eq[-1]
        worst[b] = eq.min()
        if eq.min() <= floor:
            ruined += 1
    return dict(p_ruin=ruined / reps, median_final=float(np.median(finals)),
                p5_final=float(np.quantile(finals, 0.05)),
                median_worst=float(np.median(worst)), reps=reps)
