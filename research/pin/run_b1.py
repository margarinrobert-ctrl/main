"""B1 -- swap Yan's moment estimator for the Griffin-Oberoi-Oduro Gibbs sampler, change nothing else.

This is the controlled comparison the paper invites. Same bars, same volume-weighted B and S, same
rolling 120-session window, same posterior decision rule, same geometry, same costs. ONLY the way
(a, d, mu, lb, ls) is obtained differs. Anything that moves is the estimator.

The Bayesian version also DROPS A FREE PARAMETER: Yan needs event periods labelled before it can
estimate anything, and the causal replacement for his event study was a trailing-sd rule with a
threshold evK that had to be chosen. The Gibbs sampler infers D_t as a latent variable instead.
"""
import sys, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import pin_core as P
import pin_bayes as PB

TF = 10
t0 = time.time()
pd.set_option("display.width", 200)

D = P.load(tf=TF)
b1 = D["base"]
c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
v = b1["volume"].to_numpy().astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
vbar = np.nanmean(v[on1])
w = v / vbar

f = pd.DataFrame({"b": np.where(on1 & (c > o), w, 0.0),
                  "s": np.where(on1 & (c < o), w, 0.0), "d": day1, "c": c, "o": o}, index=b1.index)
agg = f[on1].groupby("d").agg(B=("b", "sum"), S=("s", "sum"),
                              first=("o", "first"), last=("c", "last")).sort_index()
agg["ret"] = (agg["last"] / agg["first"] - 1.0) * 100.0
F = agg.reset_index().rename(columns={"d": "day"})
print(f"sessions {len(F)}   mean B {F.B.mean():.1f}  mean S {F.S.mean():.1f}  "
      f"[{time.time()-t0:.0f}s]")

# ---------------------------------------------------------------- the two estimators, rolling
WIN = 120
yan, bay = {}, {}
Bv, Sv = F.B.to_numpy(), F.S.to_numpy()
for i in range(len(F)):
    day = int(F.day.iloc[i])
    yan[day] = P.fit_causal(F, i, window=WIN, k=1.0)
    lo = max(0, i - WIN)
    if i - lo >= 30:
        fit = PB.gibbs(np.rint(Bv[lo:i]), np.rint(Sv[lo:i]), sweeps=900, burn=300, seed=i)
        bay[day] = None if fit is None else dict(a=fit["a"], d=fit["d"], mu=fit["mu"],
                                                 lb=fit["lb"], ls=fit["ls"], pin=fit["pin"],
                                                 pin_sd=fit["pin_sd"], ratio=fit["ratio"])
    else:
        bay[day] = None
print(f"fits: Yan {sum(x is not None for x in yan.values())}  "
      f"Bayes {sum(x is not None for x in bay.values())}   [{time.time()-t0:.0f}s]")

both = [d for d in yan if yan[d] and bay.get(d)]
cmp = pd.DataFrame([dict(day=d, a_y=yan[d]["a"], a_b=bay[d]["a"], d_y=yan[d]["d"], d_b=bay[d]["d"],
                         mu_y=yan[d]["mu"], mu_b=bay[d]["mu"],
                         eb_y=yan[d]["eb"], eb_b=bay[d]["lb"],
                         es_y=yan[d]["es"], es_b=bay[d]["ls"],
                         pin_y=yan[d]["pin"], pin_b=bay[d]["pin"],
                         r_y=yan[d]["mu"] / (yan[d]["eb"] + yan[d]["es"]), r_b=bay[d]["ratio"])
                    for d in both])
print("\n" + "=" * 100)
print("B1.1  THE TWO ESTIMATORS ON THE SAME WINDOWS")
print("=" * 100)
print(f"  common sessions {len(cmp)}")
for lbl, a, b in (("alpha", "a_y", "a_b"), ("delta", "d_y", "d_b"), ("mu", "mu_y", "mu_b"),
                  ("lambda_b", "eb_y", "eb_b"), ("lambda_s", "es_y", "es_b"),
                  ("PIN", "pin_y", "pin_b"), ("mu/(lb+ls)", "r_y", "r_b")):
    print(f"  {lbl:>11}  Yan {cmp[a].mean():>9.4f}   Bayes {cmp[b].mean():>9.4f}   "
          f"corr {cmp[a].corr(cmp[b]):>6.3f}")

# ---------------------------------------------------------------- the intraday posterior
cb = f.groupby("d").b.cumsum().to_numpy(); cs = f.groupby("d").s.cumsum().to_numpy()
cb[~on1] = np.nan; cs[~on1] = np.nan
Bt = pd.Series(cb, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
St = pd.Series(cs, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
wl = D["win_close"] - D["win_open"]

def build_post(params):
    pg = np.full(D["n"], np.nan); pb = np.full(D["n"], np.nan)
    for i in np.flatnonzero(D["inw"]):
        p = params.get(int(D["day"][i]))
        if p is None or not np.isfinite(Bt[i]):
            continue
        fr = min(max((D["mod"][i] + TF - D["win_open"]) / wl, 1e-3), 1.0)
        if "eb" in p:
            g, bb, _ = P.posterior(Bt[i], St[i], p, fr)
        else:
            q = dict(a=p["a"], d=p["d"], eb=p["lb"], es=p["ls"], mu=p["mu"])
            g, bb, _ = P.posterior(Bt[i], St[i], q, fr)
        pg[i] = g; pb[i] = bb
    return pg, pb

POST = {"Yan": build_post(yan), "Bayes": build_post(bay)}
np.save("research/pin/_b1_post.npy",
        np.array([POST["Yan"][0], POST["Yan"][1], POST["Bayes"][0], POST["Bayes"][1]]))
pd.to_pickle(dict(yan=yan, bay=bay), "research/pin/_b1_params.pkl")

print("\n" + "=" * 100)
print("B1.2  WHAT THE POSTERIOR ACTUALLY DOES -- how often it is decisive at all")
print("=" * 100)
print(f"{'estimator':>10} {'finite':>8} {'maxPg':>7} {'>=0.5':>8} {'>=0.7':>8} {'>=0.85':>8} "
      f"{'>=0.95':>8}")
for k, (pg, pb) in POST.items():
    fin = np.isfinite(pg)
    row = [f"{k:>10} {fin.sum():>8,} {np.nanmax(pg):>7.3f}"]
    for th in (0.50, 0.70, 0.85, 0.95):
        n = int(((np.nan_to_num(pg) >= th) | (np.nan_to_num(pb) >= th)).sum())
        row.append(f"{n:>8,}")
    print(" ".join(row))
print(f"\n[{time.time()-t0:.0f}s]")
