"""Run the supplied specification on US100 M15 and report it honestly."""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/us100dc")
import numpy as np, pandas as pd
import dc_run as DC

R = "results/us100dc/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(3)
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)

f = DC.load_us100()
print(f"US100_LONG_15m: {len(f):,} bars  {f.index.min()} .. {f.index.max()}")
mod = (f.index.hour * 60 + f.index.minute).to_numpy()
g = pd.DataFrame({"m": mod, "r": (f.high - f.low).to_numpy()}).groupby("m").r.mean()
pk = int(g.idxmax())
print(f"  clock check: mean bar range peaks at {pk//60:02d}:{pk%60:02d} New York "
      f"(positive control: 09:30)")
D = DC.build(f)
print(f"  ATR(80) median {np.nanmedian(D['atr']):.2f} pts | research to {D['cut_date']}\n")

# ============================================================ 1  the spec as given
print("=" * 104)
print("1  THE SPECIFICATION AS SUPPLIED")
print("=" * 104)
rows = []
for sp in (0.5, 1.0, 2.0, 3.0):
    t, floor, keep = DC.run(D, assumed_spread=sp)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        dd = D["days"][(D["days"] >= D["cut_day"]) if b else (D["days"] < D["cut_day"])]
        if len(s) < 20:
            continue
        rows.append(dict(assumed_spread=sp, atr_floor=floor, bars_kept=keep,
                         block=lab, **DC.stats(s, dd)))
S = pd.DataFrame(rows)
S.to_csv(R + "spec.csv", index=False)
print("  `spread/ATR <= 0.20` with a FIXED spread IS an ATR floor of spread/0.20. The assumed")
print("  spread is swept because no feed here carries bid/ask, so the filter's strength is an")
print("  assumption rather than a measurement.\n")
print(S.round(4).to_string(index=False))

# ============================================================ 2  does the gate matter
print("\n" + "=" * 104)
print("2  WHAT THE SPREAD-TO-ATR FILTER ACTUALLY DOES")
print("=" * 104)
rows = []
t_off, _, _ = DC.run(D, gate_on=False)
for b, lab in ((0, "research"), (1, "LOCKED")):
    dd = D["days"][(D["days"] >= D["cut_day"]) if b else (D["days"] < D["cut_day"])]
    rows.append(dict(setting="filter OFF", block=lab, **DC.stats(t_off[t_off.blk == b], dd)))
for sp in (1.0, 2.0):
    t, floor, keep = DC.run(D, assumed_spread=sp)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        dd = D["days"][(D["days"] >= D["cut_day"]) if b else (D["days"] < D["cut_day"])]
        rows.append(dict(setting=f"ATR >= {floor:.1f} ({keep:.0%} of bars)", block=lab,
                         **DC.stats(t[t.blk == b], dd)))
G = pd.DataFrame(rows)
G.to_csv(R + "gate.csv", index=False)
print(G.round(4).to_string(index=False))

# ============================================================ 3  the components
print("\n" + "=" * 104)
print("3  DROP-ONE -- which part of the exit is doing the work (research block)")
print("=" * 104)
rows = []
dd0 = D["days"][D["days"] < D["cut_day"]]
for lab, kw in (("as specified", dict()),
                ("no trail (stop 1.5N only)", dict(trail_n=99.0)),
                ("no fixed stop (trail 2.0N only)", dict(stop_n=99.0)),
                ("wider stop 2.5N", dict(stop_n=2.5)),
                ("wider trail 3.0N", dict(trail_n=3.0)),
                ("tighter trail 1.5N", dict(trail_n=1.5))):
    t, _, _ = DC.run(D, assumed_spread=1.0, **kw)
    rows.append(dict(variant=lab, **DC.stats(t[t.blk == 0], dd0)))
A = pd.DataFrame(rows)
A.to_csv(R + "ablation.csv", index=False)
print(A.round(4).to_string(index=False))

# ============================================================ 4  the control
print("\n" + "=" * 104)
print("4  AGAINST A MATCHED RANDOM ENTRY -- same geometry, same rate, same exits")
print("=" * 104)


def control(D, n_target, stop_n, trail_n, blk, draws=300):
    elig = np.flatnonzero(np.isfinite(D["up"]) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    rate = min(1.0, n_target / max(len(elig), 1))
    out = np.empty(draws)
    # a finite sentinel, NOT -inf: the walker requires isfinite(up[i]), so -inf silently
    # produces zero trades and the control comes back all-NaN (it did on the first run).
    up_hi = np.full(D["n"], -1e12)
    for i in range(draws):
        m = np.zeros(D["n"], np.bool_)
        m[elig[RNG.random(len(elig)) < rate]] = True
        cap = int(m.sum()) + 8
        oi = np.zeros(cap, np.int64); ox = np.zeros(cap, np.int64)
        op = np.full(cap, np.nan); oR = np.full(cap, np.nan)
        ow = np.zeros(cap, np.int64); om = np.full(cap, np.nan)
        k = DC.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], up_hi, D["dn"], m,
                    stop_n, trail_n, DC.RT_POINTS, DC.SLIP, oi, ox, op, oR, ow, om)
        tt = pd.DataFrame(dict(sig=oi[:k], pts=op[:k]))
        tt["blk"] = D["blk"][tt.sig.to_numpy()]
        s = tt[tt.blk == blk]
        out[i] = s.pts.mean() if len(s) else np.nan
    return out


rows = []
for lab_v, kw in (("as specified", dict(trail_n=2.0)), ("no trail", dict(trail_n=99.0))):
    t, _, _ = DC.run(D, assumed_spread=1.0, **kw)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 20:
            continue
        ctl = control(D, len(s), 1.5, kw["trail_n"], b)
        rows.append(dict(variant=lab_v, block=lab, n=len(s), rule_pts=s.pts.mean(),
                         control_pts=float(np.nanmedian(ctl)),
                         p=float(np.nanmean(ctl >= s.pts.mean()))))
        print(f"  {lab_v:14s} {lab:9s} n {len(s):4d}   rule {s.pts.mean():+8.3f} pts   "
              f"random entry {np.nanmedian(ctl):+8.3f}   p "
              f"{float(np.nanmean(ctl >= s.pts.mean())):.3f}")
pd.DataFrame(rows).to_csv(R + "control.csv", index=False)

print("\n" + "=" * 104)
print("4b  THE DROP-ONE READ ON THE LOCKED BLOCK -- the trail is the whole result, so read it once")
print("=" * 104)
rows = []
for lab_v, kw in (("as specified", dict()), ("no trail (stop 1.5N only)", dict(trail_n=99.0)),
                  ("wider trail 3.0N", dict(trail_n=3.0))):
    t, _, _ = DC.run(D, assumed_spread=1.0, **kw)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        dd = D["days"][(D["days"] >= D["cut_day"]) if b else (D["days"] < D["cut_day"])]
        st = DC.stats(t[t.blk == b], dd)
        if st:
            rows.append(dict(variant=lab_v, block=lab, **st))
L = pd.DataFrame(rows)
L.to_csv(R + "locked.csv", index=False)
print(L.round(4).to_string(index=False))

# ============================================================ 5  the account
print("\n" + "=" * 104)
print("5  THE $1,000 ACCOUNT AT 1:100 -- the part the per-trade numbers do not answer")
print("=" * 104)
t, _, _ = DC.run(D, assumed_spread=1.0)
for b, lab in ((0, "research"), (1, "LOCKED")):
    s = t[t.blk == b]
    if len(s) < 20:
        continue
    px = D["c"][s.sig.to_numpy()]
    marg = px / 100.0                      # 1:100 on one unit of the index, $1 a point
    risk_pts = 1.5 * s.atr0.to_numpy()
    print(f"  {lab}: median index level {np.median(px):,.0f} -> margin for ONE unit "
          f"${np.median(marg):,.0f}, i.e. {1000/np.median(marg):.1f} units affordable on $1,000")
    print(f"     risk on one unit is {np.median(risk_pts):.1f} pts = "
          f"${np.median(risk_pts):,.0f} = {np.median(risk_pts)/1000*100:.1f}% of the deposit")
    print(f"     total on one unit {s.pts.sum():+,.0f} pts = ${s.pts.sum():+,.0f} on $1,000, "
          f"max drawdown ${DC.stats(s, D['days'])['dd']:,.0f}")
t.to_csv(R + "trades.csv", index=False)
print(f"\ntotal {time.time()-t0:.0f}s")
