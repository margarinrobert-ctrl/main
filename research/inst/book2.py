"""The book again, this time keeping only the leg x feed pairs that are POSITIVE ON RESEARCH
(a legitimate research-only selection), then reading the reserved blocks once."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research/top5"))
import t5_adapt as A
warnings.filterwarnings("ignore")
def pf(p): w = p > 0; return p[w].sum() / max(1e-9, -p[~w].sum())
LEGS = [("FTM_ORB", ("NQ",)), ("APM_VWAP", ("NQ", "US100", "US30")), ("TFI", ("NQ", "US100", "US30")),
        ("TRENDDAY", ("NQ", "US100", "US30"))]
tabs = []
for name, feeds in LEGS:
    for fd in feeds:
        b = A.bundle(name, fd); t = b["tr"].copy(); t["leg"] = name; t["feed"] = fd
        t["blk"] = np.where(t["block"] == "research", "research", "reserved"); tabs.append(t)
T = pd.concat(tabs, ignore_index=True)
keep = []
for (lg, fd), s in T[T.blk == "research"].groupby(["leg", "feed"]):
    if len(s) >= 25 and pf(s.pct.to_numpy()) > 1.10: keep.append((lg, fd))
print("legs kept by RESEARCH PF > 1.10 (n >= 25):", keep)
S = T[[ (a, b) in keep for a, b in zip(T.leg, T.feed)]]
for bk in ("research", "reserved"):
    s = S[S.blk == bk]; yrs = (s.ts.max() - s.ts.min()).days / 365.25
    daily = s.groupby(s.ts.dt.normalize())["pct"].sum(); sh = np.sqrt(252) * daily.mean() / daily.std()
    x = np.sort(s.pct.to_numpy())[::-1]; tot = x.sum()
    print(f"  {bk:9s}: {len(s):>5,} trades / {yrs:.1f} yrs = {len(s)/yrs:>4.0f} trades/yr  pooled PF {pf(s.pct.to_numpy()):.3f}  pct/trade {s.pct.mean():+.4f}  "
          f"win {100*(s.pct>0).mean():.1f}%  Sharpe {sh:.2f}  top 5% of trades = {100*x[:len(x)//20].sum()/tot:.0f}% of net")
# the two best-PF legs only, for the trade-off
for lgs in (("TRENDDAY",), ("TRENDDAY", "APM_VWAP"), ("FTM_ORB",)):
    s2 = S[S.leg.isin(lgs)]
    for bk in ("research", "reserved"):
        s = s2[s2.blk == bk]; yrs = (s.ts.max() - s.ts.min()).days / 365.25
        print(f"  {'+'.join(lgs):20s} {bk:9s}: {len(s):>5,} trades = {len(s)/yrs:>4.0f}/yr  PF {pf(s.pct.to_numpy()):.3f}")
