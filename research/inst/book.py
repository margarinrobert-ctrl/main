"""The best INTRADAY legs on this branch pooled into one book, in percent of entry price, with
per-feed costs -- the number a book of everything already validated here actually reaches.
Daily-position strategies (IBS, CMMA) and the 30m CVD rule (median hold 11 hours, carries
overnight) are excluded; V56 is shown separately for reference."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research/top5"))
import t5_adapt as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
LEGS = [("FTM_ORB", ("NQ",)), ("APM_VWAP", ("NQ", "US100", "US30")), ("TFI", ("NQ", "US100", "US30")),
        ("TRENDDAY", ("NQ", "US100", "US30")), ("VWAP_DRIFT", ("NQ", "US100", "US30"))]
def pf(p): w = p > 0; return p[w].sum() / max(1e-9, -p[~w].sum())
rows = []; tabs = []
for name, feeds in LEGS:
    for fd in feeds:
        try:
            b = A.bundle(name, fd)
        except Exception as e:
            print(f"  {name} {fd}: skipped ({type(e).__name__}: {str(e)[:60]})"); continue
        t = b["tr"].copy(); t["leg"] = name; t["feed"] = fd
        t["blk"] = np.where(t["block"] == "research", "research", "reserved")
        tabs.append(t)
        for bk in ("research", "reserved"):
            s = t[t.blk == bk]
            if len(s) < 10: continue
            yrs = max((s.ts.max() - s.ts.min()).days / 365.25, 0.1)
            rows.append(dict(leg=name, feed=fd, block=bk, n=len(s), tpy=len(s) / yrs, pct=s.pct.mean(), pf=pf(s.pct.to_numpy())))
L = pd.DataFrame(rows)
line("A. EACH INTRADAY LEG, per feed, research and reserved -- percent of entry price, real costs")
print(L.to_string(index=False, float_format=lambda x: f"{x:+.4f}" if abs(x) < 1 else f"{x:.2f}"))
T = pd.concat(tabs, ignore_index=True)
line("B. THE POOLED BOOK -- every leg on every feed, one unit each, trades pooled by calendar")
for bk in ("research", "reserved"):
    s = T[T.blk == bk]
    yrs = (s.ts.max() - s.ts.min()).days / 365.25
    daily = s.groupby(s.ts.dt.normalize())["pct"].sum()
    sh = np.sqrt(252) * daily.mean() / daily.std() if daily.std() > 0 else np.nan
    print(f"  {bk:9s}: {len(s):>6,} trades over {yrs:.1f} calendar years = {len(s)/yrs:>6.0f} trades/yr  pooled PF {pf(s.pct.to_numpy()):.3f}  "
          f"pct/trade {s.pct.mean():+.4f}  Sharpe (daily, traded days) {sh:.2f}")
    print(f"             by leg: " + "  ".join(f"{k} PF {pf(v.pct.to_numpy()):.2f}/n{len(v)}" for k, v in s.groupby('leg')))
line("C. DIVERSIFICATION -- correlation of daily returns between legs on shared dates (research)")
s = T[T.blk == "research"]
piv = s.groupby([s.ts.dt.normalize(), "leg"])["pct"].sum().unstack().fillna(0.0)
print(piv.corr().round(2).to_string())
line("D. WHAT THE POOLED BOOK WOULD NEED -- to reach PF 2.0 at its trade count")
s = T[T.blk == "research"]; p = s.pct.to_numpy(); w = p > 0
print(f"  research book: win {100*w.mean():.1f}%, avg win {p[w].mean():+.4f}, avg loss {p[~w].mean():+.4f}, PF {pf(p):.3f}")
need = 2.0 * (-p[~w].mean()) / (2.0 * (-p[~w].mean()) + p[w].mean())
print(f"  with the same average win and loss, PF 2.0 needs a {100*need:.1f}% win rate -- a lift of {100*(need - w.mean()):+.1f} points.")
