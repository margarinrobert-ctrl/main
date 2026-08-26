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


def label_for(name: str, tf: int, p: P) -> str:
    return f"{name} {tf}m  {sess_str(p.sess_start, p.sess_end)} NY"


def build(keys: list[str], path: str, title: str, subtitle: str) -> list:
    presets, sessions, tfs, fingerprints = {}, {}, {}, []
    for k in keys:
        name, tf = k.split(":")
        tf = int(tf)
        with open(os.path.join(OUT, f"chosen_{name}_{tf}m.json")) as fh:
            j = json.load(fh)
        p = P(**j["params"])
        lab = label_for(name, tf, p)
        presets[lab] = p
        sessions[lab] = (sess_str(p.sess_start, p.sess_end),
                         sess_str(p.flatten_min, p.flatten_min + 5))
        tfs[lab] = str(tf)
        fingerprints.append(
            f"//   {lab:<28} selected on {j['n_trials']:,} configurations, "
            f"trial Sharpe sd {j['trial_sd']:.3f}")

    # The supplied script, confined to the window, kept as a preset so the comparison the study
    # rests on is one dropdown click away rather than a claim in a document.
    spec = P(entry1=20, entry2=55, exit1=10, exit2=20, atr_len=20, atr_mult=2.0, pyr_step=0.5,
             max_units=4, skip_win=True, use_chan_exit=True, chan_shift=1, armed_stop=False,
             sess_start=420, sess_end=660, flatten_min=660, tp_r=0.0, one_shot=False)
    presets["Spec Turtle  0700-1100 NY"] = spec
    sessions["Spec Turtle  0700-1100 NY"] = ("0700-1100", "1100-1105")
    tfs["Spec Turtle  0700-1100 NY"] = "60"
    fingerprints.append("//   Spec Turtle                   the supplied 20/55 Turtle, unchanged, "
                        "confined to the window")

    fp = "// Provenance:\n" + "\n".join(fingerprints) + "\n//\n"
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
