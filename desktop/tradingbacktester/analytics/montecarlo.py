"""Monte Carlo resampling of a trade sequence.

A backtest produces one path. That path is one draw from a distribution the
strategy could have produced, and the shape of the distribution is what tells
you whether the drawdown you saw was the worst you should plan for or a
comfortable sample of a much worse one.

Three resamplers, answering three different questions:

* **Shuffle** — the same trades in a different order. The final equity is
  identical in every draw by construction; only the *path* changes. This is
  the honest answer to "how much of my drawdown was the order the trades
  happened to arrive in?"
* **Bootstrap** — draw the same number of trades with replacement. The final
  equity moves too, because the sample of trades changes. This answers "how
  much of my result was the particular trades I got?" and it assumes the
  trades you have are a fair sample of the population, which is a real
  assumption and not always a safe one.
* **Block bootstrap** — the same, but in contiguous runs. Trades are not
  independent: they cluster by regime, so a plain bootstrap breaks up the
  losing streaks and reports a drawdown gentler than the strategy will
  actually produce. Sampling blocks keeps the short-run structure.

What none of them can do is tell you whether the strategy has an edge. They
resample the trades it took; if those came from a rule fitted to this data,
every draw is fitted to it too. A Monte Carlo answers "given these trades,
what range of paths?" -- never "will this work?".

Two ways to compound, and they answer different questions as well. In
``additive`` mode each trade contributes its cash P&L, which is what a fixed
position size produces and makes the arithmetic order-independent. In
``compounded`` mode each trade contributes its return as a fraction of the
equity it was opened against, so a loss early costs more than the same loss
late -- which is what a percent-of-equity size actually does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from ..core.errors import InsufficientDataError, ParameterError
from ..logging_setup import get_logger

log = get_logger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: Methods this module knows how to resample by.
METHODS: tuple[str, ...] = ("shuffle", "bootstrap", "block")

#: Draws are processed in chunks of this many paths so that a long trade list
#: and a large draw count cannot allocate a matrix measured in gigabytes.
_CHUNK = 256

#: Ceiling on the elements in one chunk's matrix. 4M float64 is 32MB per
#: intermediate, and the path arithmetic holds a handful of them at once, so a
#: 50,000-trade run drops to five paths per chunk instead of allocating half a
#: gigabyte per step.
_MAX_CHUNK_ELEMENTS = 4_000_000

#: Below this many trades every percentile in the report is an artefact of the
#: handful of numbers that went into it.  Not refused -- labelled.
RELIABLE_TRADES = 30


@dataclass
class PathStats:
    """What one equity path did."""

    final_equity: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    longest_drawdown_trades: int

    def to_dict(self) -> dict[str, Any]:
        return {"final_equity": self.final_equity,
                "total_return_pct": self.total_return_pct,
                "max_drawdown": self.max_drawdown,
                "max_drawdown_pct": self.max_drawdown_pct,
                "longest_drawdown_trades": self.longest_drawdown_trades}


@dataclass
class MonteCarloResult:
    """The distribution, and where the backtest sits inside it."""

    method: str
    compounded: bool
    draws: int
    trades: int
    starting_capital: float
    block_size: int
    seed: int
    observed: PathStats
    final_equity: np.ndarray = field(default_factory=lambda: np.empty(0))
    max_drawdown: np.ndarray = field(default_factory=lambda: np.empty(0))
    max_drawdown_pct: np.ndarray = field(default_factory=lambda: np.empty(0))
    longest_drawdown: np.ndarray = field(default_factory=lambda: np.empty(0))
    ruin_level: float = 0.0
    ruin_probability: float = 0.0
    losing_probability: float = 0.0
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    # -- reading the distribution -----------------------------------------

    @staticmethod
    def percentiles(values: np.ndarray,
                    qs: Sequence[float] = (5, 25, 50, 75, 95)) -> dict[float, float]:
        if values.size == 0:
            return {q: float("nan") for q in qs}
        found = np.percentile(values, list(qs))
        return {q: float(v) for q, v in zip(qs, np.atleast_1d(found))}

    def rank_of_observed(self) -> float:
        """Fraction of draws that finished no better than the backtest did.

        Near 1 means the backtest was a lucky path even holding the strategy
        fixed; near 0 means it was an unlucky one.  Under ``shuffle`` every
        draw ends at the same equity, so this is not meaningful and the
        drawdown rank is the one to read.
        """
        if self.final_equity.size == 0:
            return float("nan")
        return float(np.mean(self.final_equity <= self.observed.final_equity))

    def drawdown_rank_of_observed(self) -> float:
        """Fraction of draws whose worst drawdown was no deeper than the backtest's."""
        if self.max_drawdown.size == 0:
            return float("nan")
        return float(np.mean(self.max_drawdown <= self.observed.max_drawdown))

    def drawdown_at(self, q: float) -> float:
        if self.max_drawdown.size == 0:
            return float("nan")
        return float(np.percentile(self.max_drawdown, q))

    def verdict(self) -> str:
        """What the distribution says, in a sentence."""
        if self.final_equity.size == 0:
            return "no draws were produced"
        worse = self.drawdown_at(95)
        observed = self.observed.max_drawdown
        deeper = worse / observed if observed > 0 else float("inf")
        if self.method == "shuffle":
            if math.isfinite(deeper) and deeper >= 1.5:
                return (f"the same trades in a different order produce a "
                        f"drawdown {deeper:.1f}x deeper than the backtest's in "
                        f"1 draw in 20, so the drawdown you saw was a mild "
                        f"ordering of these trades")
            return ("the drawdown is not very sensitive to the order the "
                    "trades arrived in")
        if self.observed.final_equity < self.starting_capital:
            return (f"the backtest itself lost money, and "
                    f"{self.losing_probability * 100:.0f}% of the resampled "
                    f"runs did too — there is no result here for the "
                    f"resampling to put a range around")
        if self.losing_probability >= 0.5:
            return (f"{self.losing_probability * 100:.0f}% of resampled runs "
                    f"lost money, so the backtest's profit is well within the "
                    f"range this trade distribution produces by chance")
        if self.ruin_probability > 0.05:
            return (f"{self.ruin_probability * 100:.0f}% of resampled runs fell "
                    f"below {self.ruin_level:,.0f} at some point — the position "
                    f"size is too large for this distribution of trades")
        if self.losing_probability >= 0.1:
            return (f"most resampled runs made money, but "
                    f"{self.losing_probability * 100:.0f}% did not")
        return (f"{(1 - self.losing_probability) * 100:.0f}% of resampled runs "
                f"made money, and the worst 5% still finished above "
                f"{self.percentiles(self.final_equity, (5,))[5]:,.0f}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method, "compounded": self.compounded,
            "draws": self.draws, "trades": self.trades,
            "starting_capital": self.starting_capital,
            "block_size": self.block_size, "seed": self.seed,
            "observed": self.observed.to_dict(),
            "final_equity": {str(q): v for q, v in
                             self.percentiles(self.final_equity).items()},
            "max_drawdown": {str(q): v for q, v in
                             self.percentiles(self.max_drawdown).items()},
            "max_drawdown_pct": {str(q): v for q, v in
                                 self.percentiles(self.max_drawdown_pct).items()},
            "longest_drawdown_trades": {
                str(q): v for q, v in
                self.percentiles(self.longest_drawdown.astype(float)).items()},
            "ruin_level": self.ruin_level,
            "ruin_probability": self.ruin_probability,
            "losing_probability": self.losing_probability,
            "rank_of_observed": self.rank_of_observed(),
            "drawdown_rank_of_observed": self.drawdown_rank_of_observed(),
            "verdict": self.verdict(), "notes": list(self.notes),
            "elapsed_seconds": round(self.elapsed, 2),
        }


# --------------------------------------------------------------------------
# the paths
# --------------------------------------------------------------------------

def _longest_true_run(mask: np.ndarray) -> np.ndarray:
    """Longest run of ``True`` in each row, without a Python loop.

    ``reset`` holds the position of each ``False`` and -1 elsewhere; a running
    maximum turns that into "where did the current run start", and the distance
    from there is the run length so far.
    """
    if mask.size == 0:
        return np.zeros(mask.shape[0], dtype="int64")
    positions = np.arange(mask.shape[1], dtype="int64")
    reset = np.where(~mask, positions, -1)
    run_start = np.maximum.accumulate(reset, axis=1)
    lengths = np.where(mask, positions - run_start, 0)
    return lengths.max(axis=1)


def _path_stats(equity: np.ndarray, starting: float) -> tuple[np.ndarray, ...]:
    """Final equity, drawdown in cash and percent, and time under water.

    ``equity`` is ``(draws, trades)`` and excludes the starting capital, which
    is prepended here so that a first trade in loss counts as a drawdown from
    the account's opening balance rather than from its own result.
    """
    opening = np.full((equity.shape[0], 1), float(starting))
    full = np.concatenate([opening, equity], axis=1)
    peak = np.maximum.accumulate(full, axis=1)
    fall = peak - full
    with np.errstate(divide="ignore", invalid="ignore"):
        fall_pct = np.where(peak > 0, fall / peak, 0.0) * 100.0
    under = fall[:, 1:] > 0
    return (full[:, -1], fall.max(axis=1), np.nanmax(fall_pct, axis=1),
            _longest_true_run(under), full.min(axis=1))


def _equity(values: np.ndarray, starting: float, compounded: bool) -> np.ndarray:
    """Turn resampled per-trade results into equity paths."""
    if compounded:
        # Guard the arithmetic, not the outcome: a trade that lost more than the
        # whole account is a busted account, not a negative multiplier.
        growth = np.maximum(1.0 + values, 0.0)
        return float(starting) * np.cumprod(growth, axis=1)
    return float(starting) + np.cumsum(values, axis=1)


def _indices(method: str, rng: np.random.Generator, rows: int, n: int,
             block: int) -> np.ndarray:
    """One ``(rows, n)`` index matrix under the chosen resampler."""
    if method == "shuffle":
        return rng.permuted(np.tile(np.arange(n), (rows, 1)), axis=1)
    if method == "bootstrap":
        return rng.integers(0, n, size=(rows, n))
    if method == "block":
        block = max(1, min(int(block), n))
        count = int(math.ceil(n / block))
        starts = rng.integers(0, n - block + 1, size=(rows, count))
        offsets = np.arange(block)
        drawn = (starts[:, :, None] + offsets[None, None, :])
        return drawn.reshape(rows, count * block)[:, :n]
    raise ParameterError(
        f"'{method}' is not a resampling method. Use one of: "
        f"{', '.join(METHODS)}.")


def suggested_block(n: int) -> int:
    """A default block length for the block bootstrap.

    ``n ** (1/3)`` is the standard rule of thumb for a stationary bootstrap and
    is used here for the same reason: long enough to keep a losing streak
    together, short enough that the draws are not all the same path.
    """
    return max(2, int(round(n ** (1.0 / 3.0))))


def resample_trades(net_pnl: Sequence[float], starting_capital: float, *,
                    method: str = "bootstrap", draws: int = 5000,
                    compounded: bool = False,
                    returns: Sequence[float] | None = None,
                    block_size: int = 0, ruin_level: float | None = None,
                    seed: int = 12345,
                    progress: ProgressFn | None = None,
                    cancel: Any = None) -> MonteCarloResult:
    """Resample a trade sequence and describe the distribution of paths.

    ``net_pnl`` is the cash result of each trade in the order it happened.
    ``returns`` is each trade's result as a fraction of the equity it opened
    against, and is required for ``compounded``: resampling cash and then
    compounding it would apply a $500 loss taken on a $100,000 account as
    though it were the same fraction of a $40,000 one.
    """
    import time

    started = time.time()
    values = np.asarray(net_pnl, dtype="float64")
    if values.ndim != 1:
        raise ParameterError("The trade results must be a flat list.")
    n = int(values.size)
    if n < 2:
        raise InsufficientDataError(
            f"A Monte Carlo needs at least two trades to resample and this run "
            f"produced {n}.")
    draws = max(1, int(draws))
    starting = float(starting_capital)
    if starting <= 0:
        raise ParameterError(
            "The starting capital must be positive for a Monte Carlo: every "
            "drawdown here is measured against it.")

    if compounded:
        if returns is None:
            raise ParameterError(
                "Compounded mode needs each trade's return as a fraction of "
                "the equity it was opened against.")
        source = np.asarray(returns, dtype="float64")
        if source.size != n:
            raise ParameterError(
                "The returns and the cash results describe different numbers "
                "of trades.")
    else:
        source = values

    block = int(block_size) if block_size else suggested_block(n)
    level = (float(ruin_level) if ruin_level is not None
             else starting * 0.5)
    rng = np.random.default_rng(int(seed))

    finals, falls, fall_pcts, longest, mins = [], [], [], [], []
    chunk = max(1, min(_CHUNK, _MAX_CHUNK_ELEMENTS // max(1, n)))
    done = 0
    while done < draws:
        if cancel is not None and getattr(cancel, "cancelled", False):
            from ..core.errors import CancelledError

            raise CancelledError("The Monte Carlo was cancelled.")
        rows = min(chunk, draws - done)
        index = _indices(method, rng, rows, n, block)
        equity = _equity(source[index], starting, compounded)
        final, fall, fall_pct, run, low = _path_stats(equity, starting)
        finals.append(final)
        falls.append(fall)
        fall_pcts.append(fall_pct)
        longest.append(run)
        mins.append(low)
        done += rows
        if progress is not None:
            progress(done, draws, f"{done:,} of {draws:,} resampled runs")

    final_equity = np.concatenate(finals)
    max_dd = np.concatenate(falls)
    max_dd_pct = np.concatenate(fall_pcts)
    longest_dd = np.concatenate(longest)
    lowest = np.concatenate(mins)

    observed_equity = _equity(source.reshape(1, n), starting, compounded)
    o_final, o_fall, o_fall_pct, o_run, _ = _path_stats(observed_equity, starting)
    observed = PathStats(
        final_equity=float(o_final[0]),
        total_return_pct=float((o_final[0] / starting - 1.0) * 100.0),
        max_drawdown=float(o_fall[0]), max_drawdown_pct=float(o_fall_pct[0]),
        longest_drawdown_trades=int(o_run[0]))

    result = MonteCarloResult(
        method=method, compounded=compounded, draws=draws, trades=n,
        starting_capital=starting, block_size=block if method == "block" else 0,
        seed=int(seed), observed=observed, final_equity=final_equity,
        max_drawdown=max_dd, max_drawdown_pct=max_dd_pct,
        longest_drawdown=longest_dd, ruin_level=level,
        ruin_probability=float(np.mean(lowest <= level)),
        losing_probability=float(np.mean(final_equity < starting)))
    result.elapsed = time.time() - started
    result.notes = _notes(result)
    return result


def resample_result(result: Any, *, method: str = "bootstrap",
                    draws: int = 5000, compounded: bool = False,
                    block_size: int = 0, ruin_level: float | None = None,
                    seed: int = 12345,
                    progress: ProgressFn | None = None,
                    cancel: Any = None) -> MonteCarloResult:
    """:func:`resample_trades` over a finished :class:`BacktestResult`."""
    trades = list(getattr(result, "trades", ()) or ())
    if not trades:
        raise InsufficientDataError(
            "This backtest produced no trades, so there is nothing to "
            "resample.")
    starting = float(getattr(getattr(result, "config", None),
                             "starting_capital", 0.0) or 0.0)
    if starting <= 0:
        starting = float(trades[0].equity_at_entry or 0.0)
    return resample_trades(
        [t.net_pnl for t in trades], starting, method=method, draws=draws,
        compounded=compounded,
        returns=[float(t.return_pct or 0.0) / 100.0 for t in trades],
        block_size=block_size, ruin_level=ruin_level, seed=seed,
        progress=progress, cancel=cancel)


# --------------------------------------------------------------------------
# saying what it means
# --------------------------------------------------------------------------

def _notes(result: MonteCarloResult) -> list[str]:
    method = {
        "shuffle": "The same trades in a different order, so every draw "
                   "finishes at the same equity and only the path differs. "
                   "Read the drawdown, not the final balance.",
        "bootstrap": "Trades drawn with replacement, so the sample of trades "
                     "changes from draw to draw. This treats the trades you "
                     "have as a fair sample of the ones the strategy would "
                     "take, which is an assumption and not a finding.",
        "block": f"Trades drawn in contiguous runs of {result.block_size}, so "
                 f"the short-run structure survives. Where trades cluster by "
                 f"regime a plain bootstrap breaks up the losing streaks and "
                 f"reports a gentler drawdown than the strategy will actually "
                 f"produce; where they do not, the two agree.",
    }[result.method]
    notes = [
        f"{result.draws:,} resampled runs over the {result.trades:,} trades "
        f"this backtest produced. {method}",
        "This resamples the trades the strategy took; it cannot tell you "
        "whether the strategy has an edge. If those trades came from a rule "
        "fitted to this data, every draw is fitted to it too. The question it "
        "answers is 'given these trades, what range of paths?' — never 'will "
        "this work?'.",
    ]
    if result.compounded:
        notes.append(
            "Compounded: each trade contributes its return as a fraction of "
            "the equity it was opened against, so an early loss costs more "
            "than the same loss late.")
    else:
        notes.append(
            "Additive: each trade contributes its cash result, which is what a "
            "fixed position size produces.")
    worst = result.drawdown_at(95)
    if math.isfinite(worst) and result.observed.max_drawdown > 0:
        notes.append(
            f"The backtest's worst drawdown was "
            f"{result.observed.max_drawdown:,.0f}. One resampled run in twenty "
            f"was worse than {worst:,.0f} — that is the number to size the "
            f"account against, not the one the backtest happened to produce.")
    if result.trades < RELIABLE_TRADES:
        notes.append(
            f"{result.trades} trades is too few for any of these percentiles "
            f"to mean much: {result.draws:,} draws over {result.trades} numbers "
            f"is still {result.trades} numbers.")
    if result.ruin_probability > 0:
        notes.append(
            f"Equity is measured at trade closes, so the "
            f"{result.ruin_probability * 100:.1f}% that fell below "
            f"{result.ruin_level:,.0f} is a floor on how often it happened: an "
            f"open position that went far against you and came back does not "
            f"appear here at all.")
    notes.append(
        "Every draw assumes the future looks like the trades in this backtest. "
        "It cannot contain a regime this sample did not.")
    return notes


def format_monte_carlo(result: MonteCarloResult, currency: str = "USD",
                       width: int = 78) -> str:
    """The whole distribution as plain text."""
    import textwrap

    rule = "-" * width
    title = {"shuffle": "order shuffle", "bootstrap": "bootstrap",
             "block": "block bootstrap"}[result.method]
    out = [f"Monte Carlo — {title}"
           f"{', compounded' if result.compounded else ''}", rule]
    out.append(f"{result.draws:,} draws over {result.trades:,} trades, "
               f"starting capital {result.starting_capital:,.0f} {currency}.  "
               f"{result.elapsed:.1f}s.")
    out.append("")

    quantiles = (5, 25, 50, 75, 95)
    finals = result.percentiles(result.final_equity, quantiles)
    falls = result.percentiles(result.max_drawdown, quantiles)
    fall_pcts = result.percentiles(result.max_drawdown_pct, quantiles)
    runs = result.percentiles(result.longest_drawdown.astype(float), quantiles)

    out.append(f"   {'':<20}" + "".join(f"{f'{q}th':>11}" for q in quantiles))
    out.append(f"   {'final equity':<20}"
               + "".join(f"{finals[q]:>11,.0f}" for q in quantiles))
    out.append(f"   {'worst drawdown':<20}"
               + "".join(f"{falls[q]:>11,.0f}" for q in quantiles))
    out.append(f"   {'worst drawdown %':<20}"
               + "".join(f"{fall_pcts[q]:>11,.1f}" for q in quantiles))
    out.append(f"   {'trades under water':<20}"
               + "".join(f"{runs[q]:>11,.0f}" for q in quantiles))
    out.append("")
    out.append(f"   the backtest finished at "
               f"{result.observed.final_equity:,.0f} {currency} "
               f"({result.observed.total_return_pct:+.1f}%), worst drawdown "
               f"{result.observed.max_drawdown:,.0f} "
               f"({result.observed.max_drawdown_pct:.1f}%),")
    out.append(f"   {result.observed.longest_drawdown_trades} trades under "
               f"water")
    if result.method != "shuffle":
        out.append(f"   it finished better than "
                   f"{result.rank_of_observed() * 100:.0f}% of the draws")
    out.append(f"   its drawdown was milder than "
               f"{(1 - result.drawdown_rank_of_observed()) * 100:.0f}% of them")
    out.append(f"   {result.losing_probability * 100:.1f}% of draws lost money; "
               f"{result.ruin_probability * 100:.1f}% fell below "
               f"{result.ruin_level:,.0f} at some point")
    out.append("")
    for line in textwrap.wrap(f"verdict: {result.verdict()}", max(40, width - 3)):
        out.append("   " + line)
    out.append("")
    out.append(rule)
    for note in result.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
