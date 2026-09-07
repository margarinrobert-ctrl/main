"""B2 -- is the Bayesian PIN measuring information, or is it absorbing overdispersion?

B1 moved PIN from 0.0142 to 0.1554, straight into the literature's 0.10-0.20 band, which is what
the paper predicts for a liquid asset. It also returned delta = 0.93 -- 93% of news events are BAD
-- on a sample where the index rose 89%. Both cannot be right, so this is the diagnostic.

THE MECHANISM UNDER SUSPICION. The model's only way to explain a spread in B or S wider than a
Poisson allows is to invent an informed component: Poisson variance EQUALS its mean, so any excess
is attributed to mu. Nothing in the estimator distinguishes "informed traders arrived" from "this
series is simply more variable than a Poisson". Duarte and Young (2009) and Gan, Wei and Johnstone
(2017) -- both cited in the paper itself -- make exactly this argument about PIN.

Three checks, in increasing severity:
  1. DISPERSION. var/mean of B and S. A Poisson has 1.0.
  2. CONVERGENCE. Four chains from different starts, Gelman-Rubin R-hat, so a strange answer is
     not just an unconverged one.
  3. POSTERIOR PREDICTIVE. Simulate B and S from the fitted parameters and compare the simulated
     spread to the observed one. This is the Bayesian method's own natural diagnostic and it is the
     decisive one: if the fitted model still cannot reproduce the observed dispersion, the informed
     component has been maxed out trying and PIN is a dispersion reading.
  4. THE PLACEBO. Fit the model to DELIBERATELY INFORMATION-FREE data with the same mean and the
     same overdispersion -- a negative binomial with independent B and S. There is no information
     in it by construction. Whatever PIN it returns is the estimator's floor, not a measurement.
"""
import sys, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/pin")
import numpy as np, pandas as pd
import pin_core as P
import pin_bayes as PB

t0 = time.time()
TF, WIN = 10, 120
D = P.load(tf=TF)
b1 = D["base"]
c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
v = b1["volume"].to_numpy().astype(float)
mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
vbar = np.nanmean(v[on1])

def sess(weight):
    f = pd.DataFrame({"b": np.where(on1 & (c > o), weight, 0.0),
                      "s": np.where(on1 & (c < o), weight, 0.0), "d": day1}, index=b1.index)
    g = f[on1].groupby("d").agg(B=("b", "sum"), S=("s", "sum")).sort_index()
    return g.B.to_numpy(), g.S.to_numpy()

SETS = {"bar counts (EKOP's own unit)": sess(np.ones_like(v)),
        "volume-weighted": sess(v / vbar)}

print("=" * 104)
print("B2.1  DISPERSION -- a Poisson has variance EQUAL to its mean, so var/mean is 1.0")
print("=" * 104)
print(f"{'construction':>30} {'mean B':>9} {'var/mean B':>11} {'mean S':>9} {'var/mean S':>11}")
for k, (B, S) in SETS.items():
    print(f"{k:>30} {B.mean():>9.1f} {B.var(ddof=1)/B.mean():>11.2f} "
          f"{S.mean():>9.1f} {S.var(ddof=1)/S.mean():>11.2f}")

print("\n" + "=" * 104)
print("B2.2  CONVERGENCE -- four chains from different starts, Gelman-Rubin R-hat")
print("=" * 104)
B, S = SETS["volume-weighted"]
Bw, Sw = np.rint(B[-WIN:]), np.rint(S[-WIN:])
chains = []
inits = [dict(a=0.1, d=0.2, mu=5.0, lb=B.mean(), ls=S.mean()),
         dict(a=0.5, d=0.5, mu=50.0, lb=B.mean() * .8, ls=S.mean() * .8),
         dict(a=0.9, d=0.8, mu=150.0, lb=B.mean() * .5, ls=S.mean() * .5),
         dict(a=0.3, d=0.5, mu=20.0, lb=B.mean() * .95, ls=S.mean() * .95)]
for j, ini in enumerate(inits):
    fit = PB.gibbs(Bw, Sw, sweeps=4000, burn=1000, seed=100 + j, init=ini)
    chains.append(fit["chain"])
ch = np.stack(chains)                                  # (4, n, 5)
names = ["alpha", "delta", "mu", "lambda_b", "lambda_s"]
print(f"{'param':>10} " + " ".join(f"{'chain'+str(j):>9}" for j in range(4)) + f" {'R-hat':>7}")
for p in range(5):
    x = ch[:, :, p]
    m, n = x.shape
    Bv = n * x.mean(1).var(ddof=1)
    Wv = x.var(1, ddof=1).mean()
    rhat = np.sqrt(((n - 1) / n * Wv + Bv / n) / Wv) if Wv > 0 else np.nan
    print(f"{names[p]:>10} " + " ".join(f"{x[j].mean():>9.3f}" for j in range(4))
          + f" {rhat:>7.4f}")

print("\n" + "=" * 104)
print("B2.3  POSTERIOR PREDICTIVE -- can the FITTED model reproduce the spread it was fitted to?")
print("=" * 104)
rng = np.random.default_rng(0)
print(f"{'construction':>30} {'':>8} {'observed':>10} {'model':>10} {'ratio':>8}")
for k, (Bx, Sx) in SETS.items():
    Bw, Sw = np.rint(Bx[-WIN:]), np.rint(Sx[-WIN:])
    fit = PB.gibbs(Bw, Sw, sweeps=3000, burn=1000, seed=5)
    reps = []
    for _ in range(400):
        i = rng.integers(len(fit["chain"]))
        a, d, mu, lb, ls = fit["chain"][i]
        u = rng.random(len(Bw))
        Dt = np.where(u < a * d, 1, np.where(u < a, 2, 3))
        bb = rng.poisson(np.where(Dt == 2, lb + mu, lb))
        ss = rng.poisson(np.where(Dt == 1, ls + mu, ls))
        reps.append((bb.std(ddof=1), ss.std(ddof=1), bb.mean(), ss.mean()))
    reps = np.array(reps)
    print(f"{k:>30} {'sd(B)':>8} {Bw.std(ddof=1):>10.1f} {reps[:,0].mean():>10.1f} "
          f"{Bw.std(ddof=1)/reps[:,0].mean():>8.2f}")
    print(f"{'':>30} {'sd(S)':>8} {Sw.std(ddof=1):>10.1f} {reps[:,1].mean():>10.1f} "
          f"{Sw.std(ddof=1)/reps[:,1].mean():>8.2f}")
    print(f"{'':>30} {'PIN':>8} {'':>10} {fit['pin']:>10.4f}  a {fit['a']:.3f} d {fit['d']:.3f} "
          f"mu {fit['mu']:.1f}")

print("\n" + "=" * 104)
print("B2.4  THE PLACEBO -- information-free data with the SAME mean and the SAME overdispersion")
print("=" * 104)
print("  Negative binomial, B and S drawn INDEPENDENTLY. There is no news process in it at all.")
print(f"\n{'target var/mean':>16} {'PIN':>9} {'alpha':>8} {'delta':>8} {'mu':>9} "
      f"{'mu/(lb+ls)':>11}")
for vm in (1.0, 2.0, 5.0, 10.0, 20.0):
    mB, mS = 190.0, 188.0
    def nb(mean, vmr, n, r):
        if vmr <= 1.0001:
            return r.poisson(mean, n)
        rr = mean / (vmr - 1.0)
        return r.negative_binomial(rr, rr / (rr + mean), n)
    r = np.random.default_rng(11)
    Bp, Sp = nb(mB, vm, 400, r), nb(mS, vm, 400, r)
    fit = PB.gibbs(Bp, Sp, sweeps=3000, burn=1000, seed=11)
    print(f"{vm:>16.1f} {fit['pin']:>9.4f} {fit['a']:>8.3f} {fit['d']:>8.3f} {fit['mu']:>9.1f} "
          f"{fit['ratio']:>11.4f}")
print(f"\n[{time.time()-t0:.0f}s]")
