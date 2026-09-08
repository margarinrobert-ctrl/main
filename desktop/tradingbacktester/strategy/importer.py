"""Paste a strategy in, get a runnable one out -- or an honest refusal.

The rule this module is built around: **a strategy that cannot be fully
interpreted is reported, never approximated.**  An import that quietly drops a
condition, or reads an indented ``strategy.entry`` as if it were unconditional,
produces a backtest that runs, looks fine, and describes a strategy the user
did not write.  That is worse than refusing, because there is nothing on screen
to tell them.

So every line of the source ends up in exactly one of three buckets:

* **converted** -- it became part of the :class:`StrategySpec`.
* **ignored** -- it has no effect on what the strategy trades (``plot``,
  ``bgcolor``, a chart label).  Listed, so nothing is silently absent.
* **unsupported** -- it affects behaviour and could not be represented.  Listed
  with its line, its source, and why.

If anything lands in *unsupported*, the report says the conversion is partial
and names what is missing.  A partial spec is still produced and can still be
run, because seeing the part that did convert is useful -- but it is labelled
partial everywhere it appears, and :attr:`ImportReport.faithful` is False.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .pine_parse import (Node, PineSyntaxError, Statement, parse)
from .spec import (Compare, ConditionGroup, ConstOperand, Cross,
                   ExitSettings, ExprOperand, IndicatorOperand, IndicatorSlot,
                   PriceOperand, State, StrategySpec)

log = logging.getLogger(__name__)

#: What the detector can tell apart.
FORMATS = ("pine", "json", "mql", "easylanguage", "thinkscript", "csharp",
           "unknown")

#: Pine's price series, and what they are called here.
_PRICE_FIELDS = {
    "close": "close", "open": "open", "high": "high", "low": "low",
    "volume": "volume", "hl2": "hl2", "hlc3": "hlc3", "ohlc4": "ohlc4",
    "src": "close",
}

#: ``ta.*`` calls that map onto a registered indicator.  The tuple is
#: (registry key, positional parameter names in Pine's order, output).
#: Anything not in here is reported, not guessed at.
_INDICATORS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "ta.sma": ("SMA", ("period",), "value"),
    "ta.ema": ("EMA", ("period",), "value"),
    "ta.wma": ("WMA", ("period",), "value"),
    "ta.hma": ("HMA", ("period",), "value"),
    "ta.vwma": ("VWMA", ("period",), "value"),
    "ta.rma": ("RMA", ("period",), "value"),
    "ta.dema": ("DEMA", ("period",), "value"),
    "ta.tema": ("TEMA", ("period",), "value"),
    "ta.rsi": ("RSI", ("period",), "value"),
    "ta.atr": ("ATR", ("period",), "value"),
    "ta.cci": ("CCI", ("period",), "value"),
    "ta.mfi": ("MFI", ("period",), "value"),
    "ta.roc": ("ROC", ("period",), "value"),
    "ta.mom": ("MOM", ("period",), "value"),
    "ta.stdev": ("STDDEV", ("period",), "value"),
    "ta.highest": ("HIGHEST", ("period",), "value"),
    "ta.lowest": ("LOWEST", ("period",), "value"),
    "ta.wpr": ("WILLR", ("period",), "value"),
    "ta.linreg": ("LINREG", ("period",), "value"),
    "ta.obv": ("OBV", (), "value"),
    "ta.tr": ("TRUE_RANGE", (), "value"),
    "ta.vwap": ("VWAP", (), "value"),
}

#: Multi-output ``ta.*`` calls.  Pine returns a tuple; this app names outputs,
#: so ``[macdLine, signalLine, hist] = ta.macd(...)`` needs the tuple unpacked.
_MULTI: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "ta.macd": ("MACD", ("fast", "slow", "signal"),
                ("macd", "signal", "histogram")),
    "ta.bb": ("BBANDS", ("period", "deviation"), ("middle", "upper", "lower")),
    "ta.stoch": ("STOCH", ("k_period",), ("k",)),
    "ta.dmi": ("ADX", ("period", "adx_period"), ("plus_di", "minus_di", "adx")),
    "ta.supertrend": ("SUPERTREND", ("multiplier", "period"),
                      ("value", "direction")),
}

#: Calls that draw on the chart and change nothing about what is traded.
_COSMETIC = {
    "plot", "plotshape", "plotchar", "plotarrow", "plotcandle", "plotbar",
    "bgcolor", "barcolor", "fill", "hline", "line.new", "label.new",
    "box.new", "table.new", "table.cell", "alertcondition", "alert",
    "indicator", "study", "strategy.risk.allow_entry_in",
}

_INPUTS = {"input", "input.int", "input.float", "input.bool", "input.string",
           "input.source", "input.timeframe", "input.color", "input.session",
           "input.symbol", "input.price", "input.time"}

_PINE_HINTS = ("//@version=", "ta.", "strategy(", "indicator(", "study(",
               "plot(", "strategy.entry", "close[", "syminfo.")
_MQL_HINTS = ("#property", "OnTick()", "OnInit()", "iMA(", "OrderSend(",
              "MqlTick", "input int", "extern double")
_EL_HINTS = ("Inputs:", "Vars:", "Buy(", "SellShort(", "ExitLong",
             "Begin", "End;")
_TS_HINTS = ("declare lower", "declare upper", "def ", "plot ", "AddOrder(",
             "input ")
#: cTrader cBots and NinjaTrader/Quantower strategies are all C#.  None of
#: them can be imported, but naming the language beats "could not be
#: identified": it tells the reader the refusal is about the format and not
#: about something they typed wrong.
_CSHARP_HINTS = ("using cAlgo", "namespace cAlgo", ": Robot", "OnBar()",
                 "ExecuteMarketOrder(", "using NinjaTrader", "protected "
                 "override void On", "public class", "[Parameter(")


@dataclass
class Line:
    """One source line and what became of it."""

    line: int
    source: str
    outcome: str
    """converted | ignored | unsupported"""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "source": self.source,
                "outcome": self.outcome, "detail": self.detail}


@dataclass
class ImportReport:
    """What the importer made of the text, and what it could not."""

    detected: str = "unknown"
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    spec: StrategySpec | None = None
    lines: list[Line] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    named: tuple[Any, ...] = ()
    """Numbers that were turned into parameters on the way in.

    A pasted strategy is all literals -- ``ta.ema(close, 100)`` and ``adx <
    22`` -- so ``spec.params`` would be empty and the optimiser, walk-forward
    and the variant search would each have nothing to move.  Naming them costs
    nothing and changes nothing about what the strategy trades; see
    :mod:`tradingbacktester.strategy.parameterise`.
    """

    @property
    def unsupported(self) -> list[Line]:
        return [l for l in self.lines if l.outcome == "unsupported"]

    @property
    def converted(self) -> list[Line]:
        return [l for l in self.lines if l.outcome == "converted"]

    @property
    def ignored(self) -> list[Line]:
        return [l for l in self.lines if l.outcome == "ignored"]

    @property
    def faithful(self) -> bool:
        """True only when every behaviour-carrying line was represented.

        The one thing a caller must check before describing a backtest of this
        spec as a backtest of the pasted strategy.
        """
        return (self.spec is not None and not self.errors
                and not self.unsupported)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected, "confidence": round(self.confidence, 2),
            "evidence": list(self.evidence),
            "faithful": self.faithful,
            "spec": self.spec.to_dict() if self.spec is not None else None,
            "lines": [l.to_dict() for l in self.lines],
            "errors": list(self.errors), "warnings": list(self.warnings),
            "named": [p.name for p in self.named],
        }


# ---------------------------------------------------------------------------
# format detection
# ---------------------------------------------------------------------------

def detect_format(text: str) -> tuple[str, float, list[str]]:
    """Guess the language, with the evidence that decided it.

    Evidence is returned rather than a bare label so a wrong guess is arguable
    instead of mysterious.
    """
    stripped = text.strip()
    if not stripped:
        return "unknown", 0.0, ["the text is empty"]

    if stripped.startswith("{") and '"' in stripped:
        try:
            import json

            data = json.loads(stripped)
        except ValueError:
            pass
        else:
            if isinstance(data, dict) and ("indicators" in data or
                                           "entry_long" in data or
                                           "schema_version" in data):
                return "json", 1.0, ["it parses as this application's own "
                                     "strategy JSON"]

    def hits(needles: tuple[str, ...]) -> list[str]:
        return [n for n in needles if n in text]

    scores = {
        "pine": hits(_PINE_HINTS),
        "mql": hits(_MQL_HINTS),
        "easylanguage": hits(_EL_HINTS),
        "thinkscript": hits(_TS_HINTS),
        "csharp": hits(_CSHARP_HINTS),
    }
    best = max(scores, key=lambda k: len(scores[k]))
    found = scores[best]
    if not found:
        return "unknown", 0.0, ["nothing in the text identified a language"]
    if "//@version=" in text:
        version = re.search(r"//@version=(\d+)", text)
        return "pine", 1.0, [f"a Pine v{version.group(1) if version else '?'} "
                             f"version pragma"]
    confidence = min(1.0, len(found) / 3.0)
    return best, confidence, [f"found {', '.join(repr(f) for f in found[:4])}"]


# ---------------------------------------------------------------------------
# the Pine converter
# ---------------------------------------------------------------------------

class _Converter:
    """Turns parsed Pine statements into a StrategySpec, or explains why not."""

    def __init__(self, report: ImportReport) -> None:
        self.report = report
        self.spec = StrategySpec(name="Imported strategy")
        self.slots: dict[str, IndicatorSlot] = {}
        #: Pine variable name -> the Node it was assigned. Resolved lazily so a
        #: variable used before this pass reaches it still works.
        self.bindings: dict[str, Node] = {}
        self.tuple_bindings: dict[str, tuple[str, str]] = {}
        self._counter = 0
        self._resolving: set[str] = set()
        #: Bindings a rule successfully resolved through.  Only these were
        #: really converted; the rest are classified after the rules are in.
        self.used: set[str] = set()

    # -- indicator slots -------------------------------------------------

    def _ref(self, key: str) -> str:
        self._counter += 1
        return f"{key.lower()}{self._counter}"

    def _slot(self, key: str, params: dict[str, Any], source: str) -> str:
        """Add an indicator slot, reusing an identical one."""
        for ref, slot in self.slots.items():
            if (slot.indicator == key and slot.params == params
                    and slot.source == source):
                return ref
        ref = self._ref(key)
        self.slots[ref] = IndicatorSlot(ref=ref, indicator=key,
                                        params=dict(params), source=source)
        return ref

    # -- operands --------------------------------------------------------

    def _number(self, node: Node) -> float | None:
        if node.kind == "number":
            return float(node.value)
        if node.kind == "unary" and node.value == "-":
            inner = self._number(node.args[0])
            return None if inner is None else -inner
        if node.kind == "call" and str(node.value) in _INPUTS:
            for candidate in list(node.args) + list(node.keywords.values()):
                value = self._number(candidate)
                if value is not None:
                    return value
            return None
        if node.kind == "name" and str(node.value) in self.bindings:
            return self._number(self.bindings[str(node.value)])
        return None

    def _source_field(self, node: Node | None) -> str:
        if node is None:
            return "close"
        if node.kind == "name":
            return _PRICE_FIELDS.get(str(node.value), "close")
        if node.kind == "name" and str(node.value) in self.bindings:
            return self._source_field(self.bindings[str(node.value)])
        return "close"

    def operand(self, node: Node, offset: int = 0) -> Any:
        """One Pine expression as a spec operand, or raise Unconvertible."""
        if node.kind == "number":
            return ConstOperand(value=float(node.value))
        if node.kind == "bool":
            return ConstOperand(value=1.0 if node.value else 0.0)
        if node.kind == "index":
            back = self._number(node.args[1])
            if back is None:
                raise _Unconvertible(
                    f"`{node.describe()}` looks back a variable number of bars, "
                    f"which this format cannot express")
            return self.operand(node.args[0], offset + int(back))
        if node.kind == "unary" and node.value == "-":
            # No unary minus in the spec: 0 - x means the same thing.
            return ExprOperand(op="-", left=ConstOperand(value=0.0),
                               right=self.operand(node.args[0], offset))
        if node.kind == "unary" and node.value == "+":
            return self.operand(node.args[0], offset)
        if node.kind == "binary" and node.value in ("+", "-", "*", "/"):
            return ExprOperand(op=str(node.value),
                               left=self.operand(node.args[0], offset),
                               right=self.operand(node.args[1], offset))
        if node.kind == "name":
            name = str(node.value)
            if name in _PRICE_FIELDS:
                return PriceOperand(field=_PRICE_FIELDS[name], offset=offset)
            if name in self.tuple_bindings:
                ref, output = self.tuple_bindings[name]
                return IndicatorOperand(ref=ref, output=output, offset=offset)
            if name in self.bindings:
                if name in self._resolving:
                    raise _Unconvertible(
                        f"`{name}` is defined in terms of itself, which this "
                        f"format has no way to express")
                self._resolving.add(name)
                try:
                    resolved = self.operand(self.bindings[name], offset)
                finally:
                    self._resolving.discard(name)
                self.used.add(name)
                return resolved
            if name == "na":
                raise _Unconvertible("`na` is not a value this format has")
            raise _Unconvertible(f"`{name}` is not defined anywhere this "
                                 f"importer could see")
        if node.kind == "call":
            return self._call_operand(node, offset)
        raise _Unconvertible(f"`{node.describe()}` is not something this "
                             f"format can express")

    def _call_operand(self, node: Node, offset: int) -> Any:
        name = str(node.value)
        if name in _INPUTS:
            value = self._number(node)
            if value is None:
                raise _Unconvertible(f"`{node.describe()}` is an input whose "
                                     f"default could not be read")
            return ConstOperand(value=value)

        if name in _INDICATORS:
            key, parameters, output = _INDICATORS[name]
            args = list(node.args)
            source = "close"
            values: list[Node] = []
            if key in ("ATR", "TRUE_RANGE", "OBV", "VWAP", "MFI", "WILLR",
                       "CCI", "STOCH", "ADX"):
                # These read the whole bar, not one series, so Pine gives them
                # no source argument.
                values = args
            elif args:
                source = self._source_field(args[0])
                values = args[1:]
            params: dict[str, Any] = {}
            for index, parameter in enumerate(parameters):
                if index < len(values):
                    number = self._number(values[index])
                    if number is None:
                        raise _Unconvertible(
                            f"`{node.describe()}` has a {parameter} that is not "
                            f"a fixed number, and an indicator here needs a "
                            f"fixed one")
                    params[parameter] = int(number) if parameter.endswith(
                        ("period", "_period", "fast", "slow", "signal")) else number
            ref = self._slot(key, params, source)
            return IndicatorOperand(ref=ref, output=output, offset=offset)

        if name == "ta.change":
            inner = self.operand(node.args[0], offset) if node.args else None
            if inner is None:
                raise _Unconvertible("`ta.change` needs an argument")
            back = 1
            if len(node.args) > 1:
                number = self._number(node.args[1])
                if number is None:
                    raise _Unconvertible("`ta.change` needs a fixed lookback")
                back = int(number)
            return ExprOperand(op="-", left=inner,
                               right=self.operand(node.args[0], offset + back))

        raise _Unconvertible(
            f"`{name}(...)` has no equivalent here. The indicators this "
            f"application knows are listed in the Indicators panel; anything "
            f"else has to be rewritten in terms of them.")

    def bind_tuple(self, targets: tuple[str, ...], node: Node) -> str:
        """Bind ``[a, b, c] = ta.macd(...)`` to one slot's three outputs.

        Returns "" on success, or why it could not be done. Pine has no other
        way to write a multi-output indicator, so until this existed MACD,
        Bollinger Bands, DMI, Stochastic and SuperTrend could not be imported
        at all -- the map naming their outputs had been in place from the
        start, and nothing ever reached it.

        One slot is created, not three: the outputs of a MACD are three views
        of a single computation, and registering them separately would compute
        it three times and give the optimiser three names for one knob.
        """
        if node is None or node.kind != "call":
            return "the right-hand side is not an indicator call"
        name = str(node.value)
        if name not in _MULTI:
            return (f"`{name}(...)` does not return a tuple this application "
                    f"knows how to unpack")
        key, parameters, outputs = _MULTI[name]
        if len(targets) > len(outputs):
            return (f"`{name}(...)` returns {len(outputs)} values and "
                    f"{len(targets)} names were given")

        args = list(node.args)
        source = "close"
        if key in ("ADX", "STOCH", "SUPERTREND"):
            # Read the whole bar, so Pine gives them no source argument.
            values = args
        elif args:
            source = self._source_field(args[0])
            values = args[1:]
        else:
            values = []

        params: dict[str, Any] = {}
        for index, parameter in enumerate(parameters):
            if index >= len(values):
                continue
            number = self._number(values[index])
            if number is None:
                return (f"`{name}(...)` has a {parameter} that is not a fixed "
                        f"number, and an indicator here needs a fixed one")
            params[parameter] = (int(number)
                                 if parameter.endswith(
                                     ("period", "_period", "fast", "slow",
                                      "signal"))
                                 else number)
        ref = self._slot(key, params, source)
        for target, output in zip(targets, outputs):
            # Pine allows `_` for a value the script does not want.
            if target != "_":
                self.tuple_bindings[target] = (ref, output)
        return ""

    # -- conditions ------------------------------------------------------

    def condition(self, node: Node) -> Any:
        if node.kind == "binary" and node.value in ("and", "or"):
            return ConditionGroup(
                op="AND" if node.value == "and" else "OR",
                children=[self.condition(node.args[0]),
                          self.condition(node.args[1])])
        if node.kind == "unary" and node.value == "not":
            inner = self.condition(node.args[0])
            if isinstance(inner, ConditionGroup):
                return ConditionGroup(op=inner.op, children=list(inner.children),
                                      negate=not inner.negate)
            return ConditionGroup(op="AND", children=[inner], negate=True)
        if node.kind == "binary" and node.value in (">", "<", ">=", "<=",
                                                    "==", "!="):
            if node.value in ("==", "!="):
                self.report.warnings.append(
                    f"line {node.line}: `{node.value}` compares floating-point "
                    f"values within a tolerance here, where Pine compares them "
                    f"exactly. On continuous series the two rarely agree.")
            return Compare(left=self.operand(node.args[0]), op=str(node.value),
                           right=self.operand(node.args[1]))
        if node.kind == "call":
            return self._call_condition(node)
        if node.kind == "name":
            name = str(node.value)
            if name in self.bindings:
                if name in self._resolving:
                    raise _Unconvertible(f"`{name}` is defined in terms of "
                                         f"itself")
                self._resolving.add(name)
                try:
                    resolved = self.condition(self.bindings[name])
                finally:
                    self._resolving.discard(name)
                self.used.add(name)
                return resolved
            raise _Unconvertible(f"`{name}` is not defined anywhere this "
                                 f"importer could see")
        if node.kind == "bool":
            raise _Unconvertible(
                "a rule that is always true or always false is not a rule")
        # A bare numeric expression used as a condition: Pine treats non-zero
        # as true, and the spec has a state operator that means exactly that.
        return State(left=self.operand(node), op="true")

    def _call_condition(self, node: Node) -> Any:
        name = str(node.value)
        if name in ("ta.crossover", "ta.crossunder", "ta.cross"):
            if len(node.args) != 2:
                raise _Unconvertible(f"`{name}` needs two arguments")
            direction = {"ta.crossover": "above", "ta.crossunder": "below",
                         "ta.cross": "any"}[name]
            return Cross(left=self.operand(node.args[0]), direction=direction,
                         right=self.operand(node.args[1]))
        if name in ("ta.rising", "ta.falling"):
            bars = 1
            if len(node.args) > 1:
                number = self._number(node.args[1])
                if number is None:
                    raise _Unconvertible(f"`{name}` needs a fixed bar count")
                bars = max(1, int(number))
            return State(left=self.operand(node.args[0]),
                         op="increasing_for" if name == "ta.rising"
                            else "decreasing_for", bars=bars)
        # Anything else that returns a number: non-zero is true.
        return State(left=self.operand(node), op="true")


class _Unconvertible(Exception):
    """One expression could not be represented.  Carries the reason verbatim."""


# ---------------------------------------------------------------------------
# the entry point
# ---------------------------------------------------------------------------

def _source_line(text: str, number: int) -> str:
    lines = text.splitlines()
    if 1 <= number <= len(lines):
        return lines[number - 1].strip()
    return ""


def import_pine(text: str, report: ImportReport) -> ImportReport:
    """Convert Pine source, recording the fate of every line."""
    try:
        statements = parse(text)
    except PineSyntaxError as exc:
        report.errors.append(
            f"The text could not be read as Pine — {exc.message} at line "
            f"{exc.line}. Nothing was converted.")
        return report

    converter = _Converter(report)
    entries: list[tuple[int, Any, int]] = []      # (side, condition, line)
    exits: list[tuple[int, Any, int]] = []
    assignments: list[tuple[int, Any, str]] = []  # (row in report.lines, ...)

    # Pass one: bind every variable, so a rule may use a name defined below it.
    tuple_errors: dict[int, str] = {}
    for statement in statements:
        if statement.kind == "assignment" and statement.value is not None:
            converter.bindings[statement.target] = statement.value
        elif statement.kind == "tuple_assignment":
            problem = converter.bind_tuple(statement.targets, statement.value)
            if problem:
                tuple_errors[statement.line] = problem

    for statement in statements:
        source = _source_line(text, statement.line) or statement.source
        if statement.kind == "unsupported":
            report.lines.append(Line(statement.line, source, "unsupported",
                                     statement.reason))
            continue

        if statement.kind == "tuple_assignment":
            names = ", ".join(statement.targets)
            problem = tuple_errors.get(statement.line, "")
            if problem:
                report.lines.append(Line(statement.line, source, "unsupported",
                                         problem))
            else:
                report.lines.append(Line(
                    statement.line, source, "converted",
                    f"`{names}` are the outputs of one indicator"))
            continue

        if statement.kind == "assignment":
            # Classified after the rules are in: whether an assignment was
            # really converted depends on whether anything that trades could
            # resolve it.  Reserve its place in the table so the lines stay in
            # source order.
            assignments.append((len(report.lines), statement, source))
            report.lines.append(Line(statement.line, source, "converted", ""))
            continue

        name = statement.target
        base = name.split("(")[0]
        if base in _COSMETIC or base.split(".")[0] in ("plot", "label", "line",
                                                       "box", "table"):
            report.lines.append(Line(statement.line, source, "ignored",
                                     "draws on the chart; changes nothing "
                                     "about what is traded"))
            continue

        if base in ("strategy", "indicator", "study"):
            _read_header(statement, converter.spec, report, source)
            continue

        if base == "strategy.entry":
            _read_entry(statement, converter, entries, report, source)
            continue

        if base in ("strategy.close", "strategy.close_all"):
            _read_close(statement, converter, exits, report, source)
            continue

        if base == "strategy.exit":
            _read_exit(statement, converter, report, source)
            continue

        report.lines.append(Line(
            statement.line, source, "unsupported",
            f"`{base}(...)` is not something this importer knows how to "
            f"translate"))

    _apply(converter, entries, exits, report)
    _classify_assignments(converter, report, assignments,
                          _rule_roots(statements))
    report.spec = converter.spec
    return report


def _rule_roots(statements: list) -> set[str]:
    """Every Pine name a ``strategy.*`` call or its guard mentions.

    Syntactic on purpose.  ``_Converter.used`` only records bindings a rule
    resolved *successfully*, so a rule that failed on the very binding in
    question would leave no trace there -- which is precisely the case that
    has to be reported.  Reading the names out of the source cannot miss it.
    """
    roots: set[str] = set()
    for statement in statements:
        name = str(getattr(statement, "target", "") or "")
        if not name.split("(")[0].startswith("strategy."):
            continue
        roots |= _names_in(getattr(statement, "value", None))
        roots |= _names_in(getattr(statement, "guard", None))
    return roots


def _classify_assignments(converter: _Converter, report: ImportReport,
                          assignments: list, roots: set[str]) -> None:
    """Say what really became of each ``x = ...`` line.

    A binding used to be reported as converted the moment its name was bound,
    without anyone having tried to convert its value.  So
    ``higher = request.security(...)`` -- the one construct the placeholder
    text promises will be listed rather than guessed at -- was reported as
    *converted*, and a script that computed it but never traded on it was
    reported as converted **in full**.  The line table is the whole premise of
    this dialog; a row in it that says "converted" about a line that was not
    is the exact failure the module exists to prevent.

    Three outcomes, matching the module's three buckets:

    * a rule resolved through it -- **converted**, and now it is true.
    * its value cannot be expressed here and no rule uses it -- **ignored**,
      because it changes nothing about what is traded.  The reason is stated
      rather than hidden: a reader looking for their higher-timeframe filter
      needs to find out here that it is not in the strategy.
    * its value cannot be expressed here and a rule does use it --
      **unsupported**.  The rule's own line is already unsupported for the
      same reason, and it stays that way; this makes the cause visible where
      the cause is written.
    """
    for row, statement, source in assignments:
        name = str(statement.target)
        line = statement.line
        if name in converter.used:
            report.lines[row] = Line(line, source, "converted",
                                     f"`{name}` was used by a rule")
            continue
        detail = _why_not(converter, statement)
        if detail is None:
            report.lines[row] = Line(
                line, source, "converted",
                f"`{name}` was translated, but no rule uses it")
            continue
        depends = _depends_on(converter, name, roots)
        if depends:
            report.lines[row] = Line(
                line, source, "unsupported",
                f"{detail} \u2014 and what this strategy trades depends on it "
                f"through {', '.join(sorted(depends))}")
        else:
            report.lines[row] = Line(
                line, source, "ignored",
                f"{detail}; no rule uses it, so nothing that is traded "
                f"depends on it")


def _why_not(converter: _Converter, statement: Statement) -> str | None:
    """``None`` if the value converts, else why it does not.

    The attempt is made on a copy of the slot table so a probe cannot leave an
    indicator behind in the spec: this runs after the rules are assembled, and
    a slot added here would be one nothing plots and nothing uses.
    """
    node = statement.value
    if node is None:
        return "there is nothing on the right-hand side of this assignment"
    slots = dict(converter.slots)
    counter = converter._counter
    used = set(converter.used)
    try:
        converter.operand(node)
        return None
    except _Unconvertible:
        # Not an operand.  It may still be a boolean expression -- `longCond =
        # ta.crossover(a, b)` is not a value here but is a perfectly good
        # condition -- so try that before calling it untranslatable.
        pass
    except Exception:                       # pragma: no cover - defensive
        return "this could not be translated"
    finally:
        converter.slots = slots
        converter._counter = counter
        converter.used = used
    try:
        converter.condition(node)
        return None
    except _Unconvertible as exc:
        return str(exc)
    except Exception:                       # pragma: no cover - defensive
        return "this could not be translated"
    finally:
        converter.slots = slots
        converter._counter = counter
        converter.used = used


def _depends_on(converter: _Converter, name: str,
                roots: set[str]) -> set[str]:
    """Which rule roots reach ``name``, directly or through other bindings."""
    direct = {target: _names_in(node)
              for target, node in converter.bindings.items()}
    out: set[str] = set()
    for candidate in roots:
        if candidate == name:
            out.add(candidate)
            continue
        seen: set[str] = set()
        stack = [candidate]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for referenced in direct.get(current, ()):
                if referenced == name:
                    out.add(candidate)
                stack.append(referenced)
    return out


def _names_in(node: Node | None) -> set[str]:
    if node is None:
        return set()
    out: set[str] = set()
    if node.kind == "name":
        out.add(str(node.value))
    for child in list(node.args) + list(node.keywords.values()):
        out |= _names_in(child)
    return out


def _read_header(statement: Statement, spec: StrategySpec,
                 report: ImportReport, source: str) -> None:
    node = statement.value
    if node is not None and node.args and node.args[0].kind == "string":
        spec.name = str(node.args[0].value)[:80] or spec.name
    keywords = node.keywords if node is not None else {}
    noted: list[str] = []
    for key in ("pyramiding", "initial_capital", "default_qty_type",
                "default_qty_value", "commission_type", "commission_value",
                "slippage", "margin_long", "margin_short", "calc_on_every_tick",
                "process_orders_on_close"):
        if key in keywords:
            noted.append(f"{key}={keywords[key].describe()}")
    if noted:
        report.warnings.append(
            f"line {statement.line}: the strategy() call sets "
            f"{', '.join(noted)}. Position sizing and costs are set in this "
            f"application's own Risk and Costs panels and were NOT taken from "
            f"here, so check them before comparing results.")
    report.lines.append(Line(statement.line, source, "ignored",
                             "the declaration; its title was used as the name"))


def _read_entry(statement: Statement, converter: _Converter,
                entries: list, report: ImportReport, source: str) -> None:
    node = statement.value
    side = 0
    for argument in list(node.args) + list(node.keywords.values()):
        if argument.kind == "name":
            if str(argument.value) == "strategy.long":
                side = 1
            elif str(argument.value) == "strategy.short":
                side = -1
        if argument.kind == "bool":
            side = 1 if argument.value else -1
    if side == 0:
        report.lines.append(Line(
            statement.line, source, "unsupported",
            "which direction this enters could not be determined"))
        return

    condition_node = node.keywords.get("when") or statement.guard
    if condition_node is None:
        report.lines.append(Line(
            statement.line, source, "unsupported",
            "this entry has no condition — neither a `when=` nor an enclosing "
            "`if` — so it would fire on every bar. Refused rather than "
            "imported as an always-on rule."))
        return
    if statement.guard is not None and "when" in node.keywords:
        condition_node = Node("binary", statement.line, "and",
                              [statement.guard, node.keywords["when"]])
    try:
        condition = converter.condition(condition_node)
    except _Unconvertible as exc:
        report.lines.append(Line(statement.line, source, "unsupported",
                                 f"its condition could not be translated: {exc}"))
        return
    entries.append((side, condition, statement.line))
    report.lines.append(Line(
        statement.line, source, "converted",
        f"{'long' if side > 0 else 'short'} entry"))


def _read_close(statement: Statement, converter: _Converter, exits: list,
                report: ImportReport, source: str) -> None:
    node = statement.value
    condition_node = node.keywords.get("when") or statement.guard
    if condition_node is None:
        report.lines.append(Line(
            statement.line, source, "unsupported",
            "this exit has no condition, so it would fire on every bar"))
        return
    try:
        condition = converter.condition(condition_node)
    except _Unconvertible as exc:
        report.lines.append(Line(statement.line, source, "unsupported",
                                 f"its condition could not be translated: {exc}"))
        return
    exits.append((0, condition, statement.line))
    report.lines.append(Line(statement.line, source, "converted",
                             "exit rule"))


def _read_exit(statement: Statement, converter: _Converter,
               report: ImportReport, source: str) -> None:
    """`strategy.exit` carries the stop and the target."""
    node = statement.value
    keywords = node.keywords
    spec = converter.spec
    handled: list[str] = []
    refused: list[str] = []

    if "stop" in keywords or "stop_price" in keywords:
        refused.append(
            "a stop at an absolute price (`stop=`); this application places "
            "stops as a multiple of ATR or a percentage, not at a price "
            "computed on the entry bar")
    if "limit" in keywords or "limit_price" in keywords:
        refused.append(
            "a target at an absolute price (`limit=`); same reason as the stop")
    for key, mode, attribute in (("loss", "points", "stop_loss"),
                                 ("profit", "points", "take_profit")):
        if key in keywords:
            value = converter._number(keywords[key])
            if value is None:
                refused.append(f"`{key}=` is not a fixed number")
                continue
            if attribute == "stop_loss":
                spec.exits.stop_loss_enabled = True
                spec.exits.stop_loss_mode = "points"
                spec.exits.stop_loss_value = float(value)
            else:
                spec.exits.take_profit_enabled = True
                spec.exits.take_profit_mode = "points"
                spec.exits.take_profit_value = float(value)
            handled.append(f"{key}={value:g} points")
    for key in ("trail_points", "trail_price", "trail_offset"):
        if key in keywords:
            refused.append(f"`{key}=` — trailing stops are configured in the "
                           f"Exits panel, not imported")

    if refused and not handled:
        report.lines.append(Line(statement.line, source, "unsupported",
                                 "; ".join(refused)))
        return
    detail = ", ".join(handled) if handled else "nothing usable"
    if refused:
        report.lines.append(Line(
            statement.line, source, "unsupported",
            f"took {detail}, but could not take: {'; '.join(refused)}"))
        return
    report.lines.append(Line(statement.line, source, "converted", detail))


def _apply(converter: _Converter, entries: list, exits: list,
           report: ImportReport) -> None:
    """Fold the collected rules into the spec, or say why there are none."""
    spec = converter.spec
    spec.indicators = list(converter.slots.values())

    def merge(items: list, side: int) -> Any:
        matching = [c for s, c, _ in items if s == side]
        if not matching:
            return None
        if len(matching) == 1:
            return matching[0]
        # Several entries in the same direction: any of them opens a position.
        return ConditionGroup(op="OR", children=matching)

    spec.entry_long = merge(entries, 1)
    spec.entry_short = merge(entries, -1)
    combined_exit = merge(exits, 0)
    if combined_exit is not None:
        if spec.entry_long is not None:
            spec.exit_long = combined_exit
        if spec.entry_short is not None:
            spec.exit_short = combined_exit

    if spec.entry_long is None and spec.entry_short is None:
        report.errors.append(
            "No entry rule could be translated, so there is no strategy to "
            "run. The lines below say what stopped each one.")


def import_strategy(text: str, *, name_numbers: bool = True) -> ImportReport:
    """Detect, parse and convert a pasted strategy.

    Always returns a report.  ``report.faithful`` is the flag that matters: it
    is True only when every behaviour-carrying line was represented, and a
    caller must not describe a backtest of ``report.spec`` as a backtest of the
    pasted strategy unless it is.

    ``name_numbers`` promotes the strategy's hard-coded numbers to named
    parameters as the last step.  It is on by default because a strategy
    arriving without any is the reason three of this application's features --
    the optimiser, walk-forward and the variant search -- would refuse to open
    on it.  The promotion is a change of shape only, and
    :func:`~tradingbacktester.strategy.parameterise.extract_parameters` is
    tested trade-for-trade to keep it that way; pass False for the literal
    conversion, which is what the round-trip tests want.
    """
    report = _import_strategy(text)
    if name_numbers and report.spec is not None:
        from .parameterise import extract_parameters

        try:
            extraction = extract_parameters(report.spec)
        except Exception:                     # noqa: BLE001
            log.exception("Naming the numbers of an imported strategy failed")
            return report
        if extraction.changed:
            report.spec = extraction.spec
            report.named = extraction.added
    return report


def _import_strategy(text: str) -> ImportReport:
    """The conversion itself, before anything is named."""
    report = ImportReport()
    report.detected, report.confidence, report.evidence = detect_format(text)

    if report.detected == "json":
        try:
            import json

            report.spec = StrategySpec.from_dict(json.loads(text))
            report.lines.append(Line(1, "", "converted",
                                     "this application's own strategy format, "
                                     "loaded unchanged"))
        except Exception as exc:              # noqa: BLE001
            report.errors.append(f"The JSON could not be loaded as a strategy: "
                                 f"{exc}")
        return report

    if report.detected == "pine":
        return import_pine(text, report)

    known = {"mql": "MQL4/MQL5", "easylanguage": "EasyLanguage",
             "thinkscript": "thinkScript",
             "csharp": "C# (cTrader, NinjaTrader or Quantower)"}
    if report.detected in known:
        report.errors.append(
            f"This looks like {known[report.detected]} ({report.evidence[0]}). "
            f"Only Pine Script and this application's own strategy JSON can be "
            f"imported. Nothing was converted — the alternative would be a "
            f"guess at what the code means, and a wrong guess produces a "
            f"backtest of a strategy you did not write.")
        return report

    report.errors.append(
        "The language could not be identified, so nothing was converted. "
        "Pine Script and this application's own exported strategy JSON are the "
        "formats that can be imported.")
    return report
