"""G4 -- the matched control on the volume-weighted PIN posterior, and the PF-2 arithmetic.

G3 got the posterior working: volume-weighted B and S raise mu/eps from 0.015 to 0.052 and the
posterior now spans [0,1]. Research is weakly positive at 3 of 5 thresholds, best PF 1.116. This
asks the only question that matters next: is that better than entering at random in the same
window with the same geometry and the same rate?
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import s5data as S, s5walk as W
import pin_core as P

R = "results/pin/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240)
rng = np.random.default_rng(19)
TF = 10
D = P.load(TF)
b1 = D["base"]
c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
v = b1["volume"].to_numpy().astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
vbar = np.nanmean(v[on1])
f = pd.DataFrame({"b": np.where(on1 & (c > o), v / vbar, 0.0),
                  "s": np.where(on1 & (c < o), v / vbar, 0.0), "d": day1, "c": c, "o": o},
                 index=b1.index)
agg = f[on1].groupby("d").agg(B=("b", "sum"), S=("s", "sum"), first=("o", "first"),
                              last=("c", "last")).sort_index()
agg["ret"] = (agg["last"] / agg["first"] - 1.0) * 100.0
F = agg.reset_index().rename(columns={"d": "day"})
params = {int(F.day.iloc[i]): P.fit_causal(F, i, window=120, k=1.0) for i in range(len(F))}
cb = f.groupby("d").b.cumsum().to_numpy(); cs = f.groupby("d").s.cumsum().to_numpy()
cb[~on1] = np.nan; cs[~on1] = np.nan
Bt = pd.Series(cb, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
St = pd.Series(cs, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
wl = D["win_close"] - D["win_open"]
pg = np.full(D["n"], np.nan); pb = np.full(D["n"], np.nan)
for i in np.flatnonzero(D["inw"]):
    p = params.get(int(D["day"][i]))
    if p is None or not np.isfinite(Bt[i]):
        continue
    fr = min(max((D["mod"][i] + TF - D["win_open"]) / wl, 1e-3), 1.0)
    g, b, _ = P.posterior(Bt[i], St[i], p, fr)
    pg[i] = g; pb[i] = b

DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]],
        1: D["all_days"][D["all_days"] >= D["cut_day"]]}
GEOM = dict(stop=2.5, tgt=0.0, be=0.0, be_off=0.0, arm=1.0, tr=1.0)
def walk(lg, sh):
    sig = lg | sh
    n = int(sig.sum())
    if n < 5:
        return pd.DataFrame(columns=["sig", "pts", "blk", "day"])
    side = np.where(lg, 1, -1).astype(np.int64)
    z = lambda t: np.zeros(n, t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, GEOM["stop"], GEOM["tgt"], GEOM["be"], GEOM["be_off"],
               GEOM["arm"], GEOM["tr"], oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], pts=op[:m]))
    t["blk"] = D["blk"][t.sig.to_numpy()]; t["day"] = D["day"][t.sig.to_numpy()]
    return t

print("=" * 116)
print("G4.1  THE MATCHED CONTROL -- random bars, same window, same rate, same side mix, same exits")
print("=" * 116)
rows = []
for th in (0.50, 0.70, 0.85, 0.95):
    lg = np.nan_to_num(pg, nan=0.0) >= th
    sh = np.nan_to_num(pb, nan=0.0) >= th
    lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
    t = walk(lg, sh)
    for blk, bl in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == blk]
        if len(s) < 20:
            continue
        real = s.pts.mean()
        elig = np.flatnonzero(D["inw"] & ~D["last_win"] & (D["blk"] == blk)
                              & np.isfinite(D["atr"]) & (D["atr"] > 0))
        p_long = float((lg[s.sig.to_numpy()]).mean())
        ctl = np.empty(300)
        for j in range(300):
            pick = np.sort(rng.choice(elig, min(len(s), len(elig)), replace=False))
            L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
            isl = rng.random(len(pick)) < p_long
            L[pick[isl]] = True; Sh[pick[~isl]] = True
            q = walk(L, Sh); q = q[q.blk == blk]
            ctl[j] = q.pts.mean() if len(q) else np.nan
        ctl = ctl[np.isfinite(ctl)]
        r = s.pts.to_numpy()
        rows.append(dict(thresh=th, block=bl, n=len(s), rule=real,
                         PF=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9),
                         ctl_med=np.median(ctl), excess=real - np.median(ctl),
                         p=float((ctl >= real).mean())))
        print(f"  ...{th} {bl} done {time.time()-t0:.0f}s")
C = pd.DataFrame(rows)
C.to_csv(R + "g4_control.csv", index=False)
print(C.round(4).to_string(index=False))
res = C[C.block == "research"]
print(f"\n  research cells clearing the control at p<=0.05: {int((res.p<=0.05).sum())} of {len(res)}")
print(f"  best research p anywhere: {res.p.min():.3f}   best research PF: {res.PF.max():.3f}")

print("\n" + "=" * 116)
print("G4.2  THE ASK -- what PF 2.0 requires at this geometry")
print("=" * 116)
th = 0.95
lg = np.nan_to_num(pg, nan=0.0) >= th; sh = np.nan_to_num(pb, nan=0.0) >= th
lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
t = walk(lg, sh)
r = t[t.blk == 0].pts.to_numpy()
gp, gl, w = r[r > 0].mean(), -r[r < 0].mean(), (r > 0).mean()
print(f"  best research cell (threshold {th}): n {len(r)}, mean win {gp:+.2f} pts, "
      f"mean loss {-gl:+.2f}, win rate {w:.3f}  ->  PF {w*gp/((1-w)*gl):.3f}")
print(f"  {'target PF':>10} {'win rate needed':>16} {'lift required':>14}")
for target in (1.5, 2.0, 3.0):
    need = target * gl / (target * gl + gp)
    print(f"  {target:>10.1f} {need:>16.3f} {need-w:>+14.3f}")
print(f"\n  The best honest win-rate lift measured anywhere on this branch is +1 to +5 points.")
print(f"  PF 2.0 here needs {2*gl/(2*gl+gp)-w:+.3f} -- {(2*gl/(2*gl+gp)-w)*100:.0f} points.")
print(f"\ntotal {time.time()-t0:.0f}s")
