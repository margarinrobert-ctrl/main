"""W4 -- the dollar answer, with the synthetic-level deflator applied.

`STUDY_US100.md`: the stored NQ series carries levels well above the real Nasdaq-100 (13,915 on
2023-01-10 where US100 reads 11,184), and the ratio decays smoothly over the sample. Win rates,
R-multiples and ATR-unit measurements are unaffected; DOLLAR magnitudes are not, and they are
inflated most EARLY -- which is the research block. So a dollar figure quoted off raw points
overstates, and by more at the start than the end.

Deflator: the ratio of the US100 close to the NQ close on shared sessions, forward-filled onto
every trade date, applied per trade.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"
PT_VALUE = 2.0          # MNQ, $2 per index point
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)

D, F, base = T.build(5)
lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)
t["ts"] = pd.to_datetime(t.day.to_numpy(), unit="D")

# --- the deflator, from the second feed
u = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
u.columns = [c.strip().lower() for c in u.columns]
u["ts"] = pd.to_datetime(u["datetime"].astype(str).str.strip(),
                         format="%Y.%m.%d %H:%M:%S", errors="coerce")
u = u.dropna(subset=["ts"]).sort_values("ts").set_index("ts")
u.index = u.index - pd.Timedelta(hours=7)
us_daily = u["close"].resample("D").last().dropna()
nq_daily = pd.Series(D["c"], index=D["ix"]).resample("D").last().dropna()
j = pd.DataFrame({"nq": nq_daily, "us": us_daily}).dropna()
j["ratio"] = j.us / j.nq
print(f"  overlapping sessions {len(j)}   ratio US100/NQ: "
      f"first {j.ratio.iloc[0]:.4f}  last {j.ratio.iloc[-1]:.4f}  median {j.ratio.median():.4f}")
defl = j.ratio.reindex(pd.date_range(j.index.min(), t.ts.max(), freq="D")).ffill()
t["defl"] = t.ts.map(defl).ffill().fillna(j.ratio.iloc[-1])
t["pts_real"] = t.pts * t.defl
print(f"  mean deflator applied: research {t[t.blk==0].defl.mean():.4f}, "
      f"locked {t[t.blk==1].defl.mean():.4f}  -> raw points overstate by "
      f"{1/t[t.blk==0].defl.mean()-1:.1%} and {1/t[t.blk==1].defl.mean()-1:.1%}")

print("\n" + "=" * 104)
print("W4.1  ONE MNQ CONTRACT, COSTS INCLUDED, NOTHING SELECTED")
print("=" * 104)
t["yr"] = t.ts.dt.year
print(f"  {'year':>6} {'trades':>7} {'raw pts':>10} {'real pts':>10} {'$ (MNQ)':>10} {'PF':>6} {'win':>6}")
for y, g in t.groupby("yr"):
    r = g.pts_real.to_numpy()
    print(f"  {y:>6} {len(g):>7} {g.pts.sum():>10.1f} {r.sum():>10.1f} "
          f"{r.sum()*PT_VALUE:>10,.0f} {r[r>0].sum()/max(-r[r<0].sum(),1e-9):>6.3f} {(r>0).mean():>6.1%}")
tot = t.pts_real.sum()
yrs = (t.ts.max() - t.ts.min()).days / 365.25
print(f"  {'TOTAL':>6} {len(t):>7} {t.pts.sum():>10.1f} {tot:>10.1f} {tot*PT_VALUE:>10,.0f}")
print(f"\n  over {yrs:.1f} years = ${tot*PT_VALUE/yrs:,.0f} a year on ONE contract, "
      f"{len(t)/yrs:.0f} trades a year, ${tot*PT_VALUE/len(t):.2f} a trade")

d = t.groupby("day").pts_real.sum()
full = pd.Series(0.0, index=pd.Index(D["all_days"])); full.loc[d.index] = d.to_numpy()
eq = full.cumsum().to_numpy() * PT_VALUE
dd = np.maximum.accumulate(eq) - eq
print(f"  worst drawdown ${dd.max():,.0f}   return/drawdown {eq[-1]/dd.max():.2f}")
print(f"  by block: research ${t[t.blk==0].pts_real.sum()*PT_VALUE:,.0f} over "
      f"{int((t.blk==0).sum())} trades = ${t[t.blk==0].pts_real.mean()*PT_VALUE:.2f}/trade;  "
      f"LOCKED ${t[t.blk==1].pts_real.sum()*PT_VALUE:,.0f} over {int((t.blk==1).sum())} "
      f"= ${t[t.blk==1].pts_real.mean()*PT_VALUE:.2f}/trade")

print("\n" + "=" * 104)
print("W4.2  HOW MUCH OF THAT IS THE COST ASSUMPTION?")
print("=" * 104)
for mult, lab in ((0.0, "zero cost"), (1.0, "as modelled"), (2.0, "2x"), (4.0, "4x")):
    q = T.run(D, lg, sh, rt=S.RT_POINTS * mult, slip=S.SLIP_POINTS * mult)
    q["defl"] = pd.to_datetime(q.day.to_numpy(), unit="D")
    q["pr"] = q.pts * pd.Series(q.defl).map(defl).ffill().fillna(j.ratio.iloc[-1]).to_numpy()
    print(f"  {lab:>12}: ${q.pr.sum()*PT_VALUE:>8,.0f} total   "
          f"${q.pr.mean()*PT_VALUE:>6.2f}/trade   PF {q.pr[q.pr>0].sum()/max(-q.pr[q.pr<0].sum(),1e-9):.3f}")
print("  A 3xATR stop on 5m NQ is ~45 points, so the 1.72-point round turn is under 4% of risk --")
print("  this is one of the few candidates on this branch where cost is not the binding question.")

print("\n" + "=" * 104)
print("W4.3  WHAT A LIVE ACCOUNT WOULD HAVE FELT")
print("=" * 104)
m = pd.Series(full.to_numpy() * PT_VALUE, index=pd.to_datetime(full.index, unit="D")).resample("ME").sum()
print(f"  months traded {len(m)}   positive {int((m>0).sum())} = {(m>0).mean():.0%}   "
      f"best ${m.max():,.0f}   worst ${m.min():,.0f}")
neg = 0; worst = 0
for v in m:
    neg = neg + 1 if v <= 0 else 0
    worst = max(worst, neg)
print(f"  longest run of losing MONTHS: {worst}")
print(f"  first 12 months: ${m.iloc[:12].sum():,.0f}   next 12: ${m.iloc[12:24].sum():,.0f}   "
      f"rest: ${m.iloc[24:].sum():,.0f}")
print(f"\ntotal {time.time()-t0:.0f}s")
