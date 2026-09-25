"""MA TYPE x MA LENGTH on the traded 30-second rule (na_live.TV35), one declared grid.

5 types (EMA, SMA, WMA, Hull, linear-regression endpoint) x 3 fast/slow pairs (9/21, 13/48, 21/55)
= 15 cells, everything else frozen at TV35. Each cell: all / research / holdout, the MDE, and a
matched random entry (same session, side mix, geometry; sorted draws). The noise floor for 15 looks
is printed BEFORE the table. STUDY_MA_LAG's prior: type is not a degree of freedom, LAG is -- so
the lag of each average is printed beside it.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); NA = os.path.dirname(HERE)
sys.path[:0] = [NA, os.path.dirname(NA)]
import na_30s as T, na_s30 as S, na_live as L, na_core as N

P = dict(L.TV35)
f = T.frame(tf=0.5, atr_n=14)
TYPES = ["ema", "sma", "wma", "hull", "linreg"]
PAIRS = [(9, 21), (13, 48), (21, 55)]
cells = len(TYPES) * len(PAIRS)
print(f"{cells} declared cells. E[max t | pure noise] = {N.e_max_normal(cells):.3f} against 2.802 to detect.\n")

def ramp_lag(kind, n):
    x = np.arange(600, dtype=float); y = N.ma(x, n, kind)
    return float(x[-1] - y[-1])

base = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL")
is_d, oos_d = S.split_days(base, P, 0.5)
rhi, rlo, _ = base.ranges(P["range_end"])
ok = (base.mod >= P["open_m"]) & (base.mod < P["end_m"]) & np.isfinite(rhi) & np.isfinite(rlo)
elig = np.flatnonzero(ok); eday = base.day[elig]

def control(c, sig, sd, n_draw=400, seed=11):
    g = np.random.default_rng(seed); atrf = c.atr_frame(P["atr_n"])
    pool = {d: elig[eday == d] for d in np.unique(c.day[sig])}
    out = []
    for _ in range(n_draw):
        bb, ss = [], []
        for b, s in zip(sig, sd):
            cand = pool.get(c.day[b])
            if cand is not None and len(cand): bb.append(g.choice(cand)); ss.append(s)
        o = np.argsort(bb, kind="stable")
        t = c._walk_sig(P, atrf, np.asarray(bb)[o], np.asarray(ss)[o])
        out.append(np.nan if t is None else t.pct.mean())
    return np.asarray(out)

def pf(r):
    w = r > 0
    return r[w].sum() / -r[~w].sum() if (~w).any() and r[~w].sum() < 0 else np.nan

rows = []
for kind in TYPES:
    for fa, sl in PAIRS:
        c = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL", fast=fa, slow=sl, kind=kind)
        tr = c.trades(P)
        if tr is None or len(tr) < 5:
            rows.append(dict(type=kind, pair=f"{fa}/{sl}", n=0)); continue
        r = tr.pct.to_numpy(); sd = r.std(ddof=1); mde = N.mde(sd, len(r))
        ri = S.sub(tr, is_d).pct.to_numpy(); ro = S.sub(tr, oos_d).pct.to_numpy()
        sig, sde = c.sigs(P); nul = control(c, sig, sde)
        bo = np.asarray(N.boot_edge(tr, n=3000, seed=3, col="pct"))
        rows.append(dict(type=kind, pair=f"{fa}/{sl}", lag=f"{ramp_lag(kind,fa):.1f}/{ramp_lag(kind,sl):.1f}",
                         n=len(r), pct=r.mean(), pf=pf(r), win=(r > 0).mean(),
                         pf_res=pf(ri), pf_hold=pf(ro), n_res=len(ri), n_hold=len(ro),
                         ratio=r.mean() / mde, p_entry=float(np.nanmean(nul >= r.mean())),
                         p_le0=float(np.mean(bo <= 0)), t=r.mean() / sd * np.sqrt(len(r))))
        print(f"  {kind:6s} {fa:2d}/{sl:2d}  n {len(r):3d}  PF {pf(r):5.2f}  res {pf(ri):5.2f} hold {pf(ro):5.2f}  "
              f"ratio {r.mean()/mde:4.2f}  p_entry {rows[-1]['p_entry']:.3f}", flush=True)
df = pd.DataFrame(rows); df.to_csv(os.path.join(HERE, "m1_grid.csv"), index=False)

print("\nMARGINAL AVERAGE BY TYPE (over the three pairs)  -- read this, not the top row")
print(df.groupby("type", sort=False)[["n", "pct", "pf", "pf_res", "pf_hold", "ratio"]].mean().to_string(float_format=lambda v: f"{v:.4f}"))
print("\nMARGINAL AVERAGE BY PAIR (over the five types)")
print(df.groupby("pair", sort=False)[["n", "pct", "pf", "pf_res", "pf_hold", "ratio"]].mean().to_string(float_format=lambda v: f"{v:.4f}"))
print(f"\nbest |t| in the grid {df.t.abs().max():.3f} vs noise floor {N.e_max_normal(cells):.3f}; "
      f"cells beating a random entry at p<=0.05: {int((df.p_entry<=0.05).sum())} of {cells} "
      f"({0.05*cells:.2f} expected by chance); cells with ratio >= 1: {int((df.ratio>=1).sum())}")
# how much do the TYPES actually differ on the same pair? signal-set overlap
print("\nSIGNAL OVERLAP with EMA at the same pair (Jaccard of taken entry bars):")
for fa, sl in PAIRS:
    ce = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL", fast=fa, slow=sl, kind="ema")
    se = set(ce.trades(P).sig)
    line = []
    for kind in TYPES[1:]:
        ck = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL", fast=fa, slow=sl, kind=kind)
        sk = set(ck.trades(P).sig); line.append(f"{kind} {len(se & sk)/len(se | sk):.2f}")
    print(f"  {fa}/{sl}: " + "   ".join(line))
