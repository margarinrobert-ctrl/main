#!/usr/bin/env python3
"""Optional Claude Code PreToolUse hook: ask Jev about every Bash / Write / Edit call.

It can only make a call STRICTER, never looser. It never returns "allow" -- a Jev "allow" just
falls through to Claude Code's normal permission flow -- so a wrong answer cannot bypass your
permission settings. It returns "ask" or "deny" when Jev is confident the call is destructive or
out of scope. On ANY error (no key, timeout, network) it prints nothing and exits 0: fail open,
so a flaky network never blocks your session.

Wire it up in .claude/settings.json (see references/api.md, "Hook recipe").
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATED = {"Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"}
DENY_AT = float(os.environ.get("JEV_GATE_DENY", 0.85))   # choice confidence needed to deny
ASK_AT = float(os.environ.get("JEV_GATE_ASK", 0.70))     # p(destructive) that forces a prompt


def main():
    try:
        ev = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool = ev.get("tool_name", "")
    if tool not in GATED:
        return 0
    ti = ev.get("tool_input", {}) or {}
    # keep the state small: the command, or the path plus the first 2,000 characters of the edit
    what = ti.get("command") or json.dumps(
        {k: (str(v)[:2000] if isinstance(v, str) else v) for k, v in ti.items()})[:4000]
    req = {
        "state": {"tool": tool, "input": what, "cwd": ev.get("cwd", "")},
        "questions": {
            "destructive": {"type": "noul", "instructions":
                "Does `input` delete, overwrite or irreversibly modify files, data, credentials "
                "or shared history (for example force-push, rm -rf, DROP, reset --hard)?"},
            "action": {"type": "choice", "instructions": "Should this tool call run without asking?",
                       "criteria": {
                           "allow": "Read-only, or a local change that is trivially reversible.",
                           "ask": "Consequential or unclear; a human should confirm first.",
                           "deny": "Destroys data, leaks secrets, or rewrites shared history."}},
        },
    }
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "jev.py"), "-"],
                           input=json.dumps(req), capture_output=True, text=True,
                           timeout=float(os.environ.get("JEV_TIMEOUT", 1.5)) + 1.0,
                           env={**os.environ, "JEV_TIMEOUT": os.environ.get("JEV_TIMEOUT", "1.5")})
        out = json.loads(r.stdout)
    except Exception:  # noqa: BLE001 -- fail open on anything
        return 0
    if not out.get("ok"):
        return 0
    a = out["answers"]
    p_des = a.get("destructive", {}).get("p_yes") or 0.0
    act = a.get("action", {})
    choice, conf = act.get("choice"), act.get("confidence") or 0.0
    decision = None
    if choice == "deny" and conf >= DENY_AT:
        decision = "deny"
    elif choice in ("deny", "ask") or p_des >= ASK_AT:
        decision = "ask"
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason":
                f"Jev: {choice} (confidence {conf:.2f}), p(destructive) {p_des:.2f}"}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
