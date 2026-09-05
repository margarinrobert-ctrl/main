"""A structural linter for emitted Pine, because there is no Pine compiler here.

It cannot check semantics. It checks the one thing that has actually broken a generated script:
indentation. Pine's rule is specific and easy to violate by accident --

    a line indented by a MULTIPLE OF FOUR is a block body, and a block must be open for it
    a line indented by anything else is a continuation of the line above

and the rule holds INSIDE an unclosed bracket too, which is where it keeps being violated: a
multi-line `options = [...]` or a wrapped ternary lines its arguments up at 12 or 16 spaces
because that is what looks tidy, and Pine rejects the file.

so an assignment emitted at global scope with a stray four-space indent is read as a block body
with no block open, and the compiler rejects it with CE10013, "expecting end of line without
line continuation". That is what shipped once. A ternary wrapped at column 22 is fine; the same
expression wrapped at column 24 is not.

This walks the text with that rule, tracking unclosed brackets and a stack of open block indents.
"""
from __future__ import annotations

import re

# a block opener: `if`, `for`, `while`, `switch` (which may sit after an assignment, as in
# `stopLevel := switch stopMethod`), a bare or trailing `else`, or a function declaration.
OPENERS = re.compile(r"(?:^|[\s=:(\[,])(?:if|for|while|switch)\b|(?:^|\s)else\s*$|=>\s*$")
TERNARY = re.compile(r"\?")


def _strip(line):
    """Drop // comments and replace string literals with a placeholder token.

    A placeholder, not deletion: deleting the string turns a switch arm like `1 => "text"` into
    a bare `1 =>`, which then looks exactly like a function declaration and opens a phantom
    block. Brackets and quotes inside strings still must not be counted, which is the other half
    of the job."""
    out, i, n, instr = [], 0, len(line), None
    while i < n:
        ch = line[i]
        if instr:
            if ch == "\\":
                i += 2
                continue
            if ch == instr:
                instr = None
                out.append("S")
            i += 1
            continue
        if ch in "\"'":
            instr = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def lint(text, name="script"):
    problems = []
    depth = 0                       # unclosed ( or [
    stack = [0]                     # indents at which a block is open
    opener = False                  # previous logical line opened a block
    for ln, raw in enumerate(text.split("\n"), 1):
        if not raw.strip():
            continue
        code = _strip(raw)
        if not code.strip():
            depth += code.count("(") + code.count("[") - code.count(")") - code.count("]")
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent]:
            problems.append((ln, "tab in leading whitespace", raw))
        if depth == 0 and indent % 4 == 0:   # a block body: a block must be open for it
            if opener:
                if indent <= stack[-1]:
                    problems.append((ln, f"block opened above has no body -- expected indent > "
                                         f"{stack[-1]}, got {indent}", raw))
                else:
                    stack.append(indent)
            else:
                while len(stack) > 1 and indent < stack[-1]:
                    stack.pop()
                if indent != stack[-1]:
                    problems.append((ln, f"indent {indent} is a multiple of 4, so Pine reads it "
                                         f"as a block body, but the open blocks are at {stack}. "
                                         f"Indent a continuation by a non-multiple of 4 -- "
                                         f"CE10013", raw))
            opener = bool(OPENERS.search(code.strip()))
        elif depth == 0:
            pass                             # non-multiple of 4: a continuation, always legal
        elif indent % 4 == 0:
            # INSIDE an unclosed bracket. Pine's continuation rule does not care that a bracket
            # is open: a line indented by a multiple of four is still read as a block body. This
            # is the case the linter used to skip entirely, and it shipped twice -- an `options`
            # array wrapped at 16 spaces in TURTLE_4_FINALISTS and again in V61.
            problems.append((ln, f"indent {indent} is a multiple of 4 INSIDE an unclosed "
                                 f"bracket, so Pine reads the continuation as a block body -- "
                                 f"CE10013. Wrap at a non-multiple of 4", raw))
        depth += code.count("(") + code.count("[") - code.count(")") - code.count("]")
        if depth < 0:
            problems.append((ln, "closes a bracket that was never opened", raw))
            depth = 0
    if depth != 0:
        problems.append((0, f"{depth} bracket(s) never closed", ""))
    return problems


def check(text, name="script", verbose=True):
    p = lint(text, name)
    if verbose:
        for ln, msg, raw in p:
            print(f"   {name}:{ln}  {msg}\n      {raw!r}")
    return p


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "research")
    import itertools
    import numpy as np
    import pine_export as PX

    rng = np.random.default_rng(3)
    names = list(PX.P)
    bad = 0
    n = 0
    for trial in range(400):
        k = int(rng.integers(1, 4))
        rule = [names[i] for i in rng.choice(len(names), k, replace=False)]
        side = int(rng.choice([1, -1]))
        am = float(rng.choice([1.0, 1.5, 2.0, 2.5]))
        tp = float(rng.choice([1.0, 1.5, 2.0, 3.0]))
        flat = int(rng.choice([0, 960]))
        for kind, fn in (("strategy", PX.emit_strategy), ("indicator", PX.emit_indicator)):
            code = fn(rule, side, am, tp, flat)
            n += 1
            probs = check(code, f"{kind}[{trial}]", verbose=(bad < 5))
            if probs:
                bad += 1
    print(f"\n{n} emitted scripts linted, {bad} with structural problems")
    raise SystemExit(1 if bad else 0)
