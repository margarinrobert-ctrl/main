"""Drop-one-year and walk-forward on the optimised family. RESEARCH ONLY."""
import numpy as np, pandas as pd, sys, itertools, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
TM, ORD = "barclose", "adverse"
NQ = dict(point_value=20.0, qty=1)
RTH = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)
ATRD = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0, trail_offset_atr=0.5)
BASE = {**NQ, **ATRD, **RTH}
WIN = dict(trend_ema=34, trend_ma="ema", fast_ema=13, slow_ema=34)


def book(mask=R, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    return nqs.simulate(df, I, p, lo & mask, sh & mask, order=ORD, trail_mode=TM)


print("=" * 116)
print("29. DROP-ONE-YEAR - does the result survive removing any single year?")
print("=" * 116)
tr = book(**BASE, **WIN)
yr = pd.DatetimeIndex(tr.ts).year
full = tr.net_pts.mean()
print(f"  full research block          n={len(tr):>5}  net {full:+.2f} pts/trade")
rows = []
for y in sorted(set(yr)):
    g = tr[yr != y]
    rows.append(dict(dropped=y, n=len(g), exp=g.net_pts.mean()))
    flag = "  <-- collapses" if g.net_pts.mean() < 1.0 else ""
    print(f"  drop {y}                    n={len(g):>5}  net {g.net_pts.mean():+.2f} pts/trade{flag}")
g = tr[(yr != 2020) & (yr != 2022)]
print(f"  drop 2020 AND 2022           n={len(g):>5}  net {g.net_pts.mean():+.2f} pts/trade")
gross_rt = 2 * 0.25 + 2 * 1.24 / 20.0
print(f"  (round turn on full-size NQ is {gross_rt:.2f} pts, so anything under that is a loss)")
pd.DataFrame(rows).to_csv(OUT + "dropyear.csv", index=False)

print("\n" + "=" * 116)
print("30. WALK-FORWARD over the optimised family - re-select the MA on every training window")
print("=" * 116)
GRID = list(itertools.product([34, 50, 89, 144, 200], ["ema", "sma"], [5, 8, 13, 21], [21, 34, 50]))
GRID = [g for g in GRID if g[2] < g[3]]
books = {}
for tn, tt, fn, sn in GRID:
    t = book(**BASE, trend_ema=tn, trend_ma=tt, fast_ema=fn, slow_ema=sn)
    if len(t) >= 80:
        books[(tn, tt, fn, sn)] = (t.sess.values, t.net_pts.values)
print(f"  {len(books)} books with >=80 research trades")
rs = np.unique(df.sess.values[R])
wf = {}
for tr_s, te_s in ((400, 150), (600, 200)):
    s0, folds, oos = rs.min(), [], []
    while s0 + tr_s + te_s <= rs.max():
        best, bv = None, -np.inf
        for k, (bs, net) in books.items():
            m = (bs >= s0) & (bs < s0 + tr_s)
            if m.sum() < 25: continue
            if net[m].mean() > bv: bv, best = net[m].mean(), k
        if best is None: s0 += te_s; continue
        bs, net = books[best]
        m = (bs >= s0 + tr_s) & (bs < s0 + tr_s + te_s)
        folds.append(dict(is_exp=bv, oos_exp=net[m].mean() if m.sum() else np.nan,
                          n=int(m.sum()), cfg=str(best)))
        if m.sum(): oos.append(net[m])
        s0 += te_s
    F = pd.DataFrame(folds); allo = np.concatenate(oos) if oos else np.array([])
    bsm = np.array([np.random.default_rng(i).choice(allo, len(allo)).mean() for i in range(2000)])
    lo_, hi_ = np.percentile(bsm, 2.5), np.percentile(bsm, 97.5)
    ok = bool(allo.mean() > 0 and lo_ > 0 and (F.oos_exp > 0).mean() >= 0.60 and F.oos_exp.median() > 0)
    wf[f"{tr_s}/{te_s}"] = dict(folds=len(F), profitable=float((F.oos_exp > 0).mean()),
                                median_is=float(F.is_exp.median()), median_oos=float(F.oos_exp.median()),
                                stitched=float(allo.mean()), ci_lo=float(lo_), ci_hi=float(hi_),
                                worst=float(F.oos_exp.min()), n=int(len(allo)),
                                modal=float(F.cfg.value_counts().iloc[0] / len(F)), PASS=ok)
    print(f"  train {tr_s}/test {te_s}: {len(F)} folds  profitable {(F.oos_exp>0).mean():.0%}  "
          f"median IS {F.is_exp.median():+.2f} -> OOS {F.oos_exp.median():+.2f}  "
          f"stitched {allo.mean():+.2f} CI [{lo_:+.2f},{hi_:+.2f}]  worst {F.oos_exp.min():+.2f}  "
          f"modal cfg {F.cfg.value_counts().iloc[0]/len(F):.0%}  {'PASS' if ok else 'FAIL'}")
    print(f"    fold OOS: " + "  ".join(f"{v:+.2f}" for v in F.oos_exp))
json.dump(wf, open(OUT + "walkforward_opt.json", "w"), indent=2)
