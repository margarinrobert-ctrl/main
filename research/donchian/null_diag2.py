"""Where exactly does the driftless bias come from?

Candidates:
  (1) log-space martingale => price-space drift (Jensen)   -> helps longs
  (2) asymmetric gap rule: stop fills at the WORSE of open/stop, but a target
      that gaps through still fills at exactly the target  -> pure drag
  (3) a genuine mis-assignment bug
"""
import numpy as np, pandas as pd
from engine import build_walk, stats, simulate, atr, REASONS
from strategy import run, signals
from null_test import synth
import data as D

real = D.load("NAS")
d = synth(real, phi=0.0, seed=1000); w = build_walk(d)

print("="*104)
print("(1) does the synthetic series drift in PRICE space?")
lr = np.diff(np.log(d.close.values)); pr = np.diff(d.close.values)/d.close.values[:-1]
print(f"    mean log return   = {lr.mean():+.3e}   (built to be 0)")
print(f"    mean simple return= {pr.mean():+.3e}   (Jensen lifts this by sigma^2/2 = {lr.var()/2:+.3e})")
print(f"    total price change over sample: {d.close.values[-1]/d.close.values[0]-1:+.1%}")

print("\n"+"="*104)
print("(2) P&L decomposition by exit reason, and LONG vs SHORT symmetry")
for sm, tm in ((1.0, 3.0), (2.5, 1.5)):
    tr = run(d, w, n_entry=20, stop_mult=sm, targ_mult=tm, cost_pts=0.0, slip_pts=0.0)
    print(f"\n  stop={sm} targ={tm}   overall exp={tr.net.mean():+.3f}  n={len(tr):,}")
    for r in sorted(tr.reason.unique()):
        s = tr[tr.reason == r]
        print(f"    {REASONS[r]:<9} n={len(s):>5,} ({len(s)/len(tr):>5.1%})  exp={s.net.mean():>+9.3f}"
              f"  contrib={s.net.sum()/len(tr):>+8.3f}")
    for sd_, nm in ((1, "long"), (-1, "short")):
        s = tr[tr.side == sd_]
        if len(s): print(f"    {nm:<9} n={len(s):>5,} ({len(s)/len(tr):>5.1%})  exp={s.net.mean():>+9.3f}")

print("\n"+"="*104)
print("(3) ISOLATE the asymmetric gap rule: how much does a stop fill differ from")
print("    the stop price, and what would a symmetric rule (fill AT the barrier) give?")
for sm, tm in ((1.0, 3.0), (1.5, 2.0), (2.5, 1.5)):
    tr = run(d, w, n_entry=20, stop_mult=sm, targ_mult=tm, cost_pts=0.0, slip_pts=0.0)
    st = tr[tr.reason == 0]
    slip = (st.side*(st.exit - st.stop))          # <=0 : how much worse than the stop
    sym = tr.net.values.copy()
    sym[(tr.reason == 0).values] -= slip.values   # undo the gap pessimism
    print(f"  stop={sm} targ={tm}:  stop-exits={len(st):>5,}  mean gap beyond stop="
          f"{slip.mean():>+7.3f} pts  total drag={slip.sum()/len(tr):>+7.3f} pts/trade"
          f"   ->  exp with symmetric fills = {sym.mean():+.3f} (was {tr.net.mean():+.3f})")

print("\n"+"="*104)
print("(4) CLEAN TEST - arithmetic driftless walk, symmetric fills, no gaps possible")
print("    Bars constructed so open==prev close and no overnight jumps.")
r = np.random.default_rng(5)
n = len(real); sd = np.diff(real.close.values).std()
step = r.normal(0, sd, n); px = 20000 + np.cumsum(step)
o = np.concatenate([[px[0]], px[:-1]])
wig = np.abs(r.normal(0, sd*0.7, n))
d2 = real.copy()
d2["open"]=o; d2["close"]=px
d2["high"]=np.maximum(o,px)+wig; d2["low"]=np.minimum(o,px)-wig
d2 = d2.reset_index(drop=True); w2 = build_walk(d2)
print(f"    mean price step = {step.mean():+.4f} (driftless by construction)")
print(f"    {'stop':>5} {'targ':>5} {'n':>7} {'exp':>9} {'t':>7}")
allt=[]
for sm in (1.0,1.5,2.5):
    for tm in (1.5,2.0,3.0):
        tr = run(d2, w2, n_entry=20, stop_mult=sm, targ_mult=tm, cost_pts=0.0, slip_pts=0.0)
        s = stats(tr); allt.append(s["t"])
        print(f"    {sm:>5.1f} {tm:>5.1f} {s['n']:>7,} {s['exp']:>+9.3f} {s['t']:>+7.2f}")
print(f"    mean t over grid = {np.mean(allt):+.3f}   |t|>1.96: {np.mean(np.abs(allt)>1.96):.0%}")
