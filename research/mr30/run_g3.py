"""GATE 1 ON THE OVERNIGHT PREMIUM: three nulls, the mechanism's own gradient, and every year.

`run_g2` found the one US30 object with the right shape: the overnight leg is positive on all three
blocks (+0.0388 / +0.0167 / +0.0617 % of price a session, net of one round turn +0.0314 / +0.0094 /
+0.0566), it DECAYS across the research split, it comes back on a reserved forward block from a
DIFFERENT PROVIDER, and its research skew is -1.05 -- which is what the risk-transfer story predicts
and would have refuted it had the skew come back positive.

It has zero fitted parameters, so the multiplicity of this test is one. That is the whole argument
for running it: every US30 primary killed here carried four to ten tuned thresholds.

FOUR THINGS CAN STILL KILL IT AND ALL FOUR ARE RUN:
  1. A RANDOM HOLDING WINDOW OF THE SAME LENGTH, started uniformly within a day either side of the
     real one and held the same number of bars. This is the null that prices the CLOCK: if the
     premium is just "be long for 17 hours in a market that rose", a random 17-hour window earns it
     too. Re-simulated, not split out of realised trades.
  2. ALWAYS-LONG on the same sessions -- the 24-hour exposure the overnight leg is a subset of.
  3. THE MECHANISM'S OWN GRADIENT. The premium is compensation for gap risk, so it must be LARGER
     when there is more risk to transfer. Conditioned on the prior 20-session realised volatility,
     it must RISE. `STUDY_LEV_ETF_REBALANCE` and this study's own `run_g0` both died on exactly
     this test, so it is run before any p-value is believed.
  4. EVERY CALENDAR YEAR, because `STUDY_DL50` was a five-year run of one sign followed by three of
     the other and the split date sat on the boundary.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402
from mr30.run_g2 import RTH0, RTH1, boot  # noqa: E402


def legs(f):
    """Entry/exit BAR INDICES for the overnight leg, so a control can hold the same length."""
    g = f.copy()
    g["day"] = g.index.normalize()
    pos = np.arange(len(g))
    inr = (g["mod"] >= RTH0) & (g["mod"] < RTH1)
    r = g[inr]
    rp = pos[inr.to_numpy()]
    day = r["day"].to_numpy()
    last, first, cnt = {}, {}, {}
    for p, d in zip(rp, day):
        if d not in first:
            first[d] = p
            cnt[d] = 0
        last[d] = p
        cnt[d] += 1
    days = sorted(first)
    rows = []
    for a, b in zip(days[:-1], days[1:]):
        if cnt[a] < 20 or cnt[b] < 20:
            continue
        rows.append((last[a], first[b], b))
    e = np.array([r[0] for r in rows]); x = np.array([r[1] for r in rows])
    return e, x, pd.DatetimeIndex([r[2] for r in rows])


def ret_pct(f, e, x):
    c = f["close"].to_numpy(); o = f["open"].to_numpy()
    return 100.0 * (o[x] - c[e]) / c[e]


def rand_window(f, e, x, n_draw=400, seed=3):
    """Same LENGTH, random start within +-24h. Prices the clock, not the exposure."""
    rng = np.random.default_rng(seed)
    c = f["close"].to_numpy(); o = f["open"].to_numpy()
    L = x - e
    n = len(c)
    out = np.empty(n_draw)
    for k in range(n_draw):
        s = e + rng.integers(-96, 97, len(e))
        s = np.clip(s, 1, n - 2)
        t = np.clip(s + L, 1, n - 1)
        out[k] = np.mean(100.0 * (o[t] - c[s]) / c[s])
    return out


def main():
    cost_by = {}
    for feed in ("US30L", "US30I"):
        f = M.load(feed)
        e, x, days = legs(f)
        r = ret_pct(f, e, x)
        cost = 100.0 * M.COST / float(f["close"].median())
        cost_by[feed] = cost
        blk = M.blocks(f, feed)
        print(f"\n=== {feed}: {len(r)} overnight legs, mean length "
              f"{np.mean(x - e):.0f} bars ({np.mean(x - e) * 15 / 60:.1f} h), "
              f"round turn {cost:.4f}% ===")
        for bn, mask in blk.items():
            sel = np.array([bool(mask[i]) for i in e])
            if sel.sum() < 60:
                continue
            rr = r[sel] - cost
            ctl = rand_window(f, e[sel], x[sel]) - cost
            # always-long over the same span, per session
            c_ = f["close"].to_numpy()
            al = 100.0 * (c_[x[sel]] - c_[e[sel]][0]) / c_[e[sel]][0]
            al_sess = np.diff(np.r_[0.0, al])
            lo, hi, p0 = boot(rr)
            p_ctl = float(np.mean(ctl >= rr.mean()))
            sh = rr.mean() / rr.std(ddof=1) * np.sqrt(252)
            print(f"\n  {bn}: n={int(sel.sum())}  net {rr.mean():+.4f}%/session  "
                  f"Sharpe {sh:.2f}  win {np.mean(rr > 0):.3f}  skew {pd.Series(rr).skew():+.2f}")
            print(f"    day-block bootstrap 95% CI [{lo:+.4f}, {hi:+.4f}]  P(mean<=0) {p0:.3f}")
            print(f"    NULL 1 random same-length window: median {np.median(ctl):+.4f}%  "
                  f"p {p_ctl:.3f}   ({'CLEARS' if p_ctl <= 0.05 else 'fails'})")
            print(f"    NULL 2 always-long same sessions: {al_sess.mean():+.4f}%/session "
                  f"Sharpe {al_sess.mean() / al_sess.std(ddof=1) * np.sqrt(252):.2f}  "
                  f"({'overnight better' if sh > al_sess.mean() / al_sess.std(ddof=1) * np.sqrt(252) else 'ALWAYS-LONG BETTER'} risk-adjusted)")
            for mult, lab in ((2.0, "2x cost"), (4.0, "4x cost")):
                print(f"    {lab}: {(r[sel] - mult * cost).mean():+.4f}%/session")

    print("\n\n3. THE MECHANISM'S GRADIENT -- premium by prior 20-session realised volatility")
    print("   compensation for gap risk must RISE with the risk; if it falls, the story is wrong")
    f = M.load("US30L")
    e, x, days = legs(f)
    r = ret_pct(f, e, x) - cost_by["US30L"]
    sess = 100.0 * np.diff(np.r_[np.nan, f["close"].to_numpy()[x]]) / f["close"].to_numpy()[x]
    rv = pd.Series(sess).rolling(20).std().shift(1).to_numpy()
    blk = M.blocks(f)
    for bn, mask in blk.items():
        sel = np.array([bool(mask[i]) for i in e]) & np.isfinite(rv)
        q = np.nanquantile(rv[sel], [0.2, 0.4, 0.6, 0.8])
        edges = np.r_[-np.inf, q, np.inf]
        cells = [r[sel & (rv >= edges[i]) & (rv < edges[i + 1])].mean() for i in range(5)]
        sl = cells[-1] - cells[0]
        print(f"  {bn:<12} " + " ".join(f"{v:>+9.4f}" for v in cells) +
              f"   Q5-Q1 {sl:>+8.4f}  {'RISES' if sl > 0 else 'FALLS'}")

    print("\n4. EVERY CALENDAR YEAR (net %/session, US30L then the ISO forward block)")
    for feed in ("US30L", "US30I"):
        f = M.load(feed)
        e, x, days = legs(f)
        rr = ret_pct(f, e, x) - cost_by[feed]
        d = pd.DataFrame(dict(y=days.year, r=rr))
        if feed == "US30I":
            d = d[days >= M.ISO_FROM]
        g = d.groupby("y").r.agg(["size", "mean"])
        print(f"  {feed}: " + "  ".join(
            f"{int(y)} {row['mean']:+.4f}({int(row['size'])})" for y, row in g.iterrows()))
        print(f"    positive years: {int((g['mean'] > 0).sum())}/{len(g)}")


if __name__ == "__main__":
    main()
