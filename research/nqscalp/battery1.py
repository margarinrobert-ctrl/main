"""Research-block battery: baseline under every exit convention, the intrabar
artifact decomposition, exit-reason split, regime and side breakdown, parameter
sensitivity, cost sensitivity, and the correlation matrices.

RESEARCH BLOCK ONLY. Nothing here touches the holdout.
"""
import numpy as np, pandas as pd, sys, itertools, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, nqcontrol as NC, data as D

OUT = "/home/user/main/docs/nqscalp/"
df = D.load("NAS"); B = cache.build(df)
R, H = D.blocks(df)
rbars = np.flatnonzero(R)
CONV = [("intrabar", "favorable"), ("intrabar", "adverse"),
        ("barclose", "favorable"), ("barclose", "adverse")]


def book(tm, order, mask=R, flat_at=None, cost_mult=1.0, **kw):
    I, p = cache.indicators(df, B, **kw)
    (lo, sh), _ = nqs.conditions(df, I, p)
    lo = lo & mask; sh = sh & mask
    return nqs.simulate(df, I, p, lo, sh, order=order, trail_mode=tm,
                        flat_at=flat_at, cost_mult=cost_mult), I, p


def line(tag, tr, extra=""):
    s = nqs.stats(tr)
    if not s["n"]:
        print(f"  {tag:<38} no trades"); return s
    print(f"  {tag:<38} n={s['n']:>5} exp={s['exp_pts']:>+7.2f}pts "
          f"${s['exp_usd']:>+8.2f} wr={s['wr']:>6.1%} pf={s['pf']:>5.2f} "
          f"net=${s['net_usd']:>+10,.0f} mdd=${s['mdd_usd']:>8,.0f} "
          f"med={s['med_bars']:>3.0f}b {extra}")
    return s


print("=" * 118)
print("NQ SCALPING SYSTEM - RESEARCH BLOCK (2016-11-14 -> 2022-08-29, 1,785 sessions)")
print("  5 contracts, $2/point (MNQ), $1.24/contract/order, 1 tick slippage")
print("=" * 118)

print("\n1. THE HEADLINE DEPENDS ENTIRELY ON WHAT YOU ASSUME HAPPENS INSIDE A 15m BAR")
print("-" * 118)
res = {}
for tm, order in CONV:
    tr, I, p = book(tm, order)
    res[(tm, order)] = tr
    line(f"trail {tm}/{order}", tr, str(tr.reason.value_counts().to_dict()))
for order in ("favorable", "adverse"):
    tr, _, _ = book("intrabar", order, use_trail=False)
    res[("notrail", order)] = tr
    line(f"NO TRAIL  {order}", tr, str(tr.reason.value_counts().to_dict()))

print("\n2. MATCHED CONTROL - random entries, same sides, same minute-of-day, SAME EXITS")
print("-" * 118)
ctrl = {}
for tm, order in CONV:
    I, p = cache.indicators(df, B)
    ctrl[(tm, order)] = NC.score(df, I, p, res[(tm, order)], n_draws=300, mask=R,
                                 order=order, trail_mode=tm, label=f"trail {tm}/{order}")

print("\n3. WHERE THE MONEY COMES FROM - P&L split by exit reason and by hold length")
print("-" * 118)
for tm, order in CONV:
    tr = res[(tm, order)]
    print(f"  {tm}/{order}:")
    for rsn, g in tr.groupby("reason"):
        print(f"      {rsn:<8} n={len(g):>5} ({len(g)/len(tr):>5.1%})  "
              f"exp={g.net_pts.mean():>+7.2f}  total=${g.net_usd.sum():>+10,.0f}")
    same = tr[tr.bars_held == 0]
    print(f"      exits on the FILL BAR ITSELF: {len(same)} ({len(same)/len(tr):.1%}), "
          f"${same.net_usd.sum():+,.0f} of ${tr.net_usd.sum():+,.0f}")

print("\n4. THE ARTIFACT, ISOLATED")
print("-" * 118)
a = nqs.stats(res[("intrabar", "adverse")])["net_usd"]
b = nqs.stats(res[("barclose", "adverse")])["net_usd"]
c_ = nqs.stats(res[("notrail", "adverse")])["net_usd"]
print(f"  intrabar trail (assumes a path inside the bar)      ${a:>+12,.0f}")
print(f"  barclose trail (no intrabar claim at all)           ${b:>+12,.0f}")
print(f"  no trail at all                                     ${c_:>+12,.0f}")
print(f"  --> attributable to the intrabar path assumption    ${a-b:>+12,.0f}  ({(a-b)/max(abs(a),1):.0%} of the headline)")
print(f"  --> attributable to the trail as a real mechanic    ${b-c_:>+12,.0f}")

print("\n5. BY YEAR (primary model: barclose/adverse; intrabar/adverse for contrast)")
print("-" * 118)
print(f"  {'year':<6}{'n':>6}{'barclose exp':>14}{'barclose $':>13}{'intrabar exp':>14}{'intrabar $':>13}")
for y in sorted(pd.DatetimeIndex(res[("barclose", "adverse")].ts).year.unique()):
    g1 = res[("barclose", "adverse")]; g1 = g1[pd.DatetimeIndex(g1.ts).year == y]
    g2 = res[("intrabar", "adverse")]; g2 = g2[pd.DatetimeIndex(g2.ts).year == y]
    print(f"  {y:<6}{len(g1):>6}{g1.net_pts.mean():>+14.2f}{g1.net_usd.sum():>+13,.0f}"
          f"{g2.net_pts.mean():>+14.2f}{g2.net_usd.sum():>+13,.0f}")

print("\n6. LONG vs SHORT")
print("-" * 118)
for tm, order in CONV:
    tr = res[(tm, order)]
    L, S = tr[tr.side > 0], tr[tr.side < 0]
    print(f"  {tm}/{order:<10} long n={len(L):>4} exp={L.net_pts.mean():>+7.2f}  "
          f"short n={len(S):>4} exp={S.net_pts.mean():>+7.2f}")

print("\n7. NO SESSION FLATTEN vs FLATTEN AT 11:30 CHICAGO (the Pine has no exit rule)")
print("-" * 118)
for tm, order in CONV:
    tr, _, _ = book(tm, order, flat_at=690)
    line(f"{tm}/{order} + flatten", tr)
tr_nf = res[("barclose", "adverse")]
print(f"  longest hold without a flatten: {tr_nf.bars_held.max():,} bars "
      f"({tr_nf.bars_held.max()*15/60/24:.1f} days); "
      f"{(tr_nf.bars_held > 26).mean():.1%} of trades run past their own session")

print("\n8. COST SENSITIVITY AND BREAKEVEN")
print("-" * 118)
print(f"  {'cost x':>8}" + "".join(f"{tm[:4]+'/'+o[:3]:>16}" for tm, o in CONV))
print(f"  (round turn at 1.0x = 2 x 1 tick slippage + 2 x $1.24/contract = 1.74 points)")
cost_rows = []
for cm in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0):
    row = [book(tm, order, cost_mult=cm)[0].net_pts.mean() for tm, order in CONV]
    cost_rows.append([cm] + row)
    print(f"  {cm:>8.2f}" + "".join(f"{x:>+16.2f}" for x in row))
pd.DataFrame(cost_rows, columns=["cost_mult"] + [f"{tm}_{o}" for tm, o in CONV]).to_csv(OUT + "cost_sensitivity.csv", index=False)
print("  breakeven cost multiple (linear interpolation from the rows above):")
for i, (tm, o) in enumerate(CONV):
    xs = [r[0] for r in cost_rows]; ys = [r[i + 1] for r in cost_rows]
    be = np.nan
    for a in range(len(xs) - 1):
        if ys[a] > 0 >= ys[a + 1]:
            be = xs[a] + (xs[a + 1] - xs[a]) * ys[a] / (ys[a] - ys[a + 1]); break
    gross = ys[0]
    print(f"    {tm}/{o:<10} gross edge {gross:+.2f} pts/trade, breaks even at "
          + (f"{be:.2f}x the real cost ({be*1.74:.2f} pts round turn)" if np.isfinite(be)
             else ("still positive at 3x the real cost" if ys[-1] > 0 else "negative even at zero cost")))

print("\n9. PARAMETER SENSITIVITY - a real edge decays smoothly, noise spikes")
print("-" * 118)
sweeps = dict(trend_ema=[34, 50, 89, 144, 200], min_pullback=[5, 10, 15, 20, 30],
              atr_stop=[1.0, 1.25, 1.5, 2.0, 2.5], atr_target=[1.5, 2.0, 2.5, 3.5, 5.0],
              trail_arm=[8, 12, 15, 20, 30], trail_offset=[4, 6, 8, 12, 16],
              reset_lookback=[4, 6, 8, 12, 16], pullback_lookback=[5, 8, 10, 15, 20])
sens = []
for k, vals in sweeps.items():
    cells = []
    for v in vals:
        tr, _, _ = book("barclose", "adverse", **{k: v})
        tri, _, _ = book("intrabar", "adverse", **{k: v})
        cells.append((v, len(tr), tr.net_pts.mean(), tri.net_pts.mean()))
        sens.append(dict(param=k, value=v, n=len(tr), exp_barclose=tr.net_pts.mean(),
                         exp_intrabar=tri.net_pts.mean()))
    s = "  ".join(f"{v}:{e:+.2f}" for v, n, e, ei in cells)
    print(f"  {k:<18} barclose/adverse   {s}")
    s2 = "  ".join(f"{v}:{ei:+.2f}" for v, n, e, ei in cells)
    print(f"  {'':<18} intrabar/adverse   {s2}")
pd.DataFrame(sens).to_csv(OUT + "sensitivity.csv", index=False)

print("\n10. CORRELATION MATRIX across parameter variants (session P&L, barclose/adverse)")
print("-" * 118)
variants = {"as-written": {}, "EMA50": dict(trend_ema=50), "EMA144": dict(trend_ema=144),
            "pull10": dict(min_pullback=10), "pull25": dict(min_pullback=25),
            "stop1.0": dict(atr_stop=1.0), "stop2.5": dict(atr_stop=2.5),
            "targ1.5": dict(atr_target=1.5), "targ5.0": dict(atr_target=5.0),
            "arm10": dict(trail_arm=10), "arm25": dict(trail_arm=25),
            "off4": dict(trail_offset=4), "off14": dict(trail_offset=14),
            "reset4": dict(reset_lookback=4), "reset16": dict(reset_lookback=16),
            "notrail": dict(use_trail=False)}
series = {}
for nm, kw in variants.items():
    tr, _, _ = book("barclose", "adverse", **kw)
    series[nm] = tr.groupby("sess").net_usd.sum()
M = pd.DataFrame(series).reindex(sorted(set().union(*[s.index for s in series.values()]))).fillna(0.0)
C = M.corr()
C.to_csv(OUT + "corr_variants.csv")
print("  " + "".join(f"{n[:9]:>10}" for n in C.columns))
for i, n in enumerate(C.index):
    print(f"  {n[:16]:<16}" + "".join(f"{C.iloc[i,j]:>10.2f}" for j in range(len(C.columns))))
off = C.values[np.triu_indices_from(C.values, 1)]
print(f"\n  mean off-diagonal correlation {off.mean():.3f}   median {np.median(off):.3f}")
ev = np.linalg.eigvalsh(C.values)[::-1]; ev = ev[ev > 0]
meff = 1 + (len(C) - 1) * (1 - np.var(ev, ddof=1) / len(C))
print(f"  Li & Ji effective number of independent tests among {len(C)} variants: M_eff = {meff:.1f}")
print(f"  first eigenvalue explains {ev[0]/ev.sum():.1%} of the variance")

print("\n11. CONVENTION CORRELATION - the same signals, different bar assumptions")
print("-" * 118)
cs = {f"{tm[:4]}/{o[:3]}": res[(tm, o)].groupby("sess").net_usd.sum() for tm, o in CONV}
cs["notrail/adv"] = res[("notrail", "adverse")].groupby("sess").net_usd.sum()
CM = pd.DataFrame(cs).fillna(0.0).corr()
CM.to_csv(OUT + "corr_conventions.csv")
print("  " + "".join(f"{n:>14}" for n in CM.columns))
for i, n in enumerate(CM.index):
    print(f"  {n:<14}" + "".join(f"{CM.iloc[i,j]:>14.2f}" for j in range(len(CM.columns))))

json.dump({f"{tm}_{o}": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                          for k, v in nqs.stats(res[(tm, o)]).items()}
           for tm, o in list(res.keys())},
          open(OUT + "research_baseline.json", "w"), indent=2, default=str)
json.dump({f"{tm}_{o}": ctrl[(tm, o)] for tm, o in CONV},
          open(OUT + "research_control.json", "w"), indent=2, default=str)
for (tm, o), tr in res.items():
    tr.to_parquet(f"/home/user/main/data/donchian/nqs_research_{tm}_{o}.parquet")
print("\n  written: research_baseline.json, research_control.json, sensitivity.csv, corr_*.csv")
