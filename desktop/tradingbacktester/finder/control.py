"""The question a backtest result has to answer before it means anything.

A rule that made money is not evidence of a rule that works. Over this sample
the market rose, the geometry had its own base rate, and the session hours the
rule happened to trade in are not neutral. All three pay out without any skill
at all, so the useful question is not "did it make money" but **"did it beat
entering at random, at the same times, with the same geometry, paying the same
costs?"**

That is what a matched control measures. Entries are drawn to match the
candidate's own distribution of time-of-day, which prices in drift, costs,
barrier width and session timing together, and the candidate is scored against
the distribution of those draws rather than against zero.

Two implementations, and they agree:

* :func:`analytic_control` computes the control mean and its standard error in
  closed form. It is exact for the mean of independent draws, costs
  microseconds, and is therefore affordable as a *gate* on every candidate --
  which is the only way a control ever gets run on all of them rather than on
  the winner, where it would be far too late to matter.
* :func:`sampled_control` actually draws the entries. It is slower, makes no
  distributional assumption, and is run on the shortlist to confirm what the
  analytic gate said.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Below this many trades at one minute of the day, the pooled variance is used
#: instead of that minute's own: a single sample has no spread of its own, and
#: pretending otherwise makes every candidate look significant.
_MIN_PER_MINUTE = 5


@dataclass
class ControlResult:
    """What entering at random, at the same times, would have paid."""

    trades: int
    expected_per_trade: float
    """Mean per-trade result of the matched control."""
    standard_error: float
    """Standard error of that mean, so the comparison has a scale."""
    excess_per_trade: float
    """Candidate minus control, per trade. This is the number that matters."""
    z: float
    p_value: float
    """One-sided: the chance a control draw beats the candidate."""
    method: str = "analytic"
    draws: int = 0

    @property
    def beat_control(self) -> bool:
        return self.excess_per_trade > 0.0

    def describe(self, currency: str = "") -> str:
        """One line, including what the control itself paid.

        The excess alone reads as nonsense whenever the control is a long way
        from zero -- "+348 excess" beside "+52 per trade" looks like an error
        until you can see that random entries lost 295.
        """
        unit = f" {currency}" if currency else ""
        how = self.method + (f", {self.draws:,} draws" if self.draws else "")
        return (f"random entries at the same times made "
                f"{self.expected_per_trade:+,.2f}{unit} per trade, so the "
                f"edge is {self.excess_per_trade:+,.2f}{unit} "
                f"(p={self.p_value:.3f}, {how})")


def _minute_statistics(minutes: np.ndarray, values: np.ndarray
                       ) -> tuple[dict[int, tuple[float, float, int]], float, float]:
    """``{minute: (mean, variance, count)}`` plus the pooled mean and variance."""
    table: dict[int, tuple[float, float, int]] = {}
    pooled_mean = float(values.mean()) if values.size else 0.0
    pooled_var = float(values.var(ddof=1)) if values.size > 1 else 0.0
    if values.size == 0:
        return table, pooled_mean, pooled_var
    order = np.argsort(minutes, kind="stable")
    m_sorted = minutes[order]
    v_sorted = values[order]
    edges = np.flatnonzero(np.diff(m_sorted)) + 1
    for group_values, minute in zip(np.split(v_sorted, edges),
                                    m_sorted[np.concatenate(([0], edges))]):
        count = group_values.size
        variance = (float(group_values.var(ddof=1)) if count > 1 else pooled_var)
        table[int(minute)] = (float(group_values.mean()), variance, count)
    return table, pooled_mean, pooled_var


@dataclass(frozen=True)
class MinuteTable:
    """The control population, summarised once and reused.

    Every candidate in a search is scored against the SAME pool -- every bar a
    trade of this geometry could have opened on -- and summarising it means
    sorting and grouping half a million values. Doing that per candidate cost
    1.3 seconds of a 15-second search on the shipped 5-minute file, 991 times
    over, for an answer that never changed.

    Built once per (cache, block) and handed to :func:`analytic_control`.
    """

    table: dict[int, tuple[float, float, int]]
    pooled_mean: float
    pooled_var: float
    size: int

    @classmethod
    def build(cls, minutes: np.ndarray, values: np.ndarray) -> "MinuteTable":
        table, mean, var = _minute_statistics(minutes, values)
        return cls(table, mean, var, int(values.size))


def analytic_control(pool_minutes: np.ndarray, pool_values: np.ndarray,
                     trade_minutes: np.ndarray, trade_values: np.ndarray,
                     table: "MinuteTable | None" = None) -> ControlResult:
    """Score trades against random entries drawn at the same times.

    *pool_\** are every bar a trade could have been opened on, with what it
    would have paid; *trade_\** are the ones the candidate actually took.

    ``table`` is that pool already summarised. Pass one when scoring many
    candidates against the same pool; the pool arrays are then only read for
    their size, and passing them at all stays optional so a single call needs
    no ceremony.
    """
    n = int(trade_values.size)
    pool_size = table.size if table is not None else int(pool_values.size)
    if n == 0 or pool_size == 0:
        return ControlResult(0, 0.0, 0.0, 0.0, 0.0, 1.0)

    if table is None:
        table = MinuteTable.build(pool_minutes, pool_values)
    pooled_mean, pooled_var = table.pooled_mean, table.pooled_var
    table = table.table
    total_mean = 0.0
    total_var = 0.0
    for minute, count in zip(*np.unique(trade_minutes, return_counts=True)):
        mean, variance, seen = table.get(int(minute),
                                         (pooled_mean, pooled_var, 0))
        if seen < _MIN_PER_MINUTE:
            variance = max(variance, pooled_var)
        total_mean += float(count) * mean
        total_var += float(count) * variance

    expected = total_mean / n
    standard_error = math.sqrt(total_var) / n if total_var > 0 else 0.0
    actual = float(trade_values.mean())
    excess = actual - expected
    if standard_error <= 0:
        return ControlResult(n, expected, 0.0, excess, 0.0,
                             0.0 if excess > 0 else 1.0)
    z = excess / standard_error
    return ControlResult(n, expected, standard_error, excess, z,
                         _upper_tail(z))


def sampled_control(pool_minutes: np.ndarray, pool_values: np.ndarray,
                    trade_minutes: np.ndarray, trade_values: np.ndarray,
                    draws: int = 2000, seed: int = 0) -> ControlResult:
    """The same comparison, by actually drawing the random entries.

    Makes no assumption about the shape of the distribution, which matters:
    trade results are not normal, they are a spike at the target, a spike at
    the stop and a smear in between.
    """
    n = int(trade_values.size)
    if n == 0 or pool_values.size == 0:
        return ControlResult(0, 0.0, 0.0, 0.0, 0.0, 1.0, "sampled", draws)

    rng = np.random.default_rng(seed)
    buckets: dict[int, np.ndarray] = {}
    order = np.argsort(pool_minutes, kind="stable")
    m_sorted = pool_minutes[order]
    v_sorted = pool_values[order]
    edges = np.flatnonzero(np.diff(m_sorted)) + 1
    for group, minute in zip(np.split(v_sorted, edges),
                             m_sorted[np.concatenate(([0], edges))]):
        buckets[int(minute)] = group

    wanted, counts = np.unique(trade_minutes, return_counts=True)
    total = float(counts.sum())
    # One draw per minute of the day, of shape (draws, count), rather than one
    # call per (draw, minute) pair. On a one-minute chart with two thousand
    # draws the loop version made three quarters of a million calls to the
    # generator for a single finding.
    totals = np.zeros(draws, dtype="float64")
    for minute, count in zip(wanted, counts):
        pool = buckets.get(int(minute))
        if pool is None or pool.size == 0:
            pool = v_sorted
        picked = rng.choice(pool, size=(draws, int(count)), replace=True)
        totals += picked.sum(axis=1)
    means = totals / total

    actual = float(trade_values.mean())
    expected = float(means.mean())
    spread = float(means.std(ddof=1)) if draws > 1 else 0.0
    beaten = float((means >= actual).mean())
    # Never report p = 0 from a finite number of draws: the honest floor is one
    # draw in the number taken.
    p_value = max(beaten, 1.0 / (draws + 1))
    z = (actual - expected) / spread if spread > 0 else 0.0
    return ControlResult(n, expected, spread, actual - expected, z, p_value,
                         "sampled", draws)


def _upper_tail(z: float) -> float:
    """``P(Z > z)`` for a standard normal, without SciPy."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def bh_q_values(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values.

    ``q = min over ranks at or above this one of p * n / rank``, clipped to 1.
    Printing the raw p-value beside a "q=" label -- which is easy to do by
    accident -- tells the reader a result is n times more certain than the
    correction actually allows.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    out = [1.0] * n
    running = 1.0
    for rank in range(n, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * n / rank)
        out[index] = min(1.0, max(0.0, running))
    return out


def benjamini_hochberg(p_values: list[float], alpha: float = 0.10) -> list[bool]:
    """Which p-values survive a false-discovery-rate correction.

    Testing eight hundred rules and reporting the best one at p=0.01 is not a
    discovery: at that multiplicity eight of them are expected to beat 0.01 by
    chance. This is the correction that says so.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    survive = [False] * n
    cutoff = -1
    for rank, index in enumerate(order, start=1):
        if p_values[index] <= alpha * rank / n:
            cutoff = rank
    for rank, index in enumerate(order, start=1):
        if rank <= cutoff:
            survive[index] = True
    return survive
