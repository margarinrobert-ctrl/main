"""Robust timezone identification: return correlation + tick-volume seasonality.

Absolute prices differ between feeds by a CFD/futures basis, so match on
15m RETURNS (basis-invariant) and confirm with the intraday activity profile:
the US cash open produces an unmistakable tick-volume spike.
"""
import numpy as np, pandas as pd
from ingest import read_csv, read_rtf, NAS, US30, RTF

rtf = read_rtf(RTF)
us  = read_csv(US30)
na  = read_csv(NAS)

# ---------- method 1: return cross-correlation vs the NY-tagged RTF ----------
r = rtf.set_index("ts")[["close"]].rename(columns={"close": "c_rtf"})
r["ret_rtf"] = np.log(r.c_rtf).diff()
lo, hi = rtf.ts.min(), rtf.ts.max()

print("="*74)
print("METHOD 1 — 15m log-return correlation, US30 CSV vs RTF (New York tagged)")
print(f"  {'assumed CSV zone':>18} {'bars':>8} {'corr(returns)':>15}")
rows = []
for off in np.arange(-12, 15, 0.25):
    cs = us.copy()
    cs["utc"] = cs.ts.dt.tz_localize("UTC") - pd.Timedelta(hours=float(off))
    cs["ret"] = np.log(cs.close).diff()
    m = cs[(cs.utc >= lo) & (cs.utc <= hi)].set_index("utc")
    j = m[["ret"]].join(r[["ret_rtf"]], how="inner").dropna()
    if len(j) < 2000: continue
    c = float(np.corrcoef(j.ret, j.ret_rtf)[0, 1])
    rows.append((off, len(j), c))
rows.sort(key=lambda x: -x[2])
for off, n, c in rows[:5]:
    print(f"  {'UTC%+.2f'%off:>18} {n:>8,} {c:>15.4f}")
best_off = rows[0][0]
print(f"\n  ==> US30 CSV stamps align at UTC{best_off:+.2f}  (corr {rows[0][2]:.4f})")

# ---------- method 2: tick-volume seasonality (independent) ----------
print("\n" + "="*74)
print("METHOD 2 — tick-volume profile. The US cash open (09:30 New York) is the")
print("           single largest activity jump of the day on both instruments.")
for nm, df in (("US30", us), ("NASDAQ", na)):
    g = df.groupby(df.ts.dt.hour * 60 + df.ts.dt.minute).tickvol.mean()
    g = g.sort_index()
    jump = g.diff()
    top = jump.nlargest(4)
    print(f"\n  {nm}: mean tick volume by CSV clock (top activity jumps)")
    for k, v in top.items():
        print(f"      CSV {k//60:02d}:{k%60:02d}   jump {v:>9,.0f}  ->  level {g[k]:>9,.0f}")
    peak = g.idxmax()
    print(f"      CSV peak-activity bar: {peak//60:02d}:{peak%60:02d}  ({g.max():,.0f})")

# ---------- method 3: RTF sanity — same profile in known NY time ----------
ny = rtf.ts.dt.tz_convert("America/New_York")
g = rtf.groupby(ny.dt.hour * 60 + ny.dt.minute).volume.mean().sort_index()
top = g.diff().nlargest(4)
print(f"\n  RTF control (timestamps KNOWN to be New York):")
for k, v in top.items():
    print(f"      NY  {k//60:02d}:{k%60:02d}   jump {v:>9,.0f}  ->  level {g[k]:>9,.0f}")
