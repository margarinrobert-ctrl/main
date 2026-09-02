"""Analyse the EMA-cross search, then walk-forward the survivors INSIDE research.

Walk-forward here re-selects the configuration on each training window from the
whole family and trades the next block with it. That charges for having to
choose, which a single research number hides. It is the OOS test for this round,
because the locked block has already been read twice.
"""
import numpy as np, pandas as pd, itertools
import lab
from emacross import prep, ema_gate, atr_gate, N_ENTRY, EMA_PAIRS, EMA_MODE, ATR_FILT, GEOM

R = pd.read_parquet("/home/user/main/data/donchian/emacross.parquet")
V = R.dropna(subset=["p"])
print("=" * 110)
print(f"EMA-CROSS x DONCHIAN x ATR SEARCH - {len(R):,} configs, {len(V):,} with >=60 trades")
print("  research block only, scored against the matched control")
print("=" * 110)
for sym, g in V.groupby("sym"):
    q = g.excess.quantile([.05, .5, .95])
    print(f"\n  {sym}: excess p5 {q.iloc[0]:+.2f}  median {q.iloc[1]:+.2f}  p95 {q.iloc[2]:+.2f}"
          f"   cells with excess>0 & p<0.05: {((g.excess>0)&(g.p<0.05)).sum()} / {len(g)}"
          f"  (chance ~{0.05*len(g):.0f})")
    print(f"       cells with exp>0 (positive after costs): {(g.exp>0).sum()} / {len(g)}"
          f" = {(g.exp>0).mean():.1%}")

print("\n" + "=" * 110)
print("MARGINALS - does each ingredient add anything, averaged over everything else?")
print("=" * 110)
base = V[V.sym == "NAS"]
for col in ("mode", "atr", "fast", "n_entry", "stop"):
    m = base.groupby(col).agg(excess=("excess","mean"), exp=("exp","mean"),
                              pos=("exp", lambda s: (s>0).mean()), n=("exp","size"))
    print(f"\n  by {col}:")
    for k_, r_ in m.iterrows():
        print(f"    {str(k_):<10} mean excess {r_.excess:>+6.2f}   mean exp {r_.exp:>+6.2f}"
              f"   frac exp>0 {r_.pos:>5.1%}   ({int(r_.n)} cells)")

# the EMA gate vs NO gate: does it beat the ungated breakout at the same geometry?
print("\n" + "=" * 110)
print("THE KEY COMPARISON - EMA-gated vs ungated Donchian at identical geometry (NAS)")
print("=" * 110)
df, w, r = lab.research("NAS")
for ne, (sm,tm) in itertools.product(N_ENTRY, GEOM):
    idx, side, _ = lab.signals(df, ne); ok = df.tod.values[idx] > 420
    g0, _ = lab.sig_gate("NAS", idx[ok], side[ok], stop_mult=sm, targ_mult=tm, n_draws=200, quiet=True)
    sub = base[(base.n_entry==ne)&(base.stop==sm)&(base.targ==tm)&(base.atr=="none")]
    print(f"  n={ne:<3} {sm}/{tm}:  UNGATED exp {g0['exp']:>+6.2f} excess {g0['excess']:>+6.2f}"
          f"   |  EMA-gated (30 variants) mean exp {sub.exp.mean():>+6.2f}"
          f"  best exp {sub.exp.max():>+6.2f}  mean excess {sub.excess.mean():>+6.2f}")

print("\n" + "=" * 110)
print("TOP 12 BY EXCESS (NAS) - to be walk-forwarded, not believed")
print("=" * 110)
top = base.sort_values("excess", ascending=False).head(12)
print(f"  {'n':>3} {'ema':>7} {'mode':<8} {'atr':<10} {'geom':>8} {'trades':>6} {'exp':>7} {'excess':>7} {'z':>6} {'p':>7} {'sel':>5}")
for _, x in top.iterrows():
    print(f"  {int(x.n_entry):>3} {int(x.fast):>3}/{int(x.slow):<3} {x['mode']:<8} {x.atr:<10} "
          f"{x.stop}/{x.targ:<4} {int(x.n):>6} {x.exp:>+7.2f} {x.excess:>+7.2f} {x.z:>+6.2f} {x.p:>7.4f} {x.sel:>5.2f}")

# ------------------------------------------------------------- walk-forward
print("\n" + "=" * 110)
print("WALK-FORWARD inside research - re-select the best config on each training window")
print("=" * 110)
P = prep("NAS")
sess = df.sess.values
res_sess = np.unique(sess[r])
# pre-build every config's book once
books = {}
for ne in N_ENTRY:
    idx, side, _ = lab.signals(df, ne); ok = P["tod"][idx] > 420
    idx, side = idx[ok], side[ok]
    for (fast,slow), mode, af, (sm,tm) in itertools.product(EMA_PAIRS, EMA_MODE, ATR_FILT, GEOM):
        gl = ema_gate(P, fast, slow, mode, +1)[idx]; gs = ema_gate(P, fast, slow, mode, -1)[idx]
        keep = ((side>0)&gl | (side<0)&gs) & atr_gate(P, af)[idx] & ~np.isnan(P["pct"][idx])
        if keep.sum() < 60: continue
        bk = lab.book("NAS", idx[keep], side[keep], stop_mult=sm, targ_mult=tm)
        bk = bk[np.isin(bk.sig_bar, np.where(r)[0])]
        if len(bk) < 60: continue
        books[(ne,fast,slow,mode,af,sm,tm)] = (sess[bk.sig_bar.values], bk.net.values)
print(f"  {len(books):,} candidate books")
WF = {}
import json
base.sort_values("excess", ascending=False).head(12).to_csv("/home/user/main/docs/donchian/emacross_top12.csv", index=False)
for tr_s, te_s in ((300, 100), (500, 150)):
    lo, hi = res_sess.min(), res_sess.max()
    folds, oos_all = [], []
    s0 = lo
    while s0 + tr_s + te_s <= hi:
        best, bv = None, -np.inf
        for key, (bs, net) in books.items():
            m = (bs >= s0) & (bs < s0+tr_s)
            if m.sum() < 30: continue
            v = net[m].mean()
            if v > bv: bv, best = v, key
        if best is None: s0 += te_s; continue
        bs, net = books[best]
        m = (bs >= s0+tr_s) & (bs < s0+tr_s+te_s)
        oos = net[m]
        folds.append(dict(is_exp=bv, oos_exp=oos.mean() if len(oos) else np.nan, n=len(oos), cfg=best))
        if len(oos): oos_all.append(oos)
        s0 += te_s
    F = pd.DataFrame(folds); allo = np.concatenate(oos_all) if oos_all else np.array([])
    print(f"\n  train {tr_s} / test {te_s} sessions: {len(F)} folds")
    print(f"    profitable folds : {(F.oos_exp>0).mean():.1%}")
    print(f"    median IS exp    : {F.is_exp.median():+.2f}    median OOS exp: {F.oos_exp.median():+.2f}")
    print(f"    stitched OOS     : n={len(allo):,}  exp={allo.mean():+.2f}  "
          f"boot 95% CI [{np.percentile([np.random.default_rng(i).choice(allo,len(allo)).mean() for i in range(2000)],2.5):+.2f},"
          f"{np.percentile([np.random.default_rng(i).choice(allo,len(allo)).mean() for i in range(2000)],97.5):+.2f}]")
    print(f"    worst fold       : {F.oos_exp.min():+.2f}")
    cfgs = F.cfg.astype(str).value_counts()
    print(f"    config stability : modal choice kept in {cfgs.iloc[0]/len(F):.0%} of folds")
    ci = [np.percentile([np.random.default_rng(i).choice(allo,len(allo)).mean() for i in range(2000)], q) for q in (2.5, 97.5)]
    WF[f"{tr_s}/{te_s}"] = dict(folds=int(len(F)), frac_profitable=float((F.oos_exp>0).mean()),
        median_is=float(F.is_exp.median()), median_oos=float(F.oos_exp.median()),
        oos_n=int(len(allo)), oos_exp=float(allo.mean()), ci_lo=float(ci[0]), ci_hi=float(ci[1]),
        worst=float(F.oos_exp.min()), modal_frac=float(cfgs.iloc[0]/len(F)),
        pass_a=bool(allo.mean()>0 and ci[0]>0), pass_b=bool((F.oos_exp>0).mean()>=0.60), pass_c=bool(F.oos_exp.median()>0))
    WF[f"{tr_s}/{te_s}"]["PASS"] = all(WF[f"{tr_s}/{te_s}"][k] for k in ("pass_a","pass_b","pass_c"))
WF["VERDICT"] = "PASS" if all(v["PASS"] for k,v in WF.items() if k!="VERDICT") else "FAIL"
json.dump(WF, open("/home/user/main/docs/donchian/emacross_walkforward.json","w"), indent=2)
print(f"\n  WALK-FORWARD VERDICT against the pre-registered criterion: {WF['VERDICT']}")
