"""Experiment ledger for the NQ Scalping System study. Every run lands here."""
import json
from pathlib import Path
P = Path("/home/user/main/docs/nqscalp/ledger.jsonl")
P.parent.mkdir(parents=True, exist_ok=True)

def log(**kw):
    kw.setdefault("id", f"N{sum(1 for _ in open(P)) + 1:04d}" if P.exists() else "N0001")
    with open(P, "a") as f:
        f.write(json.dumps(kw, default=str) + "\n")
    return kw["id"]
