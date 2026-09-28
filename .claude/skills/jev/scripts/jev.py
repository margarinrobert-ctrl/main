#!/usr/bin/env python3
"""Call TypeSafe's Jev (System One) with typed questions and print normalised JSON answers.

Standard library only, so it runs anywhere Python 3.8+ does.

    jev.py request.json          # request from a file
    jev.py -                     # request from stdin
    jev.py --check               # which key/endpoint would be used (never prints the key)
    jev.py --dry-run request.json   # validate and print the body, send nothing
    jev.py --strict request.json    # exit 2 on failure instead of failing open
    jev.py --raw request.json       # include the provider's raw response

Request: {"state": <str|obj|array>, "questions": {name: {"type": "noul"|"choice"|"score",
"instructions": str, "criteria": {...} for choice | [...] for score}}}

Output: {"ok": true, "model": ..., "latency_ms": ..., "answers": {name: {...}}} or, on any
failure, {"ok": false, "error": ..., "kind": ...}. By default a failure still exits 0 -- the
caller FAILS OPEN and decides on its own. Pass --strict where a failure must stop the caller.

The API key is read from the environment and never printed, logged or echoed back in errors.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}
MAX_CHOICE = 255
SCORE_LEVELS = (2, 10)


# ----------------------------------------------------------------------------- config
def provider():
    """Pick the route. TypeSafe direct unless told otherwise or only an OpenRouter key exists."""
    want = os.environ.get("JEV_PROVIDER", "").strip().lower()
    ts, orr = bool(os.environ.get("TYPESAFE_API_KEY")), bool(os.environ.get("OPENROUTER_API_KEY"))
    if want == "openrouter" or (not ts and orr and want != "typesafe"):
        return dict(name="openrouter", url=os.environ.get("JEV_URL", OPENROUTER_URL),
                    key_env="OPENROUTER_API_KEY",
                    model=os.environ.get("JEV_MODEL", "~typesafe/jev-latest"))
    return dict(name="typesafe", url=os.environ.get("JEV_URL", TYPESAFE_URL),
                key_env="TYPESAFE_API_KEY", model=os.environ.get("JEV_MODEL", "jev-latest"))


def _key(p):
    return os.environ.get(p["key_env"], "").strip()


def _redact(text, key):
    if key and text:
        text = text.replace(key, "***")
    return text


# ----------------------------------------------------------------------------- validation
def validate(req):
    """Catch the mistakes that would otherwise cost a round trip. Returns a list of problems."""
    errs = []
    if not isinstance(req, dict):
        return ["request must be a JSON object"]
    if "state" not in req or req["state"] in (None, "", [], {}):
        errs.append("`state` is missing or empty -- Jev answers from the state and nothing else")
    qs = req.get("questions")
    if not isinstance(qs, dict) or not qs:
        errs.append("`questions` must be a non-empty object {name: question}")
        return errs
    for name, q in qs.items():
        if not isinstance(q, dict):
            errs.append(f"{name}: question must be an object"); continue
        t = q.get("type")
        if t not in ("noul", "choice", "score"):
            errs.append(f"{name}: type must be noul, choice or score (got {t!r})")
        if not str(q.get("instructions", "")).strip():
            errs.append(f"{name}: `instructions` is required")
        c = q.get("criteria")
        if t == "choice":
            if not isinstance(c, dict) or not (2 <= len(c) <= MAX_CHOICE):
                errs.append(f"{name}: choice needs `criteria` as an object of 2-{MAX_CHOICE} "
                            "option -> description (include a `none`/`other` option)")
        elif t == "score":
            lo, hi = SCORE_LEVELS
            if not isinstance(c, list) or not (lo <= len(c) <= hi):
                errs.append(f"{name}: score needs `criteria` as an ORDERED list of {lo}-{hi} "
                            "level descriptions, lowest first")
        elif t == "noul" and c is not None:
            errs.append(f"{name}: noul takes no `criteria` -- phrase it as one true/false statement")
    return errs


# ----------------------------------------------------------------------------- normalisation
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _norm_one(q, a):
    """One answer into a stable shape, tolerating the wire-format variants seen in the wild."""
    t = (a.get("type") if isinstance(a, dict) else None) or q.get("type")
    if not isinstance(a, dict):
        a = {"value": a}
    if t == "noul":
        p = None
        for k in ("p_yes", "probability", "value", "yes", "prob"):
            if k in a and _num(a[k]) is not None:
                p = _num(a[k]); break
        if p is None and isinstance(a.get("probabilities"), dict):
            p = _num(a["probabilities"].get("yes") or a["probabilities"].get("true"))
        return {"type": "noul", "p_yes": p}
    probs = a.get("probabilities")
    if probs is None and isinstance(a.get("legend"), dict):
        probs = a["legend"].get("probabilities", a["legend"])
    out = {"type": t, "confidence": _num(a.get("confidence"))}
    if t == "choice":
        out["choice"] = a.get("choice", a.get("value"))
        if out["choice"] is None and isinstance(probs, dict) and probs:
            out["choice"] = max(probs, key=lambda k: _num(probs[k]) or 0.0)
    elif t == "score":
        out["score"] = _num(a.get("score", a.get("value")))
        if a.get("legend") is not None:
            out["legend"] = a["legend"]
    out["probabilities"] = probs
    return out


def normalise(req, resp):
    ans = resp.get("answers") or resp.get("results") or resp.get("output") or resp
    if isinstance(ans, list):                      # [{"name": ..., ...}, ...]
        ans = {x.get("name") or x.get("key"): x for x in ans if isinstance(x, dict)}
    out = {}
    for name, q in req["questions"].items():
        a = ans.get(name) if isinstance(ans, dict) else None
        out[name] = _norm_one(q, a) if a is not None else {"type": q.get("type"), "missing": True}
    return out


# ----------------------------------------------------------------------------- transport
def call(req, timeout=None, raw=False):
    p = provider()
    key = _key(p)
    if not key:
        return {"ok": False, "kind": "no_key",
                "error": f"{p['key_env']} is not set -- Jev unavailable, decide without it"}
    body = dict(req)
    body.setdefault("model", p["model"])
    data = json.dumps(body).encode()
    budget = float(timeout or os.environ.get("JEV_TIMEOUT", 5))
    t0 = time.monotonic()
    for attempt in (0, 1):                         # at most ONE retry, inside the budget
        left = budget - (time.monotonic() - t0)
        if left <= 0.05:
            return {"ok": False, "kind": "timeout", "error": f"budget of {budget:.1f}s spent"}
        r = urllib.request.Request(p["url"], data=data, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "jev-skill/1.0"})
        try:
            with urllib.request.urlopen(r, timeout=left) as h:
                resp = json.loads(h.read().decode() or "{}")
            out = {"ok": True, "provider": p["name"], "model": body["model"],
                   "latency_ms": int(1000 * (time.monotonic() - t0)),
                   "answers": normalise(req, resp)}
            if raw:
                out["raw"] = resp
            return out
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                detail = e.read().decode(errors="replace")[:400]
            except Exception:  # noqa: BLE001
                detail = ""
            detail = _redact(detail, key)
            if code in RETRYABLE and attempt == 0:
                wait = _num(e.headers.get("retry-after")) if e.headers else None
                wait = min(wait if wait is not None else 0.4, 2.0)
                if wait < budget - (time.monotonic() - t0) - 0.2:
                    time.sleep(wait); continue
            kind = ("auth" if code in (401, 403) else "validation" if code in (400, 404, 422)
                    else "rate_limit" if code == 429 else "overloaded" if code >= 500 or code == 529
                    else "http")
            return {"ok": False, "kind": kind, "status": code, "error": detail or str(e)}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 0 and (time.monotonic() - t0) < budget * 0.5:
                continue
            return {"ok": False, "kind": "network", "error": _redact(str(e), key)}
        except json.JSONDecodeError:
            return {"ok": False, "kind": "bad_response", "error": "response was not JSON"}
    return {"ok": False, "kind": "exhausted", "error": "retry budget spent"}


# ----------------------------------------------------------------------------- cli
def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if "--check" in flags:
        p = provider()
        print(json.dumps({"provider": p["name"], "endpoint": p["url"], "model": p["model"],
                          "key_env": p["key_env"], "key_present": bool(_key(p))}, indent=2))
        return 0
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        src = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
        req = json.loads(src)
    except (OSError, json.JSONDecodeError) as e:
        out = {"ok": False, "kind": "bad_request", "error": f"could not read request: {e}"}
    else:
        errs = validate(req)
        if errs:
            out = {"ok": False, "kind": "bad_request", "error": "; ".join(errs)}
        elif "--dry-run" in flags:
            p = provider()
            body = dict(req); body.setdefault("model", p["model"])
            print(json.dumps({"ok": True, "dry_run": True, "endpoint": p["url"], "body": body},
                             indent=2))
            return 0
        else:
            out = call(req, raw="--raw" in flags)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") or "--strict" not in flags else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
