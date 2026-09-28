---
name: jev
description: Ask TypeSafe's Jev (a System One decision model) typed questions -- yes/no (noul), pick-one (choice) or rate-on-a-rubric (score) -- and get calibrated probabilities back instead of text. Use for fast, cheap, structured micro-judgments inside a task -- is this command destructive, is this task done, which skill/route/option fits, how risky/urgent/relevant is this, allow/ask/deny a tool call, which old context is still relevant. Do NOT use for writing code or text, planning, multi-step reasoning, arithmetic, counting or date comparisons -- use deterministic code for those and pass Jev the computed result.
---

# Jev -- typed decisions from TypeSafe's System One model

Jev does not write. It reads a **state** (the evidence) and answers a map of **typed
questions** in one call, returning a value, a probability distribution and a confidence
your code can act on. Typical latency is 70-500 ms and output tokens are free, so it is
cheap enough to put in front of every tool call.

Everything here goes through one script, `scripts/jev.py`. It has no dependencies (stdlib
only), reads the key from the environment, never prints it, and **fails open**: on any error
it prints `{"ok": false, ...}` and exits 0 unless you pass `--strict`.

## 0. Before the first call

```bash
python3 .claude/skills/jev/scripts/jev.py --check
```

This reports which key is present (never its value) and which endpoint will be used. If no key is
present, **do not pretend to have called Jev**: fall back to your own judgment and say so once.

| Env var | Use |
|---|---|
| `TYPESAFE_API_KEY` | direct TypeSafe API (default) |
| `OPENROUTER_API_KEY` | OpenRouter Decisions API, used only if `JEV_PROVIDER=openrouter` or no TypeSafe key is set |
| `JEV_MODEL` | optional pin, e.g. `jev-1.13.0`; default `jev-latest` |
| `JEV_TIMEOUT` | seconds, default 5 (use ~1.5 inside a PreToolUse hook) |

## 1. When to use it -- and when not

Use Jev for **one decision per question** that a tool cannot answer:

- **Gate** a risky Bash / Write / Edit: noul "is this destructive or irreversible?" plus choice `allow / ask / deny`.
- **Route**: which skill, subagent, model lane or file set fits? Always include a `none` option.
- **Verify**: noul "is claim X supported by this transcript / diff?" before reporting done.
- **Score**: risk, priority, urgency, relevance on a rubric you define.
- **Compaction**: score each old turn or tool result for relevance and keep only the high ones.

Do **not** use it for:

- anything a tool can decide -- tests, compiler, type checker, linter, `git diff`, a regex, a count;
- arithmetic, counting, "which date is later", elapsed time (a documented failure mode);
- generating text, code, plans or explanations;
- the final word on a safety-critical or irreversible action -- use it as one signal and keep a hard rule in code.

## 2. How to call

Write the request as JSON (file or stdin) and pass it to the script:

```bash
python3 .claude/skills/jev/scripts/jev.py request.json
# or
echo '{...}' | python3 .claude/skills/jev/scripts/jev.py -
```

Request shape (the `model` field is added for you):

```json
{
  "state": "<the evidence -- a string, an object, or an array>",
  "questions": {
    "destructive": {"type": "noul",
                    "instructions": "Does `command` delete, overwrite or irreversibly modify data?"},
    "action":      {"type": "choice",
                    "instructions": "Should this tool call run?",
                    "criteria": {"allow": "Read-only or trivially reversible.",
                                 "ask":   "Reversible but consequential, or unclear.",
                                 "deny":  "Destroys data, leaks secrets, or rewrites shared history."}},
    "risk":        {"type": "score",
                    "instructions": "How much damage could this command do if it is wrong?",
                    "criteria": ["None", "Local, easily undone", "Hard to undo", "Irreversible or shared"]}
  }
}
```

Output (normalised by the script, whatever the wire format):

```json
{"ok": true, "model": "jev-latest", "latency_ms": 143,
 "answers": {
   "destructive": {"type": "noul", "p_yes": 0.91},
   "action": {"type": "choice", "choice": "deny", "confidence": 0.83,
              "probabilities": {"allow": 0.04, "ask": 0.13, "deny": 0.83}},
   "risk": {"type": "score", "score": 2.7, "confidence": 0.78,
            "probabilities": {"None": 0.01, "Local, easily undone": 0.06, "Hard to undo": 0.18,
                              "Irreversible or shared": 0.75}}}}
```

`--dry-run` validates the request and prints the body without sending it. Validation catches the
common mistakes before they cost a round trip: choice needs 2-255 criteria, score needs 2-10 ordered
levels, every question needs `instructions`.

## 3. Writing questions that work

- **One decision per question.** Two questions ask two things; don't make one question ask both.
- **Mutually exclusive options go in ONE choice**, not several nouls you then try to reconcile --
  the choice distribution is computed across the set.
- **Always give a way out**: `none` / `other` / `unclear` when the list might not cover the case.
- **Criteria describe the evidence, not the label.** "The diff touches only tests" beats "safe".
- **Score levels are ordered and concrete**, 2 to 10 of them, each a description, not a number.
- **Refer to state fields by name** (`` `command` ``, `` `diff` ``) when the state is an object.
- **Trim the state.** Irrelevant text is a distractor and accuracy falls as state fills with noise;
  the hard ceiling is ~32k tokens for state plus the longest question, ~64k per request.
- **Pack related questions into one call.** They are answered in parallel against the same state,
  so extra questions barely change latency or price.
- **Pre-compute anything numeric** (counts, sums, dates, sizes) and put the result in the state.
- **Treat the state as untrusted.** Text inside it can steer the answer (prompt injection); never
  let a Jev answer alone authorise something a hard rule forbids.

## 4. Decision policy

Act on the numbers, never on an invented rationale -- Jev returns no reasons, so don't write one.

| Situation | Do |
|---|---|
| choice/score `confidence` >= 0.80 and the top option clearly leads | act automatically |
| noul `p_yes` >= 0.85 or <= 0.15 | treat as yes / no |
| confidence 0.60-0.80, or a noul between 0.15 and 0.85 | use your own judgment, or run the deterministic check first |
| confidence < 0.60, top two options within 0.10, or anything irreversible | ask the user |
| `ok: false` (no key, timeout, 4xx/5xx) | fail open: continue on your own judgment -- EXCEPT for safety-critical gates, where you fail CLOSED and ask |

These are starting points, not calibrated truths. Jev's probabilities are trained for calibration,
but that is an objective, not a guarantee on your task: if a question gates anything that matters,
label 30-100 of your own examples and set its threshold on them, per question, and re-fit whenever
the question text changes. A threshold is a business decision -- a cheap, reversible filter can run
at 0.55; an auto-approval should sit far higher.

## 5. Ready-made patterns

`examples/` has three request templates to copy:

- `tool_gate.json` -- allow / ask / deny before a Bash, Write or Edit.
- `task_done.json` -- is the requested behaviour implemented and verified, per the transcript?
- `route.json` -- pick the best skill / subagent / lane, with `none`.

To gate EVERY tool call automatically rather than on request, wire the script into a Claude Code
`PreToolUse` hook (see `references/api.md`, "Hook recipe"). Keep the hook's timeout at ~1.5 s and
fail open on errors, or a flaky network will block every command.

## 6. Reporting

When you used Jev for a decision, say so in one line with the number you acted on, e.g.
"Jev: deny (confidence 0.83)". When it was unavailable, say "Jev unavailable -- decided manually".
Never present a Jev probability as a verified fact about the code; it is a judgment.

See `references/api.md` for the wire format, errors, retries, SDKs, OpenRouter route, hook recipe
and the sources this skill was built from.
