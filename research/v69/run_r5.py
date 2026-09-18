"""R5 -- does a SCALE-FREE minimum range rescue Asia and London?

THE PREDICTION IS WRITTEN DOWN BEFORE THE RUN, because it is the whole point of the test.

`STUDY_V69_ORB` established that Asia and London lose while New York does not, and attributed it to
arithmetic: a fixed 1.72-point round turn is ~6% of an Asia stop and ~1.8% of a New York stop. If
that attribution is RIGHT, then filtering to larger ranges must show one specific signature --

    GROSS profit factor FLAT across the range buckets, NET profit factor rising with them.

Because a range filter cannot change what a market does; it can only change the denominator the
fixed cost is divided by. A gate that lifts GROSS as well is doing something else, and the
something else has to clear a control before it is called an edge.

The corollary decides whether any of this is worth trading: if gross PF on Asia/London sits at
~1.00 in EVERY bucket, then a perfect cost fix takes those sessions to break-even and no further,
and the right answer is still to drop them.

THREE GATES, one of which is the script's own:
  C  `rng_min` in POINTS          -- the shipped input; cannot mean the same thing in two sessions
  B  range as a PERCENT OF PRICE  -- what "cost is a fraction of risk" literally asks for
  A  range as a MULTIPLE OF ATR   -- the same idea keyed on realised volatility instead of level

Scored on the research block, then a same-selectivity random filter over SESSION INSTANCES, and
only then one locked read.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from v69 import v69core as V  # noqa: E402

pd.set_option("display.width", 200)
BAR = "=" * 110


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def blocks(d):
    """First 65% of SESSION INSTANCES is research, exactly as the rest of the study splits it."""
    ks = np.unique(d.loc[d.skey > 0, "skey"].to_numpy())
    ks = np.sort(ks)
    cut = ks[int(0.65 * len(ks))]
    return cut


def score(t, cost_label="net"):
    if len(t) < 5:
        return dict(n=len(t), win=np.nan, pf=np.nan, pct=np.nan, total=np.nan)
    x = t.pct.to_numpy() if cost_label == "net" else t.gross_pct.to_numpy()
    return dict(n=len(t), win=float((x > 0).mean()),
                pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)),
                pct=float(x.mean()), total=float(x.sum()))


def main():
    d = V.sessionize(V.load())
    av = V.atr(d, 14)
    cut = blocks(d)
    print(f"rows {len(d):,}   research/locked cut at session key {cut}")

    def run(**kw):
        kw.setdefault("cost_pts", V.RT_POINTS)
        return V.walk(d, atr_arr=av, **kw)

    # ---------------------------------------------------------------- R5.0 reproduction
    hdr("R5.0  REPRODUCTION -- the patch must not have moved the shipped numbers")
    t = run(**{k: v for k, v in V.SHIPPED.items()})
    g = score(t, "gross"); nt = score(t, "net")
    print(f"  shipped GROSS  n {g['n']:>5}  win {g['win']:.3f}  PF {g['pf']:.3f}  total {g['total']:+.2f}")
    print(f"  shipped NET    n {nt['n']:>5}  win {nt['win']:.3f}  PF {nt['pf']:.3f}  total {nt['total']:+.2f}")
    print("  (STUDY_V69_ORB published 6,163 / 1.064 gross / 0.938 net)")

    # ---------------------------------------------------------------- R5.1 cost as a fraction of risk
    hdr("R5.1  COST AS A FRACTION OF RISK -- the quantity the arithmetic is about")
    print(f"  {'session':<9}{'n':>6}{'med rng':>10}{'med risk%':>11}{'cost/risk':>11}"
          f"{'BE win':>9}{'actual':>9}{'gap':>8}")
    for k, nm in enumerate(("asia", "london", "ny")):
        s = t[t.sid == k]
        if len(s) < 5:
            continue
        cf = float(s.cost_frac.median())
        # driftless break-even with cost expressed in R: (1 + c) / (1 + rr) is the win rate needed
        be = (1.0 + cf) / (1.0 + V.SHIPPED["rr"])
        aw = float((s.pct.to_numpy() > 0).mean())
        print(f"  {nm:<9}{len(s):>6}{s.rng.median():>10.1f}{s.risk_pct.median():>11.3f}"
              f"{cf:>11.3f}{be:>9.3f}{aw:>9.3f}{aw - be:>+8.3f}")

    # ---------------------------------------------------------------- R5.2 the three gates
    hdr("R5.2  THE THREE MINIMUM-RANGE GATES, RESEARCH BLOCK, GROSS BESIDE NET")
    print("  The signature to look for: gross FLAT, net RISING. That is a cost fix and nothing more.")
    LADDERS = [("C  points", "rng_min", [0, 10, 15, 20, 30, 40, 60]),
               ("B  pct of price", "rng_min_pct", [0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]),
               ("A  x ATR(14)", "rng_min_atr", [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])]
    keep = {}
    for name, arg, rungs in LADDERS:
        for k, nm in enumerate(("asia", "london", "ny")):
            print(f"\n  {name}   session {nm}")
            print(f"    {'rung':>8}{'n':>7}{'kept%':>8}{'grossPF':>10}{'netPF':>9}"
                  f"{'net%/tr':>10}{'cost/risk':>11}")
            base_n = None
            for r in rungs:
                tt = run(sessions=(nm,), **{arg: r})
                tt = tt[tt.skey < cut]
                if base_n is None:
                    base_n = max(len(tt), 1)
                if len(tt) < 5:
                    print(f"    {r:>8}{len(tt):>7}   -- too few trades")
                    continue
                gg, nn = score(tt, "gross"), score(tt, "net")
                print(f"    {r:>8}{len(tt):>7}{100.0*len(tt)/base_n:>8.1f}{gg['pf']:>10.3f}"
                      f"{nn['pf']:>9.3f}{nn['pct']:>+10.4f}{tt.cost_frac.median():>11.3f}")
                keep[(arg, r, nm)] = (len(tt), gg["pf"], nn["pf"], nn["pct"])

    # ---------------------------------------------------------------- R5.3 the control
    hdr("R5.3  SAME-SELECTIVITY RANDOM FILTER over SESSION INSTANCES")
    print("  A gate that keeps the biggest ranges also keeps FEWER trades, and restrictiveness")
    print("  alone raises PF on this branch. The null keeps the same NUMBER of session instances,")
    print("  drawn at random, and the strategy is RE-SIMULATED under it.")
    rng = np.random.default_rng(7)
    print(f"\n  {'session':<9}{'gate':<20}{'kept':>6}{'rule net%':>11}{'ctl med':>10}"
          f"{'p':>8}{'verdict':>10}")
    for nm in ("asia", "london", "ny"):
        full = run(sessions=(nm,))
        full = full[full.skey < cut]
        allk = np.unique(full.skey.to_numpy())
        for arg, r in (("rng_min_atr", 1.5), ("rng_min_atr", 2.0), ("rng_min_pct", 0.25)):
            tt = run(sessions=(nm,), **{arg: r})
            tt = tt[tt.skey < cut]
            if len(tt) < 20:
                continue
            obs = float(tt.pct.mean())
            m = len(np.unique(tt.skey.to_numpy()))
            draws = []
            for _ in range(400):
                sub = set(rng.choice(allk, size=min(m, len(allk)), replace=False).tolist())
                c = full[full.skey.isin(sub)]
                if len(c) >= 5:
                    draws.append(float(c.pct.mean()))
            draws = np.array(draws)
            p = float((draws >= obs).mean())
            print(f"  {nm:<9}{arg + ' ' + str(r):<20}{len(tt):>6}{obs:>+11.4f}"
                  f"{np.median(draws):>+10.4f}{p:>8.3f}{('PASS' if p <= 0.05 else 'fail'):>10}")




def closing():
    """R5.4 -- the ceiling. What is the gross edge, and can a cost fix ever reach it?

    A minimum-range gate can only push NET up toward GROSS. So the question that ends the family
    is not "does the gate help" but "what is gross, and is gross above one".
    """
    d = V.sessionize(V.load())
    av = V.atr(d, 14)
    cut = blocks(d)
    hdr("R5.4  THE CEILING -- gross win rate against the driftless bound the geometry demands")
    be = 1.0 / (1.0 + V.SHIPPED["rr"])
    print(f"  RR {V.SHIPPED['rr']} => driftless break-even win rate {be:.4f} at ZERO cost.\n")
    print(f"  {'session':<9}{'block':<10}{'n':>7}{'gross win':>11}{'need':>8}{'gap':>8}"
          f"{'grossPF':>10}{'ceiling':>10}")
    for nm in ("asia", "london", "ny"):
        for lab, sel in (("research", lambda x: x.skey < cut), ("locked", lambda x: x.skey >= cut)):
            tt = V.walk(d, sessions=(nm,), atr_arr=av, cost_pts=V.RT_POINTS)
            tt = tt[sel(tt)]
            if len(tt) < 5:
                continue
            gx = tt.gross_pct.to_numpy()
            w = float((gx > 0).mean())
            pf = float(gx[gx > 0].sum() / max(-gx[gx < 0].sum(), 1e-9))
            print(f"  {nm:<9}{lab:<10}{len(tt):>7}{w:>11.4f}{be:>8.4f}{w - be:>+8.4f}"
                  f"{pf:>10.3f}{('reachable' if pf > 1.0 else 'NONE'):>10}")
    print("\n  'ceiling' is what a PERFECT cost fix could deliver: a range gate moves net toward")
    print("  gross and can never pass it. Where gross PF <= 1.00 the session is unrescuable by any")
    print("  filter on range, because there is nothing under the cost to uncover.")


if __name__ == "__main__":
    main()
    closing()
