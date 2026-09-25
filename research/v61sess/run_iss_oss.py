"""IN-SAMPLE / OUT-OF-SAMPLE on the incumbent, as the user is running it -- and 15m against 30m.

>>> THE NUMBERS HERE WILL NOT MATCH THE STRATEGY TESTER, and the reason is data, not code. This
>>> branch's `NQ_1m.csv` covers 2022-12-26 to 2025-12-12 -- three years. A TradingView chart carries
>>> more history, which is why the screenshot shows 187 trades where this shows far fewer. What
>>> transfers between the two is the SHAPE: which block earns, what the flatten costs, whether 15m
>>> beats 30m. The absolute totals do not.
>>>
>>> AND THE SHIPPED SCRIPT SETS NO COMMISSION AND NO SLIPPAGE. If Properties was left alone, the
>>> +8,540 in the screenshot is a ZERO-COST number. Everything below charges 0.72 points a side plus
>>> 0.25 of slippage, which is the real MNQ stack. Read the commission load before the P&L
>>> (STUDY_TICK_RECALC).
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import sess_core as S    # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61sess")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


def row(t, D, tag):
    out = []
    for b, nm in ((0, "research"), (1, "locked")):
        z = t[t.blk == b]
        if len(z) < 8:
            out.append(dict(cfg=tag, block=nm, n=len(z)))
            continue
        p = z.pts.to_numpy()
        cum = np.cumsum(p)
        dd = float(np.max(np.maximum.accumulate(cum) - cum))
        yrs = max((z.ts.iloc[-1] - z.ts.iloc[0]).days / 365.25, 1e-9)
        out.append(dict(cfg=tag, block=nm, n=len(z), per_yr=len(z) / yrs,
                        pf=p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9),
                        win=100 * (p > 0).mean(), pts=p.sum(), usd=p.sum() * 2.0,
                        dd_usd=dd * 2.0, ret_dd=p.sum() / max(dd, 1e-9),
                        pct=z.pct.mean(), tot_pct=z.pct.sum()))
    return out


print(__doc__)
t0 = time.time()
D30 = S.build(30)
D15 = S.build(15)
print(f"  NQ 1-minute source -> 30m {D30['n']:,} bars, 15m {D15['n']:,} bars")
print(f"  research/locked split at day {D30['cut_day']} (first 65% of sessions)")
g30, k30, w30 = S.gate(D30, 90, 600)
g15, k15, w15 = S.gate(D15, 90, 600)
print(f"  the SAME minutes settings give:  30m pivot k={k30} window w={w30} bars   |   "
      f"15m pivot k={k15} window w={w15} bars")
print(f"  gate passes {100*g30.mean():.1f}% of 30m bars and {100*g15.mean():.1f}% of 15m bars")

CFG = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True)
USER = dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=True)
SHIP = dict(sess=False)

line("1  THE USER'S CONFIGURATION vs THE SHIPPED DEFAULT, on both timeframes")
print("  incumbent geometry (20/20, 2.0N, no target). 'user' = 07:00-11:00 New York + flatten.\n")
rows = []
for tfn, D, g in (("30m", D30, g30), ("15m", D15, g15)):
    for tag, kw in (("as shipped  (all hours, no flatten)", SHIP), ("as you run it (07-11 + flatten)", USER)):
        t = S.run(D, **CFG, **kw, g=g)
        rows += [dict(tf=tfn, **r) for r in row(t, D, tag)]
T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUT, "iss_oss.csv"), index=False)
print(f"  {'tf':>4} {'configuration':36s} {'block':9s} {'n':>4} {'/yr':>5} {'PF':>6} {'win':>6} "
      f"{'$ (MNQ)':>9} {'maxDD $':>9} {'ret/DD':>7} {'%/trade':>9} {'total %':>8}")
for _, r in T.iterrows():
    if r.get("n", 0) < 8 or pd.isna(r.get("pf", np.nan)):
        print(f"  {r.tf:>4} {r.cfg:36s} {r.block:9s} {int(r.n):>4}   (too few)")
        continue
    print(f"  {r.tf:>4} {r.cfg:36s} {r.block:9s} {int(r.n):>4} {r.per_yr:>5.0f} {r.pf:>6.3f} "
          f"{r.win:>5.1f}% {r.usd:>9.0f} {r.dd_usd:>9.0f} {r.ret_dd:>7.2f} {r.pct:>+9.4f} {r.tot_pct:>+8.2f}")

line("2  WHAT THE FLATTEN AND THE WINDOW EACH COST, separated")
print("  Four arms so the two changes are not confounded. Same geometry, same gate.\n")
arms = {"all hours, no flatten": dict(sess=False),
        "07:00-11:00, NO flatten": dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=False),
        "all hours, flatten 11:00": dict(sess=True, s_start=0, s_stop=11 * 60, flat=True),
        "07:00-11:00 + flatten": USER}
abl = []
for tfn, D, g in (("30m", D30, g30), ("15m", D15, g15)):
    print(f"  {tfn}")
    print(f"    {'arm':26s} {'block':9s} {'n':>4} {'PF':>6} {'%/trade':>9} {'total %':>8} "
          f"{'maxDD $':>9} {'ret/DD':>7}")
    for an, kw in arms.items():
        t = S.run(D, **CFG, **kw, g=g)
        for b, nm in ((0, "research"), (1, "locked")):
            z = t[t.blk == b]
            if len(z) < 8:
                continue
            p = z.pts.to_numpy(); cum = np.cumsum(p)
            dd = float(np.max(np.maximum.accumulate(cum) - cum))
            abl.append(dict(tf=tfn, arm=an, block=nm, n=len(z),
                            pf=p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9),
                            pct=z.pct.mean(), tot=z.pct.sum(), dd=dd * 2.0,
                            ret_dd=p.sum() / max(dd, 1e-9)))
            r = abl[-1]
            print(f"    {an:26s} {nm:9s} {len(z):>4} {r['pf']:>6.3f} {r['pct']:>+9.4f} "
                  f"{r['tot']:>+8.2f} {r['dd']:>9.0f} {r['ret_dd']:>7.2f}")
    print()
AB = pd.DataFrame(abl)
AB.to_csv(os.path.join(OUT, "ablation.csv"), index=False)

line("3  IS THE 15m ADVANTAGE THE TIMEFRAME, OR THE CHANNEL'S TIME REACH?")
print("  On 15m the incumbent's 20-bar channels are 300 minutes; on 30m they are 600. Matching the")
print("  channels IN MINUTES is the controlled comparison.\n")
print(f"  {'tf':>4} {'entry/exit (bars)':18s} {'= minutes':>10} {'block':9s} {'n':>4} {'PF':>6} "
      f"{'%/trade':>9} {'total %':>8} {'ret/DD':>7}")
mrows = []
for tfn, D, g, pairs in (("30m", D30, g30, [(20, 20), (10, 10), (40, 40)]),
                         ("15m", D15, g15, [(20, 20), (40, 40), (10, 10)])):
    tf = int(tfn[:-1])
    for e, x in pairs:
        t = S.run(D, **{**CFG, "ent": e, "exN": x}, **USER, g=g)
        for b, nm in ((0, "research"), (1, "locked")):
            z = t[t.blk == b]
            if len(z) < 8:
                continue
            p = z.pts.to_numpy(); cum = np.cumsum(p)
            dd = float(np.max(np.maximum.accumulate(cum) - cum))
            mrows.append(dict(tf=tfn, ent=e, exN=x, mins=e * tf, block=nm, n=len(z),
                              pf=p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9),
                              pct=z.pct.mean(), tot=z.pct.sum(), ret_dd=p.sum() / max(dd, 1e-9)))
            r = mrows[-1]
            print(f"  {tfn:>4} {f'{e}/{x}':18s} {e*tf:>10} {nm:9s} {len(z):>4} {r['pf']:>6.3f} "
                  f"{r['pct']:>+9.4f} {r['tot']:>+8.2f} {r['ret_dd']:>7.2f}")
pd.DataFrame(mrows).to_csv(os.path.join(OUT, "tf_matched.csv"), index=False)

line("4  ZERO-COST vs REAL COST -- because the script ships with no commission set")
print(f"  {'tf':>4} {'configuration':36s} {'block':9s} {'n':>4} {'NET $':>9} {'GROSS $':>9} "
      f"{'cost $':>8} {'cost as % of gross':>19}")
for tfn, D, g in (("30m", D30, g30), ("15m", D15, g15)):
    for tag, kw in (("as shipped", SHIP), ("as you run it", USER)):
        t = S.run(D, **CFG, **kw, g=g)
        tz = S.run(D, **CFG, **kw, g=g, cost=0.0, slip=0.0)
        for b, nm in ((0, "research"), (1, "locked")):
            z, zz = t[t.blk == b], tz[tz.blk == b]
            if len(z) < 8:
                continue
            net, gross = z.pts.sum() * 2, zz.pts.sum() * 2
            print(f"  {tfn:>4} {tag:36s} {nm:9s} {len(z):>4} {net:>9.0f} {gross:>9.0f} "
                  f"{gross-net:>8.0f} {100*(gross-net)/max(abs(gross),1e-9):>18.1f}%")
print(f"\n  runtime {time.time()-t0:.0f}s")
