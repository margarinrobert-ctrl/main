#!/usr/bin/env python3
"""One command, or one interactive prompt, for tuning a rule's indicators, session, entry and exits.

    python research/tune.py "close>ema200 and close<ema20 and rsi14<40"
    python research/tune.py "close>ema{n} and rsi{p}<40" --set n=50,100,200 --set p=7,14,21 \\
                            --stop 1.5,2,2.5 --target 0.5,1,1.5,2 --win 09:30-11:00 --reveal 3
    python research/tune.py -i                       interactive; state stays warm between rules
    python research/tune.py --catalogue              every indicator and how to write it

Anything given as a comma-separated list becomes an axis of the sweep. Geometry axes are free --
they index a cached exit tensor -- so widen them first and widen the rule last.

The output is the RESEARCH block. `--reveal k` reads the locked block once, for the top k.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuner as U


def _nums(s, cast=float):
    return [cast(x) for x in str(s).split(",") if str(x).strip() != ""]


def _flats(s):
    out = []
    for x in str(s).split(","):
        x = x.strip()
        out.append(U.window(x)[0] if ":" in x else int(x))
    return out


def _entries(s):
    """market | limit:K | limit:K:EXPIRY:THRU"""
    out = []
    for x in str(s).split(","):
        x = x.strip()
        if x in ("market", "mkt", ""):
            out.append(U.Entry())
            continue
        p = x.split(":")
        k = float(p[1]) if len(p) > 1 else 0.75
        exp = int(p[2]) if len(p) > 2 else 6
        thru = float(p[3]) if len(p) > 3 else 2.0
        out.append(U.Entry(kind="limit", k=k, expiry=exp, thru=thru))
    return out


def parser():
    p = argparse.ArgumentParser(prog="tune.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rule", nargs="?", default="always",
                   help="entry condition, e.g. \"close>ema200 and rsi14<40\"")
    p.add_argument("--tf", default="30", help="timeframe(s) in minutes")
    p.add_argument("--side", default="long", help="long, short, or both")
    p.add_argument("--win", default="09:30-11:00", help="New York session window(s)")
    p.add_argument("--stop", default="1.5,2.0,2.5", help="stop, in ATR multiples")
    p.add_argument("--target", default="0.5,1.0,1.5,2.0", help="take profit, in R")
    p.add_argument("--flat", default="0", help="flatten at this NY time; 0 = never")
    p.add_argument("--hold", default="0", help="max hold in BARS; 0 = no limit")
    p.add_argument("--atr", type=int, default=14, help="ATR period the stop is sized in")
    p.add_argument("--entry", default="market", help="market | limit:K[:EXPIRY:THRU]")
    p.add_argument("--cost", default="1.0", help="cost multiplier(s); 2 is the stress case")
    p.add_argument("--set", action="append", default=[], metavar="NAME=V1,V2",
                   help="value(s) for a {NAME} placeholder in the rule; repeatable")
    p.add_argument("--min-trades", type=int, default=30)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--control", type=int, default=20,
                   help="run the matched control for the top N by research (0 to skip)")
    p.add_argument("--reveal", type=int, default=0,
                   help="read the LOCKED block for the top k. Do this once, after choosing.")
    p.add_argument("--sort", default="res_per")
    p.add_argument("-i", "--interactive", action="store_true")
    p.add_argument("--catalogue", action="store_true")
    return p


def once(a, rule=None):
    sides = {"long": [1], "short": [-1], "both": [1, -1]}[a.side]
    sets = {}
    for kv in a.set:
        k, v = kv.split("=", 1)
        try:
            sets[k] = _nums(v, int)
        except ValueError:
            sets[k] = _nums(v, float)
    df = U.sweep(rule or a.rule, tf=_nums(a.tf, int), side=sides, win=a.win.split(","),
                 stop=_nums(a.stop), target=_nums(a.target), flat=_flats(a.flat),
                 hold=_nums(a.hold, int), atr_n=a.atr, entry=_entries(a.entry),
                 costs=[U.Costs(mult=m) for m in _nums(a.cost)],
                 control=a.control, sort=a.sort, top=a.top, min_trades=a.min_trades,
                 verbose=True, **sets)
    if a.reveal and len(df):
        U.reveal(df, k=a.reveal)
    return df


BANNER = """
  Type a rule and press enter. Anything else you want to change is a flag:
      close>ema200 and close<ema20
      close>ema200 and rsi14<35            --stop 1,1.5,2,2.5 --target 0.5,1,1.5,2
      close>ema{n} and rsi14<40            --set n=20,50,100,200
      supertrend(10,3)>0 and pos<30        --win 07:00-11:00 --entry market,limit:0.75
  Commands:  :help   :cat   :reveal N   :q
"""


def repl(a):
    print(BANNER)
    last = None
    while True:
        try:
            line = input("rule> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if not line:
            continue
        if line in (":q", ":quit", ":exit"):
            return
        if line in (":help", ":h"):
            print(BANNER); continue
        if line in (":cat", ":catalogue"):
            print(U.catalogue_text()); continue
        if line.startswith(":reveal"):
            k = int(line.split()[1]) if len(line.split()) > 1 else 3
            if last is None or not len(last):
                print("  run a rule first")
            else:
                U.reveal(last, k=k)
            continue
        rule, *rest = line.split(" --")
        args = a
        if rest:
            # inline flags LAYER ON the session's flags rather than resetting them: typing
            # `--top 4` must not silently restore the default stop and target grid
            import copy as _copy
            args = _copy.deepcopy(a)
            flags = []
            for r in rest:
                flags += ("--" + r).split(" ", 1)
            parser().parse_args(flags, namespace=args)
            args.rule = rule
        t0 = time.time()
        try:
            last = once(args, rule.strip())
        except Exception as e:                                   # a typo must not end the session
            print(f"  {type(e).__name__}: {e}")
            continue
        print(f"  [{time.time()-t0:.2f}s]")


def main(argv=None):
    a = parser().parse_args(argv)
    if a.catalogue:
        print(U.catalogue_text()); return 0
    t0 = time.time()
    if a.interactive:
        U.bars(int(str(a.tf).split(",")[0]))
        print(f"  bars warm in {time.time()-t0:.2f}s")
        repl(a); return 0
    once(a)
    print(f"  total {time.time()-t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
