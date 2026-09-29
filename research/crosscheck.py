"""Check the Python engine against the TypeScript one, trade for trade.

Summary statistics can agree while the underlying trades differ, so this compares indices and
prices, not just expectancy.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from ib_sim import COMMISSION_PTS, POINT_VALUE, TAKER_SIDE, TICK, simulate
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

TS_CSV = sys.argv[1] if len(sys.argv) > 1 else "results/crosscheck/ts_trades.csv"
RETR = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
STOP = float(sys.argv[3]) if len(sys.argv) > 3 else 80.0
RR = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0

seg = session_slice(load_bars("data/NQ_1m.csv"), 570, 719)
mod = minute_of_day(seg.index)
sess = session_index(seg.index, 570)
mso = minutes_since_open(mod, 570).astype(np.int64)
o, h, l, c = (seg[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
atr = np.zeros(len(seg))

print(f"python segment bars = {len(seg):,}")

res = simulate(o, h, l, c, sess, mso, atr,
               60, RETR, STOP, RR, 0, 0, 0, 1.5, 40.0, 0, 10.0, 50.0, 149,
               TICK, POINT_VALUE, TAKER_SIDE, COMMISSION_PTS)
py = pd.DataFrame({
    "entryIndex": res[0], "exitIndex": res[1], "side": res[2],
    "entryPx": res[3], "exitPx": res[4], "pnl": res[5], "r": res[6], "isTarget": res[7],
})
ts = pd.read_csv(TS_CSV)

print(f"\n{'':22}{'TypeScript':>14}{'Python':>14}{'':>6}")
def cmp(name, a, b, fmt="{:.4f}"):
    ok = "OK" if (abs(a - b) < 1e-6 if isinstance(a, float) else a == b) else "MISMATCH"
    print(f"  {name:<20}{fmt.format(a):>14}{fmt.format(b):>14}   {ok}")

cmp("trades", len(ts), len(py), "{:.0f}")
cmp("longs", int((ts.side == 1).sum()), int((py.side == 1).sum()), "{:.0f}")
cmp("win rate %", float((ts.pnl > 0).mean() * 100), float((py.pnl > 0).mean() * 100))
cmp("expectancy R", float(ts.r.mean()), float(py.r.mean()))
cmp("total pnl", float(ts.pnl.sum()), float(py.pnl.sum()), "{:.2f}")
gp_ts, gl_ts = ts.pnl[ts.pnl > 0].sum(), -ts.pnl[ts.pnl < 0].sum()
gp_py, gl_py = py.pnl[py.pnl > 0].sum(), -py.pnl[py.pnl < 0].sum()
cmp("profit factor", float(gp_ts / gl_ts), float(gp_py / gl_py))

# --- the part that matters: are they the SAME trades? ---
print("\n  trade-for-trade:")
if len(ts) != len(py):
    only_ts = set(ts.entryIndex) - set(py.entryIndex)
    only_py = set(py.entryIndex) - set(ts.entryIndex)
    print(f"    counts differ. only in TS: {sorted(only_ts)[:10]}  only in PY: {sorted(only_py)[:10]}")
else:
    m = ts.join(py, rsuffix="_py")
    for col, tol in [("entryIndex", 0), ("exitIndex", 0), ("side", 0), ("entryPx", 1e-9), ("exitPx", 1e-9), ("pnl", 1e-6), ("r", 1e-6)]:
        d = (m[col] - m[f"{col}_py"]).abs()
        bad = int((d > tol).sum())
        worst = float(d.max())
        print(f"    {col:<12} mismatches {bad:>4} / {len(m)}   max diff {worst:.10g}")
