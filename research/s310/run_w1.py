"""W1 -- is it an edge or a regime? Four tests that need no new data and select nothing.

The claim under test is mine, not the rule's: I said S3's result is one regime read twice. That is
falsifiable on the data already here, and these are the tests that do it. NOTHING IS SELECTED in
any of them -- the constants are the shipped ones throughout, so there is no multiplicity to
deflate and no holdout being spent.

Declared before running:
  W1.1  every quarter of the whole sample, fixed constants. An edge is positive in most quarters
        across BOTH halves. A regime is positive only in the recent block.
  W1.2  the split date swept. If "research positive, locked positive" holds at many cut dates the
        result is not an artifact of where the cut happens to fall.
  W1.3  concentration. If the top 5% of trades carry the whole result it is a tail, not an edge.
  W1.4  the expanding walk-forward equity a trader would actually have lived through.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

D, F, base = T.build(5)              # the SHIPPED timeframe -- this tests the 5m claim, not 10m
lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)
t["ts"] = pd.to_datetime(t.day.to_numpy(), unit="D")
t["q"] = t.ts.dt.to_period("Q")
all_days = pd.to_datetime(D["all_days"], unit="D")
print(f"  NQ 5m, k3/w20, shipped geometry: {len(t)} trades over {len(all_days)} sessions, "
      f"{all_days.min().date()} to {all_days.max().date()}")

print("\n" + "=" * 112)
print("W1.1  EVERY QUARTER, FIXED CONSTANTS -- nothing selected, nothing held out")
print("=" * 112)
rows = []
for q, g in t.groupby("q"):
    r = g.pts.to_numpy()
    dq = all_days[(all_days >= q.start_time) & (all_days <= q.end_time)]
    shp, _ = S.day_sharpe(g.day.to_numpy(), r, np.array(
        [int(x) for x in (dq.normalize().values.astype("datetime64[D]").astype(np.int64))]))
    rows.append(dict(quarter=str(q), n=len(r), pts=r.mean(), total=r.sum(),
                     pf=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), win=(r > 0).mean(),
                     sharpe=shp, block="research" if q.end_time < pd.Timestamp(D["cut_date"])
                     else ("LOCKED" if q.start_time >= pd.Timestamp(D["cut_date"]) else "straddles")))
Q = pd.DataFrame(rows)
Q.to_csv(R + "w1_quarters.csv", index=False)
print(Q.round(3).to_string(index=False))
sc = Q[Q.n >= 15]
pre = sc[sc.quarter < "2024Q3"]; post = sc[sc.quarter >= "2024Q3"]
print(f"\n  quarters with >=15 trades: {len(sc)}")
print(f"  positive overall            : {(sc.pts>0).sum()} of {len(sc)} = {(sc.pts>0).mean():.0%}")
print(f"  positive in the FIRST half  : {(pre.pts>0).sum()} of {len(pre)} = {(pre.pts>0).mean():.0%}"
      f"   mean {pre.pts.mean():+.2f} pts")
print(f"  positive in the SECOND half : {(post.pts>0).sum()} of {len(post)} = {(post.pts>0).mean():.0%}"
      f"   mean {post.pts.mean():+.2f} pts")
print("  AN EDGE IS POSITIVE IN BOTH HALVES. A REGIME IS POSITIVE IN ONE.")

print("\n" + "=" * 112)
print("W1.2  THE SPLIT DATE SWEPT -- does the verdict depend on where the cut falls?")
print("=" * 112)
rows = []
for frac in np.arange(0.30, 0.86, 0.05):
    cd = int(D["all_days"][int(frac * len(D["all_days"]))])
    a = t[t.day < cd].pts.to_numpy(); b = t[t.day >= cd].pts.to_numpy()
    if len(a) < 60 or len(b) < 60:
        continue
    rows.append(dict(frac=frac, cut=str(pd.Timestamp(cd, unit="D").date()),
                     n_a=len(a), pts_a=a.mean(), pf_a=a[a > 0].sum() / max(-a[a < 0].sum(), 1e-9),
                     n_b=len(b), pts_b=b.mean(), pf_b=b[b > 0].sum() / max(-b[b < 0].sum(), 1e-9)))
SP = pd.DataFrame(rows)
SP.to_csv(R + "w1_splits.csv", index=False)
print(SP.round(3).to_string(index=False))
both = ((SP.pts_a > 0) & (SP.pts_b > 0)).sum()
print(f"\n  cuts where BOTH sides are profitable: {both} of {len(SP)}")
print(f"  the shipped cut (0.65) is at frac 0.65; the EARLIER the cut, the more of the weak")
print(f"  stretch sits in the first block -- read the pts_a column top to bottom.")

print("\n" + "=" * 112)
print("W1.3  CONCENTRATION -- is the result a population or a handful of trades?")
print("=" * 112)
for b, bl in ((0, "research"), (1, "LOCKED")):
    r = np.sort(t[t.blk == b].pts.to_numpy())[::-1]
    tot = r.sum()
    line = f"  {bl:8s} n {len(r):4d}  total {tot:+9.1f}"
    for pc in (0.01, 0.05, 0.10, 0.25):
        k = max(int(round(pc * len(r))), 1)
        line += f"   top {pc:.0%} ({k:3d}) = {r[:k].sum()/tot:6.1%}"
    print(line)
    med = np.median(r)
    print(f"           median trade {med:+.2f} pts;  "
          f"share of trades that are winners {np.mean(r>0):.1%};  "
          f"result WITHOUT the best 5%: {r[max(int(round(.05*len(r))),1):].mean():+.3f} pts/trade")
print("  A result that survives removing its best 5% is a population. One that does not is a tail.")

print("\n" + "=" * 112)
print("W1.4  THE EQUITY A TRADER WOULD HAVE LIVED THROUGH -- fixed constants, day one to the end")
print("=" * 112)
d = t.groupby("day").pts.sum()
full = pd.Series(0.0, index=pd.Index(D["all_days"]))
full.loc[d.index] = d.to_numpy()
eq = full.cumsum()
dd = np.maximum.accumulate(eq.to_numpy()) - eq.to_numpy()
yr = pd.Series(full.to_numpy(), index=pd.to_datetime(full.index, unit="D")).resample("YE").sum()
print("  cumulative points by year-end, and the running drawdown:")
for ts, v in yr.items():
    m = pd.to_datetime(full.index, unit="D") <= ts
    print(f"    {ts.year}: year {v:+9.1f} pts   cumulative {eq.to_numpy()[m][-1]:+9.1f}   "
          f"max DD so far {dd[m].max():8.1f}")
print(f"\n  worst drawdown over the whole sample {dd.max():.1f} pts "
      f"(= ${dd.max()*2:,.0f} on one MNQ contract)")
neg = (full < 0).to_numpy()
runs = np.diff(np.flatnonzero(np.concatenate(([True], full.to_numpy() > 0, [True]))))
print(f"  longest run of losing SESSIONS: {int(runs.max()-1) if len(runs) else 0}")
full.to_csv(R + "w1_daily.csv")
print(f"\ntotal {time.time()-t0:.0f}s")
