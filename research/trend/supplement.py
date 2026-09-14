"""Two supplements to the battery: a shorter walk-forward window so there is a fold DISTRIBUTION
(the spec's 1260/252 yields one fold on 6.5 years of training data), and per-instrument raw P&L."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import backtest as B
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
DPY = 256
def sh(x): x = x.dropna(); return float(x.mean() / x.std() * np.sqrt(DPY)) if x.std() > 0 else np.nan
c = B.calibrate(); o = B.run(c=c); net = o["net"]; tr = net.index < o["split"]; x = net[tr]
print("SUPPLEMENT A. walk-forward with a 756-day (3y) train / 252 test window -- a DEVIATION from the spec's 1260,")
print("made only because 1260/252 yields a single fold here. Reported as a distribution, not a mean.")
rows = []
for s in range(0, len(x) - 756 - 252 + 1, 252):
    te = x.iloc[s + 756:s + 756 + 252]
    rows.append(dict(test=f"{te.index[0].date()} -> {te.index[-1].date()}", sharpe=sh(te), ret=100 * te.sum()))
F = pd.DataFrame(rows); print(F.to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
print(f"  fold Sharpe: mean {F.sharpe.mean():+.3f}  sd {F.sharpe.std():.3f}  min {F.sharpe.min():+.3f}  max {F.sharpe.max():+.3f}  positive {int((F.sharpe>0).sum())}/{len(F)}")
print("\nSUPPLEMENT B. per-instrument contribution, training, gross of costs (percent of capital, summed)")
g = (o["held"][tr] * o["r_exec"][tr])
for n in o["names"]:
    print(f"  {n:6s} total {100*g[n].sum():+7.2f}%   Sharpe {sh(g[n]):+.3f}   mean |exposure| {o['held'][tr][n].abs().mean():.2f}x capital   long share {100*(o['held'][tr][n] > 0).mean():.0f}%")
print(f"  book   total {100*g.sum(axis=1).sum():+7.2f}%   Sharpe {sh(g.sum(axis=1)):+.3f}")
print("\nSUPPLEMENT C. the 2022 question -- trend following's best year on a diversified book; here:")
y = net[net.index.year == 2022]; pos22 = o["held"][o["held"].index.year == 2022]
print(f"  2022 net {100*y.sum():+.2f}%  Sharpe {sh(y):+.2f}   days short US100 {100*(pos22['US100'] < 0).mean():.0f}%  short US30 {100*(pos22['US30'] < 0).mean():.0f}%")
print(f"  US100 2022 close-to-close {100*(o['close']['US100'][o['close'].index.year == 2022].iloc[-1] / o['close']['US100'][o['close'].index.year == 2022].iloc[0] - 1):+.1f}%")
print("  A trend system that was short most of a -30% year and still lost was whipsawed by the bear rallies --")
print("  which is what a 5-sleeve ensemble on ONE asset class does, and what bonds / energy / FX exist to offset.")
