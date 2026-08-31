"""Turn a strategy's hard-coded numbers into named, tunable parameters.

A strategy that comes in from Pine or C# arrives as literals.  ``ta.ema(close,
100)`` becomes ``EMA(period=100)`` and ``adx < 22.0`` becomes ``Compare(Ind,
"<", Const(22.0))``.  Everything about it is correct and it backtests fine --
but three of the application's features read ``spec.params`` and find nothing
there, so they refuse to run:

* **Optimise Parameters** says "this strategy has no parameters to optimise";
* **Find a Better Version** builds zero axes and returns zero variants;
* **Walk-forward** has nothing to re-fit on each fold.

The strategy is not the problem; the *shape* it arrives in is.  This module
rewrites it into the shape the rest of the application already understands: a
``ParamSpec`` per tunable number, with the indicator slot or rule now holding
a ``$reference`` to it.  Nothing about what the strategy trades changes -- the
defaults are exactly the literals that were there before, which
:func:`extract_parameters` is tested to guarantee trade-for-trade.

Two things it deliberately does not do.

It does not invent bounds.  An indicator's period gets the bounds the
**registry** declares for that indicator, and a threshold compared against an
oscillator gets that oscillator's ``scale_hint`` range.  Where neither exists
-- a bare multiplier like ``3.964 * ATR`` -- the band is a stated ratio around
the value the author chose, and :attr:`ExtractedParam.basis` says so in words
that reach the UI.  A range presented as knowledge when it is really a guess
is how a sweep ends up exploring somewhere the strategy was never meant to go.

It does not promote every number.  A constant of zero has no ratio band, an
offset is structure rather than a knob, and a number that appears inside a
condition the compiler treats as fixed is left alone.  Every refusal is
reported in :attr:`Extraction.skipped` rather than dropped silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from ..indicators.base import REGISTRY, ParamSpec
from .spec import (Compare, Condition, ConditionGroup, ConstOperand, Cross,
                   IndicatorOperand, IndicatorSlot, Operand, ParamOperand,
                   PriceOperand, ExprOperand, State, StrategySpec, Vote)

__all__ = ["ExtractedParam", "Extraction", "extract_parameters",
           "describe_extraction"]

#: How far either side of the author's number to sweep when nothing better is
#: known.  Four-fold each way: wide enough that a real optimum inside it is
#: reachable, narrow enough that the grid stays a neighbourhood of the
#: strategy rather than a different strategy.
_RATIO = 4.0

#: Scale hints whose natural range is known, and what it is.
_SCALE_BOUNDS: dict[str, tuple[float, float]] = {
    "oscillator_0_100": (0.0, 100.0),
    "percent": (-100.0, 100.0),
}


@dataclass(frozen=True)
class ExtractedParam:
    """One number that became a parameter, and where it came from."""

    name: str
    label: str
    value: float
    where: str
    """Human-readable origin, e.g. ``"the period of HIGHEST on high"``."""
    basis: str
    """Where the sweep bounds came from.  Shown to the user verbatim."""
    minimum: float
    maximum: float

    def describe(self) -> str:
        return (f"{self.label} = {_num(self.value)} "
                f"(from {self.where}; range {_num(self.minimum)} to "
                f"{_num(self.maximum)}, {self.basis})")


@dataclass(frozen=True)
class Extraction:
    """The rewritten strategy, what was promoted, and what was not."""

    spec: StrategySpec
    added: tuple[ExtractedParam, ...] = ()
    skipped: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.added)

    def describe(self) -> str:
        return describe_extraction(self)


def describe_extraction(extraction: Extraction) -> str:
    """A paragraph the dialogs can show without reformatting."""
    if not extraction.added:
        reason = ("; ".join(extraction.skipped) if extraction.skipped
                  else "every number in it is already a parameter")
        return f"Nothing to extract: {reason}."
    lines = [f"{len(extraction.added)} parameter"
             f"{'s' if len(extraction.added) != 1 else ''} extracted. The "
             f"strategy trades exactly as before -- each default is the number "
             f"that was already there."]
    lines += [f"  • {p.describe()}" for p in extraction.added]
    if extraction.skipped:
        lines.append("Left alone:")
        lines += [f"  • {s}" for s in extraction.skipped]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """``"Highest 2.upper"`` -> ``"highest_2_upper"``."""
    out = re.sub(r"[^0-9a-zA-Z]+", "_", str(text)).strip("_").lower()
    out = re.sub(r"_+", "_", out)
    if not out:
        out = "value"
    if out[0].isdigit():
        out = f"p_{out}"
    return out


def _unique(base: str, taken: set[str]) -> str:
    name = base
    n = 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    taken.add(name)
    return name


def _titled(name: str) -> str:
    return " ".join(w.capitalize() if w.islower() else w
                    for w in name.split("_"))


def _num(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return f"{float(value):g}"


# ---------------------------------------------------------------------------
# bounds
# ---------------------------------------------------------------------------

def _ratio_bounds(value: float, integral: bool) -> tuple[float, float, str]:
    """A band around ``value`` when nothing authoritative is known."""
    lo, hi = (value / _RATIO, value * _RATIO)
    if value < 0:
        lo, hi = hi, lo
    if integral:
        lo, hi = max(1.0, float(int(lo))), float(int(hi) + 1)
    else:
        lo, hi = float(f"{lo:.6g}"), float(f"{hi:.6g}")
    return lo, hi, (f"no declared range for this number, so the band is "
                    f"{_num(1 / _RATIO)}x to {_num(_RATIO)}x the value the "
                    f"strategy already used")


def _scale_bounds(hint: str) -> tuple[float, float, str] | None:
    known = _SCALE_BOUNDS.get(hint)
    if known is None:
        return None
    lo, hi = known
    return lo, hi, f"the indicator's own scale ({hint.replace('_', ' ')})"


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

@dataclass
class _Collector:
    """Accumulates parameters while the tree is rewritten around it."""

    taken: set[str] = field(default_factory=set)
    params: list[ParamSpec] = field(default_factory=list)
    added: list[ExtractedParam] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add(self, base: str, value: float, where: str, kind: str,
            minimum: float, maximum: float, step: float, basis: str,
            help_text: str = "") -> str:
        name = _unique(_slug(base), self.taken)
        coerced: Any = int(round(value)) if kind == "int" else float(value)
        # A default outside its own bounds would make every later call to
        # ``param_values`` raise, which is a worse failure than not extracting.
        minimum = min(minimum, float(coerced))
        maximum = max(maximum, float(coerced))
        self.params.append(ParamSpec(
            name=name, label=_titled(name), kind=kind, default=coerced,
            minimum=minimum, maximum=maximum, step=step,
            help=help_text or f"Extracted from {where}. {basis[0].upper()}{basis[1:]}."))
        self.added.append(ExtractedParam(
            name=name, label=_titled(name), value=float(coerced), where=where,
            basis=basis, minimum=minimum, maximum=maximum))
        return name


def _indicator_label(slot: IndicatorSlot) -> str:
    definition = REGISTRY.get(slot.indicator) if slot.indicator else None
    name = definition.name if definition is not None else slot.indicator
    if slot.source and definition is not None and definition.uses_source:
        return f"{name} on {slot.source}"
    return str(name)


def _promote_slots(spec: StrategySpec, col: _Collector) -> None:
    """Give every literal indicator parameter a name and a ``$reference``."""
    for slot in spec.indicators:
        try:
            definition = REGISTRY.get(slot.indicator)
        except Exception:
            col.skipped.append(
                f"{slot.ref}: '{slot.indicator}' is not an indicator this "
                f"application knows, so its numbers were left as they are")
            continue
        rewritten = dict(slot.params)
        for key, value in slot.params.items():
            if isinstance(value, str):
                continue                      # already "$something"
            try:
                declared = definition.param_spec(key)
            except Exception:
                continue
            if declared.kind not in ("int", "float"):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            lo = float(declared.minimum) if declared.minimum is not None else 1.0
            hi = (float(declared.maximum) if declared.maximum is not None
                  else number * _RATIO)
            name = col.add(
                base=f"{slot.ref}_{key}", value=number,
                where=f"the {declared.label.lower()} of "
                      f"{_indicator_label(slot)}",
                kind=declared.kind, minimum=lo, maximum=hi,
                step=float(declared.step or 1),
                basis=f"the range {definition.name} itself declares for "
                      f"{declared.label.lower()}")
            rewritten[key] = f"${name}"
        slot.params = rewritten


def _oscillator_hint(op: Operand, spec: StrategySpec) -> str:
    """The scale of whatever this operand measures, or ``""``."""
    if isinstance(op, IndicatorOperand):
        try:
            slot = spec.slot(op.ref)
            return REGISTRY.get(slot.indicator).scale_hint
        except Exception:
            return ""
    if isinstance(op, ExprOperand):
        return _oscillator_hint(op.left, spec) or _oscillator_hint(op.right, spec)
    return ""


def _sibling_name(op: Operand) -> str:
    """A readable stem for a constant, taken from what it is compared with."""
    if isinstance(op, IndicatorOperand):
        return op.ref if op.output in ("value", "") else f"{op.ref}_{op.output}"
    if isinstance(op, PriceOperand):
        return op.field
    if isinstance(op, ExprOperand):
        return _sibling_name(op.left) or _sibling_name(op.right)
    return ""


def _promote_operand(op: Operand, spec: StrategySpec, col: _Collector,
                     sibling: Operand | None, rule: str,
                     position: str = "threshold") -> Operand:
    """Rewrite constants inside one operand into parameter references.

    ``rule`` is the whole condition as the user reads it, so an extracted
    number can say which rule it came out of; ``position`` distinguishes a
    threshold compared against something (``adx < 22``) from a multiplier
    applied to it (``3.964 * atr``), which changes both the name and where the
    bounds may legitimately come from.
    """
    if isinstance(op, ExprOperand):
        # ``3.964 * atr`` -- the constant is a multiplier of its sibling, and a
        # multiplier of an oscillator is not itself on the oscillator's scale,
        # so the scale hint must not be inherited through here.
        return ExprOperand(
            op.op,
            _promote_operand(op.left, spec, col, op.right, rule, "multiplier"),
            _promote_operand(op.right, spec, col, op.left, rule, "multiplier"))
    if not isinstance(op, ConstOperand):
        return op

    value = float(op.value)
    if value == 0.0:
        col.skipped.append(
            f"the constant 0 in `{rule}`: zero has no proportional range to "
            f"sweep, so it stays a literal")
        return op

    stem = _sibling_name(sibling) if sibling is not None else ""
    suffix = "mult" if position == "multiplier" else "level"
    base = f"{stem}_{suffix}" if stem else suffix

    hint = _oscillator_hint(sibling, spec) if sibling is not None else ""
    scaled = _scale_bounds(hint) if position != "multiplier" else None
    if scaled is not None:
        lo, hi, basis = scaled
    else:
        lo, hi, basis = _ratio_bounds(value, integral=False)

    name = col.add(base=base, value=value,
                   where=f"the {position} in `{rule}`", kind="float",
                   minimum=lo, maximum=hi,
                   step=_step_for(lo, hi), basis=basis)
    return ParamOperand(name)


def _step_for(lo: float, hi: float) -> float:
    span = abs(hi - lo)
    if span >= 200:
        return 1.0
    if span >= 20:
        return 0.5
    if span >= 2:
        return 0.1
    return 0.01


def _promote_condition(cond: Condition | None, spec: StrategySpec,
                       col: _Collector) -> Condition | None:
    """Rewrite constants in a rule tree, returning the rebuilt tree."""
    if cond is None:
        return None
    if isinstance(cond, Compare):
        rule = cond.describe()
        return Compare(
            _promote_operand(cond.left, spec, col, cond.right, rule),
            cond.op,
            _promote_operand(cond.right, spec, col, cond.left, rule))
    if isinstance(cond, Cross):
        rule = cond.describe()
        return Cross(
            _promote_operand(cond.left, spec, col, cond.right, rule),
            cond.direction,
            _promote_operand(cond.right, spec, col, cond.left, rule))
    if isinstance(cond, ConditionGroup):
        return ConditionGroup(
            cond.op,
            [c for c in (_promote_condition(child, spec, col)
                         for child in cond.children) if c is not None],
            cond.negate)
    if isinstance(cond, Vote):
        return Vote(
            cond.threshold,
            [c for c in (_promote_condition(child, spec, col)
                         for child in cond.children) if c is not None],
            cond.negate)
    # State, SessionWindow and Always carry structure rather than knobs.
    return cond


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def extract_parameters(spec: StrategySpec, *, indicators: bool = True,
                       thresholds: bool = True) -> Extraction:
    """Return a copy of ``spec`` whose literals are named parameters.

    The returned strategy trades identically: every extracted parameter
    defaults to the number it replaced.  Only the *shape* changes, and that is
    what the optimiser, the variant search and walk-forward read.

    ``indicators`` promotes indicator periods and the like; ``thresholds``
    promotes constants that appear inside the rules.  Both default on because
    a strategy is rarely worth tuning on only one of them, but the editor
    exposes them separately: someone who wants to sweep the channel lengths
    without also moving the ADX gate can say so.
    """
    out = spec.copy(spec.name)
    out.id = spec.id
    col = _Collector(taken={p.name for p in out.params})

    if indicators:
        _promote_slots(out, col)
    else:
        col.skipped.append("indicator parameters were not requested")

    if thresholds:
        out.entry_long = _promote_condition(out.entry_long, out, col)
        out.entry_short = _promote_condition(out.entry_short, out, col)
        out.exit_long = _promote_condition(out.exit_long, out, col)
        out.exit_short = _promote_condition(out.exit_short, out, col)
    else:
        col.skipped.append("rule thresholds were not requested")

    out.params = list(out.params) + col.params
    return Extraction(spec=out, added=tuple(col.added),
                      skipped=tuple(col.skipped))
