"""Measuring whether a feature predicts anything, and saying how sure that is.

The correlation between an indicator and what happens next is easy to compute
and almost always misleading, for two reasons that this module exists to
handle.

**Overlapping observations.** A trade opened on this bar and a trade opened on
the next one share most of their future. Treating those as two independent
observations inflates the sample size by roughly the horizon -- a fortyfold
overstatement on a forty-bar hold -- and every t-statistic with it. The
standard errors here are Newey-West with the lag set to the horizon, which is
the correction for exactly that.

**Multiplicity.** Eighty features against four horizons is a lot of chances.
The p-values are corrected, and the number of *independent* features is
reported alongside the number of significant ones, because eighty features are
rarely eighty ideas.

And one thing statistics cannot tell you: whether the edge is big enough to
trade. A rank correlation of 0.03 can be overwhelmingly significant on half a
million bars and worth a quarter of a tick against a six-tick round turn. So
every result is also reported in money.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Deciles used for the economic spread.  Ten buckets need a few thousand
#: observations to be stable; below that the study says so.
_BUCKETS = 10


@dataclass
class ICResult:
    """What one feature predicts about one target, and how sure we are."""

    name: str
    observations: int
    ic: float
    """Spearman rank correlation between the feature and the outcome."""
    standard_error: float
    t_stat: float
    p_value: float
    q_value: float = 1.0
    """The p-value after correcting for how many features were tested."""
    top_decile: float = 0.0
    """Mean outcome of the highest tenth of the feature, in account currency."""
    bottom_decile: float = 0.0
    spread: float = 0.0
    """Top decile minus bottom decile: what the feature is worth per trade."""
    spread_error: float = 0.0
    monotonic: float = 0.0
    """Rank correlation between decile number and decile mean, -1 to +1. A real
    signal is monotone across the buckets, not a spike in one of them."""
    lag: int = 0

    @property
    def significant(self) -> bool:
        return self.q_value <= 0.10

    def describe(self, currency: str = "USD", cost: float = 0.0) -> str:
        economics = (f"{self.spread:+,.2f} {currency}/trade between the top and "
                     f"bottom tenth")
        if cost > 0:
            economics += f" against a {cost:,.2f} {currency} round turn"
        return (f"IC {self.ic:+.4f} (t={self.t_stat:+.2f}, q={self.q_value:.3f}); "
                f"{economics}; monotone {self.monotonic:+.2f}")


def rank_standardise(values: np.ndarray) -> np.ndarray:
    """Rank-transform to mean 0, unit variance, NaN preserved.

    Ranks rather than raw values because an indicator's distribution is its
    own business: RSI is bounded, a z-score is not, and a volume ratio has a
    tail that would otherwise decide the correlation by itself.
    """
    values = np.asarray(values, dtype="float64")
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values)
    count = int(ok.sum())
    if count < 3:
        return out
    present = values[ok]
    order = np.argsort(present, kind="stable")
    sorted_values = present[order]
    # Average the ranks of ties, or a feature with many equal values (a
    # bounded oscillator sitting at its floor) gets an arbitrary ordering.
    # Done with run boundaries rather than a loop: this is called several
    # hundred times per study, and a per-element loop over a 400,000-bar block
    # costs more than every other computation in the study put together.
    starts = np.flatnonzero(np.concatenate(
        ([True], sorted_values[1:] != sorted_values[:-1])))
    ends = np.concatenate((starts[1:], [count]))
    average = (starts + ends - 1) / 2.0
    ranks = np.empty(count, dtype="float64")
    ranks[order] = np.repeat(average, ends - starts)
    centred = ranks - ranks.mean()
    spread = centred.std()
    if spread <= 0:
        return out
    out[ok] = centred / spread
    return out


def newey_west(values: np.ndarray, lag: int) -> tuple[float, float]:
    """``(mean, standard error)`` for a series whose terms overlap.

    With ``lag`` zero this is the ordinary standard error of a mean. With a
    positive lag the autocovariances up to that lag are added with Bartlett
    weights, which is what stops overlapping trades being counted as
    independent evidence.
    """
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    n = values.size
    if n < 3:
        return (float(values.mean()) if n else 0.0), 0.0
    mean = float(values.mean())
    centred = values - mean
    variance = float(np.dot(centred, centred)) / n
    total = variance
    lag = max(0, min(int(lag), n - 2))
    for k in range(1, lag + 1):
        cov = float(np.dot(centred[:-k], centred[k:])) / n
        total += 2.0 * (1.0 - k / (lag + 1.0)) * cov
    if total <= 0:
        # A negative Newey-West variance is possible and meaningless; fall back
        # to the uncorrected one rather than reporting a zero standard error,
        # which would make everything look certain.
        total = variance
    return mean, math.sqrt(total / n)


def two_sided_p(t_stat: float) -> float:
    """``P(|Z| > |t|)`` for a standard normal, without SciPy."""
    return math.erfc(abs(float(t_stat)) / math.sqrt(2.0))


def decile_profile(feature: np.ndarray, target: np.ndarray,
                   buckets: int = _BUCKETS) -> tuple[np.ndarray, np.ndarray]:
    """Mean outcome in each bucket of the feature, lowest first."""
    ok = np.isfinite(feature) & np.isfinite(target)
    if int(ok.sum()) < buckets * 5:
        return np.full(buckets, np.nan), np.zeros(buckets, dtype="int64")
    values = feature[ok]
    outcomes = target[ok]
    edges = np.quantile(values, np.linspace(0.0, 1.0, buckets + 1))
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    index = np.clip(np.searchsorted(edges, values, side="right") - 1, 0,
                    buckets - 1)
    means = np.full(buckets, np.nan)
    counts = np.zeros(buckets, dtype="int64")
    for b in range(buckets):
        picked = outcomes[index == b]
        counts[b] = picked.size
        if picked.size:
            means[b] = float(picked.mean())
    return means, counts


def evaluate(name: str, feature: np.ndarray, target: np.ndarray,
             lag: int) -> ICResult:
    """Score one feature against one outcome series."""
    ok = np.isfinite(feature) & np.isfinite(target)
    count = int(ok.sum())
    if count < 100:
        return ICResult(name, count, 0.0, 0.0, 0.0, 1.0)

    x = rank_standardise(np.where(ok, feature, np.nan))
    y = rank_standardise(np.where(ok, target, np.nan))
    product = (x * y)[ok]
    ic, error = newey_west(product, lag)
    t_stat = ic / error if error > 0 else 0.0
    p_value = two_sided_p(t_stat)

    means, counts = decile_profile(feature[ok], target[ok])
    finite = np.isfinite(means)
    spread = 0.0
    spread_error = 0.0
    monotonic = 0.0
    if finite.sum() >= 4:
        spread = float(means[finite][-1] - means[finite][0])
        top = target[ok][feature[ok] >= np.quantile(feature[ok], 0.9)]
        bottom = target[ok][feature[ok] <= np.quantile(feature[ok], 0.1)]
        _, top_err = newey_west(top, lag)
        _, bottom_err = newey_west(bottom, lag)
        spread_error = math.sqrt(top_err ** 2 + bottom_err ** 2)
        rank_index = rank_standardise(np.arange(int(finite.sum()),
                                                dtype="float64"))
        rank_means = rank_standardise(means[finite])
        monotonic = float(np.nanmean(rank_index * rank_means))

    return ICResult(name=name, observations=count, ic=float(ic),
                    standard_error=float(error), t_stat=float(t_stat),
                    p_value=float(p_value), top_decile=float(
                        means[finite][-1]) if finite.any() else 0.0,
                    bottom_decile=float(means[finite][0]) if finite.any() else 0.0,
                    spread=spread, spread_error=spread_error,
                    monotonic=monotonic, lag=int(lag))


def redundancy_groups(matrix: np.ndarray, names: list[str],
                      threshold: float = 0.9) -> list[list[str]]:
    """Cluster features that are saying the same thing.

    Eighty features are not eighty ideas. Reporting "twelve were significant"
    without saying that nine of them are the same momentum measured nine ways
    is the difference between a finding and a restatement.
    """
    columns = matrix.shape[1]
    ranked = np.column_stack([rank_standardise(matrix[:, j])
                              for j in range(columns)]) if columns else matrix
    parent = list(range(columns))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in range(columns):
        for b in range(a + 1, columns):
            ok = np.isfinite(ranked[:, a]) & np.isfinite(ranked[:, b])
            if int(ok.sum()) < 50:
                continue
            correlation = float(np.mean(ranked[ok, a] * ranked[ok, b]))
            if abs(correlation) >= threshold:
                parent[find(b)] = find(a)

    clusters: dict[int, list[str]] = {}
    for j in range(columns):
        clusters.setdefault(find(j), []).append(names[j])
    return sorted(clusters.values(), key=lambda g: (-len(g), g[0]))
