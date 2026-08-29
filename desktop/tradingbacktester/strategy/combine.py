"""Merge several strategies into one, without inventing anything.

Two people asking "what if I ran these together?" mean one of three things,
and this module keeps them apart:

``all``
    every strategy must signal on the same bar.  A confirmation filter.  It
    trades least and is the only mode that can make a strategy *stricter*
    than any of its parts.
``any``
    one signal is enough.  This is the union, and it trades most.  It is not
    a portfolio of the parts -- there is still one position at a time -- so
    its results will not resemble running the strategies side by side.
``majority``
    at least *k* of *n* agree, expressed as :class:`~spec.Vote`.  The middle
    of the scale, and the reason ``Vote`` exists.

The whole job is namespacing.  Two strategies that both call an indicator
``ema`` and both have a parameter called ``period`` cannot be pasted into one
spec: the second would silently take over the first's slot and the merged
strategy would trade something neither of them describes.  So every source is
rewritten into its own prefix -- indicator refs, strategy parameters, the
``$name`` references inside indicator parameters, and every operand in every
rule -- before anything is joined.

Three things this deliberately will **not** do.

It will not merge risk, exit, execution, session or cost settings.  A stop of
1.5 ATR and a stop of 3 ATR have no average that either author would accept,
and picking one silently is how a merged strategy ends up being backtested
under a risk model nobody chose.  One source is named the primary, its
settings are used whole, and **every** field the others disagree about is
listed in :attr:`CombineReport.conflicts` for the caller to show.

It will not lower a vote's threshold to match how many strategies happen to
have a rule for that direction.  Three strategies of which one is long-only,
combined with ``majority``, needs two of *three* to agree on a long entry;
the two short-only ones simply never do, so the long side goes quiet.  That
is the honest reading, and quietly turning it into "one of one" would be a
different strategy that trades far more.

It will not combine the *results* of backtests.  Merging two equity curves is
a portfolio question -- correlation, capital allocation, concurrent positions
-- and this produces a single strategy that holds one position at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from ..core.errors import StrategyError
from .spec import (Condition, ExprOperand, Group, IndicatorOperand,
                   IndicatorSlot, Operand, ParamOperand, StrategySpec, Vote,
                   _enum_dict, walk_conditions)

__all__ = ["COMBINE_MODES", "CombineReport", "combine_strategies",
           "default_threshold", "describe_mode"]

#: The ways rules may be joined.  ``exit_mode`` accepts the same three.
COMBINE_MODES = ("all", "any", "majority")

_MODE_HELP = {
    "all": "every strategy must signal on the same bar",
    "any": "any one strategy signalling is enough",
    "majority": "at least half of the strategies must agree",
}

#: The rule attributes on a spec, and whether each is an entry.
_RULES = (("entry_long", True), ("entry_short", True),
          ("exit_long", False), ("exit_short", False))

#: Settings blocks taken whole from the primary strategy.
_SETTINGS = ("risk", "exits", "execution", "session", "costs")

#: Decided by the combination, not copied from the primary, so they are not
#: reported as conflicts.
_DERIVED_FIELDS = {("risk", "allow_long"), ("risk", "allow_short")}

_IDENT = re.compile(r"[^0-9A-Za-z]+")


def describe_mode(mode: str) -> str:
    """One clause explaining a mode, for a dialog or a report."""
    return _MODE_HELP.get(str(mode).lower(), str(mode))


def default_threshold(count: int) -> int:
    """How many of ``count`` strategies a ``majority`` needs.

    A strict majority: 2 of 3, 2 of 4, 3 of 5.  Two strategies need both,
    which makes ``majority`` identical to ``all`` at n=2 -- correct rather
    than convenient, and the report says so.
    """
    return max(1, int(count) // 2 + 1)


@dataclass
class CombineReport:
    """The merged strategy and everything the merge had to decide."""

    spec: StrategySpec
    mode: str = "all"
    exit_mode: str = "any"
    threshold: int = 1
    sources: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Things the caller should know but that are not disagreements."""
    conflicts: list[str] = field(default_factory=list)
    """Settings the sources disagreed about, and which value was used."""
    shared: list[str] = field(default_factory=list)
    """Indicator slots that were identical and therefore computed once."""
    warnings: list[str] = field(default_factory=list)
    """Whatever ``spec.validate()`` returned."""

    def summary(self) -> str:
        """A single paragraph fit for a status bar or a CLI line."""
        joined = ", ".join(self.sources)
        head = (f"{len(self.sources)} strategies combined with "
                f"'{self.mode}' ({describe_mode(self.mode)}): {joined}.")
        if self.conflicts:
            head += (f" {len(self.conflicts)} setting"
                     f"{'' if len(self.conflicts) == 1 else 's'} differed and "
                     f"the primary strategy's value was used.")
        return head

    def lines(self) -> list[str]:
        """The full explanation, one point per line."""
        out = [self.summary()]
        for group, items in (("Shared indicator", self.shared),
                             ("Conflict", self.conflicts),
                             ("Note", self.notes),
                             ("Warning", self.warnings)):
            for item in items:
                out.append(f"{group}: {item}")
        return out


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------


def _slug(name: str, fallback: str) -> str:
    """A short identifier fragment from a strategy name.

    Refs and parameter names end up in rule descriptions and Pine exports, so
    the prefix has to be an identifier: letters, digits and underscores, never
    leading with a digit.
    """
    parts = [p for p in _IDENT.split(str(name or "")) if p]
    if not parts:
        return fallback
    text = parts[0][:10] + "".join(p[:1].upper() + p[1:4] for p in parts[1:2])
    text = text[:14]
    if not text or not text[0].isalpha():
        text = fallback + text
    return text


def _prefixes(specs: Sequence[StrategySpec]) -> list[str]:
    """One unique prefix per source, derived from its name where possible."""
    out: list[str] = []
    used: set[str] = set()
    for i, spec in enumerate(specs):
        base = _slug(spec.name, f"s{i + 1}")
        candidate, n = base, 1
        while candidate.lower() in used:
            n += 1
            candidate = f"{base}{n}"
        used.add(candidate.lower())
        out.append(candidate)
    return out


# --------------------------------------------------------------------------
# Rewriting one source into its own namespace
# --------------------------------------------------------------------------


def _rewrite_operand(op: Operand, refs: dict[str, str],
                     params: dict[str, str]) -> None:
    if isinstance(op, IndicatorOperand):
        op.ref = refs.get(op.ref, op.ref)
    elif isinstance(op, ParamOperand):
        op.name = params.get(op.name, op.name)
    elif isinstance(op, ExprOperand):
        _rewrite_operand(op.left, refs, params)
        _rewrite_operand(op.right, refs, params)


def _rewrite_condition(cond: Condition | None, refs: dict[str, str],
                       params: dict[str, str]) -> None:
    """Rename every reference inside a rule tree, in place.

    ``walk_conditions`` reaches nested groups and votes alike, and the operand
    attributes are always called ``left`` and ``right`` -- ``State`` has only
    a ``left``, ``SessionWindow`` and ``Always`` have neither.
    """
    for node in walk_conditions(cond):
        for attribute in ("left", "right"):
            operand = getattr(node, attribute, None)
            if isinstance(operand, Operand):
                _rewrite_operand(operand, refs, params)


def _namespace(spec: StrategySpec, prefix: str) -> StrategySpec:
    """A copy of ``spec`` with every name it owns moved under ``prefix``.

    The maps are built first and applied in one pass.  Renaming one name at a
    time would let an early rename collide with a name not yet processed --
    ``a -> b`` followed by ``b -> c`` turns the original ``a`` into ``c``.
    """
    out = spec.copy()
    refs = {slot.ref: f"{prefix}_{slot.ref}" for slot in out.indicators}
    params = {p.name: f"{prefix}_{p.name}" for p in out.params}

    # ``ParamSpec`` is frozen, so a rename is a new instance.  The label is
    # left alone: it is what the author wrote and what the optimiser shows.
    out.params = [replace(p, name=params[p.name]) for p in out.params]
    for slot in out.indicators:
        slot.ref = refs[slot.ref]
        for key, value in list(slot.params.items()):
            if isinstance(value, str) and value.startswith("$"):
                old = value[1:]
                if old in params:
                    slot.params[key] = f"${params[old]}"
    for attribute, _is_entry in _RULES:
        _rewrite_condition(getattr(out, attribute, None), refs, params)
    return out


# --------------------------------------------------------------------------
# Sharing identical indicators
# --------------------------------------------------------------------------


def _slot_key(slot: IndicatorSlot) -> tuple[Any, ...] | None:
    """A key for two slots that are certainly the same computation.

    Only slots whose parameters are all literals qualify.  Two slots that
    both read ``{"period": "$fast"}`` are identical *today* but their
    parameters are now separate and either can be optimised on its own, so
    sharing them would silently tie two knobs together.
    """
    for value in slot.params.values():
        if isinstance(value, str) and value.startswith("$"):
            return None
    items = tuple(sorted((k, _hashable(v)) for k, v in slot.params.items()))
    return (slot.indicator, slot.source, items)


def _hashable(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    return value


def _disambiguate_labels(sources: Sequence[StrategySpec],
                         names: Sequence[str]) -> None:
    """Suffix the source name onto any chart label two sources share.

    Only where they collide.  Suffixing everything would turn a legend of
    "EMA Fast" into "EMA Fast (Donchian Breakout with a 200 EMA filter)" for
    no reason, and suffixing nothing leaves two lines called "EMA 20" with no
    way to tell whose is whose.
    """
    counts: dict[str, int] = {}
    for spec in sources:
        for slot in spec.indicators:
            label = slot.display_label()
            counts[label] = counts.get(label, 0) + 1
    for spec, name in zip(sources, names):
        for slot in spec.indicators:
            if counts.get(slot.display_label(), 0) > 1:
                slot.label = f"{slot.display_label()} ({name})"


def _share_identical(sources: list[StrategySpec]) -> list[str]:
    """Fold duplicate indicator slots together, rewriting the rules.

    Returns one line per slot that was shared.  This is the one place the
    merge removes something, and it is safe because the removed slot computed
    the same array from the same inputs.
    """
    seen: dict[tuple[Any, ...], tuple[str, str]] = {}
    shared: list[str] = []
    for spec in sources:
        rename: dict[str, str] = {}
        keep: list[IndicatorSlot] = []
        for slot in spec.indicators:
            key = _slot_key(slot)
            if key is None:
                keep.append(slot)
                continue
            if key in seen:
                first_ref, first_label = seen[key]
                rename[slot.ref] = first_ref
                shared.append(
                    f"{slot.display_label()} is used by more than one "
                    f"strategy and is computed once, as '{first_ref}' "
                    f"({first_label}).")
                continue
            seen[key] = (slot.ref, slot.display_label())
            keep.append(slot)
        if rename:
            spec.indicators = keep
            for attribute, _is_entry in _RULES:
                _rewrite_condition(getattr(spec, attribute, None), rename, {})
    return shared


# --------------------------------------------------------------------------
# Joining the rules
# --------------------------------------------------------------------------


def _rule_of(spec: StrategySpec, attribute: str) -> Condition | None:
    """The rule, or ``None`` when this strategy would never act on it.

    A long entry rule on a strategy with ``allow_long`` off is not a rule the
    strategy trades, so under ``all`` it must count as a withheld vote rather
    than as agreement.  Reading the gate here keeps that in one place.
    """
    cond = getattr(spec, attribute, None)
    if cond is None:
        return None
    if attribute.endswith("_long") and not spec.risk.allow_long:
        return None
    if attribute.endswith("_short") and not spec.risk.allow_short:
        return None
    return cond


def _merge_rules(mode: str, rules: Sequence[Condition | None],
                 threshold: int) -> Condition | None:
    """Join one rule slot across the sources according to ``mode``."""
    present = [c for c in rules if c is not None]
    if not present:
        return None
    if mode == "all":
        # A source with no rule here can never agree, so the conjunction is
        # unsatisfiable.  Saying so is better than dropping the absent source
        # and returning a rule that is really "all of the others".
        if len(present) < len(rules):
            return None
        return present[0] if len(present) == 1 else Group("AND", present)
    if mode == "any":
        return present[0] if len(present) == 1 else Group("OR", present)
    if mode == "majority":
        if threshold > len(present):
            return None
        if threshold <= 1:
            # "at least one of them" is an OR, and reads like one.
            return present[0] if len(present) == 1 else Group("OR", present)
        return Vote(threshold, present)
    raise StrategyError(
        f"'{mode}' is not a way of combining strategies. Use one of "
        f"{', '.join(COMBINE_MODES)}.")


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def _settings_conflicts(sources: Sequence[StrategySpec], names: Sequence[str],
                        primary: int) -> list[str]:
    """Every settings field the sources disagree about, in words.

    Nothing is merged; this only reports.  The caller decides whether to show
    it, but it is never silent: a merged strategy that quietly inherits one
    author's stop loss is the single most misleading thing this module could
    produce.
    """
    out: list[str] = []
    for block in _SETTINGS:
        chosen = _enum_dict(getattr(sources[primary], block))
        others = [(names[i], _enum_dict(getattr(s, block)))
                  for i, s in enumerate(sources) if i != primary]
        for key, mine in chosen.items():
            if (block, key) in _DERIVED_FIELDS:
                continue
            differing = [(n, d[key]) for n, d in others
                         if key in d and d[key] != mine]
            if not differing:
                continue
            said = "; ".join(f"{n} has {_show(v)}" for n, v in differing)
            out.append(
                f"{block}.{key}: using {_show(mine)} from "
                f"{names[primary]} ({said}).")
    return out


def _show(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(_show(v) for v in value) + ")"
    return str(value)


# --------------------------------------------------------------------------
# The entry point
# --------------------------------------------------------------------------


def combine_strategies(specs: Iterable[StrategySpec], mode: str = "all",
                       exit_mode: str = "any", name: str = "",
                       primary: int = 0,
                       threshold: int | None = None) -> CombineReport:
    """Merge ``specs`` into one strategy.

    ``mode`` joins the entry rules and ``exit_mode`` the exit rules; they
    default differently on purpose.  Entries default to ``all`` because the
    common reason to combine strategies is confirmation, and exits default to
    ``any`` because a position whose thesis has ended under *one* of the
    strategies is a position nobody is holding for a reason.  Requiring every
    strategy to agree before closing would keep a trade open on the strength
    of a rule that is not what got you in.

    ``primary`` names the source whose risk, exit, execution, session and cost
    settings the result uses.  ``threshold`` overrides the majority count.

    Raises :class:`StrategyError` if the merge would produce a strategy that
    can never open a trade, rather than returning one that silently does
    nothing.
    """
    originals = list(specs)
    if len(originals) < 2:
        raise StrategyError(
            f"Combining needs at least two strategies; {len(originals)} "
            f"{'was' if len(originals) == 1 else 'were'} given.")
    mode = str(mode).lower().strip()
    exit_mode = str(exit_mode).lower().strip()
    for label, value in (("entry", mode), ("exit", exit_mode)):
        if value not in COMBINE_MODES:
            raise StrategyError(
                f"'{value}' is not a way of combining {label} rules. Use one "
                f"of {', '.join(COMBINE_MODES)}.")
    if not 0 <= int(primary) < len(originals):
        raise StrategyError(
            f"The primary strategy must be one of the {len(originals)} being "
            f"combined, numbered 1 to {len(originals)}.")
    primary = int(primary)

    count = len(originals)
    want = default_threshold(count) if threshold is None else int(threshold)
    if mode == "majority" or exit_mode == "majority":
        if not 1 <= want <= count:
            raise StrategyError(
                f"A majority of {count} strategies is between 1 and {count}, "
                f"not {want}.")

    names = [s.name for s in originals]
    prefixes = _prefixes(originals)
    sources = [_namespace(s, p) for s, p in zip(originals, prefixes)]
    notes: list[str] = []
    shared = _share_identical(sources)
    _disambiguate_labels(sources, names)

    merged = StrategySpec(name=name.strip() or _default_name(names, mode))
    for spec in sources:
        merged.params.extend(spec.params)
        merged.indicators.extend(spec.indicators)

    for attribute, is_entry in _RULES:
        rules = [_rule_of(s, attribute) for s in sources]
        joined = _merge_rules(mode if is_entry else exit_mode, rules, want)
        setattr(merged, attribute, joined)

    for side in ("long", "short"):
        # An exit rule for a direction that can never be entered is dead
        # weight: it would sit in the summary describing behaviour the
        # strategy does not have.  Dropping it may leave an indicator with no
        # rule using it, which ``validate`` reports honestly.
        if getattr(merged, f"entry_{side}") is None and \
                getattr(merged, f"exit_{side}") is not None:
            setattr(merged, f"exit_{side}", None)
            notes.append(
                f"The {side} exit rule was dropped: there is no {side} entry "
                f"rule, so no {side} position could ever be open to exit.")

    # Settings: the primary's, whole, with every disagreement reported.
    # Copied, not aliased.  Assigning the primary's own settings object would
    # leave the two strategies sharing it, so later editing the combination's
    # stop loss in the editor would silently change the strategy it came from.
    # Every field in these blocks is a scalar, a string, an enum or a tuple, so
    # a shallow `replace` is a real copy.
    for block in _SETTINGS:
        setattr(merged, block, replace(getattr(originals[primary], block)))
    conflicts = _settings_conflicts(originals, names, primary)

    # Direction gates follow from the combination, not from the primary.
    merged.risk = _with_directions(merged.risk, merged.entry_long is not None,
                                   merged.entry_short is not None)

    _explain(notes, originals, names, mode, exit_mode, want, count, primary)
    _check_tradeable(merged, sources, names, mode, want)

    merged.description = _description(names, mode, exit_mode, want,
                                      names[primary], conflicts)
    merged.tags = ["combined"]
    merged.created_at = merged.updated_at = _now()
    warnings = merged.validate()
    _warmup_note(notes, merged, originals, names)

    return CombineReport(spec=merged, mode=mode, exit_mode=exit_mode,
                         threshold=want, sources=names, prefixes=prefixes,
                         notes=notes, conflicts=conflicts, shared=shared,
                         warnings=warnings)


def _with_directions(risk: Any, long_ok: bool, short_ok: bool) -> Any:
    """A copy of the primary's risk settings with the gates set by the merge.

    ``dataclasses.replace`` rather than mutation: the caller's own strategy
    object is passed in and must not be edited by combining it with another.
    """
    return replace(risk, allow_long=bool(long_ok), allow_short=bool(short_ok))


def _default_name(names: Sequence[str], mode: str) -> str:
    joined = " + ".join(names)
    if len(joined) > 70:
        joined = f"{names[0]} + {len(names) - 1} more"
    return f"{joined} ({mode})"


def _warmup_note(notes: list[str], merged: StrategySpec,
                 originals: Sequence[StrategySpec],
                 names: Sequence[str]) -> None:
    """Warn when combining lengthens the warm-up, because it costs signals.

    A strategy has one warm-up, the longest of its indicators', and the
    compiler blanks every signal before it.  So combining a 20-bar Donchian
    with a 200-bar filter under ``any`` does not give you the Donchian's early
    trades: the first 200 bars go quiet.  Measured on 193,942 bars of US30 15m
    this is the *only* way a merged rule differs from the set operation its
    mode names, and it is always in the safe direction -- fewer signals, never
    one the sources did not have.
    """
    try:
        after = merged.warmup_bars()
        before = [(n, s.warmup_bars()) for n, s in zip(names, originals)]
    except Exception:                       # pragma: no cover - defensive
        return
    shorter = [f"{n} needed {w}" for n, w in before if w < after]
    if not shorter:
        return
    notes.append(
        f"The combined strategy needs {after} bars of warm-up, the longest of "
        f"its parts ({', '.join(shorter)}). No rule can fire before then, so "
        f"signals the shorter strategies would have given in that first "
        f"stretch of data are lost.")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _explain(notes: list[str], originals: Sequence[StrategySpec],
             names: Sequence[str], mode: str, exit_mode: str, want: int,
             count: int, primary: int) -> None:
    """Say out loud everything about the merge that could surprise someone."""
    if mode == "majority" and want == count:
        notes.append(
            f"A majority of {count} is all {count} of them, so this entry "
            f"rule is the same as 'all'.")
    if mode == "any" or exit_mode == "any":
        notes.append(
            "This is still one strategy holding one position at a time, not "
            "the strategies run side by side, so its results will not be the "
            "sum of theirs.")
    for attribute, is_entry in _RULES:
        rule_mode = mode if is_entry else exit_mode
        missing = [names[i] for i, s in enumerate(originals)
                   if _rule_of(s, attribute) is None]
        if not missing or len(missing) == len(originals):
            continue
        word = attribute.replace("_", " ")
        if rule_mode == "all":
            notes.append(
                f"No {word} rule: {', '.join(missing)} "
                f"{'has' if len(missing) == 1 else 'have'} none, and 'all' "
                f"needs every strategy to signal.")
        elif rule_mode == "majority":
            notes.append(
                f"The {word} rule still needs {want} of {count} votes, but "
                f"{', '.join(missing)} can never cast one, so at most "
                f"{count - len(missing)} are available.")
    others = [n for i, n in enumerate(names) if i != primary]
    notes.append(
        f"Risk, exits, execution, session and costs are taken from "
        f"{names[primary]}; the settings in {', '.join(others)} are not used.")


def _check_tradeable(merged: StrategySpec, sources: Sequence[StrategySpec],
                     names: Sequence[str], mode: str, want: int) -> None:
    """Refuse a merge that produced a strategy with no way in."""
    if merged.entry_long is not None or merged.entry_short is not None:
        return
    long_have = [names[i] for i, s in enumerate(sources)
                 if _rule_of(s, "entry_long") is not None]
    short_have = [names[i] for i, s in enumerate(sources)
                  if _rule_of(s, "entry_short") is not None]
    if not long_have and not short_have:
        raise StrategyError(
            "None of these strategies has an entry rule that its own risk "
            "settings allow, so there is nothing to combine.")
    detail = []
    if long_have:
        detail.append(f"only {', '.join(long_have)} can enter long")
    if short_have:
        detail.append(f"only {', '.join(short_have)} can enter short")
    raise StrategyError(
        f"Combining with '{mode}' leaves no entry rule at all: "
        f"{'; '.join(detail)}. Use 'any', or combine strategies that trade "
        f"the same direction.")


def _description(names: Sequence[str], mode: str, exit_mode: str, want: int,
                 primary: str, conflicts: Sequence[str]) -> str:
    """Provenance, written into the strategy so it survives being saved."""
    entry = (f"at least {want} of {len(names)} agree" if mode == "majority"
             else describe_mode(mode))
    exit_text = (f"at least {want} of {len(names)} agree"
                 if exit_mode == "majority" else describe_mode(exit_mode))
    lines = [
        f"Combined from {len(names)} strategies: {', '.join(names)}.",
        f"Entries: {entry}. Exits: {exit_text}.",
        f"Risk, exits, execution, session and cost settings come from "
        f"{primary}.",
    ]
    if conflicts:
        lines.append(
            f"{len(conflicts)} setting"
            f"{'' if len(conflicts) == 1 else 's'} differed between the "
            f"sources and {primary}'s value was used:")
        lines.extend(f"  - {c}" for c in conflicts)
    return "\n".join(lines)
