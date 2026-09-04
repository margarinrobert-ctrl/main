"""Why is every MA structure positive? Three tests that separate 'the MA entry is
good' from 'the window is doing it'.

1. DECOMPOSITION - how much of the Phase B number is the window, and how much is
   the MA search on top of it.
2. PLACEBO SIGNAL - keep the window, the trend gate and the pullback, but replace
   the StochRSI trigger with a random draw at the same rate. If the placebo earns
   the same, the entry rule is not what is earning it.
3. CONCENTRATION - year by year, and long vs short.
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
TM, ORD = "barclose", "adverse"
NQ = dict(point_value=20.0, qty=1)
RTH = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)
ATRD = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0, trail_offset_atr=0.5)
WIN = dict(trend_ema=34, trend_ma="ema", fast_ema=13, slow_ema=34)   # Phase B winner


def book(mask=R, cost_mult=1.0, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    return nqs.simulate(df, I, p, lo & mask, sh & mask, order=ORD, trail_mode=TM,
                        cost_mult=cost_mult), I, p, lo, sh


print("=" * 120)
print("26. DECOMPOSITION - what is actually producing the Phase B number?")
print("=" * 120)
LADDER = [
    ("as written, MNQ, full window", dict()),
    ("+ full-size NQ cost model", dict(**NQ)),
    ("+ ATR-relative distances", dict(**NQ, **ATRD)),
    ("+ RTH window 09:31-11:00 NY", dict(**NQ, **ATRD, **RTH)),
    ("+ best MA of 165 searched (ema34, 13/34)", dict(**NQ, **ATRD, **RTH, **WIN)),
]
prev = None
for lbl, kw in LADDER:
    tr, I, p, lo, sh = book(**kw)
    g = NC.score(df, I, p, tr, n_draws=300, mask=R, order=ORD, trail_mode=TM)
    d = "" if prev is None else f"   step {g['exp']-prev:+.2f}"
    print(f"  {lbl:<44} n={g['n']:>5} net{g['exp']:>+7.2f} ctrl{g['ctrl']:>+7.2f} "
          f"excess{g['excess']:>+7.2f} p={g['p']:.4f}{d}")
    prev = g["exp"]

print("\n" + "=" * 120)
print("27. PLACEBO - same window, same trend gate, same pullback, RANDOM trigger timing")
print("    If a coin flip in this window earns what the StochRSI cross earns, the entry rule is decoration.")
print("=" * 120)
kw = dict(**NQ, **ATRD, **RTH, **WIN)
I, p = cache.indicators(df, B, **kw)
(lo, sh), insess = nqs.conditions(df, I, p)
real = nqs.simulate(df, I, p, lo & R, sh & R, order=ORD, trail_mode=TM)
# the pullback+trend context WITHOUT the StochRSI condition, inside the window
c = I["c"]
up, dn = c > I["trend"], c < I["trend"]
thr = p["pullback_atr"] * I["atr"]
touch_l = (I["l"] <= I["fast"]) | (I["l"] <= I["slow"])
touch_s = (I["h"] >= I["fast"]) | (I["h"] >= I["slow"])
ctx_l = up & ((I["swing_hi"] - I["l"]) >= thr) & touch_l & insess & np.isfinite(I["atr"])
ctx_s = dn & ((I["h"] - I["swing_lo"]) >= thr) & touch_s & insess & np.isfinite(I["atr"])
print(f"  real rule            n={len(real):>5}  net {real.net_pts.mean():+.2f} pts/trade")
print(f"  context bars (trend+pullback+window, NO StochRSI): long {int((ctx_l&R).sum())}, short {int((ctx_s&R).sum())}")
ctx = nqs.simulate(df, I, p, ctx_l & R, ctx_s & R, order=ORD, trail_mode=TM)
print(f"  take EVERY context bar (no StochRSI at all)  n={len(ctx):>5}  net {ctx.net_pts.mean():+.2f} pts/trade")
rng = np.random.default_rng(0)
rate_l = (lo & R).sum() / max((ctx_l & R).sum(), 1)
rate_s = (sh & R).sum() / max((ctx_s & R).sum(), 1)
res = []
for s_ in range(200):
    r = np.random.default_rng(s_)
    pl = ctx_l & R & (r.random(len(df)) < rate_l)
    ps = ctx_s & R & (r.random(len(df)) < rate_s)
    t = nqs.simulate(df, I, p, pl, ps, order=ORD, trail_mode=TM)
    if len(t) > 30: res.append(t.net_pts.mean())
res = np.array(res)
pv = float((res >= real.net_pts.mean()).mean())
print(f"  PLACEBO: random trigger at the same rate inside the same context, 200 draws")
print(f"    placebo net p5 {np.percentile(res,5):+.2f}  median {np.percentile(res,50):+.2f}  "
      f"p95 {np.percentile(res,95):+.2f}   real {real.net_pts.mean():+.2f}   p = {pv:.4f}")

print("\n" + "=" * 120)
print("28. CONCENTRATION - is it a few periods?")
print("=" * 120)
yr = pd.DatetimeIndex(real.ts).year
print(f"  {'year':<7}{'n':>6}{'net/trade':>12}{'total pts':>12}")
for y in sorted(set(yr)):
    g = real[yr == y]
    print(f"  {y:<7}{len(g):>6}{g.net_pts.mean():>+12.2f}{g.net_pts.sum():>+12.0f}")
L, S = real[real.side > 0], real[real.side < 0]
print(f"\n  long  n={len(L):>4} net {L.net_pts.mean():+.2f}    short n={len(S):>4} net {S.net_pts.mean():+.2f}")
srt = np.sort(real.net_pts.values)[::-1]
print(f"  top 5% of trades ({max(int(.05*len(real)),1)}) contribute {srt[:max(int(.05*len(real)),1)].sum()/real.net_pts.sum():.0%} of total P&L")
json.dump(dict(placebo_p=pv, placebo_median=float(np.median(res)),
               real=float(real.net_pts.mean()), n=int(len(real)),
               ctx_all=float(ctx.net_pts.mean()), ctx_n=int(len(ctx))),
          open(OUT + "placebo.json", "w"), indent=2)
