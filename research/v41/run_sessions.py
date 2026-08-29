"""V41 -- what a trading session costs these three configurations.

They were selected and measured with NO session constraint. Adding one is a real change to the
strategy, not a cosmetic input, so it is measured before it is shipped. `CLAUDE.md` records the
intraday constraint costing ~88% of the result on a different family and a fixed-time flatten
costing about half the per-trade edge where the exit is a channel -- and these are 60-MINUTE
configurations whose exit is a 10- or 20-bar channel, so the flatten truncates precisely the
trades the channel exists to hold.

Windows are hour-aligned because the bars are: this feed resamples to 60-minute bars stamped on
the hour, so a 09:30 start is indistinguishable from 10:00 and would be a false precision.

Entries are restricted to the window; EXITS are never restricted except by the hard flatten,
which fills at the NEXT bar's open exactly as `strategy.close_all()` does.

Usage: python3 research/v41/run_sessions.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v41")
import v38grid as G          # noqa: E402
from pine_parity import CANDS, script_walk, _pf            # noqa: E402
from run_v41c import market_prep                           # noqa: E402

WINDOWS = [
    ("all hours (as measured)", None),
    ("08:00-16:00", (480, 960, 960)),
    ("09:00-16:00", (540, 960, 960)),
    ("09:00-17:00", (540, 1020, 1020)),
    ("10:00-16:00", (600, 960, 960)),
    ("08:00-20:00", (480, 1200, 1200)),
    ("13:00-21:00", (780, 1260, 1260)),
    ("09:00-12:00", (540, 720, 720)),
]


def main():
    print("=" * 118)
    print("V41 -- THE COST OF A SESSION WINDOW, US100 60-minute, script order model")
    print("=" * 118)
    print("   entries restricted to the window; a hard flatten at its end, filling at the NEXT open.")
    print("   The 'all hours' row is the configuration as measured and published.\n")
    rows = []
    for mkt in ("US100L", "US30L"):
        P = market_prep(mkt, 60)
        print(f"   ===== {mkt.replace('L', '')} =====")
        print(f"   {'window':<24}" + "".join(f"{nm:>26}" for nm in CANDS))
        print(f"   {'':<24}" + "".join(f"{'n':>7}{'PF':>8}{'$/trade':>11}" for _ in CANDS))
        for wnm, w in WINDOWS:
            cells = []
            for cnm, cfg in CANDS.items():
                t = script_walk(P, cfg, anchor_close=True, exit_next_open=True, sess=w)
                if len(t) < 10:
                    cells.append((0, np.nan, np.nan))
                    rows.append(dict(mkt=mkt, win=wnm, cand=cnm, n=len(t), pf=np.nan, usd=np.nan))
                    continue
                p = t.pnl.to_numpy()
                cells.append((len(t), _pf(p), float(p.mean())))
                rows.append(dict(mkt=mkt, win=wnm, cand=cnm, n=len(t), pf=_pf(p),
                                 usd=float(p.mean()),
                                 flat_share=float((t.why == 3).mean())))
            print(f"   {wnm:<24}" + "".join(
                f"{c[0]:>7}{c[1]:>8.3f}{c[2]:>+11.2f}" if c[0] else f"{'--':>26}" for c in cells))
        print()
    T = pd.DataFrame(rows)
    T.to_csv("research/v41/v41_sessions.csv", index=False)

    print("=" * 118)
    print("VERDICT")
    print("=" * 118)
    base = T[T.win == "all hours (as measured)"].set_index(["mkt", "cand"])
    for mkt in ("US100L", "US30L"):
        sub = T[(T.mkt == mkt) & (T.win != "all hours (as measured)")]
        better = 0
        tot = 0
        for _i, r in sub.iterrows():
            b = base.loc[(mkt, r.cand)]
            if np.isfinite(r.usd) and np.isfinite(b.usd):
                tot += 1
                better += int(r.usd > b.usd)
        print(f"   {mkt.replace('L', ''):<8} windows beating all-hours on $/trade: {better} of {tot}")
    best = T[(T.mkt == 'US100L') & (T.win != 'all hours (as measured)')]
    if len(best.dropna(subset=['usd'])):
        b = best.loc[best.usd.idxmax()]
        print(f"   best US100 windowed cell: {b.win} / {b.cand} at {b.usd:+.2f} $/trade over "
              f"{int(b.n)} trades")
    if "flat_share" in T:
        fs = T[(T.win != "all hours (as measured)")].flat_share.dropna()
        if len(fs):
            print(f"   share of trades ended by the CLOCK rather than by the rule: "
                  f"median {fs.median():.1%}, max {fs.max():.1%}")


if __name__ == "__main__":
    main()
