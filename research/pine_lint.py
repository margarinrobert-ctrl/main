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

IT ALSO CHECKS CONST-STRING ARGUMENTS, added after a shipped script failed to compile on

    plot(useEma ? ema : na, "EMA " + str.tostring(emaLen), ...)

    Cannot call 'plot' with argument 'title'='call 'operator +' (simple string)'. An argument of
    'simple string' type was used but a 'const string' is expected.

A title built from an input is a SIMPLE string -- known only once the inputs are read -- and Pine
requires a CONST string, known at compile time, for every title and for `input.string`'s options.
The rule is easy to violate precisely because the concatenation looks harmless and reads better
than a literal. Same lesson as the indentation rule: when a script fails to compile, fix the
LINTER first and the file second, or the next script repeats it.
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


# Functions whose title argument must be a CONST string, with the title's positional slot.
# `None` means the title can only be passed by name.
CONST_TITLE = {
    "plot": 1, "plotshape": 1, "plotchar": 1, "plotarrow": 1,
    "plotcandle": 4, "plotbar": 4, "hline": 1,
    "indicator": 0, "strategy": 0,
    "bgcolor": None, "fill": None, "barcolor": None,
}
for _f in ("int", "float", "bool", "string", "timeframe", "color", "source",
           "session", "symbol", "price", "text_area", "enum"):
    CONST_TITLE[f"input.{_f}"] = 1
CONST_TITLE["input"] = 1

_LITERAL = re.compile(r"""^\s*(?:"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*')\s*$""")
_CALL = re.compile(r"(?<![\w.])((?:input\.)?[a-z_]+(?:\.[a-z_]+)?)\s*\(")


def _split_args(src):
    """Top-level comma split, respecting brackets and string literals."""
    args, buf, depth, instr = [], [], 0, None
    i = 0
    while i < len(src):
        ch = src[i]
        if instr:
            buf.append(ch)
            if ch == "\\":
                if i + 1 < len(src):
                    buf.append(src[i + 1])
                i += 2
                continue
            if ch == instr:
                instr = None
            i += 1
            continue
        if ch in "\"'":
            instr = ch
            buf.append(ch)
        elif ch in "([":
            depth += 1
            buf.append(ch)
        elif ch in ")]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        args.append("".join(buf))
    return args


def const_string_problems(text):
    """Flag title / shorttitle / options arguments that are not compile-time constants."""
    out = []
    # blank out comments so a `//` mention of plot(...) is not parsed as a call
    lines = []
    for raw in text.split("\n"):
        st = raw.lstrip()
        lines.append("" if st.startswith("//") else raw)
    flat = "\n".join(lines)
    for m in _CALL.finditer(flat):
        fn = m.group(1)
        if fn not in CONST_TITLE:
            continue
        i = m.end()
        depth, instr, j = 1, None, i
        while j < len(flat) and depth:
            c = flat[j]
            if instr:
                if c == "\\":
                    j += 2
                    continue
                if c == instr:
                    instr = None
            elif c in "\"'":
                instr = c
            elif c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            j += 1
        inner = flat[i:j - 1]
        ln = flat[:m.start()].count("\n") + 1
        args = _split_args(inner)
        named = {}
        pos = []
        for a in args:
            k = re.match(r"\s*([A-Za-z_]\w*)\s*=(?!=)(.*)$", a, re.S)
            if k and not k.group(2).lstrip().startswith("="):
                named[k.group(1)] = k.group(2)
            else:
                pos.append(a)
        slot = CONST_TITLE[fn]
        checks = []
        if "title" in named:
            checks.append(("title", named["title"]))
        elif slot is not None and len(pos) > slot:
            checks.append(("title", pos[slot]))
        for extra in ("shorttitle", "textcolor_title"):
            if extra in named:
                checks.append((extra, named[extra]))
        for label, expr in checks:
            if expr.strip() in ("", "na"):
                continue
            if not _LITERAL.match(expr):
                out.append((ln, f"{fn}(): `{label}` must be a CONST string but is an expression "
                                f"-- Pine rejects a title built with `+` or str.tostring() "
                                f"(\"a 'simple string' was used but a 'const string' is "
                                f"expected\")", expr.strip()[:90]))
        if fn == "input.string" and "options" in named:
            for o in _split_args(named["options"].strip().lstrip("[").rstrip("]")):
                if o.strip() and not _LITERAL.match(o):
                    out.append((ln, "input.string(): every entry of `options` must be a const "
                                    "string literal", o.strip()[:90]))
    return out


_MULTI_DECL = re.compile(
    r"^\s*(?:var\s+|varip\s+)?(float|int|bool|string|color|line|label|box|table)\s+"
    r"[A-Za-z_]\w*\s*=(?!=)")


def multi_decl_problems(text):
    """Flag `float a = na, b = na` -- Pine applies the type keyword to the FIRST name only.

    Pine parses a comma-separated declaration list, but the type keyword governs only the first
    binding; every later name is declared by INFERENCE. When the initialiser is `na` that is a
    compile error TradingView reports as "Value with NA type cannot be assigned to a variable
    that was defined without type keyword", pointing at a line that reads as though it declares
    the type explicitly. When the initialiser is a literal it compiles and the later names simply
    lose the declared type, which is worse because nothing complains.

    One declaration per line. This shipped once, in PIN_POSTERIOR, and the file lint-passed.
    """
    out = []
    for ln, raw in enumerate(text.split("\n"), 1):
        code = _strip(raw)
        if not code.strip() or not _MULTI_DECL.match(code):
            continue
        # split on commas at bracket depth 0; more than one part means a declaration list
        parts, depth, instr, buf = [], 0, None, []
        for ch in code:
            if instr:
                buf.append(ch)
                if ch == instr:
                    instr = None
                continue
            if ch in "\"'":
                instr = ch
            elif ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
        parts.append("".join(buf))
        extra = [q for q in parts[1:]
                 if re.match(r"\s*[A-Za-z_]\w*\s*=(?!=)", q)]
        if not extra:
            continue
        names = [re.match(r"\s*([A-Za-z_]\w*)", q).group(1) for q in extra]
        na_named = [n for n, q in zip(names, extra) if q.split("=", 1)[1].strip() == "na"]
        if na_named:
            out.append((ln, "comma-separated declaration: the type keyword governs only the "
                            f"FIRST name, so {', '.join(na_named)} is declared by inference and "
                            "assigned `na` -- \"Value with NA type cannot be assigned to a "
                            "variable that was defined without type keyword\". One per line",
                        code.strip()[:90]))
        else:
            out.append((ln, "comma-separated declaration: the type keyword governs only the "
                            f"FIRST name, so {', '.join(names)} silently lose the declared type. "
                            "One per line", code.strip()[:90]))
    return out


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
    problems.extend(const_string_problems(text))
    problems.extend(multi_decl_problems(text))
    return sorted(problems, key=lambda x: x[0])


def check(text, name="script", verbose=True):
    p = lint(text, name)
    if verbose:
        for ln, msg, raw in p:
            print(f"   {name}:{ln}  {msg}\n      {raw!r}")
    return p


if __name__ == "__main__":
    import sys
    import pathlib
    sys.path.insert(0, "research")

    def _lint_paths(paths):
        """Lint files on disk. The CLI used to IGNORE its arguments and lint only the emitted
        scripts, so `pine_lint.py some_file.pine` printed a clean bill of health for a file it
        never opened -- which is how PIN_POSTERIOR shipped with a comma-separated declaration."""
        files = []
        for a in paths:
            q = pathlib.Path(a)
            files.extend(sorted(q.rglob("*.pine")) if q.is_dir() else [q])
        bad = 0
        for f in files:
            probs = check(f.read_text(), str(f), verbose=True)
            if probs:
                bad += 1
        print(f"\n{len(files)} file(s) on disk linted, {bad} with structural problems")
        return bad

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        raise SystemExit(1 if _lint_paths(args) else 0)

    # no arguments: lint everything -- the emitted scripts AND every shipped file
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
    diskbad = _lint_paths(["pine"]) if pathlib.Path("pine").exists() else 0
    raise SystemExit(1 if (bad or diskbad) else 0)
