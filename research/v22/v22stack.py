"""Should the V22 adaptive stop ship on the BARE Donchian, or on the V20/V21 stack?

V22 was measured on the plain Donchian 30/20 long with a 2.0N stop and no target. That is NOT the
base V20 and V21 were built on, and three components were left out. Two of them were dropped on
evidence already in the studies; the third was dropped because it had never been tested WITH an
adaptive stop, which is a gap and not a judgement. This file closes the gap by measuring.

  linreg 50 confirmation   V20 measured all four declared readings. The best adds +0.005 R and the
                           most literal one is mechanically BACKWARDS on a breakout bar (12.1% of
                           breakout bars pass, against 50.5% of bars in general -- lift 0.24x).
  2R take profit           NO TAKE PROFIT has beaten every target tested on this branch seven
                           independent times.
  CHOP <= 45               THIS ONE EARNED ITS PLACE. V21: every ADX floor failed both blocks while
                           CHOP <= 45 cleared BOTH against a selectivity-matched control
                           (p 0.005 / 0.015). Leaving it out was not an evidence-based call.

So all three go back on the bench here, jointly with the adaptive stop, on both blocks. The branch's
standing prior is that stacking makes the holdout WORSE -- ADX>=25 + CHOP<=35 scored p 0.215 on
locked against CHOP<=35 alone at 0.083 -- so the joint test is the only thing that settles it.

ONE LIMITATION THAT CANNOT BE ARGUED AWAY. V21's CHOP result was POOLED OVER FIVE MARKETS. A
container recycle destroyed every feed except NQ, so this re-test is NQ only. A single-market
re-test is weaker evidence than the finding it is checking, and if CHOP fails here that is a
one-market disagreement, not a refutation.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
import v16core as C           # noqa: E402
import v20linreg as LR        # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as V            # noqa: E402
from v22stop import STATE, blocks, merged  # noqa: E402

CHOP_MAX = 45.0


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


def score(O, keep, sess):
    idx = C.take(O, keep)
    if len(idx) < 10:
        return None
    r = O["R"][idx]
    pf = r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan
    d = np.bincount(np.unique(sess[O["sig"][idx]], return_inverse=True)[1], weights=r)
    return dict(n=len(idx), R=float(r.mean()), pf=float(pf), win=float((r > 0).mean()),
                sharpe=float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std(ddof=1) > 0 else np.nan)


def control(O, pool, k, keepmask, draws=400, seed=11):
    """Random filters of the SAME selectivity, drawn from the same pool, same position lock."""
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool, size=k, replace=False)] = True
        idx = C.take(O, m)
        out[d] = float(O["R"][idx].mean()) if len(idx) else np.nan
    return out[np.isfinite(out)]


if __name__ == "__main__":
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        sig = C.signals(P, 1)
        sess = P["sess"]
        s = V.build(P["o"], P["h"], P["l"], P["c"])[STATE][sig]
        good = np.isfinite(s)
        low = np.where(good, s <= 0.5, False)

        ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
        lrv, _lrs, _lrr = LR.linreg(P["c"], 50)
        lr_ok = np.asarray(P["c"] > lrv)[sig]          # V20 reading C, the best of the four
        chop_ok = np.isfinite(ch) & (ch <= CHOP_MAX)

        res, lk = blocks(sess)
        res, lk = res[sig], lk[sig]

        ADAPT = merged(P, sig, 2.5, 1.5, low)
        FLAT = C.outcomes(P, 1, sig, stop_mult=2.0, tp_r=0.0)
        TP2 = merged(P, sig, 2.5, 1.5, low)   # placeholder, replaced below
        A25 = C.outcomes(P, 1, sig, stop_mult=2.5, tp_r=2.0)
        A15 = C.outcomes(P, 1, sig, stop_mult=1.5, tp_r=2.0)
        TP2 = dict(sig=sig, xb=np.where(low, A25["xb"], A15["xb"]),
                   R=np.where(low, A25["R"], A15["R"]),
                   why=np.where(low, A25["why"], A15["why"]))

        hdr(f"NQ {tf}m   PUTTING THE THREE DROPPED COMPONENTS BACK ON THE BENCH, jointly with the "
            f"adaptive stop")
        print(f"   CHOP(14) <= {CHOP_MAX:.0f} passes {float(chop_ok[good].mean()):.1%} of breakout "
              f"signals   |   linreg reading C passes {float(lr_ok[good].mean()):.1%}")
        print(f"\n   {'configuration':<44}{'RESEARCH':>30}{'|':>4}{'LOCKED':>30}")
        print(f"   {'':<44}{'n':>6}{'R/trade':>10}{'PF':>8}{'Sharpe':>6}{'|':>4}"
              f"{'n':>6}{'R/trade':>10}{'PF':>8}{'Sharpe':>6}")
        rows = [
            ("flat 2.0N, no target  (the old base)", FLAT, good),
            ("ADAPTIVE stop, no target  (SHIPPED)", ADAPT, good),
            ("ADAPTIVE + CHOP <= 45", ADAPT, good & chop_ok),
            ("ADAPTIVE + linreg C", ADAPT, good & lr_ok),
            ("ADAPTIVE + CHOP + linreg  (full V20/21 stack)", ADAPT, good & chop_ok & lr_ok),
            ("flat 2.0N + CHOP <= 45", FLAT, good & chop_ok),
            ("ADAPTIVE + 2R target", TP2, good),
        ]
        for lab, O, m in rows:
            line = f"   {lab:<44}"
            for blk in (res, lk):
                st = score(O, m & blk & (O["xb"] >= 0), sess)
                if st is None:
                    line += f"{'--':>6}{'':>10}{'':>8}{'':>6}"
                else:
                    line += (f"{st['n']:>6}{st['R']:>+10.4f}{st['pf']:>8.3f}"
                             f"{st['sharpe']:>6.2f}")
                if blk is res:
                    line += f"{'|':>4}"
            print(line)

        hdr(f"NQ {tf}m   DOES CHOP <= 45 BEAT A RANDOM FILTER OF THE SAME SELECTIVITY, on the "
            f"ADAPTIVE base?")
        print("   This is the V21 gate, re-run on the base V22 actually ships. Restrictiveness alone")
        print("   raises profit factor, so the only honest comparison is against equal selectivity.\n")
        print(f"   {'block':<12}{'n':>6}{'R/trade':>11}{'control mean':>15}{'excess':>10}{'p':>8}")
        for tag, blk in (("research", res), ("locked", lk)):
            pool = np.flatnonzero(blk & good & (ADAPT["xb"] >= 0))
            m = good & chop_ok & blk & (ADAPT["xb"] >= 0)
            idx = C.take(ADAPT, m)
            r = float(ADAPT["R"][idx].mean())
            k = int(m.sum())
            b = control(ADAPT, pool, k, m)
            print(f"   {tag:<12}{len(idx):>6}{r:>+11.4f}{b.mean():>+15.4f}{r-b.mean():>+10.4f}"
                  f"{float((b >= r).mean()):>8.3f}")


# ---------------------------------------------------------------------------------------------
# WHY THE STACK ADDS NOTHING: are CHOP and the volatility percentile the same filter?
# The branch has caught this twice already -- ADX and the efficiency ratio at rho 0.642, and eight
# literal duplicates in the condition pool. Two filters that select the same bars are one filter.
# ---------------------------------------------------------------------------------------------
def overlap():
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        sig = C.signals(P, 1)
        s = V.build(P["o"], P["h"], P["l"], P["c"])[STATE][sig]
        ch = RG.chop(P["h"], P["l"], P["c"], 14)[sig]
        g = np.isfinite(s) & np.isfinite(ch)
        calm = s <= 0.5
        keep = ch <= CHOP_MAX
        hdr(f"NQ {tf}m   ARE CHOP <= 45 AND THE VOLATILITY PERCENTILE THE SAME FILTER?")
        print(f"   correlation(CHOP, vol percentile) over breakout signals: "
              f"{np.corrcoef(ch[g], s[g])[0,1]:+.3f}")
        print(f"   share of signals CHOP keeps:                {float(keep[g].mean()):.1%}")
        print(f"   share of signals in the CALM (wide-stop) bucket: {float(calm[g].mean()):.1%}")
        print(f"   share of CHOP-kept signals that are also CALM:   "
              f"{float(calm[g & keep].mean()):.1%}")
        print(f"   share of CHOP-REJECTED signals that are CALM:    "
              f"{float(calm[g & ~keep].mean()):.1%}")
        lift = float(calm[g & keep].mean()) / float(calm[g].mean())
        print(f"   lift of CHOP toward the calm bucket: {lift:.2f}x"
              f"   (1.00x would mean the two filters are independent)")


if __name__ == "__main__":
    overlap()
