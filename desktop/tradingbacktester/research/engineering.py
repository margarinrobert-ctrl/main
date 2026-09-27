"""Building features out of other features, and counting how few there really are.

Two halves of the same argument, and the second one is the important half.

**Construction.** Two features can carry information neither has alone -- a
momentum reading is a different thing in a quiet market than in a violent one --
and the usual way to express that is a product or a ratio. This module builds
those from a small set of parents and hands them to the same evaluation
everything else here goes through.

**Dimensionality.** Every constructed feature is a new test, and none of them is
a new *fact*. Fifty features that are mostly restatements of each other look
like fifty chances to find something and behave like a handful; combine them
pairwise and you have a thousand tests over the same handful. So this module
also reports what the effective dimension actually is -- how many principal
components carry the variance -- and states the multiplicity beside every
result. The count of features is not evidence of anything. The count of
independent directions in them is a fact about the data.

Two rules, both learned the hard way and both enforced here rather than
documented and hoped for:

*Parents are chosen on the research block only.* Ranking features over both
blocks and then building interactions from the winners puts the locked block
inside the construction step, and a family selected that way once produced a
result that failed on research and "passed" on the holdout -- which is the
wrong shape and was pure leakage.

*A constructed feature is causal only if its parents are.* Every operator here
is pointwise: value at bar *i* from parent values at bar *i*. Nothing shifts,
nothing smooths, nothing looks across bars, so a causal parent cannot become a
peeking child.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from ..data.models import BarSeries
from .features import Feature, rolling_std, zscore

log = logging.getLogger(__name__)

#: How many parents an interaction sweep may draw on.  Pairs grow as the
#: square, so ten parents is 45 pairs and twenty is 190; the multiplicity is
#: the real cost and it is reported, but a ceiling stops a careless call
#: turning one study into ten thousand tests.
MAX_PARENTS = 12

#: Above this absolute correlation with either parent, a child is a restatement
#: of it rather than a new reading, and is dropped before it can be tested.
#: Testing it would spend multiplicity on a question already asked.
REDUNDANT_ABOVE = 0.95

#: Share of variance the reported effective dimension must cover.
VARIANCE_TARGET = 0.95

#: Trailing window for putting two parents on one scale.  Long enough that the
#: scale is stable, short enough to survive a change of regime -- and, above
#: all, TRAILING: a whole-series z-score would make every constructed feature
#: depend on bars that had not happened when it fired.
STANDARDISE_WINDOW = 250

#: A denominator smaller than this share of its own trailing spread is treated
#: as zero.  Not a rounding guard: a ratio through a denominator that small is
#: an arbitrarily large number that says nothing about the market.
RATIO_FLOOR = 0.05


# ---------------------------------------------------------------------------
# the operators
# ---------------------------------------------------------------------------


def _finite(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype="float64")


def _product(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``a * b`` -- "this reading, but only when that one agrees"."""
    return _finite(a) * _finite(b)


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``a / b``, undefined where the denominator is near zero.

    NaN rather than a clipped huge number: a ratio through zero is not a large
    value, it is an absent one, and clipping it invents a reading at exactly
    the bars where the feature has least to say.

    "Near zero" is measured against the denominator's own TRAILING spread, for
    two reasons. It is scale-free, so the same rule works on a price and on a
    percentage. And it is causal: a floor taken from the whole series would
    make whether bar *i* has a value at all depend on bars after it -- a
    quieter kind of look-ahead than a wrong number, and a harder one to notice.
    """
    top, bottom = _finite(a), _finite(b)
    scale = rolling_std(np.abs(bottom), STANDARDISE_WINDOW)
    floor = np.where(np.isfinite(scale) & (scale > 0), scale * RATIO_FLOOR,
                     np.nan)
    out = np.full(top.shape, np.nan)
    usable = (np.isfinite(top) & np.isfinite(bottom) & np.isfinite(floor)
              & (np.abs(bottom) > floor))
    out[usable] = top[usable] / bottom[usable]
    return out


def _difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``a - b`` on trailing-standardised parents, so units cannot dominate.

    Subtracting a percentage from a price would report the price, so both
    sides have to be put on one scale first -- and the obvious way to do that
    is the wrong one. A whole-series z-score divides by a standard deviation
    computed from bars that had not happened yet, so bar *i*'s value moves when
    the file is extended. The look-ahead check caught exactly that here.

    :data:`STANDARDISE_WINDOW` bars of trailing history instead: causal, and
    the same thing a trader could compute at the time.
    """
    return _standardise(a) - _standardise(b)


def _spread_sign(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """``+1`` where the standardised parents agree in sign, ``-1`` where not.

    A deliberately coarse operator: it throws away every magnitude and keeps
    only the agreement, which is the one thing a product cannot express without
    also multiplying two noisy sizes together.
    """
    left, right = _standardise(a), _standardise(b)
    out = np.full(left.shape, np.nan)
    usable = np.isfinite(left) & np.isfinite(right)
    out[usable] = np.where(np.sign(left[usable]) == np.sign(right[usable]),
                           1.0, -1.0)
    return out


def _standardise(values: np.ndarray) -> np.ndarray:
    """Trailing z-score over :data:`STANDARDISE_WINDOW` bars.

    Causal by construction: bar *i* is measured against bars before it and
    nothing else. The whole-series version is one line shorter and is
    look-ahead, which is why this one exists.
    """
    return zscore(_finite(values), STANDARDISE_WINDOW)


@dataclass(frozen=True)
class Operator:
    """One way of combining two features."""

    key: str
    label: str
    description: str
    apply: Callable[[np.ndarray, np.ndarray], np.ndarray]
    symmetric: bool = True
    """``a op b`` is the same question as ``b op a``, so only one is built."""


OPERATORS: tuple[Operator, ...] = (
    Operator("product", "×",
             "Both readings at once: large only where both parents are.",
             _product),
    Operator("ratio", "÷",
             "One reading measured in units of the other -- momentum per unit "
             "of volatility, say.", _ratio, symmetric=False),
    Operator("difference", "−",
             "How far apart the two trailing-standardised readings are.",
             # a - b and b - a are the same question: one is the negation of
             # the other, so their information content is identical and their
             # ICs are exact mirrors. Building both doubles the multiplicity
             # for nothing and fills the top of the table with pairs.
             _difference, symmetric=True),
    Operator("agreement", "±",
             "+1 where the two parents point the same way, -1 where they "
             "disagree. Keeps the agreement and throws away both magnitudes.",
             _spread_sign),
)

OPERATORS_BY_KEY: dict[str, Operator] = {o.key: o for o in OPERATORS}


# ---------------------------------------------------------------------------
# constructed features
# ---------------------------------------------------------------------------


@dataclass
class Interaction:
    """One constructed feature: two parents and the operator between them."""

    left: str
    right: str
    operator: str

    @property
    def name(self) -> str:
        symbol = OPERATORS_BY_KEY[self.operator].label
        return f"{self.left} {symbol} {self.right}"

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left, "right": self.right,
                "operator": self.operator, "name": self.name}


@dataclass
class Dimensionality:
    """How many independent directions a feature matrix actually holds."""

    features: int = 0
    usable_bars: int = 0
    components: int = 0
    """Principal components needed to reach :data:`VARIANCE_TARGET`."""
    explained: list[float] = field(default_factory=list)
    """Cumulative share of variance, component by component."""
    note: str = ""

    @property
    def compression(self) -> float:
        """Features per independent direction. 1.0 means none were redundant."""
        return (self.features / self.components) if self.components else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"features": self.features, "usable_bars": self.usable_bars,
                "components": self.components,
                "compression": round(self.compression, 2),
                "explained": [round(x, 4) for x in self.explained[:40]],
                "note": self.note}


def effective_dimension(matrix: np.ndarray, names: Sequence[str] | None = None,
                        target: float = VARIANCE_TARGET) -> Dimensionality:
    """How many principal components carry ``target`` of the variance.

    This is the number that belongs beside any feature count. A study of fifty
    features that turn out to be twelve directions has run fifty tests to ask
    twelve questions, and reporting only the fifty makes the search look wider
    than it was while making every correction look harsher than it needs to be.

    Standardised first, because a component analysis of unstandardised columns
    reports whichever feature happens to be measured in the largest units.
    """
    arr = np.asarray(matrix, dtype="float64")
    if arr.ndim != 2 or arr.size == 0:
        return Dimensionality(note="There was no feature matrix to analyse.")
    columns = arr.shape[1]
    rows = np.isfinite(arr).all(axis=1)
    usable = arr[rows]
    out = Dimensionality(features=columns, usable_bars=int(usable.shape[0]))
    if usable.shape[0] < columns + 2:
        out.note = (
            f"Only {usable.shape[0]:,} bars have every feature defined at "
            f"once, which is too few to describe {columns} of them. The "
            f"effective dimension is not reported rather than guessed.")
        return out

    centred = usable - usable.mean(axis=0)
    spread = centred.std(axis=0)
    spread[spread <= 0] = 1.0
    standard = centred / spread
    try:
        singular = np.linalg.svd(standard, compute_uv=False)
    except np.linalg.LinAlgError as exc:        # pragma: no cover - defensive
        out.note = f"The component analysis did not converge ({exc})."
        return out

    variance = singular ** 2
    total = float(variance.sum())
    if total <= 0:
        out.note = "Every feature is constant on this sample."
        return out
    cumulative = np.cumsum(variance) / total
    out.explained = [float(x) for x in cumulative]
    out.components = int(np.searchsorted(cumulative, target) + 1)
    out.note = (
        f"{columns} features are {out.components} independent directions: "
        f"{out.components} principal components carry {target * 100:.0f}% of "
        f"the variance. The feature count is how many tests were run; this is "
        f"how many questions were asked.")
    return out


def build_interactions(parents: Sequence[Feature],
                       operators: Sequence[Operator] = OPERATORS,
                       max_parents: int = MAX_PARENTS) -> list[Feature]:
    """Every allowed pairing of ``parents``, as real :class:`Feature` objects.

    The result plugs into ``compute_matrix`` and the IC evaluation unchanged,
    which is the point: a constructed feature is judged by exactly the
    machinery a hand-written one is, including the multiplicity correction that
    makes a thousand of them expensive.
    """
    chosen = list(parents)[:max(2, int(max_parents))]
    out: list[Feature] = []
    for i, left in enumerate(chosen):
        for j, right in enumerate(chosen):
            if i == j:
                continue
            for operator in operators:
                if operator.symmetric and j < i:
                    continue
                out.append(_child(left, right, operator))
    return out


def _child(left: Feature, right: Feature, operator: Operator) -> Feature:
    """One constructed feature.

    Pointwise: bar *i* of the child is built from bar *i* of each parent and
    nothing else, so a causal parent cannot produce a peeking child. The test
    suite asserts that on every one of them rather than trusting this comment.
    """
    def values(bars: BarSeries, _l=left, _r=right, _op=operator) -> np.ndarray:
        return _op.apply(_l.values(bars), _r.values(bars))

    interaction = Interaction(left.name, right.name, operator.key)
    return Feature(
        name=interaction.name,
        family="interaction",
        description=(f"{operator.description} Parents: {left.name} and "
                     f"{right.name}."),
        compute=values,
        # A child is undefined for as long as its slowest parent is, so it
        # inherits the longer warm-up rather than reporting a number built
        # from one parent and a NaN.
        warmup=max(int(left.warmup), int(right.warmup)))


def drop_restatements(matrix: np.ndarray, children: Sequence[Feature],
                      parent_matrix: np.ndarray,
                      parents: Sequence[Feature],
                      limit: float = REDUNDANT_ABOVE
                      ) -> tuple[list[int], list[str]]:
    """Which children are just their own parent again.

    Returns ``(keep_indices, reasons_dropped)``.  A child correlated above
    ``limit`` with either parent is not a new reading, and testing it spends
    multiplicity on a question already asked -- which makes every genuinely new
    child harder to pass for nothing.
    """
    keep: list[int] = []
    dropped: list[str] = []
    by_name = {f.name: i for i, f in enumerate(parents)}
    for index, child in enumerate(children):
        column = np.asarray(matrix[:, index], dtype="float64")
        worst = 0.0
        for parent_name in _parents_of(child):
            position = by_name.get(parent_name)
            if position is None:
                continue
            other = np.asarray(parent_matrix[:, position], dtype="float64")
            rows = np.isfinite(column) & np.isfinite(other)
            if int(rows.sum()) < 30:
                continue
            if np.std(column[rows]) <= 0 or np.std(other[rows]) <= 0:
                continue
            worst = max(worst, abs(float(np.corrcoef(column[rows],
                                                     other[rows])[0, 1])))
        if worst > limit:
            dropped.append(f"{child.name} (|r| {worst:.2f} with a parent)")
            continue
        keep.append(index)
    return keep, dropped


def _parents_of(child: Feature) -> tuple[str, str]:
    """The two parent names recorded in a constructed feature's description."""
    text = child.description
    marker = "Parents: "
    if marker not in text:
        return ("", "")
    tail = text.split(marker, 1)[1].rstrip(".")
    if " and " not in tail:
        return ("", "")
    left, right = tail.split(" and ", 1)
    return (left.strip(), right.strip())
