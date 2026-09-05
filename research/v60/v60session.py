"""V60 part six: make the Aroon BIND, and price a session window and a hard flatten.

TWO REQUESTS, AND ONE OF THEM IS A BUG REPORT. The shipped script resolved its presets by
overwriting `aroonMode` with "off", so selecting an Aroon condition while a preset was active did
NOTHING -- the input was dead unless the preset dropdown read "Custom". That is a defect and it is
fixed. But there is a second reason the Aroon can look inert even when it is wired correctly, and
it is the finding of `STUDY_V60_AROON.md`: whenever the Aroon length is no longer than the Donchian
entry length, `osc >= 0` and `up >= 70` are TRUE ON EVERY BREAKOUT BAR by construction.

SO THE ONLY WAY TO MAKE AROON DO WORK ON A BREAKOUT IS TO READ IT WHERE THE BREAKOUT HAS NOT
ALREADY DETERMINED IT. Two options are measured here, both causal:

  signal bar   the reading as shipped. Inert whenever aroon length <= donchian entry.
  prior bar    the Aroon state on the bar BEFORE the breakout. The prior bar need not be the
               N-bar high, so the identity does not apply and the condition can refuse a trade.
               This is "was the trend already up before the break", which is a different and
               genuinely testable question.

THE SESSION WINDOW AND THE FLATTEN ARE PRICED, NOT ASSUMED. `CLAUDE.md` records nine independent
confirmations that the intraday constraint is destructive on this branch and that a fixed-time
flatten costs about half the per-trade edge -- it truncates exactly the trades a channel exit
exists to hold. Both are shipped because they were asked for, both default OFF, and both carry
their measured cost in the tooltip rather than a warning in prose.

THE FLATTEN FILLS AT THE NEXT BAR'S OPEN (`tensor_stop`'s `flat_mod` path), because
`strategy.close_all()` cannot sell the close of the bar that triggers it. The engine was changed to
match the script here, not the other way round.

`P["mod"]` is NEW YORK minutes of day, verified rather than assumed: mean volume by mod-hour on the
cached NQ bars jumps to 82,036 at 09:00 and peaks at 95,079 at 10:00, with 168 at 17:00 -- the CME
maintenance break. The raw timestamps are UTC and `mod` is not.

Usage: python3 research/v60/v60session.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))
sys.path.insert(0, os.path.join(HERE, "..", "v39"))

import v60core as V             # noqa: E402
import v38grid as G             # noqa: E402
import v39mc as MC              # noqa: E402
from v60_parity import PRESETS   # noqa: E402

WINDOWS = [("all hours", 0, 1440), ("09:30-11:00", 570, 660), ("09:30-12:00", 570, 720),
           ("08:00-12:00", 480, 720), ("09:30-16:00", 570, 960), ("10:00-16:00", 600, 960)]
FLATTENS = [("none", 0), ("12:00", 720), ("15:45", 945), ("16:00", 960)]
AROON_MODES = ["off", "osc>=0", "osc>=50", "osc>=-50", "up>=70"]


def available():
    """Only the markets whose bars are actually on disk. A container recycle wipes the uploaded
    feeds, so this is checked rather than assumed."""
    out = []
    for mk in V.MARKETS:
        try:
            V.load_market(mk, 60)
            out.append(mk)
        except Exception:
            pass
    return out


def mask(P, cfg, aroon, aroon_n, at_prior, lo_mod=0, hi_mod=1440, flat_mod=0, tf=60):
    """The signal set, with the Aroon read at the signal bar or the bar before it, and with an
    optional entry window in New York minutes of day.

    WHEN A FLATTEN IS ON, a signal whose fill bar is already at or past the cutoff is DROPPED. The
    engine would take it and close it at the same open for zero P&L; the shipped script refuses it
    (`not flatDue` guards the entry as well as the exit). Modelling the script is the point."""
    base = V.signal_mask(P, (cfg["mode"], cfg["ema_f"], cfg["ema_s"], cfg["win"], cfg["don_e"],
                             cfg["gate"], 0, "off"))
    if aroon != "off":
        a = P["aroon"][aroon_n][aroon]
        if at_prior:
            a = np.r_[False, a[:-1]]
        base = base & a
    if lo_mod > 0 or hi_mod < 1440:
        base = base & (P["mod"] >= lo_mod) & (P["mod"] < hi_mod)
    if flat_mod > 0:
        base = base & (P["mod"] + tf < flat_mod)
    return base


def score(P, cfg, m, flat_mod=0):
    keep = (G.COMM, G.EC, G.SE)
    G.COMM, G.EC, G.SE = 0.0, 0.0, 0.0
    try:
        xb, pnl, _why = G.tensor_stop(P, cfg["don_x"], cfg["stop"], cfg["tp"], flat_mod)
    finally:
        G.COMM, G.EC, G.SE = keep
    cut = int(P["n"] * V.SPLIT)
    out = []
    for lo, hi in ((0, cut), (cut, P["n"])):
        s = np.flatnonzero(m)
        s = s[(s >= lo) & (s < hi)].astype(np.int64)
        p_, _ = MC.gather(P, xb, pnl, s)
        if len(p_) == 0:
            out.append((0, np.nan, np.nan))
            continue
        gw = p_[p_ > 0].sum()
        gl = -p_[p_ <= 0].sum()
        out.append((len(p_), float(p_.mean() / P["pv"]),
                    float(gw / gl) if gl > 0 else np.nan))
    return out


def main():
    mks = available()
    print("=" * 104)
    print("12. THE AROON READING BAR, AND THE SESSION WINDOW / FLATTEN")
    print("=" * 104)
    print(f"  markets with bars on disk: {', '.join(mks) if mks else 'NONE'}")
    if not mks:
        print("  no feed is present -- re-upload the CSVs and re-run.")
        return
    print("  points per trade, GROSS. research n/pts/PF then locked n/pts/PF.\n")

    for name, cfg in PRESETS.items():
        print("=" * 104)
        print(f"  {name}: EMA {cfg['ema_f']}/{cfg['ema_s']} cross w{cfg['win']}, "
              f"don {cfg['don_e']}/{cfg['don_x']}, {cfg['stop']}N, {cfg['gate']}")
        for mk in mks:
            P = V.prep(60, mk)
            ident = "IDENTITY (aroon len <= donchian entry)" if 25 <= cfg["don_e"] else \
                "binds (aroon len > donchian entry)"
            print(f"\n  --- {mk}: AROON, length 25, read at the SIGNAL bar vs the PRIOR bar "
                  f"-- at donchian {cfg['don_e']} the signal-bar reading is {ident}")
            print(f"  {'aroon':<12}{'bar':<8}"
                  f"{'res n':>7}{'res pts':>10}{'res PF':>8}"
                  f"{'lock n':>8}{'lock pts':>10}{'lock PF':>9}")
            for ar in AROON_MODES:
                for at_prior in (False, True):
                    if ar == "off" and at_prior:
                        continue
                    m = mask(P, cfg, ar, 25, at_prior)
                    (rn, rp, rf), (ln, lp, lf) = score(P, cfg, m)
                    print(f"  {ar:<12}{'prior' if at_prior else 'signal':<8}"
                          f"{rn:>7d}{rp:>+10.2f}{rf:>8.2f}{ln:>8d}{lp:>+10.2f}{lf:>9.2f}")

            print(f"\n  --- {mk}: SESSION WINDOW (New York) x HARD FLATTEN")
            print(f"  {'window':<14}{'flatten':<9}"
                  f"{'res n':>7}{'res pts':>10}{'res PF':>8}"
                  f"{'lock n':>8}{'lock pts':>10}{'lock PF':>9}")
            for wn, lo, hi in WINDOWS:
                for fn, fm in FLATTENS:
                    if fm and hi < 1440 and fm < hi:
                        continue            # a flatten before the window closes is incoherent
                    m = mask(P, cfg, "off", 25, False, lo, hi, fm)
                    (rn, rp, rf), (ln, lp, lf) = score(P, cfg, m, fm)
                    print(f"  {wn:<14}{fn:<9}"
                          f"{rn:>7d}{rp:>+10.2f}{rf:>8.2f}{ln:>8d}{lp:>+10.2f}{lf:>9.2f}")


if __name__ == "__main__":
    main()
