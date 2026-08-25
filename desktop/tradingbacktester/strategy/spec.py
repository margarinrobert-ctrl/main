"""The strategy definition -- a declarative tree that serialises to JSON.

A strategy is data, not code.  It names some indicators, gives them parameters,
and builds boolean rules out of *operands* (a price series, an indicator output,
a constant, a strategy parameter, or an arithmetic combination of those).

The example from the specification::

    LONG ENTRY:  EMA20 crosses above EMA50 AND RSI > 50
    EXIT:        EMA20 crosses below EMA50
    Stop:        1.5 x ATR      Target: 3 x ATR

is expressed as::

    StrategySpec(
        name="EMA Cross + RSI",
        params=[ParamSpec("ema_fast", "EMA Fast", "int", 20), ...],
        indicators=[
            IndicatorSlot("emaFast", "EMA", {"period": "$ema_fast"}),
            IndicatorSlot("emaSlow", "EMA", {"period": "$ema_slow"}),
            IndicatorSlot("rsi", "RSI", {"period": "$rsi_period"}),
        ],
        entry_long=Group("AND", [
            Cross(Ind("emaFast"), "above", Ind("emaSlow")),
            Compare(Ind("rsi"), ">", Param("rsi_level")),
        ]),
        ...
    )

Nothing about the number of indicators, the nesting depth of the rules or the
mix of AND/OR is fixed, so a new strategy never requires new code.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..core.errors import ParameterError, StrategyError
from ..core.types import (ExecutionSettings, ExitSettings, RiskSettings,
                          SessionSettings, SignalExecution, IntrabarPriority,
                          SizingMode, CommissionMode, SlippageMode, SpreadMode,
                          CostModel)
from ..indicators.base import ParamSpec

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Operands
# --------------------------------------------------------------------------


@dataclass
class Operand:
    """Base class for anything that evaluates to a per-bar number."""

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Operand":
        if not isinstance(d, dict):
            raise StrategyError(f"An operand must be an object, got {type(d).__name__}.")
        kind = d.get("kind")
        if kind == "price":
            # The offset must survive the round trip: dropping it would turn
            # "the previous bar's close" into "this bar's close" the first time
            # a strategy was saved and reloaded, silently changing what it means.
            return PriceOperand(d.get("field", "close"), int(d.get("offset", 0)))
        if kind == "indicator":
            return IndicatorOperand(d["ref"], d.get("output", "value"), int(d.get("offset", 0)))
        if kind == "const":
            return ConstOperand(float(d["value"]))
        if kind == "param":
            return ParamOperand(d["name"])
        if kind == "expr":
            return ExprOperand(d.get("op", "+"), Operand.from_dict(d["left"]),
                               Operand.from_dict(d["right"]))
        raise StrategyError(f"'{kind}' is not an operand kind this application knows.")


@dataclass
class PriceOperand(Operand):
    """A price series: open/high/low/close/volume/hlc3/hl2/ohlc4."""

    field: str = "close"
    offset: int = 0
    """Bars back.  ``1`` means the previous bar's value."""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "price", "field": self.field, "offset": self.offset}

    def describe(self) -> str:
        base = self.field.capitalize()
        return f"{base}[{self.offset}]" if self.offset else base


@dataclass
class IndicatorOperand(Operand):
    """One output of one indicator slot declared on the strategy."""

    ref: str
    output: str = "value"
    offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "indicator", "ref": self.ref, "output": self.output,
                "offset": self.offset}

    def describe(self) -> str:
        base = self.ref if self.output in ("value", "") else f"{self.ref}.{self.output}"
        return f"{base}[{self.offset}]" if self.offset else base


@dataclass
class ConstOperand(Operand):
    """A fixed number."""

    value: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "const", "value": self.value}

    def describe(self) -> str:
        return f"{self.value:g}"


@dataclass
class ParamOperand(Operand):
    """A named strategy parameter, so a threshold can be optimised."""

    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "param", "name": self.name}

    def describe(self) -> str:
        return f"${self.name}"


@dataclass
class ExprOperand(Operand):
    """Arithmetic on two operands, e.g. ``EMA20 * 1.01`` or ``close - ATR``."""

    op: str
    left: Operand
    right: Operand

    OPS = ("+", "-", "*", "/")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "expr", "op": self.op, "left": self.left.to_dict(),
                "right": self.right.to_dict()}

    def describe(self) -> str:
        return f"({self.left.describe()} {self.op} {self.right.describe()})"


# Convenience constructors used by the builtin strategies and by tests.
def Price(field: str = "close", offset: int = 0) -> PriceOperand:
    return PriceOperand(field, offset)


def Ind(ref: str, output: str = "value", offset: int = 0) -> IndicatorOperand:
    return IndicatorOperand(ref, output, offset)


def Const(value: float) -> ConstOperand:
    return ConstOperand(float(value))


def Param(name: str) -> ParamOperand:
    return ParamOperand(name)


# --------------------------------------------------------------------------
# Conditions
# --------------------------------------------------------------------------

COMPARE_OPS = (">", ">=", "<", "<=", "==", "!=")
CROSS_DIRECTIONS = ("above", "below", "any")
STATE_OPS = ("rising", "falling", "positive", "negative", "increasing_for",
             "decreasing_for", "true", "false")


@dataclass
class Condition:
    """Base class for anything that evaluates to a per-bar boolean."""

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def referenced_indicators(self) -> set[str]:
        return set()

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "Condition | None":
        if d is None:
            return None
        if not isinstance(d, dict):
            raise StrategyError(f"A condition must be an object, got {type(d).__name__}.")
        kind = d.get("kind")
        if kind == "group":
            return ConditionGroup(
                d.get("op", "AND").upper(),
                [c for c in (Condition.from_dict(x) for x in d.get("children", [])) if c],
                bool(d.get("negate", False)),
            )
        if kind == "compare":
            return Compare(Operand.from_dict(d["left"]), d.get("op", ">"),
                           Operand.from_dict(d["right"]))
        if kind == "cross":
            return Cross(Operand.from_dict(d["left"]), d.get("direction", "above"),
                         Operand.from_dict(d["right"]))
        if kind == "state":
            return State(Operand.from_dict(d["left"]), d.get("op", "rising"),
                         int(d.get("bars", 1)))
        if kind == "session":
            return SessionWindow(d.get("start", "09:30"), d.get("end", "16:00"),
                                 d.get("timezone", "America/New_York"),
                                 tuple(d.get("weekdays", (0, 1, 2, 3, 4))))
        if kind == "always":
            return Always(bool(d.get("value", True)))
        raise StrategyError(f"'{kind}' is not a condition kind this application knows.")


@dataclass
class Compare(Condition):
    """``left <op> right`` evaluated bar by bar."""

    left: Operand
    op: str
    right: Operand

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "compare", "left": self.left.to_dict(), "op": self.op,
                "right": self.right.to_dict()}

    def describe(self) -> str:
        return f"{self.left.describe()} {self.op} {self.right.describe()}"

    def referenced_indicators(self) -> set[str]:
        return _refs(self.left) | _refs(self.right)


@dataclass
class Cross(Condition):
    """True on the bar where ``left`` crosses ``right``.

    A cross requires the relationship to have been strictly the other way on the
    previous bar, so it fires once per crossing rather than on every bar the
    inequality happens to hold.
    """

    left: Operand
    direction: str
    right: Operand

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "cross", "left": self.left.to_dict(),
                "direction": self.direction, "right": self.right.to_dict()}

    def describe(self) -> str:
        word = {"above": "crosses above", "below": "crosses below",
                "any": "crosses"}.get(self.direction, self.direction)
        return f"{self.left.describe()} {word} {self.right.describe()}"

    def referenced_indicators(self) -> set[str]:
        return _refs(self.left) | _refs(self.right)


@dataclass
class State(Condition):
    """A property of a single series: rising, falling, positive, negative."""

    left: Operand
    op: str = "rising"
    bars: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "state", "left": self.left.to_dict(), "op": self.op,
                "bars": self.bars}

    def describe(self) -> str:
        if self.op in ("increasing_for", "decreasing_for"):
            word = "rising" if self.op == "increasing_for" else "falling"
            return f"{self.left.describe()} {word} for {self.bars} bars"
        return f"{self.left.describe()} is {self.op}"

    def referenced_indicators(self) -> set[str]:
        return _refs(self.left)


@dataclass
class SessionWindow(Condition):
    """True only inside a time-of-day window on allowed weekdays."""

    start: str = "09:30"
    end: str = "16:00"
    timezone: str = "America/New_York"
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "session", "start": self.start, "end": self.end,
                "timezone": self.timezone, "weekdays": list(self.weekdays)}

    def describe(self) -> str:
        return f"time in {self.start}-{self.end} {self.timezone}"


@dataclass
class Always(Condition):
    """A constant.  ``Always(True)`` is useful as a placeholder entry rule."""

    value: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "always", "value": self.value}

    def describe(self) -> str:
        return "always" if self.value else "never"


@dataclass
class ConditionGroup(Condition):
    """``AND``/``OR`` over children, optionally negated."""

    op: str = "AND"
    children: list[Condition] = field(default_factory=list)
    negate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "group", "op": self.op,
                "children": [c.to_dict() for c in self.children],
                "negate": self.negate}

    def describe(self) -> str:
        if not self.children:
            return "never" if self.op == "AND" and self.negate else "(empty)"
        joiner = f" {self.op} "
        inner = joiner.join(
            c.describe() if not isinstance(c, ConditionGroup) else f"({c.describe()})"
            for c in self.children
        )
        return f"NOT ({inner})" if self.negate else inner

    def referenced_indicators(self) -> set[str]:
        out: set[str] = set()
        for c in self.children:
            out |= c.referenced_indicators()
        return out


def Group(op: str, children: Iterable[Condition], negate: bool = False) -> ConditionGroup:
    return ConditionGroup(op.upper(), list(children), negate)


def _refs(op: Operand) -> set[str]:
    if isinstance(op, IndicatorOperand):
        return {op.ref}
    if isinstance(op, ExprOperand):
        return _refs(op.left) | _refs(op.right)
    return set()


# --------------------------------------------------------------------------
# Indicator slots and the strategy itself
# --------------------------------------------------------------------------


@dataclass
class IndicatorSlot:
    """One indicator instance used by a strategy.

    Parameter values may be literals (``{"period": 20}``) or references to a
    strategy parameter (``{"period": "$ema_fast"}``), which is what makes a
    strategy optimisable without editing its rules.
    """

    ref: str
    """Name used by rules to refer to this slot, e.g. ``"emaFast"``."""
    indicator: str
    """Registry key, e.g. ``"EMA"``."""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "close"
    plot: bool = True
    panel: str = "auto"
    """``price``, ``auto`` (follow the indicator's ``overlay`` flag) or a
    sub-panel id such as ``"panel1"``."""
    color: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "indicator": self.indicator, "params": dict(self.params),
                "source": self.source, "plot": self.plot, "panel": self.panel,
                "color": self.color, "label": self.label}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "IndicatorSlot":
        return IndicatorSlot(
            ref=d["ref"], indicator=d["indicator"], params=dict(d.get("params", {})),
            source=d.get("source", "close"), plot=bool(d.get("plot", True)),
            panel=d.get("panel", "auto"), color=d.get("color", ""),
            label=d.get("label", ""),
        )

    def display_label(self) -> str:
        if self.label:
            return self.label
        nums = [str(v) for v in self.params.values() if not isinstance(v, str)]
        return f"{self.indicator} {' '.join(nums)}".strip()


@dataclass
class StrategySpec:
    """A complete, serialisable strategy."""

    name: str = "New Strategy"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    author: str = ""
    version: int = 1
    schema_version: int = SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)

    params: list[ParamSpec] = field(default_factory=list)
    indicators: list[IndicatorSlot] = field(default_factory=list)

    entry_long: Condition | None = None
    entry_short: Condition | None = None
    exit_long: Condition | None = None
    exit_short: Condition | None = None

    risk: RiskSettings = field(default_factory=RiskSettings)
    exits: ExitSettings = field(default_factory=ExitSettings)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    session: SessionSettings = field(default_factory=SessionSettings)
    costs: CostModel = field(default_factory=CostModel)

    # -- parameters ------------------------------------------------------

    def param_values(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Default parameter values with ``overrides`` applied and validated."""
        overrides = dict(overrides or {})
        out: dict[str, Any] = {}
        for p in self.params:
            raw = overrides.pop(p.name, p.default)
            try:
                out[p.name] = p.coerce(raw)
            except Exception as exc:
                raise ParameterError(str(exc)) from exc
        if overrides:
            raise ParameterError(
                f"This strategy has no parameter(s) called "
                f"{', '.join(sorted(overrides))}."
            )
        return out

    def param(self, name: str) -> ParamSpec:
        for p in self.params:
            if p.name == name:
                return p
        raise ParameterError(f"This strategy has no parameter called '{name}'.")

    def slot(self, ref: str) -> IndicatorSlot:
        for s in self.indicators:
            if s.ref == ref:
                return s
        raise StrategyError(f"This strategy has no indicator called '{ref}'.")

    # -- validation ------------------------------------------------------

    def validate(self) -> list[str]:
        """Check the strategy is internally consistent.

        Raises :class:`StrategyError` for anything that would stop the strategy
        running, and returns a list of non-fatal warnings.
        """
        from ..indicators.base import REGISTRY

        warnings: list[str] = []
        if not str(self.name).strip():
            raise StrategyError("A strategy needs a name.")

        seen: set[str] = set()
        for s in self.indicators:
            if not s.ref:
                raise StrategyError("Every indicator needs a reference name.")
            if s.ref in seen:
                raise StrategyError(f"Two indicators are both called '{s.ref}'.")
            seen.add(s.ref)
            d = REGISTRY.get(s.indicator)
            for key, val in s.params.items():
                if isinstance(val, str) and val.startswith("$"):
                    self.param(val[1:])          # raises if the parameter is missing
                else:
                    d.param_spec(key).coerce(val)

        pnames = [p.name for p in self.params]
        if len(pnames) != len(set(pnames)):
            raise StrategyError("Two strategy parameters share the same name.")

        used: set[str] = set()
        for cond in (self.entry_long, self.entry_short, self.exit_long, self.exit_short):
            if cond is not None:
                used |= cond.referenced_indicators()
        missing = used - seen
        if missing:
            raise StrategyError(
                f"The rules refer to indicator(s) that are not defined: "
                f"{', '.join(sorted(missing))}."
            )
        unused = seen - used
        if unused:
            warnings.append(
                f"Indicator(s) {', '.join(sorted(unused))} are calculated and plotted "
                f"but no rule uses them."
            )

        if self.entry_long is None and self.entry_short is None:
            raise StrategyError("A strategy needs at least one entry rule.")
        if self.entry_long is not None and not self.risk.allow_long:
            warnings.append("There is a long entry rule but long trading is disabled.")
        if self.entry_short is not None and not self.risk.allow_short:
            warnings.append("There is a short entry rule but short trading is disabled.")
        if self.entry_long is not None and self.exit_long is None and not (
                self.exits.stop_loss_enabled or self.exits.take_profit_enabled
                or self.exits.trailing_enabled or self.exits.max_bars_in_trade):
            warnings.append(
                "Long trades have no exit rule and no stop, target or time stop, "
                "so a position will be held until the data ends."
            )
        total_partial = sum(f for f, _ in self.exits.partial_exits)
        if total_partial > 1.0 + 1e-9:
            raise StrategyError(
                f"Partial exits add up to {total_partial:.0%} of the position, "
                f"which is more than the whole."
            )
        self.risk.validate()
        self.costs.validate()
        return warnings

    def warmup_bars(self, overrides: dict[str, Any] | None = None) -> int:
        """Bars needed before any rule can be evaluated."""
        from ..indicators.base import REGISTRY

        values = self.param_values(overrides)
        need = 1
        for s in self.indicators:
            d = REGISTRY.get(s.indicator)
            resolved = {}
            for k, v in s.params.items():
                resolved[k] = values[v[1:]] if isinstance(v, str) and v.startswith("$") else v
            need = max(need, d.warmup(d.coerce_params(resolved)))
        if self.exits.stop_loss_enabled or self.exits.take_profit_enabled or \
                self.exits.trailing_enabled:
            need = max(need, self.exits.atr_period)
        if self.risk.sizing_mode is SizingMode.VOLATILITY_TARGET:
            need = max(need, self.risk.volatility_atr_period)
        return int(need) + 1

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id, "name": self.name, "description": self.description,
            "author": self.author, "version": self.version,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "tags": list(self.tags),
            "params": [_param_to_dict(p) for p in self.params],
            "indicators": [s.to_dict() for s in self.indicators],
            "entry_long": self.entry_long.to_dict() if self.entry_long else None,
            "entry_short": self.entry_short.to_dict() if self.entry_short else None,
            "exit_long": self.exit_long.to_dict() if self.exit_long else None,
            "exit_short": self.exit_short.to_dict() if self.exit_short else None,
            "risk": _enum_dict(self.risk), "exits": _enum_dict(self.exits),
            "execution": _enum_dict(self.execution), "session": _enum_dict(self.session),
            "costs": _enum_dict(self.costs),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "StrategySpec":
        if not isinstance(d, dict):
            raise StrategyError("A strategy file must contain a JSON object.")
        ver = int(d.get("schema_version", 1))
        if ver > SCHEMA_VERSION:
            raise StrategyError(
                f"This strategy was saved by a newer version of the application "
                f"(format {ver}, this build understands {SCHEMA_VERSION})."
            )
        try:
            spec = StrategySpec(
                name=d.get("name", "Untitled"),
                id=d.get("id") or uuid.uuid4().hex[:12],
                description=d.get("description", ""), author=d.get("author", ""),
                version=int(d.get("version", 1)), schema_version=ver,
                created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
                tags=list(d.get("tags", [])),
                params=[_param_from_dict(p) for p in d.get("params", [])],
                indicators=[IndicatorSlot.from_dict(s) for s in d.get("indicators", [])],
                entry_long=Condition.from_dict(d.get("entry_long")),
                entry_short=Condition.from_dict(d.get("entry_short")),
                exit_long=Condition.from_dict(d.get("exit_long")),
                exit_short=Condition.from_dict(d.get("exit_short")),
                risk=_risk_from_dict(d.get("risk", {})),
                exits=_exits_from_dict(d.get("exits", {})),
                execution=_execution_from_dict(d.get("execution", {})),
                session=_session_from_dict(d.get("session", {})),
                costs=_costs_from_dict(d.get("costs", {})),
            )
        except StrategyError:
            raise
        except KeyError as exc:
            raise StrategyError(
                f"This strategy file is missing the field {exc}.", detail=repr(exc)
            ) from exc
        except Exception as exc:
            raise StrategyError(
                "This strategy file could not be read; it may be from a different "
                "application or damaged.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc
        return spec

    @staticmethod
    def from_json(text: str) -> "StrategySpec":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StrategyError(
                f"This is not a valid strategy file: {exc.msg} (line {exc.lineno}).",
                detail=str(exc),
            ) from exc
        return StrategySpec.from_dict(data)

    def copy(self, new_name: str | None = None) -> "StrategySpec":
        s = StrategySpec.from_dict(json.loads(self.to_json()))
        s.id = uuid.uuid4().hex[:12]
        if new_name:
            s.name = new_name
        return s

    def summary_lines(self) -> list[str]:
        """Human-readable rule summary shown in the strategy panel."""
        out: list[str] = []
        if self.entry_long:
            out.append(f"Long entry:  {self.entry_long.describe()}")
        if self.exit_long:
            out.append(f"Long exit:   {self.exit_long.describe()}")
        if self.entry_short:
            out.append(f"Short entry: {self.entry_short.describe()}")
        if self.exit_short:
            out.append(f"Short exit:  {self.exit_short.describe()}")
        e = self.exits
        if e.stop_loss_enabled:
            out.append(f"Stop loss:   {e.stop_loss_value:g} {e.stop_loss_mode}")
        if e.take_profit_enabled:
            out.append(f"Take profit: {e.take_profit_value:g} {e.take_profit_mode}")
        if e.trailing_enabled:
            out.append(f"Trailing:    {e.trailing_value:g} {e.trailing_mode}")
        if e.max_bars_in_trade:
            out.append(f"Time stop:   {e.max_bars_in_trade} bars")
        return out


# -- (de)serialisation helpers -------------------------------------------


def _param_to_dict(p: ParamSpec) -> dict[str, Any]:
    return {"name": p.name, "label": p.label, "kind": p.kind, "default": p.default,
            "minimum": p.minimum, "maximum": p.maximum, "step": p.step,
            "choices": list(p.choices), "help": p.help}


def _param_from_dict(d: dict[str, Any]) -> ParamSpec:
    return ParamSpec(name=d["name"], label=d.get("label", d["name"]),
                     kind=d.get("kind", "int"), default=d.get("default", 0),
                     minimum=d.get("minimum"), maximum=d.get("maximum"),
                     step=d.get("step", 1), choices=tuple(d.get("choices", ())),
                     help=d.get("help", ""))


def _enum_dict(obj: Any) -> dict[str, Any]:
    from dataclasses import asdict as _asdict
    from enum import Enum as _Enum

    def conv(v: Any) -> Any:
        if isinstance(v, _Enum):
            return v.value
        if isinstance(v, tuple):
            return [conv(x) for x in v]
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return {k: conv(v) for k, v in _asdict(obj).items()}


def _fill(cls, d: dict[str, Any], enums: dict[str, Any]):
    d = dict(d or {})
    for key, enum_cls in enums.items():
        if key in d and d[key] is not None:
            try:
                d[key] = enum_cls(d[key])
            except ValueError as exc:
                raise StrategyError(
                    f"'{d[key]}' is not a valid value for {key}.", detail=str(exc)
                ) from exc
    known = set(cls.__dataclass_fields__)
    return cls(**{k: v for k, v in d.items() if k in known})


def _risk_from_dict(d: dict[str, Any]) -> RiskSettings:
    return _fill(RiskSettings, d, {"sizing_mode": SizingMode})


def _exits_from_dict(d: dict[str, Any]) -> ExitSettings:
    d = dict(d or {})
    if "partial_exits" in d and d["partial_exits"] is not None:
        d["partial_exits"] = tuple(tuple(float(x) for x in p) for p in d["partial_exits"])
    return _fill(ExitSettings, d, {})


def _execution_from_dict(d: dict[str, Any]) -> ExecutionSettings:
    return _fill(ExecutionSettings, d,
                 {"signal_execution": SignalExecution, "intrabar_priority": IntrabarPriority})


def _session_from_dict(d: dict[str, Any]) -> SessionSettings:
    d = dict(d or {})
    if "weekdays" in d and d["weekdays"] is not None:
        d["weekdays"] = tuple(int(x) for x in d["weekdays"])
    return _fill(SessionSettings, d, {})


def _costs_from_dict(d: dict[str, Any]) -> CostModel:
    return _fill(CostModel, d, {"commission_mode": CommissionMode,
                                "slippage_mode": SlippageMode,
                                "spread_mode": SpreadMode})
