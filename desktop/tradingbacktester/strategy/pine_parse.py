"""A tokeniser and expression parser for the subset of Pine this app can run.

Why a parser and not a pile of regular expressions: a regex that matches
``ta.ema(close, 20)`` also matches it inside a comment, inside a string, and
inside ``ta.ema(ta.ema(close, 20), 5)`` -- and it silently gets the last one
wrong.  Getting someone's strategy subtly wrong is worse than refusing it,
because a wrong import produces a backtest that looks fine and describes a
strategy they did not write.  So this reads the text properly and reports what
it could not read, with the line it gave up on.

The grammar covered here is deliberately small.  It is the part of Pine that
maps onto :mod:`tradingbacktester.strategy.spec` without inventing semantics:

    assignment     := IDENT ('='|':=') expression
    expression     := or_expr
    or_expr        := and_expr ('or' and_expr)*
    and_expr       := not_expr ('and' not_expr)*
    not_expr       := 'not' not_expr | comparison
    comparison     := additive (('>'|'<'|'>='|'<='|'=='|'!=') additive)?
    additive       := multiplicative (('+'|'-') multiplicative)*
    multiplicative := unary (('*'|'/'|'%') unary)*
    unary          := ('-'|'+') unary | postfix
    postfix        := primary ('[' expression ']')*
    primary        := NUMBER | STRING | 'true' | 'false' | IDENT
                    | IDENT '(' arguments ')' | '(' expression ')'

Everything Pine has that is not in that grammar -- ``var``, ``if``/``for``,
user functions, ``request.security``, arrays, matrices, the ternary ``?:``,
labels and lines -- is recognised well enough to be REPORTED as unsupported at
its own line number, which is the whole point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Token kinds.  Newlines are significant: Pine is line-oriented, and a
#: statement ends at one unless a bracket is still open.
NUMBER, STRING, IDENT, OP, NEWLINE, END = (
    "number", "string", "ident", "op", "newline", "end")

_KEYWORDS = {"and", "or", "not", "true", "false", "if", "else", "for", "while",
             "var", "varip", "switch", "type", "import", "export", "method"}

#: Pine type names that may sit between `var` and the variable name.
_TYPES = {"float", "int", "bool", "string", "color", "line", "label", "box",
          "table", "array", "matrix", "map", "simple", "series", "const"}

#: Longest first, so ``>=`` is not read as ``>`` then ``=``.
_OPERATORS = (":=", "==", "!=", ">=", "<=", "=>", "?", ":", ">", "<", "=",
              "+", "-", "*", "/", "%", "(", ")", "[", "]", ",", ".")

_NUMBER_RE = re.compile(r"\d+\.\d*|\.\d+|\d+")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


class PineSyntaxError(Exception):
    """Raised when the text cannot be tokenised or parsed at all."""

    def __init__(self, message: str, line: int, column: int = 0) -> None:
        super().__init__(f"line {line}: {message}")
        self.message = message
        self.line = line
        self.column = column


@dataclass
class Token:
    kind: str
    value: str
    line: int
    column: int

    def is_op(self, *values: str) -> bool:
        return self.kind == OP and self.value in values

    def is_word(self, *values: str) -> bool:
        return self.kind == IDENT and self.value in values


def tokenize(text: str) -> list[Token]:
    """Text to tokens.  Comments and line continuations disappear here.

    Pine comments run from ``//`` to end of line, but ``//`` inside a string is
    not a comment -- which is exactly the case a regex-based scraper gets wrong
    and the reason this walks the text one character at a time.
    """
    tokens: list[Token] = []
    line = 1
    column = 1
    i = 0
    n = len(text)
    depth = 0                       # open (, [ -- a newline inside is not a break

    while i < n:
        ch = text[i]

        if ch == "\n":
            if depth == 0:
                tokens.append(Token(NEWLINE, "\n", line, column))
            line += 1
            column = 1
            i += 1
            continue

        if ch in " \t\r":
            i += 1
            column += 1
            continue

        # A comment to end of line.
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue

        if ch in "\"'":
            quote = ch
            start_line, start_col = line, column
            i += 1
            column += 1
            buffer: list[str] = []
            while i < n and text[i] != quote:
                if text[i] == "\\" and i + 1 < n:
                    buffer.append(text[i + 1])
                    i += 2
                    column += 2
                    continue
                if text[i] == "\n":
                    raise PineSyntaxError("a string is not closed before the "
                                          "end of the line", start_line,
                                          start_col)
                buffer.append(text[i])
                i += 1
                column += 1
            if i >= n:
                raise PineSyntaxError("a string is never closed", start_line,
                                      start_col)
            i += 1
            column += 1
            tokens.append(Token(STRING, "".join(buffer), start_line, start_col))
            continue

        match = _NUMBER_RE.match(text, i)
        if match and ch.isdigit() or (ch == "." and match
                                      and match.group().startswith(".")):
            tokens.append(Token(NUMBER, match.group(), line, column))
            column += len(match.group())
            i = match.end()
            continue

        match = _IDENT_RE.match(text, i)
        if match:
            tokens.append(Token(IDENT, match.group(), line, column))
            column += len(match.group())
            i = match.end()
            continue

        for operator in _OPERATORS:
            if text.startswith(operator, i):
                if operator in "([":
                    depth += 1
                elif operator in ")]":
                    depth = max(0, depth - 1)
                tokens.append(Token(OP, operator, line, column))
                i += len(operator)
                column += len(operator)
                break
        else:
            raise PineSyntaxError(f"unexpected character {ch!r}", line, column)

    tokens.append(Token(END, "", line, column))
    return tokens


# ---------------------------------------------------------------------------
# the expression tree
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """One node of a parsed expression, with the line it came from."""

    kind: str
    """One of: number, string, bool, name, call, binary, unary, index, ternary."""
    line: int = 0
    value: Any = None
    """number: float. string: str. bool: bool. name: dotted name. binary/unary:
    the operator."""
    args: list["Node"] = field(default_factory=list)
    keywords: dict[str, "Node"] = field(default_factory=dict)

    def describe(self) -> str:
        """The node as something close to the source, for an error message."""
        if self.kind in ("number", "string", "bool"):
            return str(self.value)
        if self.kind == "name":
            return str(self.value)
        if self.kind == "call":
            bits = [a.describe() for a in self.args]
            bits += [f"{k}={v.describe()}" for k, v in self.keywords.items()]
            return f"{self.value}({', '.join(bits)})"
        if self.kind == "binary":
            return f"({self.args[0].describe()} {self.value} {self.args[1].describe()})"
        if self.kind == "unary":
            return f"{self.value}{self.args[0].describe()}"
        if self.kind == "index":
            return f"{self.args[0].describe()}[{self.args[1].describe()}]"
        if self.kind == "ternary":
            return (f"({self.args[0].describe()} ? {self.args[1].describe()} "
                    f": {self.args[2].describe()})")
        return self.kind


@dataclass
class Statement:
    """One line the parser understood, and what it sits under.

    ``guard`` is the ``if`` condition an indented statement belongs to, already
    negated for an ``else`` branch.  It matters more than it looks: the most
    common shape in all of Pine is

        if longCondition
            strategy.entry("Long", strategy.long)

    and an importer that reports the ``if`` as unsupported and then reads the
    indented ``strategy.entry`` as a top-level line has just produced a
    strategy that enters on EVERY bar.  It would run, it would backtest, and it
    would describe a strategy nobody wrote.  So the guard travels with the
    statement, and anything whose guard could not be determined is refused
    rather than treated as unconditional.
    """

    kind: str
    """assignment | call | unsupported | tuple_assignment"""
    line: int
    target: str = ""
    value: Node | None = None
    targets: tuple[str, ...] = ()
    """Names bound by a tuple assignment, in Pine's own order.

    ``[macdLine, signalLine, hist] = ta.macd(...)`` is the only way to write a
    multi-output indicator in Pine, and it is how MACD, Bollinger Bands, DMI,
    Stochastic and SuperTrend all appear in real scripts. The importer has
    mapped their outputs since it was written; the parser rejected the line
    before the map was ever consulted, so every one of them was unreachable.
    """
    reason: str = ""
    source: str = ""
    guard: Node | None = None
    indent: int = 0


def _tuple_targets_doc() -> None:                    # pragma: no cover - doc
    """See ``Parser._tuple_targets``; kept here so the grammar reads in order."""


def _current_guard(stack: list) -> Node | None:
    """The guard of the innermost open block, or None at top level."""
    return stack[-1][1] if stack else None


def _combine(outer: Node | None, inner: Node) -> Node:
    """`inner`, ANDed under `outer` when there is one -- nested ifs."""
    if outer is None:
        return inner
    return Node("binary", inner.line, "and", [outer, inner])


class Parser:
    """Recursive descent over the token stream."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # -- token helpers ---------------------------------------------------

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        token = self.tokens[self.pos]
        if token.kind != END:
            self.pos += 1
        return token

    def accept_op(self, *values: str) -> Token | None:
        if self.current.is_op(*values):
            return self.advance()
        return None

    def expect_op(self, value: str) -> Token:
        token = self.accept_op(value)
        if token is None:
            raise PineSyntaxError(
                f"expected {value!r} but found {self.current.value!r}",
                self.current.line, self.current.column)
        return token

    def skip_newlines(self) -> None:
        while self.current.kind == NEWLINE:
            self.advance()

    # -- expressions -----------------------------------------------------

    def expression(self) -> Node:
        return self.ternary()

    def ternary(self) -> Node:
        condition = self.or_expr()
        if self.accept_op("?"):
            true_branch = self.expression()
            self.expect_op(":")
            false_branch = self.expression()
            return Node("ternary", condition.line,
                        args=[condition, true_branch, false_branch])
        return condition

    def or_expr(self) -> Node:
        left = self.and_expr()
        while self.current.is_word("or"):
            line = self.advance().line
            left = Node("binary", line, "or", [left, self.and_expr()])
        return left

    def and_expr(self) -> Node:
        left = self.not_expr()
        while self.current.is_word("and"):
            line = self.advance().line
            left = Node("binary", line, "and", [left, self.not_expr()])
        return left

    def not_expr(self) -> Node:
        if self.current.is_word("not"):
            line = self.advance().line
            return Node("unary", line, "not", [self.not_expr()])
        return self.comparison()

    def comparison(self) -> Node:
        left = self.additive()
        if self.current.is_op(">", "<", ">=", "<=", "==", "!="):
            token = self.advance()
            return Node("binary", token.line, token.value,
                        [left, self.additive()])
        return left

    def additive(self) -> Node:
        left = self.multiplicative()
        while self.current.is_op("+", "-"):
            token = self.advance()
            left = Node("binary", token.line, token.value,
                        [left, self.multiplicative()])
        return left

    def multiplicative(self) -> Node:
        left = self.unary()
        while self.current.is_op("*", "/", "%"):
            token = self.advance()
            left = Node("binary", token.line, token.value, [left, self.unary()])
        return left

    def unary(self) -> Node:
        if self.current.is_op("-", "+"):
            token = self.advance()
            return Node("unary", token.line, token.value, [self.unary()])
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while self.current.is_op("["):
            line = self.advance().line
            index = self.expression()
            self.expect_op("]")
            node = Node("index", line, None, [node, index])
        return node

    def _tuple_targets(self) -> tuple[str, ...] | None:
        """``[a, b, c]`` at the head of a line, or ``None`` if it is not that.

        Returns None rather than raising for anything that is not a plain list
        of identifiers -- ``[1]`` is an index expression and ``[a[0], b]`` is
        not a destructuring target -- so the caller can rewind and try the
        other productions instead of failing the whole line.
        """
        if not self.current.is_op("["):
            return None
        self.advance()
        names: list[str] = []
        while True:
            if self.current.kind != IDENT:
                return None
            names.append(self.advance().value)
            if self.current.is_op(","):
                self.advance()
                continue
            break
        if not self.current.is_op("]"):
            return None
        self.advance()
        return tuple(names)

    def dotted_name(self) -> str:
        parts = [self.advance().value]
        while self.current.is_op(".") and self.tokens[self.pos + 1].kind == IDENT:
            self.advance()
            parts.append(self.advance().value)
        return ".".join(parts)

    def primary(self) -> Node:
        token = self.current
        if token.kind == NUMBER:
            self.advance()
            return Node("number", token.line, float(token.value))
        if token.kind == STRING:
            self.advance()
            return Node("string", token.line, token.value)
        if token.is_word("true", "false"):
            self.advance()
            return Node("bool", token.line, token.value == "true")
        if token.is_op("("):
            self.advance()
            inner = self.expression()
            self.expect_op(")")
            return inner
        if token.kind == IDENT:
            line = token.line
            name = self.dotted_name()
            if self.current.is_op("("):
                self.advance()
                args, keywords = self.arguments()
                return Node("call", line, name, args, keywords)
            return Node("name", line, name)
        raise PineSyntaxError(f"unexpected {token.value!r}", token.line,
                              token.column)

    def arguments(self) -> tuple[list[Node], dict[str, Node]]:
        args: list[Node] = []
        keywords: dict[str, Node] = {}
        self.skip_newlines()
        if self.accept_op(")"):
            return args, keywords
        while True:
            self.skip_newlines()
            # A keyword argument: IDENT '=' expression, but not '=='.
            if (self.current.kind == IDENT
                    and self.tokens[self.pos + 1].is_op("=")):
                name = self.advance().value
                self.advance()
                keywords[name] = self.expression()
            else:
                args.append(self.expression())
            self.skip_newlines()
            if self.accept_op(","):
                continue
            self.expect_op(")")
            return args, keywords

    # -- statements ------------------------------------------------------

    def statements(self) -> list[Statement]:
        """Every line, with the `if` condition each one sits under.

        Pine blocks are indentation-delimited, so a body is every following
        line indented further than the `if` that opened it.
        """
        out: list[Statement] = []
        # (indent of the `if`, guard for its body, guard for its else)
        stack: list[tuple[int, Node | None, Node | None]] = []

        while self.current.kind != END:
            self.skip_newlines()
            if self.current.kind == END:
                break
            indent = self.current.column

            # An `else` closes its `if` and reopens at the SAME indent, so the
            # entry it belongs to must survive the pop that any other line at
            # that indent would trigger -- otherwise the else branch loses the
            # negation it exists to carry, and its body reads as unguarded.
            closing_else = self.current.is_word("else")
            carried: tuple[int, Any, Any] | None = None
            while stack and indent <= stack[-1][0]:
                popped = stack.pop()
                if closing_else and popped[0] == indent and carried is None:
                    carried = popped

            if self.current.is_word("if"):
                if_indent = indent
                self.advance()
                try:
                    condition = self.expression()
                except PineSyntaxError as exc:
                    self._skip_line()
                    out.append(Statement(
                        "unsupported", self.current.line, indent=if_indent,
                        reason=f"the `if` condition could not be parsed: "
                               f"{exc.message}. Everything inside it is "
                               f"refused too, because reading it without its "
                               f"condition would change what the strategy does"))
                    stack.append((if_indent, None, None))
                    continue
                guard = _combine(_current_guard(stack), condition)
                negated = _combine(_current_guard(stack),
                                   Node("unary", condition.line, "not",
                                        [condition]))
                stack.append((if_indent, guard, negated))
                continue

            if self.current.is_word("else"):
                else_indent = indent
                self.advance()
                # `else if cond` chains: treat the tail as a fresh if under the
                # negation, which is what it means.
                if self.current.is_word("if"):
                    self.advance()
                    try:
                        condition = self.expression()
                    except PineSyntaxError:
                        self._skip_line()
                        stack.append((else_indent, None, None))
                        continue
                    previous = carried[2] if carried else None
                    guard = _combine(previous, condition)
                    negated = _combine(previous,
                                       Node("unary", condition.line, "not",
                                            [condition]))
                    stack.append((else_indent, guard, negated))
                    continue
                # A plain `else`: its body runs under the negation of the `if`.
                # With no `if` to negate there is nothing to guard by, and the
                # body must be refused rather than run unconditionally.
                stack.append((else_indent, carried[2] if carried else None,
                              None))
                continue

            statement = self.statement()
            statement.indent = indent
            if stack:
                if_indent, guard, _ = stack[-1]
                if indent > if_indent:
                    if guard is None:
                        statement = Statement(
                            "unsupported", statement.line, indent=indent,
                            reason="this sits inside an `if` whose condition "
                                   "could not be read, so running it "
                                   "unconditionally would change what the "
                                   "strategy does",
                            source=statement.source or statement.target)
                    else:
                        statement.guard = guard
            out.append(statement)
        return out

    def _skip_line(self) -> str:
        """Consume to the end of the line, returning what was skipped."""
        parts: list[str] = []
        while self.current.kind not in (NEWLINE, END):
            parts.append(self.advance().value)
        return " ".join(parts)

    def statement(self) -> Statement:
        token = self.current
        line = token.line

        # Constructs this grammar deliberately does not cover. Recognised so
        # they can be REPORTED at their own line rather than mis-parsed.
        if token.kind == IDENT and token.value in (
                "for", "while", "switch", "type", "import", "export",
                "method"):
            source = self._skip_line()
            return Statement("unsupported", line, indent=token.column, reason=(
                f"`{token.value}` blocks are not part of the strategy format — "
                f"a rule here is a condition over indicators, not a program"),
                source=source)

        try:
            # `var x = ...` / `varip x = ...` declare, then assign.
            declared = ""
            if token.is_word("var", "varip"):
                declared = self.advance().value
                # `var float held = na` -- Pine allows a type between the
                # keyword and the name, and swallowing it here keeps the
                # assignment recognisable so it can be reported as ONE
                # unsupported line rather than two confusing ones.
                if (self.current.kind == IDENT
                        and self.current.value in _TYPES
                        and self.tokens[self.pos + 1].kind == IDENT):
                    declared = f"{declared} {self.advance().value}"

            if self.current.is_op("["):
                # `[a, b, c] = ta.macd(...)` -- Pine's multi-output form.
                save = self.pos
                names = self._tuple_targets()
                if names is not None and self.current.is_op("=", ":="):
                    self.advance()
                    value = self.expression()
                    statement = Statement("tuple_assignment", line,
                                          target=names[0], targets=names,
                                          value=value)
                    if declared:
                        statement.reason = (
                            f"`{declared}` keeps a value between bars, which "
                            f"this format has no way to express")
                        statement.kind = "unsupported"
                        statement.source = f"{declared} [{', '.join(names)}] = ..."
                    return statement
                self.pos = save

            if self.current.kind == IDENT:
                save = self.pos
                name = self.dotted_name()
                if self.current.is_op("=", ":="):
                    self.advance()
                    value = self.expression()
                    statement = Statement("assignment", line, target=name,
                                          value=value)
                    if declared:
                        statement.reason = (
                            f"`{declared}` keeps a value between bars, which "
                            f"this format has no way to express")
                        statement.kind = "unsupported"
                        statement.source = f"{declared} {name} = ..."
                    return statement
                self.pos = save

            value = self.expression()
            if value.kind == "call":
                return Statement("call", line, target=str(value.value),
                                 value=value)
            return Statement("unsupported", line, value=value,
                             reason="this line is an expression whose result "
                                    "goes nowhere",
                             source=value.describe())
        except PineSyntaxError as exc:
            self._skip_line()
            return Statement("unsupported", line,
                             reason=f"could not be parsed: {exc.message}",
                             source="")


def parse(text: str) -> list[Statement]:
    """Tokenise and parse, returning one statement per top-level line."""
    return Parser(tokenize(text)).statements()
