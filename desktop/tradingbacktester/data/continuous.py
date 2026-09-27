"""Splicing several futures contracts into one continuous series.

A futures contract expires.  To backtest a strategy over ten years of the E-mini
you need ten years of *one* series, and no such thing exists: there are forty
quarterly contracts, each alive for a few months, each ending at a different
price from the one that replaces it.  Stitching them is not a formatting step,
it is a modelling decision that changes every number downstream, and getting it
wrong is one of the standard ways a futures backtest comes out wrong.

Three decisions, and this module makes all three explicit rather than picking
for you.

**When to roll.**  The front contract stops being the one people trade some days
before it expires.  Rolling on expiry itself backtests a market that had almost
no volume in it; rolling when volume crosses to the next contract is what a
trader actually does, and needs both series to compare.  Both are offered, and a
fixed number of days before expiry is offered as the fallback for data that
carries no volume worth trusting.

**How to join.**  The old contract's last price and the new one's first price are
different -- for a stock index usually by the cost of carry, tens of points --
and a raw concatenation puts a jump there that no trader ever paid.  A
strategy will read that jump as a gap, and a breakout rule will trade it.

**What the join costs you.**  Every adjustment is a lie of some kind, and the
useful question is which lie you can live with:

* ``BACK_ADJUSTED`` (difference) shifts all older prices by the roll gap so the
  returns across the join are the ones a rolled position earned.  The recent end
  is the real price; the far end is not, and on a long enough history it can go
  negative.  Absolute price levels and percentage stops are meaningless on it.
* ``RATIO`` scales instead of shifting, which keeps percentage returns right and
  prices positive, but no price in the series except the last contract's is one
  that ever traded.
* ``UNADJUSTED`` splices with no correction at all.  Every price is real and the
  return across each join is not: it contains the roll gap as if it were a
  market move.  Correct for reading levels off the chart, wrong for P&L.

None of the three is right for everything, so the series records which one made
it, and :func:`describe` states the consequence in a sentence.

What this module will not do: it will not guess expiry dates, invent volume, or
splice contracts whose bar sizes differ.  A roll it cannot justify is an error,
not a silent choice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

import numpy as np

from ..core.errors import DataError, InsufficientDataError
from .models import BarSeries

log = logging.getLogger(__name__)


class Adjustment(str, Enum):
    """How the price gap at each join is dealt with."""

    BACK_ADJUSTED = "back_adjusted"
    RATIO = "ratio"
    UNADJUSTED = "unadjusted"


class RollRule(str, Enum):
    """What decides the bar a contract stops being the front one."""

    VOLUME = "volume"
    """The first bar where the next contract trades more than this one, held
    for :data:`VOLUME_CONFIRM_BARS` bars so a single busy bar cannot roll it."""
    DAYS_BEFORE_END = "days_before_end"
    """A fixed number of calendar days before the contract's last bar."""
    LAST_BAR = "last_bar"
    """Roll on the contract's final bar. Honest only for data that really does
    end at expiry, and it backtests the days when nobody is trading it."""


#: Consecutive bars the next contract must out-trade the front one before the
#: roll is taken.  One bar is noise; three is a change in where the market is.
VOLUME_CONFIRM_BARS = 3

#: Default for :attr:`RollRule.DAYS_BEFORE_END`.  The CME equity index roll is
#: the Thursday before the third Friday, about a week out.
DEFAULT_ROLL_DAYS = 7

_DAY_NS = 86_400_000_000_000


@dataclass
class Contract:
    """One delivery month's bars, with the label it will be reported under."""

    label: str
    bars: BarSeries

    def __post_init__(self) -> None:
        self.label = str(self.label).strip() or "?"
        if not isinstance(self.bars, BarSeries):
            raise DataError(f"Contract {self.label} has no bars.")

    @property
    def first_ts(self) -> int:
        return int(self.bars.ts[0])

    @property
    def last_ts(self) -> int:
        return int(self.bars.ts[-1])


@dataclass
class Roll:
    """One join: which contract handed over to which, where, and at what cost."""

    at_ts: int
    from_label: str
    to_label: str
    from_price: float
    """Front contract's close on the last bar it supplied."""
    to_price: float
    """Next contract's close on the same bar."""
    rule: str = ""

    @property
    def gap(self) -> float:
        """Next minus front: what a raw splice would show as a price move."""
        return float(self.to_price - self.from_price)

    @property
    def ratio(self) -> float:
        return (float(self.to_price / self.from_price)
                if self.from_price else float("nan"))

    def to_dict(self) -> dict[str, Any]:
        return {"at_ts": int(self.at_ts), "from": self.from_label,
                "to": self.to_label, "from_price": self.from_price,
                "to_price": self.to_price, "gap": self.gap,
                "ratio": self.ratio, "rule": self.rule}


@dataclass
class ContinuousSeries:
    """The spliced series and the full record of how it was made."""

    bars: BarSeries
    adjustment: Adjustment
    rolls: list[Roll] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_gap(self) -> float:
        """Sum of every roll gap: how far the far end has been moved."""
        return float(sum(r.gap for r in self.rolls))

    def to_dict(self) -> dict[str, Any]:
        return {"adjustment": self.adjustment.value,
                "contracts": list(self.contracts),
                "rolls": [r.to_dict() for r in self.rolls],
                "total_gap": self.total_gap,
                "bars": len(self.bars),
                "notes": list(self.notes)}


def describe(series: ContinuousSeries, currency: str = "") -> str:
    """One paragraph saying what this series is and what it cannot be used for."""
    unit = f" {currency}" if currency else ""
    named = ", ".join(series.contracts)
    head = (f"{len(series.bars):,} bars spliced from {len(series.contracts)} "
            f"contracts ({named}) at {len(series.rolls)} rolls")
    if series.adjustment is Adjustment.BACK_ADJUSTED:
        return (f"{head}, back-adjusted by difference. Prices before the last "
                f"roll have been shifted by {series.total_gap:+,.2f}{unit} in "
                f"total, so returns across each join are the ones a rolled "
                f"position earned — but no price here except the front "
                f"contract's is a price that traded, and a percentage stop or "
                f"an absolute level read off this series is meaningless.")
    if series.adjustment is Adjustment.RATIO:
        return (f"{head}, ratio-adjusted. Percentage returns across each join "
                f"are right and every price stays positive, but only the front "
                f"contract's prices are ones that traded, so absolute levels "
                f"are not tradeable prices.")
    return (f"{head}, unadjusted. Every price here really traded. The return "
            f"across each join does not: it contains the roll gap "
            f"({series.total_gap:+,.2f}{unit} in total) as though it were a "
            f"market move, so P&L measured through a roll is wrong by that "
            f"much.")


# ---------------------------------------------------------------------------
# choosing the roll bar
# ---------------------------------------------------------------------------


def _overlap(front: BarSeries, nxt: BarSeries) -> tuple[np.ndarray, np.ndarray]:
    """Indices into each series where both have a bar at the same timestamp."""
    common = np.intersect1d(front.ts, nxt.ts, assume_unique=False)
    if common.size == 0:
        return np.zeros(0, dtype="int64"), np.zeros(0, dtype="int64")
    return (np.searchsorted(front.ts, common).astype("int64"),
            np.searchsorted(nxt.ts, common).astype("int64"))


def _volume_roll(front: BarSeries, nxt: BarSeries) -> int | None:
    """First front-series index where the next contract has out-traded it.

    Requires :data:`VOLUME_CONFIRM_BARS` consecutive bars, so one busy bar in
    the back month cannot roll the series.  ``None`` when the two never overlap
    or the crossover never happens -- the caller then falls back rather than
    inventing a roll.
    """
    fi, ni = _overlap(front, nxt)
    if fi.size < VOLUME_CONFIRM_BARS:
        return None
    ahead = np.asarray(nxt.volume[ni] > front.volume[fi], dtype=bool)
    if not ahead.any():
        return None
    # A run of VOLUME_CONFIRM_BARS Trues: convolve and find the first full one.
    run = np.convolve(ahead.astype("int32"),
                      np.ones(VOLUME_CONFIRM_BARS, dtype="int32"), mode="valid")
    hit = np.flatnonzero(run == VOLUME_CONFIRM_BARS)
    if hit.size == 0:
        return None
    return int(fi[int(hit[0])])


def _days_before_end_roll(front: BarSeries, days: int) -> int | None:
    """Last front-series index at or before ``days`` days from its final bar."""
    cutoff = int(front.ts[-1]) - int(max(0, days)) * _DAY_NS
    index = int(np.searchsorted(front.ts, cutoff, side="right")) - 1
    return index if index >= 0 else None


def _roll_index(front: BarSeries, nxt: BarSeries, rule: RollRule,
                days: int) -> tuple[int, str]:
    """``(last front index to use, what decided it)``.

    Never returns an index the next contract cannot take over from: the roll
    bar must exist in both series, or the join would leave a hole.
    """
    chosen: int | None = None
    why = ""
    if rule is RollRule.VOLUME:
        chosen = _volume_roll(front, nxt)
        why = f"volume crossover, confirmed over {VOLUME_CONFIRM_BARS} bars"
        if chosen is None:
            chosen = _days_before_end_roll(front, days)
            why = (f"{days} days before the contract's last bar — the volume "
                   f"crossover never happened in the overlap")
    elif rule is RollRule.DAYS_BEFORE_END:
        chosen = _days_before_end_roll(front, days)
        why = f"{days} days before the contract's last bar"
    else:
        chosen = len(front) - 1
        why = "the contract's last bar"

    if chosen is None:
        chosen = len(front) - 1
        why = "the contract's last bar — nothing else could be determined"

    # The roll has to land on a bar BOTH contracts have, or the join leaves a
    # hole. A rule can easily pick one that is not: a fixed number of days
    # before expiry can fall before the next contract started trading, and a
    # thin back month may simply have no print on the chosen bar.
    both = np.intersect1d(front.ts, nxt.ts)
    if both.size == 0:
        raise DataError(
            "Two contracts have no bar in common, so there is no bar to roll "
            "on. A continuous series needs the contracts to overlap.",
            detail=f"front ends {front.ts[-1]}, next starts {nxt.ts[0]}")

    at = int(front.ts[chosen])
    if at < int(both[0]):
        at = int(both[0])
        why += " (moved forward to the first bar both contracts have)"
    elif at > int(both[-1]):
        at = int(both[-1])
        why += " (moved back to the last bar both contracts have)"
    elif at not in set(both.tolist()):
        earlier = both[both <= at]
        at = int(earlier[-1]) if earlier.size else int(both[0])
        why += " (moved back to the nearest bar both contracts have)"
    return int(np.searchsorted(front.ts, at)), why


# ---------------------------------------------------------------------------
# splicing
# ---------------------------------------------------------------------------


def build_continuous(contracts: Sequence[Contract], *,
                     adjustment: Adjustment = Adjustment.BACK_ADJUSTED,
                     rule: RollRule = RollRule.VOLUME,
                     days_before_end: int = DEFAULT_ROLL_DAYS
                     ) -> ContinuousSeries:
    """Splice ``contracts`` into one series, oldest first.

    Every contract must be the same instrument and the same bar size; a mixed
    list is an error rather than a series nobody can interpret.
    """
    rows = [c for c in contracts if c is not None]
    if len(rows) < 2:
        raise InsufficientDataError(
            "A continuous series needs at least two contracts. One contract is "
            "already a continuous series — of itself.")
    rows.sort(key=lambda c: c.first_ts)

    first = rows[0].bars
    for c in rows[1:]:
        if c.bars.timeframe != first.timeframe:
            raise DataError(
                f"Contract {c.label} is {c.bars.timeframe.label} where "
                f"{rows[0].label} is {first.timeframe.label}. Contracts must "
                f"share a bar size before they can be spliced.")
        if c.bars.instrument.symbol != first.instrument.symbol:
            raise DataError(
                f"Contract {c.label} is {c.bars.instrument.symbol} where "
                f"{rows[0].label} is {first.instrument.symbol}. A continuous "
                f"series is one instrument.")

    # Decide every roll first, so the adjustment can be applied backwards from
    # the front contract in one pass.
    rolls: list[Roll] = []
    cuts: list[int] = []
    notes: list[str] = []
    for i in range(len(rows) - 1):
        front, nxt = rows[i].bars, rows[i + 1].bars
        index, why = _roll_index(front, nxt, rule, days_before_end)
        at = int(front.ts[index])
        position = int(np.searchsorted(nxt.ts, at, side="left"))
        rolls.append(Roll(
            at_ts=at, from_label=rows[i].label, to_label=rows[i + 1].label,
            from_price=float(front.close[index]),
            to_price=float(nxt.close[position]), rule=why))
        cuts.append(index)

    pieces: list[BarSeries] = []
    for i, row in enumerate(rows):
        bars = row.bars
        if i == 0:
            lo = 0
        else:
            # Start the bar after the roll: the roll bar itself was supplied by
            # the contract that handed over, and counting it twice would put a
            # duplicate timestamp in the series the engine refuses to run on.
            previous_at = rolls[i - 1].at_ts
            lo = int(np.searchsorted(bars.ts, previous_at, side="right"))
        hi = cuts[i] + 1 if i < len(cuts) else len(bars)
        if hi <= lo:
            notes.append(
                f"{row.label} contributed no bars: its roll to "
                f"{rows[i + 1].label if i < len(cuts) else '?'} falls at or "
                f"before the roll that handed over to it.")
            continue
        pieces.append(bars.slice(lo, hi))

    if not pieces:
        raise InsufficientDataError(
            "The rolls left no bars at all. Check that the contracts overlap "
            "and are in date order.")

    # Adjust every piece before the last by the cumulative gap ahead of it, so
    # the front contract keeps its real prices and history is shifted onto it.
    shift = 0.0
    scale = 1.0
    adjusted: list[dict[str, np.ndarray]] = []
    for i in range(len(pieces) - 1, -1, -1):
        piece = pieces[i]
        adjusted.insert(0, _apply(piece, adjustment, shift, scale))
        if i > 0:
            roll = rolls[i - 1]
            shift += roll.gap
            ratio = roll.ratio
            scale *= ratio if np.isfinite(ratio) and ratio > 0 else 1.0

    ts = np.concatenate([p.ts for p in pieces])
    order = np.argsort(ts, kind="stable")
    out = BarSeries(
        ts=ts[order],
        open=np.concatenate([a["open"] for a in adjusted])[order],
        high=np.concatenate([a["high"] for a in adjusted])[order],
        low=np.concatenate([a["low"] for a in adjusted])[order],
        close=np.concatenate([a["close"] for a in adjusted])[order],
        volume=np.concatenate([p.volume for p in pieces])[order],
        instrument=first.instrument, timeframe=first.timeframe,
        # Not the first contract's file: this series is not that file, and a
        # source that names one leg of a three-way splice is how a continuous
        # series gets mistaken for a raw one later.
        source="continuous: " + ", ".join(r.label for r in rows),
        meta={**dict(first.meta), "continuous": True,
              "adjustment": adjustment.value,
              "contracts": [r.label for r in rows],
              "rolls": [r.to_dict() for r in rolls]})

    if adjustment is Adjustment.BACK_ADJUSTED and float(out.low.min()) <= 0:
        notes.append(
            "Back-adjusting has pushed the oldest prices to zero or below. "
            "That is arithmetic, not a market: the accumulated roll gaps "
            "exceed the price the contract traded at back then. Use ratio "
            "adjustment for a history this long, or start later.")
    return ContinuousSeries(bars=out, adjustment=adjustment, rolls=rolls,
                            contracts=[r.label for r in rows], notes=notes)


def _apply(piece: BarSeries, adjustment: Adjustment, shift: float,
           scale: float) -> dict[str, np.ndarray]:
    """One contract's prices, moved onto the front contract's scale."""
    if adjustment is Adjustment.UNADJUSTED:
        return {"open": np.array(piece.open, dtype="float64", copy=True),
                "high": np.array(piece.high, dtype="float64", copy=True),
                "low": np.array(piece.low, dtype="float64", copy=True),
                "close": np.array(piece.close, dtype="float64", copy=True)}
    if adjustment is Adjustment.RATIO:
        return {name: np.asarray(getattr(piece, name), dtype="float64") * scale
                for name in ("open", "high", "low", "close")}
    return {name: np.asarray(getattr(piece, name), dtype="float64") + shift
            for name in ("open", "high", "low", "close")}
