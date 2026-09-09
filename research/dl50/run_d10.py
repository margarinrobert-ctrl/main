"""IS 2023-2025 BAD FOR THIS ARM, OR BAD FOR EVERYTHING IN THAT WINDOW?

`run_d9` settled two things and opened one.

  SETTLED: the gap is not a badly-placed cut. Slid across eleven cut points the research-minus-
  holdout gap on the 1.25 ATR arm is POSITIVE AT ALL ELEVEN, and the holdout half only turns
  negative once it is confined to 2023 and later. So something changed late in the sample.
  SETTLED: ten years cannot separate this arm from zero. The annual means run -0.160 to +0.147 with
  a standard deviation of 0.1075 around a year-weighted mean of ~+0.011.
  OPEN: whether the late block is a property of THE ARM or of THE WINDOW. Those need different
  answers -- the first says the mechanism decayed, the second says 07:00-11:00 stopped paying and
  every entry in it went with it.

So this splits the walk-forward at the research cut and then runs the framing test the branch uses
everywhere: on the SAME bars and the SAME block, compare the arm against (a) a random entry with
its geometry, (b) always-long with its geometry, (c) the same rule with no session window at all.
If the controls are negative too, the arm did not decay -- the window did, and that is a much
cheaper thing to know.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402
from dl50.run_d9 import build, slice_, walk_forward  # noqa: E402

CUT = pd.Timestamp("2023-05-01")
HOLD, TGT_R, STOP = 96, 3.0, 1.25


def wf_split(cells):
    print("2b. THE WALK-FORWARD SPLIT AT THE RESEARCH CUT (2023-05)")
    print("    Folds whose TEST window post-dates the cut are the only honest ones -- the fixed")
    print("    arms have seen everything before it.")
    for scheme, ty in (("rolling", 3), ("expanding", 0)):
        w = walk_forward(cells, scheme, ty, np.random.default_rng(7))
        pre = w[w.year < 2023]; post = w[w.year >= 2023]
        print(f"\n  {scheme.upper():<10}{'folds':>7}{'re-chosen':>11}{'fixed 1.25':>12}"
              f"{'50/150 pts':>12}{'random':>9}")
        for nm, d in (("pre-cut", pre), ("POST-CUT", post), ("all", w)):
            if not len(d):
                continue
            print(f"  {nm:<10}{len(d):>7}{d.chosen.mean():>11.4f}{d.fixed.mean():>12.4f}"
                  f"{d.point.mean():>12.4f}{d.rnd.mean():>9.4f}")
        print(f"  {'post +ve':<10}{'':>7}"
              f"{f'{int((post.chosen>0).sum())}/{len(post)}':>11}"
              f"{f'{int((post.fixed>0).sum())}/{len(post)}':>12}"
              f"{f'{int((post.point>0).sum())}/{len(post)}':>12}"
              f"{f'{int((post.rnd>0).sum())}/{len(post)}':>9}")


def framing(f):
    """Same block, same geometry: the rule, a random entry, always-long, and no window."""
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    ones = np.ones(len(c), np.int64)
    rng = np.random.default_rng(3)
    inwin = (mod >= 420) & (mod < 660)

    def blocks(ts, v):
        ts = pd.DatetimeIndex(ts)
        return {"research": v[ts < CUT], "HOLDOUT": v[ts >= CUT]}

    rows = []

    eb, r, rr, sd, hl, why, amb = D.walk_atr(o, h, l, c, at, eh, el, ou, od, STOP, TGT_R, HOLD,
                                             D.COST, 420, 660, mod, -1, ones)
    rule = blocks(f.index[eb], rr)
    n_by = {k: len(v) for k, v in rule.items()}
    for k, v in rule.items():
        rows.append(("the arm, 07:00-11:00", k, len(v), v.mean(), D.pf(v)))

    # (a) random entry inside the window, same geometry, same count, re-simulated with the lock
    elig = np.flatnonzero(inwin & np.isfinite(at) & (at > 0))
    elig = elig[(elig > 300) & (elig < len(c) - 2)]
    for k in ("research", "HOLDOUT"):
        want = n_by[k]
        sel = elig[(f.index[elig] < CUT)] if k == "research" else elig[(f.index[elig] >= CUT)]
        ms = []
        for _ in range(200):
            pick = np.sort(rng.choice(sel, size=min(want * 3, len(sel)), replace=False))
            side = rng.choice(np.array([-1, 1]), size=len(pick))
            out, rr2 = D.walk_at_atr(o, h, l, c, at, pick.astype(np.int64),
                                     side.astype(np.int64), STOP, TGT_R, HOLD, D.COST, mod, -1)
            g = rr2[np.isfinite(rr2)]
            if len(g) >= 20:
                ms.append(g.mean())
        rows.append(("  random entry in window", k, len(sel), float(np.mean(ms)), np.nan))
        p = float(np.mean(np.array(ms) >= rule[k].mean()))
        rows.append((f"  -> control p", k, 0, p, np.nan))

    # (b) always-long in the window, same geometry
    ebl, rl, rrl, *_ = D.walk_atr(o, h, l, c, at, np.full(len(c), -1e18), np.full(len(c), -1e18),
                                  ones, np.zeros(len(c), np.int64), STOP, TGT_R, HOLD,
                                  D.COST, 420, 660, mod, -1, ones)
    for k, v in blocks(f.index[ebl], rrl).items():
        rows.append(("  always-long in window", k, len(v), v.mean(), D.pf(v)))

    # (c) the same rule with NO session window
    eba, ra, rra, *_ = D.walk_atr(o, h, l, c, at, eh, el, ou, od, STOP, TGT_R, HOLD,
                                  D.COST, -1, -1, mod, -1, ones)
    for k, v in blocks(f.index[eba], rra).items():
        rows.append(("  the arm, ALL HOURS", k, len(v), v.mean(), D.pf(v)))

    print("\n4. THE FRAMING TEST -- same block, same geometry (1.25 ATR / 3R)")
    print(f"{'arm':<28}{'block':<10}{'n':>7}{'mean R':>10}{'PF':>9}")
    for a, b, n, m, p in rows:
        if a.startswith("  -> control"):
            print(f"{a:<28}{b:<10}{'':>7}{m:>10.3f}{'':>9}")
        else:
            print(f"{a:<28}{b:<10}{n:>7}{m:>10.4f}{p if np.isfinite(p) else 0:>9.3f}")


def weighting(cells):
    t = cells[(STOP, "none")]
    yr = t.assign(y=pd.DatetimeIndex(t.ts).year).groupby("y").R.agg(["mean", "size"])
    print("\n5. THE WEIGHTING DISAGREES, AND THE BAD YEARS ARE THE BUSY ONES")
    print(f"  trade-weighted mean R {t.R.mean():+.4f}   year-weighted {yr['mean'].mean():+.4f}")
    rho = np.corrcoef(yr["size"], yr["mean"])[0, 1]
    print(f"  corr(trades in a year, that year's mean R) = {rho:+.3f}  "
          f"({'busy years are worse' if rho < 0 else 'busy years are better'})")
    print(f"  {'year':<6}{'n':>6}{'mean R':>10}")
    for y, r in yr.iterrows():
        print(f"  {y:<6}{int(r['size']):>6}{r['mean']:>10.4f}")


def main():
    f = D.load(15)
    cells = build(f)
    wf_split(cells)
    framing(f)
    weighting(cells)


if __name__ == "__main__":
    main()
