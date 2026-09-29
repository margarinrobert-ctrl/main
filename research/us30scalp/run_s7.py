"""S7 -- detectability. The dispersion, not the mean, is what this window cannot overcome.

S6's diagnostic cleared the null (sd of the null mean / sd of the rule mean = 1.005-1.134, and the
null's trade count is stable at +-14) and in doing so produced the number that governs everything
else: **per-trade sd is 157.1 points on a mean of +0.68**. An estimate with 1,679 observations and
that dispersion has a standard error of 3.84 points, so the rule's entire edge is 0.18 standard
errors from zero and its excess over the null is 0.70 null sd. The p-value of 0.260 is not a
verdict on the rule; it is a statement that this sample cannot resolve effects of this size.

So the questions worth asking are:
  1. What is the SMALLEST edge this window could detect, at the trade counts it supplies?
  2. How much data would the observed edge need?
  3. And since dispersion is the binding constraint, does ranking the same grid by t-STATISTIC
     rather than by mean or profit factor choose a different geometry? Mean and detectability are
     different objectives and this branch has only ever optimised the first.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 250)
PTS = (20, 30, 40, 50, 75, 100, 150)
TGT = (20, 30, 40, 50, 75, 100, 150, 0)
HOLDS = (4, 8, 16)
Z80 = sps.norm.ppf(0.80) + sps.norm.ppf(0.975)      # 2.802, 80% power at alpha 0.05 two-sided


def cell(f, sig, sd, st, tg, hd, sessions):
    t = S.walk(f, sig, sd, stop_a=st, tgt_a=tg if tg > 0 else 1e9, hold=hd, flat=0, use_pts=1)
    if len(t) < 40:
        return None
    p = t["pts"].to_numpy()
    mu, s = p.mean(), p.std(ddof=1)
    se = s / np.sqrt(len(p))
    # day-level Sharpe, zero-filled over EVERY session in the block (STUDY_V17's rule)
    d = t.groupby(t.ts.dt.normalize())["pts"].sum()
    dd = np.zeros(max(sessions, len(d))); dd[:len(d)] = d.to_numpy()
    sh = dd.mean() / dd.std(ddof=1) * np.sqrt(252) if dd.std() > 0 else np.nan
    return dict(stop=st, target=tg, hold_h=hd * .25, n=len(p), pts=mu, sd=s, se=se,
                t=mu / se, sharpe=sh, pf=S.pf(p), win=float((p > 0).mean()),
                mde=Z80 * se, need_n=int((Z80 * s / mu) ** 2) if mu > 0 else -1,
                med_min=float(t["mins"].median()))


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res, hol = bl["A_research"], bl["B_holdout"]
    win = S.window(f)
    nsess = f.index[res & win].normalize().nunique()
    yrs = (f.index[res].max() - f.index[res].min()).days / 365.25
    print(f"research block: {nsess:,} sessions over {yrs:.2f} years")

    # ---- 1. what this window can and cannot detect -------------------------------------------
    print("\n=== 1. the smallest edge detectable at 80% power, by trade count ===")
    s2, d2 = S.TRIGGERS["fade n8 k2.0"](f)
    keep = np.isin(s2, np.flatnonzero(res))
    t = S.walk(f, s2[keep], d2[keep], stop_a=150, tgt_a=1e9, hold=16, flat=0, use_pts=1)
    sd = t["pts"].std(ddof=1)
    rows = []
    for n in (250, 500, 1000, t.shape[0], 5000, 20000, 100000):
        rows.append(dict(n_trades=n, years_at_this_rate=n / (len(t) / yrs),
                         MDE_pts=Z80 * sd / np.sqrt(n),
                         MDE_as_pct_of_stop=Z80 * sd / np.sqrt(n) / 150))
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    print(f"\nper-trade sd {sd:.1f} pts on a mean of {t['pts'].mean():+.3f}  ->  "
          f"the rule is {t['pts'].mean()/(sd/np.sqrt(len(t))):.2f} standard errors from zero")
    for eff in (0.683, 3.0, 5.0, 10.0):
        n = (Z80 * sd / eff) ** 2
        print(f"  to detect {eff:5.2f} pts/trade at 80% power: {n:>12,.0f} trades = "
              f"{n/(len(t)/yrs):>9,.0f} years at this window's rate")

    # ---- 2. and what PF targets imply ---------------------------------------------------------
    print("\n=== 2. the edge a given profit factor requires, and whether it is detectable ===")
    p = t["pts"].to_numpy()
    w, l = p[p > 0].mean(), -p[p < 0].mean()
    wr = float((p > 0).mean())
    print(f"observed: win {w:.2f} pts, loss {l:.2f} pts, win rate {wr:.4f}, PF {S.pf(p):.4f}")
    for target_pf in (1.1, 1.2, 1.5, 2.0):
        need_wr = target_pf * l / (w + target_pf * l)
        edge = need_wr * w - (1 - need_wr) * l
        n = (Z80 * sd / edge) ** 2 if edge > 0 else np.nan
        print(f"  PF {target_pf:<4} needs win rate {need_wr:.4f} (+{100*(need_wr-wr):.1f} pts) "
              f"= {edge:+7.2f} pts/trade  -> detectable in {n:,.0f} trades "
              f"({n/(len(t)/yrs):,.0f} yrs)")

    # ---- 3. rank the grid by t, not by mean --------------------------------------------------
    print("\n=== 3. the SAME 168-cell grid ranked three ways -- they choose different geometry ===")
    s2, d2 = S.TRIGGERS["donch20 long"](f)
    keep = np.isin(s2, np.flatnonzero(res))
    sig, sdd = s2[keep], d2[keep]
    rows = [r for st in PTS for tg in TGT for hd in HOLDS
            if (r := cell(f, sig, sdd, st, tg, hd, nsess)) is not None]
    G = pd.DataFrame(rows)
    print(f"{len(G)} cells")
    for by in ("pts", "t", "sharpe", "pf"):
        top = G.sort_values(by, ascending=False).head(3)
        print(f"\n-- best 3 by {by} --")
        print(top[["stop", "target", "hold_h", "n", "pts", "sd", "t", "sharpe", "pf", "win",
                   "med_min"]].round(3).to_string(index=False))

    print("\nMARGINAL AVERAGE by t-statistic (the detectability read):")
    for ax in ("stop", "target", "hold_h"):
        print(f"\n-- {ax} --")
        print(G.groupby(ax).agg(cells=("t", "size"), t=("t", "mean"), sharpe=("sharpe", "mean"),
                                pts=("pts", "mean"), sd=("sd", "mean"),
                                n=("n", "mean")).round(3).to_string())

    print(f"\ncorr(mean rank, t rank)      {sps.spearmanr(G.pts, G.t).statistic:+.3f}")
    print(f"corr(mean rank, Sharpe rank) {sps.spearmanr(G.pts, G.sharpe).statistic:+.3f}")
    print(f"corr(t rank, Sharpe rank)    {sps.spearmanr(G.t, G.sharpe).statistic:+.3f}")
    print(f"corr(PF rank, Sharpe rank)   {sps.spearmanr(G.pf, G.sharpe).statistic:+.3f}")

    # ---- 4. the Sharpe-chosen cell, read once ------------------------------------------------
    best = G.sort_values("sharpe", ascending=False).iloc[0]
    print(f"\n=== 4. the SHARPE-chosen cell read once: stop {best.stop:.0f} / target "
          f"{'none' if best.target == 0 else int(best.target)} / hold {best.hold_h}h ===")
    kw = dict(stop_a=float(best.stop), tgt_a=float(best.target) if best.target > 0 else 1e9,
              hold=int(best.hold_h * 4), flat=0, use_pts=1)
    out = []
    for feed, fname in ((f, "US30L"), (S.load("US30I"), "US30I")):
        for bn, bm in S.blocks(feed, fname).items():
            ss, dd_ = S.TRIGGERS["donch20 long"](feed)
            k = np.isin(ss, np.flatnonzero(bm))
            tt = S.walk(feed, ss[k], dd_[k], **kw)
            if len(tt) < 20:
                continue
            ns = feed.index[bm & S.window(feed)].normalize().nunique()
            ctl = S.control(feed, len(tt), tt["side"].to_numpy(), S.window(feed) & bm,
                            n_draw=400, seed=17, **kw)
            r = cell(feed, ss[k], dd_[k], best.stop, best.target, int(best.hold_h * 4), ns)
            r.update(feed=fname, block=bn, ctl=float(np.median(ctl)),
                     p=float(np.mean(ctl >= tt["pts"].mean())))
            out.append(r)
    O = pd.DataFrame(out)
    print(O[["feed", "block", "n", "pts", "sd", "t", "sharpe", "pf", "win", "ctl", "p",
             "med_min"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
