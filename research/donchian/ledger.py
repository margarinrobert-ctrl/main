"""Persistent research ledger. Every experiment lands here, pass or fail."""
import json, os
from pathlib import Path
P = Path("/home/user/main/docs/donchian/ledger.jsonl")
P.parent.mkdir(parents=True, exist_ok=True)

def log(**kw):
    kw.setdefault("id", f"E{sum(1 for _ in open(P)) + 1:04d}" if P.exists() else "E0001")
    with open(P, "a") as f:
        f.write(json.dumps(kw, default=str) + "\n")
    return kw["id"]

def all_rows():
    if not P.exists(): return []
    return [json.loads(l) for l in open(P) if l.strip()]
