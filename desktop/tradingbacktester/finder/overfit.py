"""How much of a search result is the search, and not the market.

This module answers one question in two ways, and both are the named,
citable versions of things this package was already doing informally.

**The Deflated Sharpe Ratio** (Bailey and Lopez de Prado, 2014). A Sharpe
ratio quoted from the best of N tries is not the Sharpe ratio of a strategy;
it is the Sharpe ratio of a maximum. The deflation asks what the best of N
tries would score with no skill at all, and reports the probability that the
observed Sharpe exceeds *that*, rather than the probability it exceeds zero.
It corrects for three things at once: how many things were tried, how much the
tries varied, and how non-normal the returns are -- a strategy that pays small
amounts often and loses hugely rarely has a flattering Sharpe and a negative
skew, and the deflation charges it for both.

**The Probability of Backtest Overfitting** (Bailey, Borwein, Lopez de Prado
and Zhu, 2015), by combinatorially symmetric cross-validation. This measures
something the Sharpe of any individual strategy cannot: whether the *selection
procedure* generalises. Split the sample into S blocks, take every way of
dealing half of them into a training set and half into a testing set, pick the
best strategy on the training half, and see where it lands among the others on
the testing half. If picking the winner is skill, it stays near the top. If
picking the winner is fitting noise, it lands anywhere -- and about half the
time, below the median.

PBO is the fraction of those splits where the in-sample winner came out below
the out-of-sample median. **A PBO near 0.5 means the search has learned
nothing that survives being asked again.** It is reported whether or not
anything survived the multiplicity correction, because it describes the
search, not the survivor -- and a search with a high PBO that happened to
produce a survivor is the most dangerous output this application can make.

Both are computed on the RESEARCH block only. Running cross-validation over
the whole series would put the locked block inside the selection, which is the
mistake the split exists to prevent.

**What the cross-validation cannot see, and what covers it.** The splits are
combinatorial rather than sequential, which is the point -- it avoids resting
everything on one arbitrary cut -- but it means the measurement is blind to
*when* an edge existed. A candidate that worked in the first half of the
research block and stopped working in the second has, on average, half its
good blocks in any testing half, so it still tests well: measured across the
range, the probability responds to how CONCENTRATED an edge is (one block in
twelve gives 0.65) and not at all to whether the good blocks came early or
late (six in twelve gives 0.001, however they are arranged). That failure --
an edge that was real and then stopped being real -- is exactly what the
sequential locked block catches. Neither measurement subsumes the other, which
is why this application keeps both, and reading this one as protection against
regime change would be a mistake. `tests/test_overfit.py` asserts the
limitation so it cannot be quietly forgotten.

No SciPy. The normal CDF is `erfc` from the standard library and its inverse
is Acklam's rational approximation, which is accurate to about 1.15e-9 over
the whole range -- far tighter than anything downstream can use.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Euler-Mascheroni, in the expected-maximum expression.
_EULER = 0.5772156649015329

#: Blocks the sample is cut into for cross-validation. S must be even; the
#: number of splits is C(S, S/2), so 12 gives 924 and 16 gives 12,870. Twelve
#: is enough for a stable estimate and cheap enough to run on every search.
DEFAULT_BLOCKS = 12

#: Below this many trades in a block, a candidate has no measurable
#: performance there and the whole candidate is dropped from the
#: cross-validation rather than contributing a t-statistic built on two trades.
MIN_TRADES_PER_BLOCK = 2

#: Candidates fed to the cross-validation, best first. The estimate is a
#: fraction over splits and does not need every trial; the cost is
#: O(splits x candidates) in both time and memory.
MAX_CANDIDATES = 2000


# ---------------------------------------------------------------------------
# the two normal functions, without SciPy
# ---------------------------------------------------------------------------

def norm_cdf(z: float) -> float:
    """``P(Z <= z)`` for a standard normal."""
    return 0.5 * math.erfc(-float(z) / math.sqrt(2.0))


#: Acklam's coefficients for the inverse normal CDF.
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)
_P_LOW = 0.02425


def norm_ppf(p: float) -> float:
    """The inverse of :func:`norm_cdf`, by Acklam's rational approximation.

    Refined by one step of Halley's method against `erfc`, which takes the
    approximation from about 1.15e-9 to full double precision. The refinement
    costs one `erfc` call and removes any need to think about the bound.
    """
    p = float(p)
    if not (0.0 < p < 1.0):
        if p <= 0.0:
            return -math.inf
        if p >= 1.0:
            return math.inf
        return math.nan

    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = ((((( _C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
             + _C[5]) / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    elif p <= 1.0 - _P_LOW:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r
             + _A[5]) * q / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r
                              + _B[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -((((( _C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q
              + _C[5]) / ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)

    error = 0.5 * math.erfc(-x / math.sqrt(2.0)) - p
    u = error * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


# ---------------------------------------------------------------------------
# the deflated Sharpe ratio
# ---------------------------------------------------------------------------

def expected_max_sharpe(trials: int, trial_variance: float) -> float:
    """The Sharpe the best of ``trials`` tries reaches with no skill at all.

    Bailey and Lopez de Prado's expression for the expected maximum of N draws
    from a normal with the observed cross-trial variance:

        E[max SR] = sqrt(V) * [ (1 - g) * Z(1 - 1/N) + g * Z(1 - 1/(N e)) ]

    with ``g`` the Euler-Mascheroni constant and ``Z`` the inverse normal CDF.
    It grows like ``sqrt(2 ln N)``: a hundred tries is worth about 2.5 standard
    deviations of free Sharpe, ten thousand about 3.9.
    """
    trials = int(trials)
    trial_variance = float(trial_variance)
    if trials <= 1 or not math.isfinite(trial_variance) or trial_variance <= 0:
        return 0.0
    spread = math.sqrt(trial_variance)
    first = norm_ppf(1.0 - 1.0 / trials)
    second = norm_ppf(1.0 - 1.0 / (trials * math.e))
    return spread * ((1.0 - _EULER) * first + _EULER * second)


@dataclass(frozen=True)
class DeflatedSharpe:
    """An observed Sharpe, and what is left of it after the search is priced."""

    sharpe: float
    """Observed, per trade, not annualised."""
    benchmark: float
    """What the best of this many tries reaches on no skill: ``SR0``."""
    trials: int
    observations: int
    skew: float
    kurtosis: float
    """Non-excess: 3.0 is normal."""
    probability: float
    """P(the true Sharpe is above the benchmark). This is the DSR."""

    @property
    def clears(self) -> bool:
        """Whether the observed Sharpe beats the best-of-N benchmark at all."""
        return self.sharpe > self.benchmark

    @property
    def significant(self) -> bool:
        """The paper's threshold: a DSR above 0.95."""
        return self.probability > 0.95

    def to_dict(self) -> dict[str, Any]:
        return {"sharpe": round(self.sharpe, 6),
                "benchmark_sharpe": round(self.benchmark, 6),
                "trials": self.trials, "observations": self.observations,
                "skew": round(self.skew, 4),
                "kurtosis": round(self.kurtosis, 4),
                "deflated_sharpe": round(self.probability, 6),
                "significant": self.significant}

    def redeflate(self, trials: int, trial_variance: float) -> "DeflatedSharpe":
        """The same Sharpe, priced for a DIFFERENT number of tries.

        A rule found by one sweep of a grid was really selected out of the
        whole grid, so its benchmark is the grid's, not the sweep's. Every
        input the deflation needs beyond the benchmark -- the Sharpe, the
        count, the skew and the kurtosis -- is already recorded here, so the
        re-pricing needs no access to the trades and cannot disagree with the
        original by rounding.
        """
        benchmark = expected_max_sharpe(trials, trial_variance)
        if self.observations < 2:
            return DeflatedSharpe(self.sharpe, benchmark, int(trials),
                                  self.observations, self.skew, self.kurtosis,
                                  0.0)
        variance = (1.0 - self.skew * self.sharpe
                    + 0.25 * (self.kurtosis - 1.0) * self.sharpe * self.sharpe)
        if not math.isfinite(variance) or variance <= 0:
            variance = 1.0
        z = ((self.sharpe - benchmark) * math.sqrt(self.observations - 1)
             / math.sqrt(variance))
        return DeflatedSharpe(self.sharpe, benchmark, int(trials),
                              self.observations, self.skew, self.kurtosis,
                              norm_cdf(z))

    def describe(self) -> str:
        if self.observations < 2:
            return "not enough trades to deflate a Sharpe ratio"
        verdict = ("clears it" if self.clears else "does NOT clear it")
        return (f"Sharpe {self.sharpe:+.4f}/trade against {self.benchmark:+.4f} "
                f"for the best of {self.trials:,} tries on no skill — "
                f"{verdict}; deflated Sharpe {self.probability:.3f} "
                f"({'significant' if self.significant else 'not significant'} "
                f"at 0.95)")


def deflated_sharpe(returns: np.ndarray, trials: int,
                    trial_variance: float) -> DeflatedSharpe:
    """Deflate an observed Sharpe for the search that produced it.

    ``returns`` is one number per trade -- net cash or net points, it only has
    to be consistent -- and the Sharpe is per trade, not annualised. Deflating
    an annualised figure would require dividing the benchmark by the same
    factor, and one of the two nearly always gets forgotten.
    """
    values = np.asarray(returns, dtype="float64")
    values = values[np.isfinite(values)]
    n = int(values.size)
    benchmark = expected_max_sharpe(trials, trial_variance)
    if n < 2:
        return DeflatedSharpe(0.0, benchmark, int(trials), n, 0.0, 3.0, 0.0)

    mean = float(values.mean())
    spread = float(values.std(ddof=1))
    if spread <= 0:
        return DeflatedSharpe(0.0, benchmark, int(trials), n, 0.0, 3.0, 0.0)
    sharpe = mean / spread

    centred = (values - mean) / spread
    skew = float((centred ** 3).mean())
    kurtosis = float((centred ** 4).mean())

    # The variance of the Sharpe estimator under non-normal returns
    # (Mertens, 2002): 1 - g3*SR + (g4 - 1)/4 * SR^2, over (n - 1).
    variance = 1.0 - skew * sharpe + 0.25 * (kurtosis - 1.0) * sharpe * sharpe
    if not math.isfinite(variance) or variance <= 0:
        # Can happen on a heavily skewed sample; fall back to the normal case
        # rather than reporting a probability built on a negative variance.
        variance = 1.0
    z = (sharpe - benchmark) * math.sqrt(n - 1) / math.sqrt(variance)
    return DeflatedSharpe(sharpe, benchmark, int(trials), n, skew, kurtosis,
                          norm_cdf(z))


# ---------------------------------------------------------------------------
# the probability of backtest overfitting
# ---------------------------------------------------------------------------

@dataclass
class PBOResult:
    """What happened when the selection procedure was asked to do it again."""

    probability: float
    """The fraction of splits where the in-sample winner came out below the
    out-of-sample median. Near 0.5 means selection learned nothing."""
    splits: int
    candidates: int
    blocks: int
    median_logit: float
    """Median of ``ln(w / (1 - w))``, the winner's relative out-of-sample rank.
    Positive is good; zero is a coin flip."""
    degradation: float
    """Mean out-of-sample performance of the winner minus its in-sample
    performance, in the units of the metric. Almost always negative."""
    probability_of_loss: float
    """How often the in-sample winner had a negative metric out of sample."""
    ran: bool = True
    reason: str = ""

    @property
    def overfit(self) -> bool:
        """The conventional reading: above 0.5 is a search fitting noise."""
        return self.ran and self.probability > 0.5

    def to_dict(self) -> dict[str, Any]:
        if not self.ran:
            return {"ran": False, "reason": self.reason}
        return {"ran": True, "pbo": round(self.probability, 4),
                "splits": self.splits, "candidates": self.candidates,
                "blocks": self.blocks,
                "median_logit": round(self.median_logit, 4),
                "degradation": round(self.degradation, 4),
                "probability_of_loss": round(self.probability_of_loss, 4)}

    def describe(self) -> str:
        if not self.ran:
            return f"probability of backtest overfitting: not measured — {self.reason}"
        reading = ("the search is fitting noise" if self.probability > 0.5
                   else "selection carried over" if self.probability < 0.25
                   else "selection carried over weakly")
        return (f"probability of backtest overfitting {self.probability:.2f} "
                f"over {self.splits:,} splits of {self.candidates:,} "
                f"candidates — {reading}. The in-sample winner lost "
                f"{abs(self.degradation):.3f} of its metric out of sample and "
                f"was outright negative {self.probability_of_loss:.0%} of the "
                f"time.")


def _block_statistics(counts: np.ndarray, sums: np.ndarray,
                      squares: np.ndarray, mask: np.ndarray
                      ) -> np.ndarray:
    """The t-statistic of per-trade result, for every (split, candidate).

    ``mask`` is ``(splits, blocks)``: a 1 where that block is in this side of
    the split. Everything is a matrix product over blocks, so the whole grid of
    splits is one pass rather than a Python loop over `C(12, 6)` of them.
    """
    n = mask @ counts                      # (splits, candidates)
    total = mask @ sums
    square = mask @ squares
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = np.where(n > 0, total / np.maximum(n, 1), 0.0)
        variance = np.where(n > 1,
                            (square - n * mean * mean) / np.maximum(n - 1, 1),
                            np.nan)
        t = np.where((n > 1) & (variance > 0),
                     mean * np.sqrt(np.maximum(n, 1)) / np.sqrt(
                         np.maximum(variance, 1e-300)),
                     np.nan)
    return t


def probability_of_overfitting(counts: np.ndarray, sums: np.ndarray,
                               squares: np.ndarray,
                               blocks: int = DEFAULT_BLOCKS) -> PBOResult:
    """Combinatorially symmetric cross-validation over a grid of candidates.

    The three inputs are ``(blocks, candidates)`` matrices of per-block trade
    count, sum of trade results and sum of their squares -- everything needed
    to rebuild a mean and a variance over any union of blocks without keeping
    the trades themselves. The performance metric is the t-statistic of
    per-trade result, which is what a search of this kind is really ranking on:
    it rewards a bigger edge and more trades at that edge, and is comparable
    between candidates that traded different amounts.

    Returns a result with ``ran=False`` and a reason rather than raising, so a
    search on a sample too short to cross-validate still reports everything
    else it measured.
    """
    counts = np.asarray(counts, dtype="float64")
    sums = np.asarray(sums, dtype="float64")
    squares = np.asarray(squares, dtype="float64")
    if counts.ndim != 2 or counts.shape != sums.shape != squares.shape:
        raise ValueError("counts, sums and squares must be the same "
                         "(blocks, candidates) shape")

    s = int(blocks)
    if s % 2:
        s -= 1
    if s < 4:
        return PBOResult(math.nan, 0, 0, s, math.nan, math.nan, math.nan,
                         False, "cross-validation needs at least four blocks")
    if counts.shape[0] != s:
        return PBOResult(math.nan, 0, 0, s, math.nan, math.nan, math.nan,
                         False, f"expected {s} blocks of data, got "
                                f"{counts.shape[0]}")

    # A candidate that did not trade in every block cannot be ranked in every
    # split, and dropping it is honest where imputing a zero would not be: a
    # candidate that sat out a block did not "break even" there.
    usable = np.all(counts >= MIN_TRADES_PER_BLOCK, axis=0)
    if usable.sum() < 2:
        return PBOResult(
            math.nan, 0, int(usable.sum()), s, math.nan, math.nan, math.nan,
            False, f"fewer than two candidates traded at least "
                   f"{MIN_TRADES_PER_BLOCK} times in every one of the {s} "
                   f"blocks, so there is nothing to rank against")
    counts, sums, squares = counts[:, usable], sums[:, usable], squares[:, usable]

    if counts.shape[1] > MAX_CANDIDATES:
        # Best first by whole-sample t-statistic. The estimate is a fraction
        # over splits; it does not need every trial, and the ones that matter
        # are the ones a selection procedure would ever pick.
        whole = _block_statistics(counts, sums, squares,
                                  np.ones((1, s), dtype="float64"))[0]
        keep = np.argsort(np.where(np.isfinite(whole), -whole, np.inf))
        keep = keep[:MAX_CANDIDATES]
        counts, sums, squares = counts[:, keep], sums[:, keep], squares[:, keep]

    half = s // 2
    combos = list(itertools.combinations(range(s), half))
    train = np.zeros((len(combos), s), dtype="float64")
    for row, picked in enumerate(combos):
        train[row, list(picked)] = 1.0
    test = 1.0 - train

    in_sample = _block_statistics(counts, sums, squares, train)
    out_sample = _block_statistics(counts, sums, squares, test)

    # A NaN must not win, and must not be ranked against.
    finite = np.isfinite(in_sample) & np.isfinite(out_sample)
    rows = np.flatnonzero(finite.sum(axis=1) >= 2)
    if rows.size == 0:
        return PBOResult(math.nan, len(combos), int(counts.shape[1]), s,
                         math.nan, math.nan, math.nan, False,
                         "no split had two comparable candidates")

    logits: list[float] = []
    degradation: list[float] = []
    losses = 0
    for row in rows:
        ok = finite[row]
        chosen = np.flatnonzero(ok)[int(np.argmax(in_sample[row][ok]))]
        others = out_sample[row][ok]
        n = int(others.size)
        # The winner's relative rank out of sample: 1.0 is best, 0.0 worst.
        # Ranked with ties shared, so a grid of identical candidates reports a
        # coin flip rather than a win.
        value = out_sample[row, chosen]
        below = float((others < value).sum())
        equal = float((others == value).sum())
        rank = (below + 0.5 * equal) / n
        omega = min(max(rank, 1.0 / (n + 1)), 1.0 - 1.0 / (n + 1))
        logits.append(math.log(omega / (1.0 - omega)))
        degradation.append(float(value - in_sample[row, chosen]))
        losses += int(value < 0)

    logit = np.asarray(logits, dtype="float64")
    return PBOResult(
        probability=float((logit <= 0.0).mean()),
        splits=int(logit.size),
        candidates=int(counts.shape[1]),
        blocks=s,
        median_logit=float(np.median(logit)),
        degradation=float(np.mean(degradation)),
        probability_of_loss=losses / float(logit.size),
    )


# ---------------------------------------------------------------------------
# collecting the matrices a search produces
# ---------------------------------------------------------------------------

@dataclass
class BlockCollector:
    """Accumulates per-block trade statistics as a search scores candidates.

    A search already computes, for every candidate, which bars it traded on and
    what each trade paid. Three ``bincount`` calls per candidate turn that into
    the only thing cross-validation needs, at a cost that does not show up in
    the profile, and without keeping any trade.
    """

    block_of: np.ndarray
    """Which block each bar of the research window belongs to."""
    blocks: int
    counts: list[np.ndarray] = field(default_factory=list)
    sums: list[np.ndarray] = field(default_factory=list)
    squares: list[np.ndarray] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    purged: int = 0
    """Bars dropped from the end of every block. See :meth:`over`."""

    @classmethod
    def over(cls, split: int, blocks: int = DEFAULT_BLOCKS,
             total: int = 0, purge: int = 0) -> "BlockCollector | None":
        """Cut the research block into ``blocks`` equal contiguous slices.

        Contiguous and in time order, never interleaved: blocks that are
        shuffled in time would let a training set sit on both sides of a
        testing set separated by minutes, and every serial correlation in the
        data would then read as skill.

        ``purge`` is the longest a trade may run, in bars, and the last
        ``purge`` bars of every block are removed. This is Lopez de Prado's
        purging, and it is needed because the splits are combinatorial: a trade
        signalled just before the end of block 3 finishes inside block 4, so if
        3 is dealt into training and 4 into testing, part of that trade's
        result was decided by the testing data.

        **Measured, the leak is below the noise floor here**, and that is
        stated rather than left as an implication: on US30 15m intraday, a
        48-bar hold against a 10,500-bar block, purging moved the probability
        of overfitting from 0.2965 to 0.2846 -- about eleven splits out of 924,
        which is what dropping half a percent of the trades does to a ranking
        whether or not any of them leaked. So this is kept because the leak is
        real in principle and the fix is free, NOT because it was caught
        changing an answer. On a geometry with a longer hold or a shorter
        research block it would matter more, and there is no reason to find out
        the hard way which one a user has.

        No embargo beyond the purge: an embargo protects against a training
        set that comes AFTER the testing set in time, which the combinatorial
        construction does produce. Purging the tail of every block covers both
        directions here, because every block is both a potential training and a
        potential testing block and the trades only ever run forwards.
        """
        split = int(split)
        blocks = int(blocks) - (int(blocks) % 2)
        if split < blocks * 2 or blocks < 4:
            return None
        total = max(int(total), split)
        edges = np.linspace(0, split, blocks + 1).astype("int64")
        purge = max(0, int(purge))
        # A purge that would empty a block is refused rather than applied: the
        # cross-validation is worth more than the last few bars of each block.
        width = int(np.min(np.diff(edges)))
        if purge >= width // 2:
            purge = 0
        block_of = np.full(total, -1, dtype="int64")
        for index in range(blocks):
            block_of[edges[index]:edges[index + 1] - purge] = index
        return cls(block_of=block_of, blocks=blocks, purged=purge)

    def add(self, taken: np.ndarray, values: np.ndarray, label: str = "") -> None:
        """Record one candidate: a boolean mask of trades and their results."""
        idx = np.flatnonzero(taken)
        if idx.size:
            block = self.block_of[idx]
            keep = block >= 0
            idx, block = idx[keep], block[keep]
        if idx.size == 0:
            zero = np.zeros(self.blocks, dtype="float64")
            self.counts.append(zero)
            self.sums.append(zero.copy())
            self.squares.append(zero.copy())
            self.labels.append(label)
            return
        result = values[idx].astype("float64", copy=False)
        self.counts.append(np.bincount(block, minlength=self.blocks
                                       ).astype("float64"))
        self.sums.append(np.bincount(block, weights=result,
                                     minlength=self.blocks))
        self.squares.append(np.bincount(block, weights=result * result,
                                        minlength=self.blocks))
        self.labels.append(label)

    def result(self) -> PBOResult:
        """Run the cross-validation over everything collected."""
        if not self.counts:
            return PBOResult(math.nan, 0, 0, self.blocks, math.nan, math.nan,
                             math.nan, False, "no candidates were collected")
        return probability_of_overfitting(
            np.stack(self.counts, axis=1), np.stack(self.sums, axis=1),
            np.stack(self.squares, axis=1), self.blocks)
