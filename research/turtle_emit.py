"""Assemble the shipped Pine from the configurations `turtle_ship` chose.

Reads `chosen_<INSTRUMENT>_<TF>m.json` -- written by `turtle_ship`, which is the only thing that
selects -- and emits one preset per entry.  Nothing here decides anything; if a preset looks wrong,
the study that produced it is what to change.

    python3 research/turtle_emit.py US30:60 US30:30 US30:15 US30:5
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_pine as TP
from turtle_sim import P

OUT = os.environ.get("TURTLE_SWEEP", "/tmp/turtle_sweep")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sess_str(a: int, b: int) -> str:
    return f"{a // 60:02d}{a % 60:02d}-{b // 60:02d}{b % 60:02d}"


def locked_lookup() -> dict:
    """Locked-block Sharpe per candidate, from `turtle_reveal`'s summary."""
    f = os.path.join(OUT, "locked_summary.parquet")
    if not os.path.exists(f):
        return {}
    import pandas as pd
    df = pd.read_parquet(f)
    out = {}
    for _, r in df.iterrows():
        if "marginal-supported" not in r.candidate or "SHORT" in r.candidate:
            continue
        nm, tf = r.candidate.split()[0], int(r.candidate.split()[1].rstrip("m"))
        out[(nm, tf)] = float(r.lk_sharpe)
    return out


def label_for(name: str, tf: int, p: P, locked: dict) -> str:
    """The preset's name carries its holdout number.

    Five of the six candidates lost money out of sample.  Shipping them unlabelled would invite
    exactly the rediscovery this study exists to prevent -- their RESEARCH numbers are the best in
    the file -- so the number each one failed at is in the name, where it cannot be missed.
    """
    sr = locked.get((name, tf))
    if sr is None:
        tag = ""
    elif sr > 0:
        tag = f"  [locked +{sr:.2f}]"
    else:
        tag = f"  [locked {sr:.2f} FAILED]"
    return f"{name} {tf}m  {sess_str(p.sess_start, p.sess_end)}{tag}"


def build(keys: list[str], path: str, title: str, subtitle: str) -> list:
    locked = locked_lookup()
    import turtle_reveal
    k_total = turtle_reveal.total_k()
    presets, sessions, tfs, fingerprints = {}, {}, {}, []
    for k in keys:
        name, tf = k.split(":")
        tf = int(tf)
        with open(os.path.join(OUT, f"chosen_{name}_{tf}m.json")) as fh:
            j = json.load(fh)
        p = P(**j["params"])
        lab = label_for(name, tf, p, locked)
        presets[lab] = p
        sessions[lab] = (sess_str(p.sess_start, p.sess_end),
                         sess_str(p.flatten_min, p.flatten_min + 5))
        tfs[lab] = str(tf)
        fingerprints.append(f"//   {lab}")

    # The supplied script, confined to the window, kept as a preset so the comparison the study
    # rests on is one dropdown click away rather than a claim in a document.
    spec = P(entry1=20, entry2=55, exit1=10, exit2=20, atr_len=20, atr_mult=2.0, pyr_step=0.5,
             max_units=4, skip_win=True, use_chan_exit=True, chan_shift=1, armed_stop=False,
             sess_start=420, sess_end=660, flatten_min=660, tp_r=0.0, one_shot=False)
    lab = "Spec Turtle 20/55  0700-1100"
    presets[lab] = spec
    sessions[lab] = ("0700-1100", "1100-1105")
    tfs[lab] = "60"
    fingerprints.append("//   Spec Turtle 20/55  --  the supplied script, unchanged, confined "
                        "to the window")

    fp = (
        "// ---------------------------------------------------------------------------------\n"
        "// READ THIS BEFORE TRADING IT\n"
        "//\n"
        f"// {k_total:,} configurations were evaluated across this study, on the research block\n"
        "// only, and the locked block was then read once.  FIVE of the six candidates LOST MONEY\n"
        "// out of sample -- including the one with the best research numbers (60m: research\n"
        "// Sharpe 1.05 and profit factor 1.47, holdout -0.36 and 0.88).  Their holdout Sharpe is\n"
        "// in each preset's name so it cannot be missed.\n"
        "//\n"
        "// The default preset is the only survivor, and it survives weakly: holdout Sharpe 0.22,\n"
        "// profit factor 1.04, +$18.70 a trade over 898 trades, max drawdown $40,672 against a\n"
        "// $16,789 gain.  It passes 6 of the protocol's 10 gates and fails the four that matter\n"
        "// for a claim of edge -- HAC t 0.42, deflated Sharpe 0.0000, profitable in 50% of years,\n"
        "// walk-forward efficiency -0.38.  Its Sharpe 95% confidence interval is [-0.83, 1.31].\n"
        "//\n"
        "// It is a paper-trading candidate.  It has not earned more than that.\n"
        "// ---------------------------------------------------------------------------------\n"
        "//\n"
        "// Presets:\n" + "\n".join(fingerprints) + "\n//\n")
    text = TP.emit(presets, sessions, tfs, title, subtitle, fp,
                   pyramiding=max(4, max(p.max_units for p in presets.values())))
    problems = TP.write(path, text)
    bad = TP.verify(text, presets, sessions)
    for b in bad:
        print("  VERIFY:", b)
    print(f"  {path}: {len(text.splitlines())} lines, {len(problems)} lint problems, "
          f"{len(bad)} verification failures, {len(presets)} presets")
    return problems + bad


if __name__ == "__main__":
    keys = sys.argv[1:] or ["US30:60", "US30:30", "US30:15", "US30:5"]
    rc = build(keys, os.path.join(ROOT, "TurtleScalp_0700_1100.pine"),
               "Turtle Scalp 07:00-11:00 NY (measured presets)",
               "Donchian breakout confined to a New York morning window, flat by 11:00.  Every "
               "preset was selected on the research block and read once on the locked block; the "
               "numbers are in docs/ib/STUDY_TURTLE_SCALP.md.")
    sys.exit(1 if rc else 0)
