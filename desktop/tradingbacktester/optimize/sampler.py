"""Choosing which combinations to run, when running all of them is too many.

A grid sweep evaluates every rung of every parameter.  For two parameters that
is a table; for five it is a number with a lot of zeros, most of them spent on
corners of the space nothing sensible lives in.  The samplers here spend a
fixed budget of *trials* instead, and one of them spends it where the results
so far say the good region is.

Two samplers, one contract
--------------------------

:class:`RandomSampler` draws unevaluated grid points uniformly.  It is the
baseline every smarter method has to beat, and it is what a Bayesian sampler
falls back to when it has nothing to learn from yet.

:class:`TPESampler` is the Tree-structured Parzen Estimator -- the algorithm
Optuna runs by default.  After a few random start-up trials it splits what it
has seen into the better fraction and the rest, fits a kernel density to each,
and for every parameter picks the rung where ``good(x) / rest(x)`` is largest.
Written here in NumPy rather than imported: Optuna itself brings SQLAlchemy,
Alembic, colorlog and YAML with it, none of which a backtester needs and all
of which a frozen Windows build has to ship and keep working.  The maths is a
page.

Both work on the grid's own rungs.  A sampled point is always a point the grid
sweep could have produced, so the ranking, the neighbourhood column, the heat
map and the holdout all read a sampled run exactly as they read a grid.  It
also means a sampler can never invent a value the parameter's own validation
would have refused.

What this does not change
-------------------------

A sampler finds the grid's best combination in fewer evaluations.  It does not
make that combination any more likely to be real.  The multiplicity is now the
number of trials rather than the size of the grid, and every note that prices
a result for how hard it was searched for should say *trials*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ..core.errors import ParameterError
from .grid import ParameterRange

__all__ = ["METHODS", "Sampler", "RandomSampler", "TPESampler",
           "make_sampler", "describe_method"]

#: The search methods a caller may name.  ``grid`` is the cartesian product
#: the runner has always done and is handled there; the two here sample.
METHODS: tuple[str, ...] = ("grid", "tpe", "random")

_LABELS = {
    "grid": "Grid (every combination)",
    "tpe": "Bayesian (TPE)",
    "random": "Random search",
}


def describe_method(method: str) -> str:
    return _LABELS.get(str(method).lower(), str(method))


# ---------------------------------------------------------------------------
# The search space
# ---------------------------------------------------------------------------


@dataclass
class _Axis:
    """One swept parameter as an ordered list of rungs."""

    name: str
    rungs: list[Any]

    @property
    def size(self) -> int:
        return len(self.rungs)


def _axes(ranges: Sequence[ParameterRange]) -> list[_Axis]:
    if not ranges:
        raise ParameterError("A sampled search needs at least one parameter range.")
    out: list[_Axis] = []
    for r in ranges:
        values = list(dict.fromkeys(r.values()))     # de-duplicate, keep order
        if not values:                                # pragma: no cover
            raise ParameterError(f"'{r.name}' has no values to sample.")
        out.append(_Axis(r.name, values))
    return out


def grid_size(ranges: Sequence[ParameterRange]) -> int:
    """Distinct points in the space these ranges span."""
    total = 1
    for axis in _axes(ranges):
        total *= axis.size
    return total


# ---------------------------------------------------------------------------
# Base sampler
# ---------------------------------------------------------------------------


@dataclass
class Sampler:
    """Ask for points, tell it what they scored.

    ``ask(k)`` returns up to ``k`` distinct parameter dictionaries that have not
    been asked for before; fewer when the space is nearly exhausted, and an
    empty list when it is.  ``tell(params, value)`` records a result; ``NaN``
    means the combination failed and is treated as the worst possible score.
    """

    ranges: Sequence[ParameterRange]
    maximise: bool = True
    seed: int = 0
    axes: list[_Axis] = field(init=False)
    rng: np.random.Generator = field(init=False)
    #: Index tuples handed out so far, whether or not they have been told.
    asked: set[tuple[int, ...]] = field(init=False, default_factory=set)
    #: ``(index tuple, score)`` for every told point; score is +inf-safe.
    observed: list[tuple[tuple[int, ...], float]] = field(init=False,
                                                          default_factory=list)

    def __post_init__(self) -> None:
        self.axes = _axes(self.ranges)
        self.rng = np.random.default_rng(int(self.seed))
        self.total = 1
        for axis in self.axes:
            self.total *= axis.size
        self._position = {axis.name: {v: i for i, v in enumerate(axis.rungs)}
                          for axis in self.axes}

    # -- public --------------------------------------------------------------

    @property
    def method(self) -> str:                      # pragma: no cover - overridden
        return "sampler"

    @property
    def exhausted(self) -> bool:
        return len(self.asked) >= self.total

    def remaining(self) -> int:
        return max(0, self.total - len(self.asked))

    def ask(self, k: int = 1) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _ in range(max(0, int(k))):
            if self.exhausted:
                break
            point = self._propose()
            if point is None:                     # pragma: no cover - defensive
                break
            self.asked.add(point)
            out.append(self._params_of(point))
        return out

    def tell(self, params: dict[str, Any], value: float) -> None:
        point = self._point_of(params)
        score = float(value) if value is not None else float("nan")
        if not math.isfinite(score):
            # A failed or degenerate combination is the worst thing that can
            # happen; ranking it last is what "avoid this region" means.
            score = -math.inf if self.maximise else math.inf
        self.asked.add(point)
        self.observed.append((point, score))

    # -- helpers -------------------------------------------------------------

    def _params_of(self, point: tuple[int, ...]) -> dict[str, Any]:
        return {axis.name: axis.rungs[i] for axis, i in zip(self.axes, point)}

    def _point_of(self, params: dict[str, Any]) -> tuple[int, ...]:
        out: list[int] = []
        for axis in self.axes:
            value = params.get(axis.name)
            index = self._position[axis.name].get(value)
            if index is None:
                # A value off the rungs (a float that lost precision on the way
                # round) is snapped to the nearest rung rather than refused: the
                # runner only ever evaluates what ask() produced.
                index = self._nearest(axis, value)
            out.append(int(index))
        return tuple(out)

    @staticmethod
    def _nearest(axis: _Axis, value: Any) -> int:
        try:
            target = float(value)
        except (TypeError, ValueError):
            return 0
        best, best_d = 0, math.inf
        for i, rung in enumerate(axis.rungs):
            d = abs(float(rung) - target)
            if d < best_d:
                best, best_d = i, d
        return best

    def _random_point(self) -> tuple[int, ...] | None:
        """An unasked point, uniformly.  ``None`` when the space is exhausted."""
        if self.exhausted:
            return None
        # Rejection sampling is fine while the space is mostly empty; once it is
        # mostly full, enumerate what is left rather than spin.
        if len(self.asked) * 2 < self.total or self.total > 200_000:
            for _ in range(64):
                point = tuple(int(self.rng.integers(axis.size)) for axis in self.axes)
                if point not in self.asked:
                    return point
        return self._enumerate_unasked()

    def _enumerate_unasked(self) -> tuple[int, ...] | None:
        sizes = [axis.size for axis in self.axes]
        free = [p for p in np.ndindex(*sizes) if tuple(int(i) for i in p) not in self.asked]
        if not free:
            return None
        pick = free[int(self.rng.integers(len(free)))]
        return tuple(int(i) for i in pick)

    def _propose(self) -> tuple[int, ...] | None:  # pragma: no cover - overridden
        return self._random_point()

    def _scores(self) -> np.ndarray:
        """Observed scores oriented so that larger is always better."""
        s = np.array([v for _p, v in self.observed], dtype="float64")
        return s if self.maximise else -s


# ---------------------------------------------------------------------------
# Random search
# ---------------------------------------------------------------------------


class RandomSampler(Sampler):
    """Unevaluated grid points, uniformly at random, never the same one twice."""

    @property
    def method(self) -> str:
        return "random"

    def _propose(self) -> tuple[int, ...] | None:
        return self._random_point()


# ---------------------------------------------------------------------------
# Tree-structured Parzen Estimator
# ---------------------------------------------------------------------------


class TPESampler(Sampler):
    """Independent-parameter TPE over the grid's rungs.

    Parameters
    ----------
    n_startup:
        Random trials before the model is trusted.  Optuna's default is 10;
        here it is also capped at a quarter of the budget so a 12-trial run is
        not 10 random draws and two informed ones.
    n_candidates:
        Points drawn from the *good* density per parameter, of which the one
        with the best ``good/rest`` ratio is kept.  Optuna's ``n_ei_candidates``.
    gamma:
        Fraction of observations counted as "good"; Optuna's default is
        ``min(ceil(0.1 n), 25) / n`` and that is what is used.

    Each parameter is modelled on its own (Optuna's ``multivariate=False``),
    which is the right default for a handful of strategy parameters and is what
    makes the sampler cheap: every step is a few hundred Gaussian evaluations.
    """

    def __init__(self, ranges: Sequence[ParameterRange], maximise: bool = True,
                 seed: int = 0, *, n_startup: int = 10, n_candidates: int = 24,
                 budget: int | None = None) -> None:
        super().__init__(ranges, maximise, seed)
        startup = int(n_startup)
        if budget is not None:
            startup = min(startup, max(2, int(budget) // 4))
        self.n_startup = max(2, startup)
        self.n_candidates = max(1, int(n_candidates))

    @property
    def method(self) -> str:
        return "tpe"

    # -- the estimator ---------------------------------------------------

    def _propose(self) -> tuple[int, ...] | None:
        told = len(self.observed)
        if told < self.n_startup:
            return self._random_point()
        # Points asked but not yet told (in flight on other workers) are not in
        # `observed`; the model is built from what has actually been scored.
        scores = self._scores()
        points = np.array([p for p, _v in self.observed], dtype="int64")
        n = scores.size
        n_good = max(1, min(int(math.ceil(0.1 * n)), 25))
        order = np.argsort(-scores, kind="stable")
        good = points[order[:n_good]]
        rest = points[order[n_good:]] if n > n_good else points[order[:0]]

        # Propose per axis, then make the joint point distinct.  Up to a few
        # tries at the model's suggestion; if the region it likes is already
        # fully evaluated, widen to a random unasked point rather than stall.
        for _ in range(8):
            point = tuple(self._propose_axis(axis, good[:, k], rest[:, k])
                          for k, axis in enumerate(self.axes))
            if point not in self.asked:
                return point
        return self._random_point()

    def _propose_axis(self, axis: _Axis, good: np.ndarray,
                      rest: np.ndarray) -> int:
        m = axis.size
        if m == 1:
            return 0
        l_pdf = self._parzen(good, m)           # density of the good points
        g_pdf = self._parzen(rest, m)           # density of the rest
        # Draw candidates from l, score by l/g, keep the best.
        cands = self._draw_from_mixture(good, m, self.n_candidates)
        ratio = l_pdf[cands] / np.maximum(g_pdf[cands], 1e-300)
        return int(cands[int(np.argmax(ratio))])

    def _parzen(self, centres: np.ndarray, m: int) -> np.ndarray:
        """Mixture-of-Gaussians density over the rung indices ``0..m-1``.

        A prior component sits at the centre of the axis with a bandwidth of
        the whole range, so an axis with no observations (or one) still has a
        finite, informative density, and so ``rest`` can never be zero where
        ``good`` is not -- which would make the ratio infinite and the pick
        arbitrary.  Bandwidths follow Optuna's heuristic: the larger gap to a
        neighbouring centre, floored at a fraction of the range.
        """
        idx = np.arange(m, dtype="float64")
        span = float(max(m - 1, 1))
        weights = [1.0]
        mus = [0.5 * (m - 1)]
        sigmas = [span]
        if centres.size:
            c = np.sort(centres.astype("float64"))
            # Neighbour gaps, with the edges bounded by the axis ends.
            lo = np.concatenate(([0.0], c[:-1]))
            hi = np.concatenate((c[1:], [span]))
            gaps = np.maximum(c - lo, hi - c)
            floor = max(span / max(1.0, min(100.0, float(m))), 0.5)
            sig = np.clip(gaps, floor, span)
            weights.extend([1.0] * c.size)
            mus.extend(c.tolist())
            sigmas.extend(sig.tolist())
        w = np.asarray(weights, dtype="float64")
        w /= w.sum()
        pdf = np.zeros(m, dtype="float64")
        for wi, mu, sd in zip(w, mus, sigmas):
            z = (idx - mu) / sd
            pdf += wi * np.exp(-0.5 * z * z) / (sd * math.sqrt(2.0 * math.pi))
        # Discrete domain: normalise over the rungs, not the real line.
        total = pdf.sum()
        return pdf / total if total > 0 else np.full(m, 1.0 / m)

    def _draw_from_mixture(self, centres: np.ndarray, m: int, k: int) -> np.ndarray:
        """``k`` rung indices drawn from the good-point mixture (with the prior)."""
        if centres.size == 0:
            return self.rng.integers(0, m, size=k)
        pdf = self._parzen(centres, m)
        return self.rng.choice(m, size=k, replace=True, p=pdf)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_sampler(method: str, ranges: Sequence[ParameterRange], *,
                 maximise: bool = True, seed: int = 0,
                 budget: int | None = None) -> Sampler:
    """The sampler for ``method``, or a :class:`ParameterError` naming the choices."""
    key = str(method or "").strip().lower()
    if key == "random":
        return RandomSampler(ranges, maximise, seed)
    if key in ("tpe", "bayesian", "bayes"):
        return TPESampler(ranges, maximise, seed, budget=budget)
    raise ParameterError(
        f"'{method}' is not a search method. Choose grid, tpe or random.")
