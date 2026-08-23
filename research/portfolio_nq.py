"""Are these twelve strategies a portfolio, or twelve ways of being long NQ?

That is the only question that matters here, and it has a direct test: regress each leg's daily P&L
on NQ's own daily return. Whatever survives that regression is the strategy; whatever does not is
index exposure wearing a strategy's name. Everything else in this file -- correlations, PCA,
allocations, stress tests -- is elaboration on it.

A note on what is NOT done: legs are never selected on their own full-sample profitability. Seven of
the twelve lose money, and dropping them because of that is the same selection this repository has
measured as harmful (best-of-K on 400,226 trend configurations landed at the 23rd percentile out of
sample). Where selection is unavoidable, it happens on a TRAILING window only -- see walk_forward().

Usage: python3 research/portfolio_nq.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from nqdata import load_bars, session_index, session_slice

DAILY = "research/portfolio_daily.parquet"
ANN = 252


# ------------------------------------------------------------------------------------------------
# metrics
# ------------------------------------------------------------------------------------------------
def perf(x: np.ndarray, capital=100_000.0) -> dict:
    x = np.asarray(x, float)
    if len(x) < 2 or x.std() == 0:
        return dict(sharpe=np.nan, sortino=np.nan, cagr=np.nan, maxdd=np.nan, vol=np.nan,
                    var95=np.nan, cvar95=np.nan, skew=np.nan, kurt=np.nan, total=x.sum())
    eq = capital + np.cumsum(x)
    peak = np.maximum.accumulate(eq)
    dd = ((peak - eq) / peak).max()
    yrs = len(x) / ANN
    end = eq[-1]
    cagr = (end / capital) ** (1 / yrs) - 1 if end > 0 else np.nan
    down = x[x < 0]
    sortino = x.mean() / down.std() * np.sqrt(ANN) if len(down) > 1 and down.std() > 0 else np.nan
    q = np.percentile(x, 5)
    return dict(sharpe=x.mean() / x.std() * np.sqrt(ANN), sortino=sortino, cagr=cagr, maxdd=dd,
                vol=x.std() * np.sqrt(ANN) / capital, var95=q, cvar95=x[x <= q].mean(),
                skew=float(pd.Series(x).skew()), kurt=float(pd.Series(x).kurtosis()),
                total=x.sum())


PHDR = (f"  {'allocation':<22}{'total $':>11}{'Sharpe':>8}{'Sortino':>9}{'CAGR':>8}{'vol':>8}"
        f"{'maxDD':>8}{'VaR95':>9}{'CVaR95':>9}{'skew':>7}{'kurt':>7}{'turnover':>10}")


def prow(name, p, turnover=np.nan):
    return (f"  {name:<22}{p['total']:>11,.0f}{p['sharpe']:>8.2f}{p['sortino']:>9.2f}"
            f"{100*p['cagr']:>7.1f}%{100*p['vol']:>7.1f}%{100*p['maxdd']:>7.1f}%"
            f"{p['var95']:>9,.0f}{p['cvar95']:>9,.0f}{p['skew']:>7.2f}{p['kurt']:>7.2f}"
            f"{turnover:>10.2f}")


# ------------------------------------------------------------------------------------------------
# allocations
# ------------------------------------------------------------------------------------------------
def w_equal(cov):
    n = cov.shape[0]
    return np.ones(n) / n


def w_inverse_vol(cov):
    sd = np.sqrt(np.diag(cov))
    w = 1 / np.where(sd > 0, sd, np.inf)
    return w / w.sum()


def w_risk_parity(cov, iters=2000, tol=1e-10):
    """Equal risk contribution by the standard multiplicative fixed point."""
    n = cov.shape[0]
    w = np.ones(n) / n
    for _ in range(iters):
        mrc = cov @ w
        rc = w * mrc
        target = rc.mean()
        new = w * (target / np.where(rc > 0, rc, 1e-12)) ** 0.5
        new = np.clip(new, 1e-8, None)
        new /= new.sum()
        if np.abs(new - w).max() < tol:
            w = new
            break
        w = new
    return w


ALLOCATORS = {"equal weight": w_equal, "inverse volatility": w_inverse_vol,
              "risk parity (ERC)": w_risk_parity}


def diversification_ratio(w, cov):
    sd = np.sqrt(np.diag(cov))
    port_sd = np.sqrt(w @ cov @ w)
    return (w @ sd) / port_sd if port_sd > 0 else np.nan


def effective_bets(corr):
    ev = np.linalg.eigvalsh(corr)
    ev = ev[ev > 1e-12]
    p = ev / ev.sum()
    return float(np.exp(-(p * np.log(p)).sum()))


def vol_target(x, target_ann=0.10, capital=100_000.0, lookback=60, cap=3.0):
    """Scale yesterday's estimate of vol onto a target. Causal: today's size uses data to t-1."""
    s = pd.Series(x)
    realised = s.rolling(lookback).std().shift(1) * np.sqrt(ANN) / capital
    lev = (target_ann / realised).clip(upper=cap).fillna(0.0).to_numpy()
    return x * lev, lev


def main() -> None:
    df = pd.read_parquet(DAILY)
    ts = pd.to_datetime(df.pop("ts"))
    legs = df.astype(float)
    names = list(legs.columns)
    X = legs.to_numpy()

    # NQ's own daily return, on the same session calendar -- the benchmark that matters
    full = session_slice(load_bars("data/NQ_1m.csv"), 570, 960)
    sess = session_index(full.index, 570)
    closes = pd.Series(full["close"].to_numpy(), index=sess).groupby(level=0).last()
    opens = pd.Series(full["open"].to_numpy(), index=sess).groupby(level=0).first()
    nq_ret = ((closes - opens) / opens).reindex(legs.index).fillna(0.0).to_numpy()
    nq_pts = (closes - opens).reindex(legs.index).fillna(0.0).to_numpy()

    print("=" * 118)
    print("1. IS EACH LEG A STRATEGY, OR IS IT NQ?  — regression of daily P&L on the NQ session move")
    print("=" * 118 + "\n")
    print("  alpha is the regression INTERCEPT -- the part of the daily P&L the NQ move does not")
    print("  explain. (The residual MEAN is zero by construction in any OLS with an intercept, so")
    print("  it cannot be used for this and an earlier draft of this table wrongly printed it.)\n")
    print(f"  {'leg':<16}{'total $':>11}{'$/day':>9}{'beta(NQ pt)':>13}{'R^2':>8}"
          f"{'alpha $/day':>13}{'t(alpha)':>10}{'corr(NQ)':>10}")
    resid = {}
    for nm in names:
        y = legs[nm].to_numpy()
        b, a = np.polyfit(nq_pts, y, 1)
        fit = a + b * nq_pts
        r = y - fit
        resid[nm] = r
        ss = 1 - r.var() / y.var() if y.var() > 0 else np.nan
        se_a = r.std(ddof=2) / np.sqrt(len(y))
        t_a = a / se_a if se_a > 0 else np.nan
        print(f"  {nm:<16}{y.sum():>11,.0f}{y.mean():>9.2f}{b:>13.2f}{ss:>8.3f}"
              f"{a:>13.2f}{t_a:>10.2f}{np.corrcoef(y, nq_pts)[0,1]:>10.3f}")

    print("\n" + "=" * 118)
    print("2. CORRELATION MATRIX (daily P&L, all 765 sessions)")
    print("=" * 118 + "\n")
    corr = legs.corr()
    print("      " + "".join(f"{n[:9]:>10}" for n in names))
    for nm in names:
        print(f"  {nm[:11]:<11}" + "".join(f"{corr.loc[nm, o]:>10.2f}" for o in names))

    off = corr.to_numpy()[np.triu_indices(len(names), 1)]
    print(f"\n  mean pairwise correlation {off.mean():+.3f}   median {np.median(off):+.3f}   "
          f"max {off.max():+.3f}   min {off.min():+.3f}")
    print(f"  pairs above +0.7: {(off > 0.7).sum()} of {len(off)};  above +0.9: {(off > 0.9).sum()}")

    print("\n  REDUNDANT PAIRS (|rho| >= 0.80)")
    found = False
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = corr.iloc[i, j]
            if abs(r) >= 0.80:
                found = True
                print(f"    {names[i]:<16} vs {names[j]:<16} rho = {r:+.3f}")
    if not found:
        print("    none")

    print("\n" + "=" * 118)
    print("3. HOW MANY BETS IS THIS REALLY? (PCA on the correlation matrix)")
    print("=" * 118 + "\n")
    ev, evec = np.linalg.eigh(corr.to_numpy())
    ev = ev[::-1]
    evec = evec[:, ::-1]
    share = ev / ev.sum()
    print(f"  {'PC':>4}{'eigenvalue':>13}{'variance share':>17}{'cumulative':>13}")
    for k in range(min(5, len(ev))):
        print(f"  {k+1:>4}{ev[k]:>13.3f}{100*share[k]:>16.1f}%{100*share[:k+1].sum():>12.1f}%")
    print(f"\n  effective number of independent bets: {effective_bets(corr.to_numpy()):.2f} "
          f"out of {len(names)} legs")
    load1 = pd.Series(evec[:, 0], index=names).sort_values(key=abs, ascending=False)
    print(f"  PC1 loadings (largest first): " +
          ", ".join(f"{k} {v:+.2f}" for k, v in load1.head(6).items()))
    pc1 = legs.to_numpy() @ evec[:, 0]
    print(f"  correlation of PC1 with the NQ session move: {np.corrcoef(pc1, nq_pts)[0,1]:+.3f}")

    # ---------------------------------------------------------------------------------------
    print("\n" + "=" * 118)
    print("4. CORRELATION STABILITY — rolling 120-session windows")
    print("=" * 118 + "\n")
    roll = []
    for a in range(0, len(legs) - 120, 20):
        c = legs.iloc[a:a + 120].corr().to_numpy()
        roll.append(c[np.triu_indices(len(names), 1)])
    roll = np.array(roll)
    print(f"  {len(roll)} windows; mean pairwise correlation per window: "
          f"min {roll.mean(1).min():+.3f}, median {np.median(roll.mean(1)):+.3f}, "
          f"max {roll.mean(1).max():+.3f}")
    spread = roll.max(0) - roll.min(0)
    print(f"  per-PAIR range across windows: median {np.median(spread):.3f}, "
          f"90th pct {np.percentile(spread, 90):.3f}, max {spread.max():.3f}")
    flip = ((roll.min(0) < -0.1) & (roll.max(0) > 0.1)).sum()
    print(f"  pairs whose correlation crosses from below -0.1 to above +0.1: {flip} of {roll.shape[1]}")

    print("\n" + "=" * 118)
    print("5. STRESS — correlation when NQ moves most")
    print("=" * 118 + "\n")
    absmove = np.abs(nq_pts)
    tert = pd.qcut(pd.Series(absmove), 3, labels=["calm", "normal", "volatile"])
    print(f"  {'regime':<12}{'sessions':>10}{'mean pairwise rho':>20}{'PC1 share':>12}"
          f"{'eff. bets':>11}")
    for lab in ["calm", "normal", "volatile"]:
        m = (tert == lab).to_numpy()
        c = legs[m].corr().to_numpy()
        o = c[np.triu_indices(len(names), 1)]
        e = np.linalg.eigvalsh(c)[::-1]
        print(f"  {lab:<12}{m.sum():>10}{o.mean():>20.3f}{100*e[0]/e.sum():>11.1f}%"
              f"{effective_bets(c):>11.2f}")
    top = absmove >= np.percentile(absmove, 90)
    c = legs[top].corr().to_numpy()
    o = c[np.triu_indices(len(names), 1)]
    e = np.linalg.eigvalsh(c)[::-1]
    print(f"  {'top decile':<12}{top.sum():>10}{o.mean():>20.3f}{100*e[0]/e.sum():>11.1f}%"
          f"{effective_bets(c):>11.2f}")
    print("\n  The number to watch is whether correlations RISE when it matters -- diversification")
    print("  that disappears in the tail was never diversification.")

    print("\n" + "=" * 118)
    print("6. ALLOCATIONS — equal weight vs inverse volatility vs risk parity")
    print("=" * 118 + "\n")
    cov = np.cov(X.T)
    print(PHDR)
    weights = {}
    for nm, fn in ALLOCATORS.items():
        w = fn(cov)
        weights[nm] = w
        port = X @ w
        # turnover: weights are static here, so the only turnover is the legs' own trading
        print(prow(nm, perf(port), 0.0))
        print(f"      diversification ratio {diversification_ratio(w, cov):.3f}   "
              f"weights: " + ", ".join(f"{n}={v:.3f}" for n, v in
                                       sorted(zip(names, w), key=lambda t: -t[1])[:4]))
    print(prow("NQ buy-and-hold (1 lot)", perf(nq_pts * 20.0), 0.0))

    print("\n" + "=" * 118)
    print("7. VOLATILITY TARGETING — 10% annualised on $100k, sized from a trailing 60-day estimate")
    print("=" * 118 + "\n")
    print(PHDR)
    for nm, w in weights.items():
        port = X @ w
        scaled, lev = vol_target(port)
        turn = np.abs(np.diff(lev, prepend=lev[0])).mean()
        print(prow(nm + " + vol tgt", perf(scaled), turn))

    print("\n" + "=" * 118)
    print("8. WALK-FORWARD ALLOCATION — weights estimated on a trailing 250 sessions only")
    print("=" * 118 + "\n")
    print(PHDR)
    for nm, fn in ALLOCATORS.items():
        out = np.zeros(len(X))
        prev = None
        turns = []
        for t in range(250, len(X)):
            w = fn(np.cov(X[t - 250:t].T))
            out[t] = X[t] @ w
            if prev is not None:
                turns.append(np.abs(w - prev).sum())
            prev = w
        print(prow(nm + " (WF)", perf(out[250:]), float(np.mean(turns)) if turns else np.nan))
    ew = X[250:] @ w_equal(cov)
    print(f"\n  static equal weight over the same span for comparison: ${ew.sum():,.0f}, "
          f"Sharpe {perf(ew)['sharpe']:.2f}")

    print("\n" + "=" * 118)
    print("9. MONTE CARLO — stationary block bootstrap of the portfolio's daily series")
    print("=" * 118 + "\n")
    rng = np.random.default_rng(20250822)
    for nm, w in weights.items():
        port = X @ w
        n = len(port)
        ends, dds = [], []
        for _ in range(5000):
            idx = []
            while len(idx) < n:
                st = rng.integers(0, n)
                ln = max(1, rng.geometric(1 / 10))
                idx.extend(range(st, min(st + ln, n)))
            p = port[np.array(idx[:n])]
            eq = 100_000 + np.cumsum(p)
            ends.append(eq[-1])
            dds.append(((np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)).max())
        ends = np.array(ends); dds = np.array(dds)
        print(f"  {nm:<22} median end ${np.median(ends):>9,.0f}   5th ${np.percentile(ends,5):>9,.0f}"
              f"   P(loss) {100*(ends<100_000).mean():>5.1f}%   medianDD {100*np.median(dds):>5.1f}%"
              f"   p95DD {100*np.percentile(dds,95):>5.1f}%")


if __name__ == "__main__":
    main()
