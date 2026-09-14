"""N1 -- the arithmetic and the base rates, BEFORE any P&L.

Three questions in order:
  1. What does the round turn cost as a fraction of the stop, and what break-even win rate does
     each geometry imply? If gross sits at the driftless bound there is nothing underneath the cost
     for any filter to uncover (`STUDY_V69_ORB`).
  2. What fraction of the trigger's OWN bars does each proposed confirmation already pass? A
     confirmation that passes 95% of signal bars is the trigger restated and cannot add anything;
     this branch has caught that eight times (RSI 94.7%, Aroon 100.0%, MACD 99.8%, MFI 91.7%,
     EMA13>48 82.6%, +DI>-DI 97.8%, close>EMA50 93.7%, VWAP/stoch rho +0.831).
  3. Gate 1: does the BARE primary clear a matched random entry in the same session, same side,
     with identical geometry and exits?
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

FEEDS = [("US30L", 15), ("US30I", 15), ("US100L", 15), ("NQ", 15)]
pd.set_option("display.width", 200)


def driftless(rr):
    return 1.0 / (1.0 + rr)


def main():
    print("=" * 100)
    print("N1.1  COST AS A FRACTION OF RISK, AND THE BREAK-EVEN EACH GEOMETRY IMPLIES")
    print("=" * 100)
    rows = []
    store = {}
    for name, tf in FEEDS:
        f = N.load(name, tf)
        rhi, rlo, rn = N.ranges(f)
        store[name] = (f, rhi, rlo)
        bl = N.blocks(f, name)
        sig, sd = N.events(f, rhi, rlo, side="both")
        at = f["atr"].to_numpy()[sig]
        c = f["close"].to_numpy()[sig]
        rw = (rhi - rlo)[sig]
        cost = N.COST[name]
        for stop_a in (0.5, 1.0, 1.5, 2.0, 3.0):
            risk = stop_a * np.median(at)
            rows.append(dict(feed=name, stop=f"{stop_a}N", risk_pts=round(risk, 2),
                             cost_risk=round(cost / risk, 4),
                             be_1R=round(driftless(1.0) * (1 + cost / risk) if False else
                                         (risk + cost) / (2 * risk), 4),
                             be_2R=round((risk + cost) / (3 * risk), 4)))
        print(f"  {name:7s} n_sig {len(sig):5d}  median ATR {np.median(at):8.2f}  "
              f"median range {np.nanmedian(rw):8.2f} = {np.nanmedian(rw/at):.2f} ATR  "
              f"median price {np.median(c):9.1f}  round turn {cost}")
    print()
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n  be_1R / be_2R are the DRIFTLESS break-even win rates at RR 1 and 2 after cost.")

    print()
    print("=" * 100)
    print("N1.2  BASE RATES ON THE TRIGGER'S OWN BARS  (before any P&L)")
    print("=" * 100)
    br = []
    for name, tf in FEEDS:
        f, rhi, rlo = store[name]
        sig, sd = N.events(f, rhi, rlo, side="long")
        mod = f["mod"].to_numpy()
        base_pool = np.flatnonzero((mod >= N.OPEN_M) & (mod < 960))
        for kind in ("ema", "sma", "wma", "hull", "vwma"):
            st, age, aged = N.ema_state(f, 13, 48, kind)
            p_sig = st[sig].mean()
            p_all = st[base_pool].mean()
            br.append(dict(feed=name, read=f"{kind}13>48 state", sig_rate=round(p_sig, 4),
                           all_rate=round(p_all, 4), lift=round(p_sig / max(p_all, 1e-9), 3)))
        st, age, aged = N.ema_state(f, 13, 48, "ema")
        for R in (5, 10, 20, 40):
            m = age[sig] <= R
            ma_ = (age[base_pool] <= R)
            br.append(dict(feed=name, read=f"ema cross<= {R}", sig_rate=round(m.mean(), 4),
                           all_rate=round(ma_.mean(), 4),
                           lift=round(m.mean() / max(ma_.mean(), 1e-9), 3)))
    b = pd.DataFrame(br)
    print(b.pivot_table(index="read", columns="feed", values="sig_rate").round(4).to_string())
    print("\n  lift (signal rate / all-bar rate):")
    print(b.pivot_table(index="read", columns="feed", values="lift").round(3).to_string())
    print("\n  A read above ~0.95 on the signal bars is the trigger restated and is excluded.")

    print()
    print("=" * 100)
    print("N1.3  GATE 1 -- the BARE primary against a matched random entry")
    print("=" * 100)
    out = []
    for name, tf in FEEDS:
        f, rhi, rlo = store[name]
        cost = N.COST[name]
        bl = N.blocks(f, name)
        for side in ("long", "short", "both"):
            sig, sd = N.events(f, rhi, rlo, side=side)
            for stop_a, tgt_r in ((1.0, 0.0), (1.5, 0.0), (1.0, 2.0)):
                tr = N.run(f, sig, sd, stop_a=stop_a, tgt_r=tgt_r, flat_m=960, cost=cost)
                tr = N.attach_day(f, tr)
                for bn, mask in bl.items():
                    kk = mask[tr["sig"].to_numpy()]
                    t = tr[kk]
                    if len(t) < 25:
                        continue
                    null = N.control_entries(f, t, seed=11, n_draw=300,
                                             stop_a=stop_a, tgt_r=tgt_r, flat_m=960, cost=cost)
                    e = t["pct"].mean()
                    out.append(dict(feed=name, side=side, geom=f"{stop_a}N/{tgt_r or 'none'}",
                                    block=bn, n=len(t), pct=round(e, 4),
                                    pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                             max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                    win=round((t.pts > 0).mean(), 3),
                                    ctl=round(np.nanmedian(null), 4),
                                    p=round(N.pval(e, null), 3),
                                    mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(out)
    print(o.to_string(index=False))
    n_tests = len(o)
    print(f"\n  {n_tests} Gate-1 tests; "
          f"{int((o['p'] <= 0.05).sum())} clear p<=0.05 against {0.05*n_tests:.1f} expected by chance.")
    print(f"  E[max t | pure noise] over {n_tests} looks = {N.e_max_normal(n_tests):.3f} "
          f"against the 2.802 detection needs.")
    print(f"  cells whose delivered edge exceeds its own MDE: "
          f"{int((o['pct'].abs() > o['mde']).sum())} of {n_tests}")
    o.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "n1_gate1.csv"), index=False)


if __name__ == "__main__":
    main()
