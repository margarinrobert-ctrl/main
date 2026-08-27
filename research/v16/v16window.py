"""What a trading window does to V16, measured before the knob is shipped.

A SMALL FIXED SET, NOT A SEARCH. Seven windows and two flatten choices are tested, chosen because
they are the sessions people actually name -- not swept over every start and end, which would hand
the search a free lottery over a sample where the intraday constraint has already failed eleven
independent times. The set is fixed in advance, the count is stated, and the default that ships is
the one that was measured in STUDY_V16_MOMENTUM: no window at all.

`mod` IS NEW YORK MINUTES. Verified here rather than assumed: volume by minute-of-day peaks at
570, 600, 630 and 930, which is the 09:30 equity open, the hour after it, and the 15:30 close ramp.
Pine's bare `hour`/`minute` are EXCHANGE time -- Chicago for CME -- so the script must read
`hour(time, "America/New_York")` explicitly or every level in it is an hour off.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C          # noqa: E402
import v16phase2 as P2       # noqa: E402

TF, EXIT_N, STOP = 30, 20, 2.0
WINDOWS = [("all hours", 0, 1440), ("07:00-11:00", 420, 660), ("08:00-12:00", 480, 720),
           ("09:30-11:00", 570, 660), ("09:30-12:00", 570, 720), ("09:30-16:00", 570, 960),
           ("13:00-16:00", 780, 960)]


def run(P, side, block, lo, hi, flat_mod=0):
    sig_all = C.signals(P, side)
    mod = P["mod"]
    m = block[sig_all] & (mod[sig_all] >= lo) & (mod[sig_all] < hi)
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=STOP, tp_r=0.0, flat_mod=flat_mod)
    idx = C.take(O, np.ones(len(sig), bool))
    return O, idx, C.stats(O, idx, P["sess"])


def control(P, side, block, lo, hi, O, idx, draws=2000, flat_mod=0):
    """Random entries at the SAME minutes of day inside the same window -- the only fair null for a
    session rule, because a window with no rule is itself a strategy."""
    rng = np.random.default_rng(20260827)
    mod = P["mod"]
    if len(idx) < 15:
        return np.array([]), np.nan
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0)
                          & (mod >= lo) & (mod < hi))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, side, elig.astype(np.int64), stop_mult=STOP, tp_r=0.0, flat_mod=flat_mod)
    pos = {v: i for i, v in enumerate(elig)}
    tot = np.empty(draws)
    real = O["R"][idx].sum()
    for d in range(draws):
        pick = np.concatenate([rng.choice(by[m], size=min(k, len(by[m])), replace=False)
                               for m, k in want.items() if len(by[m])])
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in np.sort(pick)]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return tot, float((tot >= real).mean())


if __name__ == "__main__":
    P, pool, res, lock = P2.ctx(TF, exit_n=EXIT_N)
    print("=" * 110)
    print(f"THE ENTRY WINDOW ON V16 -- Donchian 30/{EXIT_N}, market order, long, {TF}m, no flatten")
    print("=" * 110)
    print("   Seven windows, fixed in advance, not swept. Entries are restricted; an open trade")
    print("   still exits on its own stop and channel however long that takes.\n")
    hdr = (f"   {'window':<14}{'res n':>7}{'res R':>9}{'res R/t':>9}{'res PF':>8}{'res Shp':>9}"
           f"{'lock n':>8}{'lock R':>9}{'lock R/t':>10}{'lock PF':>9}{'lock Shp':>10}{'ctl p':>8}")
    print(hdr); print("   " + "-" * (len(hdr) - 3))
    for lab, lo, hi in WINDOWS:
        Or, ir, sr = run(P, 1, res, lo, hi)
        Ol, il, sl = run(P, 1, lock, lo, hi)
        _c, p = control(P, 1, lock, lo, hi, Ol, il)
        print(f"   {lab:<14}{sr['n']:>7}{sr['R']:>+9.1f}{sr['perR']:>+9.4f}{sr['pf']:>8.3f}"
              f"{sr.get('sharpe', np.nan):>9.2f}{sl['n']:>8}{sl['R']:>+9.1f}{sl['perR']:>+10.4f}"
              f"{sl['pf']:>9.3f}{sl.get('sharpe', np.nan):>10.2f}"
              f"{(f'{p:.3f}' if np.isfinite(p) else '  n/a'):>8}")

    print("\n" + "=" * 110)
    print("AND THE FLATTEN -- forcing the trade out, filled at the NEXT OPEN as a script must")
    print("=" * 110)
    print(f"   {'window':<14}{'flatten':>10}{'res n':>7}{'res R/t':>10}{'res PF':>9}"
          f"{'lock n':>8}{'lock R/t':>10}{'lock PF':>9}")
    for lab, lo, hi in [("all hours", 0, 1440), ("09:30-16:00", 570, 960), ("09:30-11:00", 570, 660)]:
        for fm, ftag in ((0, "none"), (960, "16:00"), (1140, "19:00")):
            Or, ir, sr = run(P, 1, res, lo, hi, flat_mod=fm)
            Ol, il, sl = run(P, 1, lock, lo, hi, flat_mod=fm)
            print(f"   {lab:<14}{ftag:>10}{sr['n']:>7}{sr['perR']:>+10.4f}{sr['pf']:>9.3f}"
                  f"{sl['n']:>8}{sl['perR']:>+10.4f}{sl['pf']:>9.3f}")


def combo_table():
    """The four combinations the script's two new inputs can produce, both blocks, one control."""
    P, pool, res, lock = P2.ctx(TF, exit_n=EXIT_N)
    print("\n" + "=" * 110)
    print("THE FOUR COMBINATIONS THE TWO NEW INPUTS PRODUCE -- both blocks")
    print("=" * 110)
    print(f"   {'configuration':<28}{'res n':>7}{'res R':>9}{'res R/t':>10}{'res PF':>9}"
          f"{'lock n':>8}{'lock R':>9}{'lock R/t':>10}{'lock PF':>9}{'lock Shp':>10}")
    for lab, win, fm in [("window off, flatten off", None, 0),
                         ("window off, flatten 16:00", None, 960),
                         ("08:00-12:00, flatten off", (480, 720), 0),
                         ("08:00-12:00, flatten 16:00", (480, 720), 960)]:
        _O, _i, sr, _k = P2.leg(P, pool, 1, res, None, 0, win=win, flat_mod=fm)
        _O, _i, sl, _k = P2.leg(P, pool, 1, lock, None, 0, win=win, flat_mod=fm)
        print(f"   {lab:<28}{sr['n']:>7}{sr['R']:>+9.1f}{sr['perR']:>+10.4f}{sr['pf']:>9.3f}"
              f"{sl['n']:>8}{sl['R']:>+9.1f}{sl['perR']:>+10.4f}{sl['pf']:>9.3f}"
              f"{sl.get('sharpe', np.nan):>10.2f}")
    print("\n   Seven windows and three flatten times were tested in total. At that multiplicity a")
    print("   single p of 0.024 corrects to 0.168, so the window is a CANDIDATE, not a finding.")
