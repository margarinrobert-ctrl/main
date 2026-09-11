"""O4 -- the dollar answer for FTM alpha.2, with the synthetic-level deflator applied.

The FTM simulator runs on NQ_1m, the same series whose index levels sit above the real Nasdaq-100
(STUDY_US100). Dollars are therefore inflated and inflated most early. The S3 study deflated for
exactly this reason; the same correction belongs here.

Note the sizing: unlike a one-contract study, FTM sizes itself -- FixedDollar, $535 risk, max 2
contracts on a $50,000 account -- so these dollars are ACCOUNT dollars, not per-contract dollars.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/ftm")
import numpy as np, pandas as pd

R = "results/ftm2/"
OOS = pd.Timestamp("2025-01-01")
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)

t = pd.read_parquet(R + "o1_a2.parquet")
t["time"] = pd.to_datetime(t.time)

# the deflator, from the second feed (see research/s310/run_w4.py)
u = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
u.columns = [c.strip().lower() for c in u.columns]
u["ts"] = pd.to_datetime(u["datetime"].astype(str).str.strip(), format="%Y.%m.%d %H:%M:%S",
                         errors="coerce")
u = u.dropna(subset=["ts"]).sort_values("ts").set_index("ts")
u.index = u.index - pd.Timedelta(hours=7)
nq = pd.read_csv("data/NQ_1m.csv") if False else None
import ftm_sim as FS
f = FS.load_nq()
j = pd.DataFrame({"nq": f["close"].resample("D").last(),
                  "us": u["close"].resample("D").last()}).dropna()
ratio = (j.us / j.nq)
defl = ratio.reindex(pd.date_range(ratio.index.min(), t.time.max(), freq="D")).ffill()
t["defl"] = t.time.dt.normalize().map(defl).ffill().fillna(ratio.iloc[-1]).to_numpy()
t["real"] = t.usd * t.defl
print(f"  {len(j)} overlapping sessions; ratio {ratio.iloc[0]:.4f} -> {ratio.iloc[-1]:.4f}")
print(f"  mean deflator: in-sample {t[t.time<OOS].defl.mean():.4f}, "
      f"out-of-sample {t[t.time>=OOS].defl.mean():.4f}"
      f"  -> raw dollars overstate by {1/t[t.time<OOS].defl.mean()-1:.1%} and "
      f"{1/t[t.time>=OOS].defl.mean()-1:.1%}")

print("\n" + "=" * 104)
print("O4.1  IS IT PROFITABLE? -- deflated, account dollars, costs included, nothing selected")
print("=" * 104)
t["yr"] = t.time.dt.year
print(f"  {'year':>6} {'trades':>7} {'raw $':>9} {'real $':>9} {'PF':>6} {'win':>7} {'$/trade':>9}")
for y, g in t.groupby("yr"):
    r = g.real.to_numpy()
    print(f"  {y:>6} {len(g):>7} {g.usd.sum():>9,.0f} {r.sum():>9,.0f} "
          f"{r[r>0].sum()/max(-r[r<0].sum(),1e-9):>6.3f} {(r>0).mean():>7.1%} {r.mean():>9,.2f}")
tot = t.real.sum()
span = (t.time.max() - t.time.min()).days / 365.25
print(f"  {'TOTAL':>6} {len(t):>7} {t.usd.sum():>9,.0f} {tot:>9,.0f}")
print(f"\n  over {span:.2f} years = ${tot/span:,.0f} a year on a $50,000 account "
      f"= {tot/span/50000:.1%} a year")
print(f"  {len(t)/span:.0f} trades a year at ${tot/len(t):.2f} a trade")

d = t.groupby(t.time.dt.normalize()).real.sum()
eq = d.cumsum().to_numpy()
dd = float((eq - np.maximum.accumulate(eq)).min())
print(f"  worst drawdown ${-dd:,.0f} = {-dd/50000:.1%} of the account; "
      f"return/drawdown {tot/max(-dd,1e-9):.2f}")

print("\n  by block:")
for bl, s in (("in-sample", t[t.time < OOS]), ("OUT-OF-SAMPLE", t[t.time >= OOS])):
    r = s.real.to_numpy()
    dd2 = s.groupby(s.time.dt.normalize()).real.sum().cumsum().to_numpy()
    ddv = float((dd2 - np.maximum.accumulate(dd2)).min())
    sp = (s.time.max() - s.time.min()).days / 365.25
    print(f"    {bl:>14}: {len(s):>4} trades  ${r.sum():>8,.0f}  ${r.mean():>7,.2f}/trade  "
          f"PF {r[r>0].sum()/-r[r<0].sum():.3f}  DD ${-ddv:>6,.0f}  "
          f"= ${r.sum()/max(sp,.01):>7,.0f}/yr")

print("\n" + "=" * 104)
print("O4.2  WHAT A LIVE ACCOUNT WOULD HAVE FELT")
print("=" * 104)
m = d.resample("ME").sum()
print(f"  months traded {len(m)}   positive {int((m>0).sum())} = {(m>0).mean():.0%}   "
      f"best ${m.max():,.0f}   worst ${m.min():,.0f}")
run = 0; worst = 0
for v in m:
    run = run + 1 if v <= 0 else 0
    worst = max(worst, run)
print(f"  longest run of losing MONTHS: {worst}")
q = d.resample("QE").sum()
print(f"  quarters: {int((q>0).sum())} of {len(q)} positive")
print(f"  first 12 months ${m.iloc[:12].sum():,.0f}   next 12 ${m.iloc[12:24].sum():,.0f}   "
      f"rest ${m.iloc[24:].sum():,.0f}")
print("\n  month by month:")
cum = 0.0
for ts, v in m.items():
    cum += v
    print(f"    {ts.strftime('%Y-%m')}  {v:>8,.0f}   cum {cum:>9,.0f}")
t.to_parquet(R + "o4_deflated.parquet")
print(f"\ntotal {time.time()-t0:.0f}s")


# ---------------------------------------------------------------------------
print("\n" + "=" * 104)
print("O4.3  THE WINTER BLOCK -- every published FTM figure is on a sample missing Nov-Feb")
print("=" * 104)
print("  The source requires a 23:00 UTC reference open. On this feed that bar DOES NOT EXIST")
print("  from November to early March: in winter 23:00 UTC is 18:00 New York, the CME session")
print("  open minute, and the feed carries no bar for it. Measured: 23:00 UTC bars per month run")
print("  20-23 from March to October and ZERO in Dec/Jan/Feb. The date then blocks.")
print("  The SHIPPED PINE defaults `refOpenFallback` to ON, so the script trades those months")
print("  and the research does not. Both are run here.")
import ftm_sim as FS2
rows = []
for lab, fb in (("source: no fallback (all published figures)", False),
                ("shipped Pine: fallback ON", True)):
    _, q = FS2.run(verbose=False, prior_bars=1, h2_cap=1, ref_fallback=fb)
    q["time"] = pd.to_datetime(q.time)
    q["defl"] = q.time.dt.normalize().map(defl).ffill().fillna(ratio.iloc[-1]).to_numpy()
    q["real"] = q.usd * q.defl
    w = q[q.time.dt.month.isin([11, 12, 1, 2])]
    dd_s = q.groupby(q.time.dt.normalize()).real.sum().cumsum().to_numpy()
    ddv = float((dd_s - np.maximum.accumulate(dd_s)).min())
    sp = (q.time.max() - q.time.min()).days / 365.25
    io = q[q.time >= OOS]
    rows.append(dict(config=lab, n=len(q), real=q.real.sum(), per_trade=q.real.mean(),
                     R=q.R.mean(), per_yr_usd=q.real.sum() / sp, dd=-ddv,
                     ret_dd=q.real.sum() / max(-ddv, 1e-9), n_winter=len(w),
                     winter_usd=w.real.sum(), n_oos=len(io), oos_usd=io.real.sum(),
                     oos_R=io.R.mean()))
W = pd.DataFrame(rows)
W.to_csv(R + "o4_winter.csv", index=False)
print()
print(W.round(3).to_string(index=False))
print("\n  The script takes 69% more trades for 46% more dollars at a 28% LOWER per-trade R.")
print("  Neither number is wrong; they are different strategies and only one has been studied.")
