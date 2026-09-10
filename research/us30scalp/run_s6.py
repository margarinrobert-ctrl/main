"""S6 -- diagnose the null and the event structure before trusting S5's verdict.

S5 reported `fade n8 k2.0` at +0.683 pts against a control median of -2.355 -- an excess of +3.04
points -- failing at p 0.260. That combination is the exact signature `STUDY_V59` recorded as a
BROKEN NULL: "a control whose median is far below the rule and which still cannot reject anything
is broken". Two candidate mechanisms, both testable:

  (a) THE CONTROL'S SPREAD. If each random draw produces a wildly different number of surviving
      trades -- because a 4-hour hold plus a position lock rejects a different share of a random
      arrival process than of a clustered one -- the null's variance is inflated by trade COUNT
      rather than by outcome, and no excess can reject.
  (b) THE EVENT STRUCTURE. With entries confined to a 4-hour window and a 4-hour cap, the FIRST
      signal of a session blocks every later one. The strategy may therefore be "the first break
      after 07:00" rather than "a break", which is a different object with a different null.

Neither is a modelling preference; both change what the p-value means.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 240)
KW = dict(stop_a=150, tgt_a=1e9, hold=16, flat=0, use_pts=1)


def draws(f, n_target, side_arr, elig, n=400, seed=3, **kw):
    """Like s30core.control but returns the COUNT of surviving trades per draw as well."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    mu = np.empty(n); cnt = np.empty(n)
    for i in range(n):
        pick = np.sort(rng.choice(pool, size=n_target, replace=False))
        sd = rng.permutation(side_arr)[:len(pick)]
        t = S.walk(f, pick, sd, **kw)
        mu[i] = t["pts"].mean() if len(t) else np.nan
        cnt[i] = len(t)
    return mu, cnt


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    win = S.window(f)
    elig = win & res

    # ---- 1. is the null broken? --------------------------------------------------------------
    print("=== 1. the null's SPREAD, not only its median ===")
    for nm in ("fade n8 k2.0", "donch20 long"):
        s2, d2 = S.TRIGGERS[nm](f)
        keep = np.isin(s2, np.flatnonzero(res))
        t = S.walk(f, s2[keep], d2[keep], **KW)
        raw_sig = int(keep.sum())
        mu, cnt = draws(f, len(t), t["side"].to_numpy(), elig, n=400, seed=3, **KW)
        ok = np.isfinite(mu)
        print(f"\n-- {nm} --")
        print(f"  signals offered {raw_sig:6d}   trades taken {len(t):5d}  "
              f"(lock rejects {100*(1-len(t)/raw_sig):.1f}%)")
        print(f"  rule  mean {t['pts'].mean():+8.4f}   per-trade sd {t['pts'].std():8.3f}   "
              f"sd of the MEAN {t['pts'].std()/np.sqrt(len(t)):8.4f}")
        print(f"  null  median {np.median(mu[ok]):+8.4f}   sd of the null {mu[ok].std():8.4f}   "
              f"p5..p95 [{np.percentile(mu[ok],5):+.3f}, {np.percentile(mu[ok],95):+.3f}]")
        print(f"  null trade COUNT: target {len(t)}, actual mean {cnt.mean():.1f}  "
              f"min {cnt.min():.0f}  max {cnt.max():.0f}  sd {cnt.std():.1f}")
        print(f"  ratio  sd(null mean) / sd(rule mean) = "
              f"{mu[ok].std()/(t['pts'].std()/np.sqrt(len(t))):.3f}   "
              f"(1.0 = the null is as tight as the estimate; >>1 = inflated)")
        z = (t["pts"].mean() - np.median(mu[ok])) / mu[ok].std()
        print(f"  excess {t['pts'].mean()-np.median(mu[ok]):+.4f} pts = {z:.2f} null sd  "
              f"-> p {np.mean(mu[ok] >= t['pts'].mean()):.3f}")

    # ---- 2. what the position lock is actually doing -----------------------------------------
    print("\n=== 2. the event structure: is this 'a break' or 'the FIRST break after 07:00'? ===")
    for nm in ("fade n8 k2.0", "donch20 long"):
        s2, d2 = S.TRIGGERS[nm](f)
        keep = np.isin(s2, np.flatnonzero(res)) & np.isin(s2, np.flatnonzero(win))
        sig = s2[keep]
        day = f.index[sig].normalize()
        per = pd.Series(1, index=day).groupby(level=0).sum()
        t = S.walk(f, s2[np.isin(s2, np.flatnonzero(res))],
                   d2[np.isin(s2, np.flatnonzero(res))], **KW)
        tday = t["ts"].dt.normalize()
        print(f"\n-- {nm} --")
        print(f"  in-window signals per session: mean {per.mean():.2f}  median {per.median():.0f}  "
              f"p90 {per.quantile(.9):.0f}  max {per.max():.0f}")
        print(f"  sessions with >=1 signal {len(per):,}   trades actually opened {len(t):,}   "
              f"trades per session with a signal {len(t)/len(per):.2f}")
        print(f"  share of sessions where only ONE trade opened: "
              f"{100*(tday.value_counts() == 1).mean():.1f}%")

    # ---- 3. first-signal-only, which is what the lock nearly produces ------------------------
    print("\n=== 3. the rule reduced to its FIRST in-window signal per session ===")
    rows = []
    for nm, fn in S.TRIGGERS.items():
        s2, d2 = fn(f)
        keep = np.isin(s2, np.flatnonzero(res)) & np.isin(s2, np.flatnonzero(win))
        if keep.sum() < 100:
            continue
        sig, sd = s2[keep], d2[keep]
        day = f.index[sig].normalize().to_numpy()
        first = np.r_[True, day[1:] != day[:-1]]
        for tag, m in (("all signals", np.ones(len(sig), bool)), ("first only", first)):
            t = S.walk(f, sig[m], sd[m], **KW)
            if len(t) < 40:
                continue
            ctl, _ = draws(f, len(t), t["side"].to_numpy(), elig, n=300, seed=13, **KW)
            ctl = ctl[np.isfinite(ctl)]
            rows.append(dict(trigger=nm, variant=tag, n=len(t), pts=t["pts"].mean(),
                             pf=S.pf(t["pts"].to_numpy()), win=float((t["pts"] > 0).mean()),
                             ctl=float(np.median(ctl)),
                             excess=t["pts"].mean() - float(np.median(ctl)),
                             p=float(np.mean(ctl >= t["pts"].mean()))))
    R = pd.DataFrame(rows)
    print(R.round(4).to_string(index=False))
    print(f"\nclearing p<=0.05: {int((R.p <= 0.05).sum())} of {len(R)}   "
          f"expected {0.05*len(R):.1f}")

    # ---- 4. concurrency ----------------------------------------------------------------------
    print("\n=== 4. concurrency of the shipped configuration (STUDY_ATME: check, never assume) ===")
    s2, d2 = S.TRIGGERS["fade n8 k2.0"](f)
    keep = np.isin(s2, np.flatnonzero(res))
    t = S.walk(f, s2[keep], d2[keep], **KW)
    ev = np.zeros(len(f), int)
    np.add.at(ev, t["e_bar"].to_numpy(), 1)
    np.add.at(ev, np.minimum(t["x_bar"].to_numpy() + 1, len(f) - 1), -1)
    conc = np.cumsum(ev)
    print(f"  concurrent positions: max {conc.max()}  mean when open "
          f"{conc[conc > 0].mean():.2f}  share of bars in a position {100*(conc > 0).mean():.1f}%")
    print(f"  median hold {t['mins'].median():.0f} min   exits: "
          f"{ {S.WHY[k]: round(v,3) for k, v in t.why.value_counts(normalize=True).items()} }")


if __name__ == "__main__":
    main()
