"""The four questions the 57-test suite leaves open for `vol rising AND midday AND
dist EMA200>2 ATR`, long, 2.5xATR stop, 3R target, 30-minute bars.

The suite returns PASS 41 / WARN 5 / FAIL 4 on this rule -- comfortably the best behaved
anything on this branch has produced. These four ask whether that survives contact with the
one thing 2022-25 NQ makes hard: separating an entry edge from a rising index.
"""
import sys, numpy as np; sys.path.insert(0,'research')
from test_suite import build, _daily, _sharpe
C=["vol rising","midday","dist EMA200>2 ATR"]
K=dict(atr_mult=2.5,tp_r=3.0,flat_min=0,tf=30)

print("="*92); print("1. DIRECTION -- the test section 4c says decides it"); print("="*92)
for sd,nm in ((1,"long"),(-1,"short")):
    s=build(C,side=sd,**K)
    r=s.pnl[s.ent_sess<s.cut].sum(); l=s.pnl[s.ent_sess>=s.cut].sum()
    print(f"   {nm:<6} {len(s.pnl):>4} trades  net ${s.pnl.sum():>9,.0f}   research ${r:>9,.0f}   locked ${l:>8,.0f}"
          f"   win {100*(s.pnl>0).mean():>5.1f}%")
L=build(C,side=1,**K); S=build(C,side=-1,**K)
print(f"\n   long + short together: ${L.pnl.sum()+S.pnl.sum():,.0f}"
      f"  (a real entry edge is not destroyed by trading both ways)")

print(); print("="*92); print("2. IS IT THE DRIFT? matched null, restricted to the SAME clock window"); print("="*92)
d=L.bars; mod=d["mod"]; c=d["c"]
mid=np.flatnonzero((mod>=690)&(mod<810)); mid=mid[(mid>300)&(mid<len(c)-2)]
rng=np.random.default_rng(5); n=len(L.pnl); obs=L.pnl.sum()
beat=0; draws=400; nets=[]
for _ in range(draws):
    t=np.sort(rng.choice(mid,size=n,replace=False))
    v=build(C,side=1,trig=t,**K).pnl.sum(); nets.append(v); beat+= v>=obs
nets=np.array(nets)
print(f"   observed ${obs:,.0f}")
print(f"   {draws} random midday-only entries, same trade count: median ${np.median(nets):,.0f}"
      f"  p5 ${np.percentile(nets,5):,.0f}  p95 ${np.percentile(nets,95):,.0f}")
print(f"   p = {(beat+1)/(draws+1):.4f}   ({beat} of {draws} random midday sets matched or beat it)")

print(); print("="*92); print("3. WHAT THE THREE CONDITIONS EACH CONTRIBUTE"); print("="*92)
for i in range(3):
    sub=[x for j,x in enumerate(C) if j!=i]
    r=build(sub,side=1,**K)
    print(f"   without '{C[i]}'   {len(r.pnl):>4} trades   ${r.pnl.sum():>9,.0f}"
          f"   research ${r.pnl[r.ent_sess<r.cut].sum():>8,.0f}   locked ${r.pnl[r.ent_sess>=r.cut].sum():>8,.0f}")
solo=build(["dist EMA200>2 ATR"],side=1,**K)
print(f"   'dist EMA200>2 ATR' ALONE  {len(solo.pnl):>4} trades   ${solo.pnl.sum():>9,.0f}"
      f"   research ${solo.pnl[solo.ent_sess<solo.cut].sum():>8,.0f}   locked ${solo.pnl[solo.ent_sess>=solo.cut].sum():>8,.0f}")

print(); print("="*92); print("4. PER-TRADE EDGE, RESEARCH vs LOCKED"); print("="*92)
for nm,m in (("research",L.ent_sess<L.cut),("locked",L.ent_sess>=L.cut)):
    p=L.pnl[m]
    print(f"   {nm:<9} {len(p):>4} trades  ${p.sum():>9,.0f}  ${p.mean():>7,.0f}/trade"
          f"  win {100*(p>0).mean():>5.1f}%  (bound 25.0%)  PF {p[p>0].sum()/-p[p<=0].sum():.2f}")
