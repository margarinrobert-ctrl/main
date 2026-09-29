"""R1 -- the shipped configuration, the arithmetic that frames it, and the components.

Order: the BREAK-EVEN the geometry demands, then the baseline, then the per-session and per-weekday
split, then the R:R ladder. The arithmetic comes first because it decides whether the backtest can
possibly work before the backtest is read.
"""
import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v69")
import v69core as V

t0 = time.time(); pd.set_option("display.width", 210)
def say(*a): print(*a, flush=True)
say(__doc__)
d = V.sessionize(V.load())
say(f"[{time.time()-t0:5.1f}s] {len(d):,} bars  {d.ny.min()} .. {d.ny.max()}")

say(f"\n{'='*100}\nR1.1  THE ARITHMETIC, BEFORE THE BACKTEST\n{'='*100}")
for rr in (0.5, 0.8, 1.0, 1.5, 2.0, 3.0):
    say(f"  R:R {rr:>4}  driftless break-even win rate {100/(1+rr):>5.1f}%")
say(f"\n  The Pine ships R:R = 0.8, so it needs 55.6% of trades to win BEFORE costs.")

say(f"\n{'='*100}\nR1.2  THE SHIPPED CONFIGURATION (minus the VIX gate, which cannot be reproduced)\n{'='*100}")
t_gross = V.walk(d, cost_pts=0.0, **{k: v for k, v in V.SHIPPED.items()})
t_net = V.walk(d, cost_pts=V.RT_POINTS, **{k: v for k, v in V.SHIPPED.items()})
for lab, t in (("GROSS (as the Pine reports it)", t_gross), ("NET (MNQ 1.72 pt round turn)", t_net)):
    s = V.stats(t)
    say(f"  {lab:>32}: n {s['n']:>5}  win {100*s['win']:>5.1f}%  PF {s['pf']:>6.3f}  "
        f"%/trade {s['pct']:>+8.5f}  total {s['total']:>+8.2f}  maxDD {s['dd']:>6.2f}")
say(f"\n  break-even needed 55.6%, delivered {100*V.stats(t_net)['win']:.1f}%  "
    f"-> {'ABOVE' if V.stats(t_net)['win']>0.5556 else 'BELOW'} the bar")
say(f"  exits: " + ", ".join(f"{k} {100*v/len(t_net):.1f}%"
                             for k, v in t_net.why.value_counts().items()))
say(f"  mean risk {t_net.risk_pct.mean():.3f}% of price; cost is "
    f"{100*V.RT_POINTS/(t_net.risk_pct.mean()/100*t_net.ent.mean()):.1f}% of the stop")

say(f"\n{'='*100}\nR1.3  PER SESSION -- one threshold pair serves three very different ranges\n{'='*100}")
say(f"{'session':>8} {'n':>6} {'win%':>7} {'PF':>7} {'%/trade':>9} {'total':>8} "
    f"{'med range':>10} {'risk%':>7}")
for i, (nm, *_ ) in enumerate(V.SESSIONS):
    q = t_net[t_net.sid == i]
    if len(q) < 10:
        continue
    s = V.stats(q)
    say(f"{nm:>8} {s['n']:>6} {100*s['win']:>6.1f}% {s['pf']:>7.3f} {s['pct']:>+9.5f} "
        f"{s['total']:>+8.2f} {q.rng.median():>10.1f} {q.risk_pct.mean():>7.3f}")

say(f"\n{'='*100}\nR1.4  THE WEEKDAY GRID -- a calendar condition, which this branch bans from search\n{'='*100}")
say(f"  CLAUDE.md: 'Ban calendar conditions from rule search. Weekday and month conditions partition")
say(f"  the sample five or twelve ways and hand the search a free lottery. Removing them was worth")
say(f"  $8,771 on the holdout.' The shipped Monday=Long is exactly such a condition, so it is")
say(f"  measured here against the unrestricted alternative rather than assumed.")
allboth = dict(V.SHIPPED); allboth["day"] = {k: "Both" for k in ("Mon","Tue","Wed","Thu","Fri")}
t_both = V.walk(d, cost_pts=V.RT_POINTS, **allboth)
say(f"\n{'variant':>26} {'n':>6} {'win%':>7} {'PF':>7} {'%/trade':>9} {'total':>8}")
for lab, t in (("shipped (Mon = Long only)", t_net), ("all days Both", t_both)):
    s = V.stats(t)
    say(f"{lab:>26} {s['n']:>6} {100*s['win']:>6.1f}% {s['pf']:>7.3f} {s['pct']:>+9.5f} "
        f"{s['total']:>+8.2f}")
say(f"\n  by weekday, all-days-Both (so the shipped Monday rule can be judged on its own evidence):")
say(f"{'dow':>6} {'n':>6} {'long n':>7} {'long %/t':>9} {'short n':>8} {'short %/t':>10}")
for dw, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri")):
    q = t_both[t_both.dow == dw]
    L, S = q[q.side > 0], q[q.side < 0]
    say(f"{nm:>6} {len(q):>6} {len(L):>7} {L.pct.mean():>+9.5f} {len(S):>8} {S.pct.mean():>+10.5f}")

say(f"\n{'='*100}\nR1.5  THE R:R LADDER -- the one axis the arithmetic says is mispriced\n{'='*100}")
say(f"{'R:R':>6} {'need':>7} {'n':>6} {'win%':>7} {'gap':>7} {'PF':>7} {'%/trade':>9} {'total':>8}")
for rr in (0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0):
    cfg = dict(V.SHIPPED); cfg["rr"] = rr
    t = V.walk(d, cost_pts=V.RT_POINTS, **cfg)
    s = V.stats(t)
    need = 100 / (1 + rr)
    say(f"{rr:>6} {need:>6.1f}% {s['n']:>6} {100*s['win']:>6.1f}% "
        f"{100*s['win']-need:>+6.1f} {s['pf']:>7.3f} {s['pct']:>+9.5f} {s['total']:>+8.2f}")
t_net.to_csv("results/v69/r1_shipped_trades.csv", index=False)
say(f"\n[{time.time()-t0:5.1f}s] done")
