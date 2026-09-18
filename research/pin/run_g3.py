"""G3 -- the second and last declared variation: B and S weighted by VOLUME, not bar count.

The failure in G1 and G2 is structural, not a tuning problem: mu is 1.5-3.4% of eps, so the
informed arrival is a rounding error against the uninformed one and the posterior cannot leave the
prior. There is exactly one construction that could change that without new data, and it follows
from the model itself: EKOP count TRADES and assume trade size is irrelevant (their footnote 7),
but an informed trader with private information trades SIZE. If informed flow is a small share of
the count and a large share of the VOLUME, then a volume-weighted B and S raises mu/eps.

B = (volume on up-minutes) / (mean volume per minute), S likewise -- rescaled so the counts stay on
a Poisson-like footing rather than becoming raw contract totals.

If this fails too, the verdict is Phase 0 and no feature work can address it.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import s5data as S, s5walk as W
import pin_core as P

R = "results/pin/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240)
TF = 10
D = P.load(TF)
b1 = D["base"]
c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
v = b1["volume"].to_numpy().astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
vbar = np.nanmean(v[on1])
up_v = np.where(c > o, v, 0.0) / vbar
dn_v = np.where(c < o, v, 0.0) / vbar
print(f"  mean volume per in-window minute {vbar:,.0f} contracts; B and S are volume / that.")

f = pd.DataFrame({"b": np.where(on1, up_v, 0), "s": np.where(on1, dn_v, 0), "d": day1,
                  "c": c, "o": o}, index=b1.index)
fo = f[on1]
agg = fo.groupby("d").agg(B=("b", "sum"), S=("s", "sum"), first=("o", "first"), last=("c", "last"))
agg["ret"] = (agg["last"] / agg["first"] - 1.0) * 100.0
agg = agg.sort_index()
F = agg.reset_index().rename(columns={"d": "day"})

print("\n" + "=" * 116)
print("G3.1  DOES VOLUME WEIGHTING RAISE THE INFORMED-TO-UNINFORMED RATIO?")
print("=" * 116)
rows = []
for k in (0.75, 1.0, 1.5):
    ps = []
    for i in range(len(F)):
        lo = max(0, i - 120)
        w = F.iloc[lo:i]
        if len(w) < 30:
            continue
        r = w.ret.to_numpy(); sd = r.std(ddof=1)
        if not np.isfinite(sd) or sd <= 0:
            continue
        ev = np.abs(r - r.mean()) > k * sd
        good = ev & (r > 0); bad = ev & (r < 0)
        if ev.sum() < 6 or good.sum() < 2 or bad.sum() < 2 or (~ev).sum() < 10:
            continue
        a = ev.mean(); d = bad.sum() / ev.sum()
        Bv, Sv = w.B.to_numpy(), w.S.to_numpy()
        eb, es = Bv[~ev].mean(), Sv[~ev].mean()
        mu = 0.5 * ((Bv[good | ~ev].mean() - eb) / max(1 - d, 1e-6)
                    + (Sv[bad | ~ev].mean() - es) / max(d, 1e-6))
        if not np.isfinite(mu) or mu <= 0 or eb <= 0 or es <= 0:
            continue
        ps.append(dict(a=a, d=d, eb=eb, es=es, mu=mu, pin=a * mu / (a * mu + eb + es)))
    if ps:
        rows.append(dict(k=k, fitted=len(ps), alpha=np.mean([p["a"] for p in ps]),
                         eps_b=np.mean([p["eb"] for p in ps]), eps_s=np.mean([p["es"] for p in ps]),
                         mu=np.mean([p["mu"] for p in ps]), PIN=np.mean([p["pin"] for p in ps]),
                         mu_over_eps=np.mean([p["mu"] / (p["eb"] + p["es"]) for p in ps])))
Z = pd.DataFrame(rows)
Z.to_csv(R + "g3_volume_params.csv", index=False)
print(Z.round(4).to_string(index=False))
print("\n  For comparison, the count-based constructions:")
print("    session, counts   mu/eps 0.0148   PIN 0.0043")
print("    30-min buckets    mu/eps 0.0339   PIN 0.0088")

print("\n" + "=" * 116)
print("G3.2  THE POSTERIOR IT PRODUCES")
print("=" * 116)
params = {}
for i in range(len(F)):
    p = P.fit_causal(F, i, window=120, k=1.0)
    params[int(F.day.iloc[i])] = p
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
print(f"  P(good): median {np.nanmedian(pg):.4f}  p99 {np.nanpercentile(pg,99):.4f}  "
      f"max {np.nanmax(pg):.4f}")
print(f"  P(bad) : median {np.nanmedian(pb):.4f}  p99 {np.nanpercentile(pb,99):.4f}  "
      f"max {np.nanmax(pb):.4f}")
for th in (0.5, 0.7, 0.9):
    print(f"    bars with P(good) >= {th}: {int(np.nansum(pg >= th)):,}   "
          f"P(bad) >= {th}: {int(np.nansum(pb >= th)):,}")

print("\n" + "=" * 116)
print("G3.3  GATE 1")
print("=" * 116)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]],
        1: D["all_days"][D["all_days"] >= D["cut_day"]]}
GEOM = dict(stop=2.5, tgt=0.0, be=0.0, be_off=0.0, arm=1.0, tr=1.0)
rows = []
for th in (0.30, 0.50, 0.70, 0.85, 0.95):
    lg = np.nan_to_num(pg, nan=0.0) >= th
    sh = np.nan_to_num(pb, nan=0.0) >= th
    lg &= D["inw"] & ~D["last_win"]; sh &= D["inw"] & ~D["last_win"] & ~lg
    sig = lg | sh
    n = int(sig.sum())
    if n < 20:
        continue
    side = np.where(lg, 1, -1).astype(np.int64)
    z = lambda t: np.zeros(n, t)
    oi, ox, oR, op, ow = z(np.int64), z(np.int64), z(float), z(float), z(np.int64)
    oa, of, ob = z(float), z(float), z(np.int64)
    m = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, GEOM["stop"], GEOM["tgt"], GEOM["be"], GEOM["be_off"],
               GEOM["arm"], GEOM["tr"], oi, ox, oR, op, ow, oa, of, ob)
    t = pd.DataFrame(dict(sig=oi[:m], pts=op[:m]))
    t["blk"] = D["blk"][t.sig.to_numpy()]; t["day"] = D["day"][t.sig.to_numpy()]
    for b, bl in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 20:
            continue
        r = s.pts.to_numpy()
        shp, _ = S.day_sharpe(s.day.to_numpy(), r, DAYS[b])
        rows.append(dict(thresh=th, block=bl, n=len(s), per_yr=len(s) / (len(DAYS[b]) / 252),
                         pts=r.mean(), usd=r.mean() * P.PV,
                         PF=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), win=(r > 0).mean(),
                         sharpe=shp))
G = pd.DataFrame(rows)
G.to_csv(R + "g3_gate1.csv", index=False)
print(G.round(4).to_string(index=False) if len(G) else "  nothing reached 20 trades")
if len(G):
    res = G[G.block == "research"]
    print(f"\n  research blocks profitable: {int((res.pts>0).sum())} of {len(res)}; "
          f"best research PF {res.PF.max():.3f}")
print(f"\ntotal {time.time()-t0:.0f}s")
