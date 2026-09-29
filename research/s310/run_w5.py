"""W5 -- the out-of-sample block on its own, in dollars.

The locked block is the only part of this sample that had no say in choosing the rule. It is also
one year and 179 trades, so it is reported month by month rather than as a single number.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"; PT = 2.0
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)
D, F, base = T.build(5)
lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)
t["ts"] = pd.to_datetime(t.day.to_numpy(), unit="D")

# deflator (see W4)
u = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
u.columns = [c.strip().lower() for c in u.columns]
u["ts"] = pd.to_datetime(u["datetime"].astype(str).str.strip(), format="%Y.%m.%d %H:%M:%S",
                         errors="coerce")
u = u.dropna(subset=["ts"]).sort_values("ts").set_index("ts")
u.index = u.index - pd.Timedelta(hours=7)
j = pd.DataFrame({"nq": pd.Series(D["c"], index=D["ix"]).resample("D").last(),
                  "us": u["close"].resample("D").last()}).dropna()
defl = (j.us / j.nq).reindex(pd.date_range(j.index.min(), t.ts.max(), freq="D")).ffill()
t["pr"] = t.pts * t.ts.map(defl).ffill().fillna((j.us / j.nq).iloc[-1]).to_numpy()

o = t[t.blk == 1].copy()
days_o = D["all_days"][D["all_days"] >= D["cut_day"]]
span = pd.to_datetime(days_o, unit="D")
r = o.pr.to_numpy()
shp, _ = S.day_sharpe(o.day.to_numpy(), r, days_o)

print("=" * 96)
print("W5.1  THE OUT-OF-SAMPLE BLOCK -- read once, nothing selected in it")
print("=" * 96)
print(f"  period            {span.min().date()} to {span.max().date()}  "
      f"({len(days_o)} sessions, {len(days_o)/252:.2f} years)")
print(f"  trades            {len(o)}   ({len(o)/(len(days_o)/252):.0f} a year)")
print(f"  NET               ${r.sum()*PT:,.0f}  on ONE MNQ contract, costs included")
print(f"  per trade         ${r.mean()*PT:.2f}   (median ${np.median(r)*PT:.2f})")
print(f"  profit factor     {r[r>0].sum()/-r[r<0].sum():.3f}")
print(f"  win rate          {(r>0).mean():.1%}   ({int((r>0).sum())}W / {int((r<=0).sum())}L)")
print(f"  Sharpe            {shp:+.2f}   (over EVERY session in the block, zero-filled)")
d = o.groupby("day").pr.sum()
full = pd.Series(0.0, index=pd.Index(days_o)); full.loc[d.index] = d.to_numpy()
eq = full.cumsum().to_numpy() * PT
dd = np.maximum.accumulate(eq) - eq
print(f"  max drawdown      ${dd.max():,.0f}   return/drawdown {eq[-1]/dd.max():.2f}")
print(f"  avg win / avg loss ${r[r>0].mean()*PT:,.0f} / ${r[r<=0].mean()*PT:,.0f}")
print(f"  biggest win / loss ${r.max()*PT:,.0f} / ${r.min()*PT:,.0f}")

print("\n" + "=" * 96)
print("W5.2  MONTH BY MONTH -- 179 trades over one year is not one number")
print("=" * 96)
m = pd.Series(full.to_numpy() * PT, index=pd.to_datetime(full.index, unit="D")).resample("ME")
mm = m.sum(); mn = o.set_index("ts").resample("ME").size()
print(f"  {'month':>9} {'trades':>7} {'$':>9} {'cum $':>9}")
cum = 0.0
for ts, v in mm.items():
    cum += v
    print(f"  {ts.strftime('%Y-%m'):>9} {int(mn.get(ts,0)):>7} {v:>9,.0f} {cum:>9,.0f}")
print(f"\n  positive months {int((mm>0).sum())} of {len(mm)} = {(mm>0).mean():.0%}   "
      f"best ${mm.max():,.0f}   worst ${mm.min():,.0f}")
runs = 0; worst = 0
for v in mm:
    runs = runs + 1 if v <= 0 else 0
    worst = max(worst, runs)
print(f"  longest losing run: {worst} months")

print("\n" + "=" * 96)
print("W5.3  WHAT THE OOS BLOCK DOES AND DOES NOT ESTABLISH")
print("=" * 96)
print("  it clears a matched random entry                p 0.018")
print("  it clears a coin-flip side on its own bars      p 0.008")
print("  day-block bootstrap against ZERO                P(mean<=0) 0.032")
print("  its median trade beats the control in           99.8% of draws")
print("  --")
print("  it is ONE YEAR and ONE MARKET, and 2025 was the rule's best calendar year;")
print("  the research block earns $4.44 a trade against this block's "
      f"${r.mean()*PT:.2f}, so the forward")
print("  expectation is somewhere in that range and much nearer the low end.")
print(f"\ntotal {time.time()-t0:.0f}s")
