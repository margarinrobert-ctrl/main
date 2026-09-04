"""INDEPENDENT VALIDATION of rule D, written from its stated description only.

The agent's description, quoted:
  "On each CLOSED bar i compute upper=max(high[i-20..i-1]), lower=min(low[i-20..i-1])
   (Donchian(20) EXCLUDING bar i), and A=ATR14=ema(true_range,14) evaluated through
   bar i. LONG trigger if close[i] > upper + 1.00*A[i]; SHORT trigger if
   close[i] < lower - 1.00*A[i]. Take only the FIRST trigger of each session. Fill
   at the OPEN of bar i+1, slipped 0.25 pts against. Stop = entry -/+ 1.5*A[i];
   target = entry +/- 2.0*A[i]. Max hold 16 bars; flatten at 11:00 NY.
   Cost 2.0 pts round turn."

Implemented here from that text with its own channel/ATR/loop code, then compared
against lab.signals(buffer_atr=1.0). If they disagree, the frozen rule D is not
the rule the agent measured.
"""
import numpy as np, pandas as pd
import lab, data as D
from engine import build_walk, simulate, stats

SYM = "NAS"
df = D.load(SYM); w = build_walk(df)
res, lock = D.blocks(df)
h, l, c, o = df.high.values, df.low.values, df.close.values, df.open.values
tod, sess = df.tod.values, df.sess.values
n = len(df)

# --- my own ATR14 = ema(TR,14), written fresh
pc = np.concatenate([[c[0]], c[:-1]])
tr_ = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
A = np.empty(n); A[0] = tr_[0]; a_ = 2.0/15.0
for i in range(1, n): A[i] = a_*tr_[i] + (1-a_)*A[i-1]

# --- my own Donchian(20) excluding bar i, written fresh with an explicit loop
up_ = np.full(n, np.nan); lo_ = np.full(n, np.nan)
for i in range(20, n):
    up_[i] = h[i-20:i].max()
    lo_[i] = l[i-20:i].min()

inwin = (tod >= 420) & (tod < 660)
longs  = inwin & (c > up_ + 1.00*A)
shorts = inwin & (c < lo_ - 1.00*A)
trig = np.where(longs | shorts)[0]
side = np.where(longs[trig], 1.0, -1.0)
# first trigger of each session
s_ = sess[trig]; keep = np.concatenate([[True], s_[1:] != s_[:-1]])
trig, side = trig[keep], side[keep]

print("="*94)
print("INDEPENDENT REPRODUCTION OF RULE D (written from the rule text)")
print("="*94)
mine = set(trig.tolist())
li, ls, _ = lab.signals(df, 20, buffer_atr=1.0)
ok = (tod[li] >= 420) & (tod[li] < 660)
li, ls = li[ok], ls[ok]
s2 = sess[li]; k2 = np.concatenate([[True], s2[1:] != s2[:-1]])
li, ls = li[k2], ls[k2]
theirs = set(li.tolist())
print(f"  my triggers      : {len(mine):,}")
print(f"  lab.signals()    : {len(theirs):,}")
print(f"  identical        : {mine == theirs}")
print(f"  in mine not lab  : {len(mine - theirs)}   in lab not mine: {len(theirs - mine)}")
sd_ok = np.array_equal(side[np.argsort(trig)], ls[np.argsort(li)]) if mine == theirs else False
print(f"  sides identical  : {sd_ok}")

# --- resolve with my own entry/stop/target arithmetic
fill = o[trig + 1]
entry = fill + side*0.25
stop = entry - side*1.5*A[trig]
targ = entry + side*2.0*A[trig]
tr = simulate(w, trig, side, entry, stop, targ, max_hold=16, flat_tod=660, cost_pts=2.0)
mine_r = tr[np.isin(tr.sig_bar, np.where(res)[0])]
g, _ = lab.sig_gate(SYM, li, ls, stop_mult=1.5, targ_mult=2.0, n_draws=400, quiet=True)
print(f"\n  my book   : n={len(mine_r):,}  exp={mine_r.net.mean():+.3f} pts")
print(f"  lab book  : n={g['n']:,}  exp={g['exp']:+.3f} pts  excess={g['excess']:+.2f} z={g['z']:+.2f} p={g['p']:.4f}")
print(f"  agreement : {'EXACT' if abs(mine_r.net.mean()-g['exp'])<1e-9 and len(mine_r)==g['n'] else 'DIFFERS'}")

print("\n  leakage re-check on the frozen rule:")
print(f"    channel uses bars [i-20, i-1], never bar i        : upper[i]==max(high[i-20:i]) by construction")
print(f"    ATR uses bars <= i (the signal bar's own close)    : allowed, the bar is CLOSED when we act")
print(f"    fill is bar i+1 open, strictly after the signal    : {np.all(trig+1 < n)}")
print(f"    triggers inside the window only                    : {tod[trig].min()} to {tod[trig].max()} (want 420-645)")
