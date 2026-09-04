"""Phase B2 (the filters and exit geometry around the best MA structures) and
Phase C (walk-forward inside research over the whole optimised family).

RESEARCH BLOCK ONLY. Reads phaseB_ma.csv so Phase A/B1 are not re-run.
"""
import numpy as np, pandas as pd, sys, itertools, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
TM, ORD = "barclose", "adverse"
NQ = dict(point_value=20.0, qty=1)
RTH = dict(sess_start_h=8, sess_start_m=30, sess_end_h=10, sess_end_m=0)
BASE = dict(dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
            trail_offset_atr=0.5, **RTH, **NQ)


def book(mask=R, cost_mult=1.0, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    return nqs.simulate(df, I, p, lo & mask, sh & mask, order=ORD, trail_mode=TM,
                        cost_mult=cost_mult), I, p


def gate(kw, n_draws=150):
    tr, I, p = book(**kw)
    if len(tr) < 40: return None
    g = NC.score(df, I, p, tr, n_draws=n_draws, mask=R, order=ORD, trail_mode=TM)
    g["gross"] = float(book(cost_mult=0.0, **kw)[0].net_pts.mean())
    g["wr"] = float((tr.net_pts > 0).mean()); g["net_usd"] = float(tr.net_usd.sum())
    return g


B1 = pd.read_csv(OUT + "phaseB_ma.csv")
top = B1.sort_values("excess", ascending=False).head(4)
STRUCTS = [dict(trend_ema=int(r.trend_n), trend_ma=r.trend_t,
                fast_ema=int(r.fast), slow_ema=int(r.slow)) for _, r in top.iterrows()]
STRUCTS.append(dict(trend_ema=89, trend_ma="ema", fast_ema=8, slow_ema=21))  # as written
names = [f"{s['trend_ma']}{s['trend_ema']} {s['fast_ema']}/{s['slow_ema']}" for s in STRUCTS]

print("=" * 132)
print("25. PHASE B2 - FILTERS AND EXIT GEOMETRY AROUND THE BEST MA STRUCTURES")
print(f"    structures carried forward: {names}")
print("=" * 132)
FLAGS = [("none", {}),
         ("EMA align", dict(require_ema_align=True)),
         ("close back through fast MA", dict(require_close_back=True)),
         ("trend MA rising 4 bars", dict(require_slope=4)),
         ("align + close back", dict(require_ema_align=True, require_close_back=True)),
         ("cap retrace at 3 ATR", dict(max_pullback_atr=3.0)),
         ("ATR pct < 0.8", dict(atr_pct_max=0.8)),
         ("ATR pct 0.2-0.8", dict(atr_pct_min=0.2, atr_pct_max=0.8))]
GEOM = [(1.5, 2.5, 1.0, 0.5), (1.0, 2.0, 1.0, 0.5), (2.0, 3.0, 1.0, 0.5),
        (1.5, 2.5, 1.5, 0.75), (1.5, 2.5, 0.75, 0.4), (1.5, 4.0, 1.5, 0.75)]
rows = []
for si, st in enumerate(STRUCTS):
    for fl, fk in FLAGS:
        for (sm, tg, ar, of) in GEOM:
            kw = {**BASE, **st, **fk, "atr_stop": sm, "atr_target": tg,
                  "trail_arm_atr": ar, "trail_offset_atr": of}
            g = gate(kw, n_draws=120)
            if g is None: continue
            tr_, _, _ = book(**kw)
            yy = pd.DatetimeIndex(tr_.ts).year
            ex_crisis = tr_[(yy != 2020) & (yy != 2022)]
            srt = np.sort(tr_.net_pts.values)[::-1]
            k5 = max(int(0.05 * len(tr_)), 1)
            rows.append(dict(struct=names[si], flag=fl, stop=sm, targ=tg, arm=ar, off=of,
                             n=g["n"], gross=g["gross"], exp=g["exp"], ctrl=g["ctrl"],
                             excess=g["excess"], z=g["z"], p=g["p"], wr=g["wr"],
                             net_usd=g["net_usd"],
                             exp_ex_2020_2022=float(ex_crisis.net_pts.mean()) if len(ex_crisis) > 20 else np.nan,
                             n_ex=int(len(ex_crisis)),
                             top5pct_share=float(srt[:k5].sum() / tr_.net_pts.sum()) if tr_.net_pts.sum() != 0 else np.nan))
    print(f"  {names[si]:<18} done ({len(rows)} cells so far)")
B2 = pd.DataFrame(rows); B2.to_csv(OUT + "phaseB2.csv", index=False)
print(f"\n  {len(B2)} cells. net>0 in {(B2.exp>0).sum()} ({(B2.exp>0).mean():.0%}); "
      f"excess>0 and p<0.05 in {((B2.excess>0)&(B2.p<0.05)).sum()} (chance ~{0.05*len(B2):.0f})")
print("\n  MARGINAL EFFECT OF EACH FILTER (mean over structures and geometries)")
for k, r in B2.groupby("flag").agg(exp=("exp", "mean"), exc=("excess", "mean"),
                                   n=("n", "mean"), pos=("exp", lambda s: (s > 0).mean())).iterrows():
    print(f"    {k:<28} mean net {r.exp:>+6.2f}  mean excess {r.exc:>+6.2f}  "
          f"mean trades {r.n:>6.0f}  {r.pos:>4.0%} positive")
RT = 2 * 0.25 + 2 * 1.24 / 20.0
print(f"\n  THE ROBUSTNESS COLUMN THAT DECIDES IT - expectancy with 2020 and 2022 removed")
print(f"  (round turn on full-size NQ is {RT:.2f} pts; below that is a loss)")
print(f"    cells still above the round turn without 2020+2022: "
      f"{(B2.exp_ex_2020_2022 > RT).sum()} / {B2.exp_ex_2020_2022.notna().sum()}")
print(f"    ex-crisis expectancy: p5 {B2.exp_ex_2020_2022.quantile(.05):+.2f}  "
      f"median {B2.exp_ex_2020_2022.median():+.2f}  p95 {B2.exp_ex_2020_2022.quantile(.95):+.2f}")
print(f"    median share of P&L from the top 5% of trades: {B2.top5pct_share.median():.0%}")
print("\n  MARGINAL EFFECT OF EACH FILTER, ex-crisis")
for k, r in B2.groupby("flag").agg(exp=("exp", "mean"), exc=("excess", "mean"),
                                   ex=("exp_ex_2020_2022", "mean"), n=("n", "mean")).iterrows():
    print(f"    {k:<28} full {r.exp:>+6.2f}   ex-crisis {r.ex:>+6.2f}   trades {r.n:>6.0f}")
print("\n  TOP 15 BY EXCESS")
print(f"  {'structure':<18}{'filter':<28}{'geom':>18}{'n':>6}{'gross':>8}{'net':>8}{'excess':>8}{'p':>8}{'ex-crisis':>9}")
for _, x in B2.sort_values("excess", ascending=False).head(15).iterrows():
    print(f"  {x.struct:<18}{x.flag:<28}{f'{x.stop}/{x.targ}/{x.arm}/{x.off}':>18}"
          f"{int(x.n):>6}{x.gross:>+8.2f}{x.exp:>+8.2f}{x.excess:>+8.2f}{x.p:>8.4f}"
          f"{x.exp_ex_2020_2022:>+9.2f}")
