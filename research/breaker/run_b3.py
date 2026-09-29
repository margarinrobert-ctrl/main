"""B3 -- the benchmarks. Random entries (50 seeds), buy and hold, walk-forward, deflated Sharpe.

RESEARCH BLOCK ONLY. The holdout is opened once, in run_b4.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import bbcore as B  # noqa: E402
# the skill directory goes AFTER research/ on sys.path -- CLAUDE.md records `metrics`/`splits`
# being shadowed when it went first
sys.path.append("/root/.claude/skills/synced/"
                "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
                "mechanism-first-alpha/scripts")
import gates  # noqa: E402

pd.set_option("display.width", 210)
BAR = "=" * 104
PRIM = (("A  2R", 2.0), ("B  no target", 0.0))


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    f = B.load()
    a = B.atr(f)
    cut = B.split_date(f)
    D = B.both_sides(f, a)
    fr = f[f.index < cut]
    print(f"  research block {f.index[0]} -> {cut}   ({len(fr):,} bars)")

    hdr("B3.1  RANDOM ENTRIES AT THE SAME FREQUENCY -- 50 seeds, risk matched trade for trade")
    print("  Same trade count, same side mix, same risk distribution, same target, same cap,")
    print("  same position lock, entries drawn uniformly and SORTED before the walk.\n")
    print(f"  {'primary':<14}{'rule %/tr':>11}{'ctl mean':>10}{'ctl sd':>9}{'ctl p5':>9}"
          f"{'ctl p95':>10}{'p(ctl>=rule)':>14}{'rule PF':>9}{'ctl PF':>8}")
    store = {}
    for lab, rr in PRIM:
        t = B.walk(f, a, D, rr)
        r = t[pd.DatetimeIndex(t.ts) < cut]
        store[lab] = (t, r)
        obs = float(r.pct.mean())
        hi_bar = int(np.searchsorted(f.index.to_numpy(), np.datetime64(cut)))
        cs, cp = [], []
        for sd in range(50):
            cc = B.random_control(fr, r, rr, sd, hi=hi_bar - B.HOLD_CAP - 2)
            cs.append(float(cc.pct.mean()))
            cp.append(B.stats(cc)["pf"])
        cs = np.array(cs)
        print(f"  {lab:<14}{obs:>+11.5f}{cs.mean():>+10.5f}{cs.std(ddof=1):>9.5f}"
              f"{np.percentile(cs,5):>+9.5f}{np.percentile(cs,95):>+10.5f}"
              f"{(cs >= obs).mean():>14.3f}{B.stats(r)['pf']:>9.3f}{np.mean(cp):>8.3f}")
    print("\n  p(ctl>=rule) is the share of 50 random-entry books that BEAT the rule.")

    hdr("B3.2  BUY AND HOLD over the same window")
    for lab, sl in (("research", f.index < cut), ("full sample", f.index == f.index)):
        seg = f[sl]
        bh = 100.0 * (seg["close"].iloc[-1] - seg["open"].iloc[0]) / seg["open"].iloc[0]
        dr = seg["close"].resample("1D").last().dropna().pct_change().dropna()
        sh = float(dr.mean() / dr.std(ddof=1) * np.sqrt(252))
        eq = (1 + dr).cumprod()
        dd = float(((eq.cummax() - eq) / eq.cummax()).max())
        print(f"  {lab:<12} total {bh:>+8.2f}%   ann Sharpe {sh:>+6.3f}   maxDD {100*dd:>6.2f}%")
    for lab, _ in PRIM:
        t, r = store[lab]
        s = B.stats(r)
        sh, _ = B.daily_sharpe(r, fr)
        print(f"  {lab:<12} total {s['total']:>+8.2f}%   ann Sharpe {sh:>+6.3f}   "
              f"maxDD {s['dd']:>6.2f}%  (sum of per-trade %, one unit, not compounded)")

    hdr("B3.3  WALK-FORWARD -- rolling quarters inside the research block")
    print("  Nothing is fitted (every parameter was frozen by the user before the first run), so")
    print("  this is a stability read across time, not a re-selection test.\n")
    print(f"  {'primary':<14}{'quarter':<10}{'n':>7}{'%/trade':>10}{'PF':>8}{'ann Sharpe':>12}")
    wf = {}
    for lab, _ in PRIM:
        t, r = store[lab]
        q = pd.PeriodIndex(pd.DatetimeIndex(r.ts), freq="Q")
        rows = []
        for pq in sorted(q.unique()):
            sub = r[q == pq]
            if len(sub) < 30:
                continue
            sh, _ = B.daily_sharpe(sub, fr[pd.PeriodIndex(fr.index, freq="Q") == pq])
            rows.append((str(pq), len(sub), B.stats(sub)["mean"], B.stats(sub)["pf"], sh))
            print(f"  {lab:<14}{str(pq):<10}{len(sub):>7}{rows[-1][2]:>+10.5f}"
                  f"{rows[-1][3]:>8.3f}{sh:>+12.3f}")
        wf[lab] = rows
        pos = sum(1 for x in rows if x[2] > 0)
        print(f"  {lab:<14}{'FOLDS':<10}{pos}/{len(rows)} positive   "
              f"mean quarter Sharpe {np.mean([x[4] for x in rows]):+.3f}\n")

    hdr("B3.4  DEFLATED SHARPE -- trial count taken from research_log.md")
    print("  Every configuration evaluated in this study is a trial, including the ones that were")
    print("  only ever run to be reported. var_trials is measured over the TRIAL SHARPES per")
    print("  observation -- not annualised, not over uplifts (the error class CLAUDE.md records).\n")
    trials = []
    for e in (30, 60, 120, 240, 480, 1440):
        for rr in (2.0, 0.0):
            Dx = B.both_sides(f, a, expiry=e)
            tx = B.walk(f, a, Dx, rr, cap=e)
            rx = tx[pd.DatetimeIndex(tx.ts) < cut]
            if len(rx) > 30:
                trials.append((f"expiry{e}_rr{rr}", B.stats(rx)["sharpe"], len(rx)))
    for k in (1, 2, 5):
        tx = B.walk(f, a, D.assign(trig=D.trig + k), 2.0)
        rx = tx[pd.DatetimeIndex(tx.ts) < cut]
        trials.append((f"delay{k}", B.stats(rx)["sharpe"], len(rx)))
    for mlt in (0.0, 2.0, 4.0):
        for rr in (2.0, 0.0):
            tx = B.walk(f, a, D, rr, cost=B.RT_POINTS * mlt)
            rx = tx[pd.DatetimeIndex(tx.ts) < cut]
            trials.append((f"cost{mlt}_rr{rr}", B.stats(rx)["sharpe"], len(rx)))
    sr = np.array([x[1] for x in trials])
    print(f"  trials counted: {len(trials)}   trial Sharpe/trade: min {sr.min():+.5f}  "
          f"max {sr.max():+.5f}  var {sr.var(ddof=1):.3e}")
    for lab, rr in PRIM:
        t, r = store[lab]
        x = r.pct.to_numpy()
        d = gates.deflated_sharpe(sr_hat=float(x.mean() / x.std(ddof=1)), T=len(x),
                                  n_trials=len(trials), var_trials=float(sr.var(ddof=1)),
                                  skew=float(pd.Series(x).skew()),
                                  kurtosis=float(pd.Series(x).kurt() + 3.0))
        print(f"  {lab:<14} SR/trade {d['sr_hat']:+.5f}   E[max SR | noise] "
              f"{d['expected_max_sr_under_null']:+.5f}   DSR {d['dsr']:.4f}   {d['verdict']}")


if __name__ == "__main__":
    main()
