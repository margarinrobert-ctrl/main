"""Everything between a candidate and a decision: perturbation, regimes, walk-forward, Monte Carlo,
cost stress, deflated Sharpe, and the one read of OOS.

WHAT EACH TEST IS FOR, because a battery run without that is decoration:

  PERTURBATION      A parameter is a hypothesis about the market; if it only works at one value it
                    was a hypothesis about the sample. Every axis is walked one rung either way and
                    the whole neighbourhood is reported, not its minimum -- `CLAUDE.md` records that
                    ranking by a MINIMUM over a neighbourhood cost $18,970.

  REGIME            Trend/chop by CHOP(14), high/low volatility by the realised-vol percentile,
                    bull/bear by the 200-bar trend, all measured AT THE SIGNAL BAR. A strategy that
                    lives in one regime is a bet on that regime persisting.

  WALK-FORWARD      Rolling train -> test. Contaminated if the thresholds were chosen on the whole
                    training span, so the folds are reported with that stated: they measure
                    STABILITY of the chosen configuration, not the selection procedure.

  MONTE CARLO       Two resamplers, never one. BOOTSTRAP whole days with their trades attached for
                    the edge; PERMUTE the realised order for the path. Permutation cannot change
                    the endpoint, so no endpoint distribution is printed from it.

  COST STRESS       1.0x to 3.0x. The test most likely to kill a result, and the cheapest.

  DEFLATED SHARPE   Bailey & Lopez de Prado. Given N independent trials, the expected MAXIMUM
                    Sharpe under the null is well above zero, so a raw Sharpe compared to zero is
                    the wrong comparison after a 200,000-cell search.
"""
from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/v33")
import v33core as V           # noqa: E402

EULER = 0.5772156649015329


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(q):
    # Acklam's rational approximation; adequate at the precision this is reported to
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if q < pl:
        r = math.sqrt(-2 * math.log(q))
        return (((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]) / \
               ((((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1)
    if q > ph:
        r = math.sqrt(-2 * math.log(1 - q))
        return -(((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]) / \
               ((((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1)
    r = q - 0.5
    s = r * r
    return (((((a[0] * s + a[1]) * s + a[2]) * s + a[3]) * s + a[4]) * s + a[5]) * r / \
           (((((b[0] * s + b[1]) * s + b[2]) * s + b[3]) * s + b[4]) * s + 1)


def deflated_sharpe(daily, n_trials, sr_bench=0.0):
    """Bailey & Lopez de Prado. Returns (observed annualised SR, the SR a search of this size
    produces under the NULL, and the probability the observed one is real)."""
    d = np.asarray(daily, float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 30 or d.std(ddof=1) == 0:
        return None
    sr = d.mean() / d.std(ddof=1)                     # per-period, not annualised
    g1 = float(pd.Series(d).skew())
    g2 = float(pd.Series(d).kurt()) + 3.0             # pandas kurt is EXCESS
    N = max(int(n_trials), 2)
    # expected maximum of N independent standard-normal SR estimates
    e_max = ((1 - EULER) * _norm_ppf(1 - 1.0 / N) + EULER * _norm_ppf(1 - 1.0 / (N * math.e)))
    sr0 = e_max / math.sqrt(T)                        # the benchmark a search of size N sets
    denom = math.sqrt(max(1e-12, 1 - g1 * sr + (g2 - 1) / 4.0 * sr * sr))
    psr = _norm_cdf((sr - max(sr0, sr_bench)) * math.sqrt(T - 1) / denom)
    return dict(sr_ann=sr * math.sqrt(V.TRADING_DAYS), sr_null_ann=sr0 * math.sqrt(V.TRADING_DAYS),
                skew=g1, kurt=g2, T=T, n_trials=N, dsr=psr)


# ---- perturbation --------------------------------------------------------------------------------
AXES = dict(entry_n=V.ENTRY_N, exit_n=V.EXIT_N, stop=V.STOP, tp_r=V.TP_R,
            chop_max=V.CHOP, adx_min=V.ADX)


def perturb(market, p, block_name="valid"):
    """Every axis walked over its whole declared ladder, on the named block.

    AN AXIS THAT CHANGES NOTHING IS MARKED INERT AND EXCLUDED FROM THE STABILITY SCORE. Two do so
    here and both would otherwise inflate it: `stop` is inert whenever `vol_policy` is on, because
    the policy supplies its own two stops and the scalar is never read; and `adx_min` is inert at
    60 minutes because every rung above None empties the sample. Counting a flat line as four
    passing rungs is how a stability score reaches 1.000 without measuring anything."""
    rows = []
    for axis, values in AXES.items():
        for v in values:
            q = V.Params(**{**p.dict(), axis: v})
            blocks = V.splits(V.prep(market, q.tf, q.entry_n, q.exit_n)["sess"])
            R, days, P, _O, _i = V.trades(market, q, blocks[block_name])
            m = V.metrics(R, days, P, all_sess=V.block_days(P, blocks[block_name], block_name))
            rows.append(dict(axis=axis, value=str(v), at_optimum=(v == getattr(p, axis)),
                             n=m["n"] if m else 0, pf=m["pf"] if m else np.nan,
                             sharpe=m["sharpe"] if m else np.nan,
                             retdd=m["retdd"] if m else np.nan))
    return pd.DataFrame(rows)


def inert_axes(pt, tol=1e-9):
    """Axes whose whole ladder returns the identical result -- they measure nothing."""
    out = []
    for axis, g in pt.groupby("axis"):
        v = g.sharpe.dropna()
        if len(v) < 2 or float(v.max() - v.min()) <= tol:
            out.append(axis)
    return out


def stability_score(pt):
    """Share of the declared ladder, across the INFORMATIVE axes, keeping PF > 1 and Sharpe > 0."""
    inert = inert_axes(pt)
    ok = pt[~pt.axis.isin(inert)].dropna(subset=["sharpe"])
    if not len(ok):
        return 0.0, inert
    return float(((ok.pf > 1.0) & (ok.sharpe > 0)).mean()), inert


# ---- regimes --------------------------------------------------------------------------------------
def regimes(market, p, block_name="valid"):
    """Split the SIGNAL bars by regime and re-simulate each subset. Filtering the TRIGGERS and
    re-running is the only valid form of this test -- a conditional split of realised trades is not
    a filter test (`STUDY_AUCTION`)."""
    import v16core as C
    blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
    blk = blocks[block_name]
    P = V.prep(market, p.tf, p.entry_n, p.exit_n)
    if p.vol_policy is not None:
        _P, sig, O, base_keep = V.outcomes_adaptive(market, p)
    else:
        _P, sig, O = V.outcomes(market, p)
        base_keep = np.ones(len(sig), bool)
    keep = base_keep & (O["xb"] >= 0) & blk[sig]
    if p.chop_max is not None:
        keep &= np.isfinite(P["chop"][sig]) & (P["chop"][sig] <= p.chop_max)
    if p.adx_min is not None:
        keep &= np.isfinite(P["adx"][sig]) & (P["adx"][sig] >= p.adx_min)
    if p.session is not None:
        a, b = p.session
        keep &= (P["mod"][sig] >= a) & (P["mod"][sig] < b)

    c = P["c"]
    ma = pd.Series(c).rolling(200).mean().to_numpy()
    ch, vp, ad = P["chop"][sig], P["volpct"][sig], P["adx"][sig]
    bull = np.isfinite(ma) & (c > ma)
    defs = {
        "TREND  chop<=40": np.isfinite(ch) & (ch <= 40),
        "CHOP   chop> 40": np.isfinite(ch) & (ch > 40),
        "HIGH vol pct>0.5": np.isfinite(vp) & (vp > 0.5),
        "LOW  vol pct<=.5": np.isfinite(vp) & (vp <= 0.5),
        "BULL  >200MA": bull[sig],
        "BEAR  <=200MA": np.isfinite(ma[sig]) & ~bull[sig],
        "HIGH momentum adx>=25": np.isfinite(ad) & (ad >= 25),
        "LOW  momentum adx<25": np.isfinite(ad) & (ad < 25),
    }
    rows = []
    for name, m_ in defs.items():
        idx = C.take(O, keep & m_)
        R = O["R"][idx]
        days = P["sess"][O["sig"][idx]]
        m = V.metrics(R, days, P, all_sess=V.block_days(P, blk, block_name)) if len(R) else None
        rows.append(dict(regime=name, n=len(R), pf=m["pf"] if m else np.nan,
                         sharpe=m["sharpe"] if m else np.nan, R=float(R.mean()) if len(R) else
                         np.nan, share=float((m_ & keep).sum() / max(keep.sum(), 1))))
    return pd.DataFrame(rows)


# ---- walk-forward ----------------------------------------------------------------------------------
def walk_forward(market, p, n_folds=6):
    """Rolling contiguous folds over the WHOLE series, reporting the configuration's stability.
    This is NOT a re-optimisation per fold: the parameters were chosen on TRAIN, so folds that
    postdate the split are the meaningful ones and are marked."""
    P = V.prep(market, p.tf, p.entry_n, p.exit_n)
    R, days, _P, _O, _i = V.trades(market, p)
    u = np.unique(P["sess"])
    cut_train = u[int(len(u) * V.TRAIN)]
    edges = np.linspace(0, len(u), n_folds + 1).astype(int)
    rows = []
    for f in range(n_folds):
        lo, hi = u[edges[f]], u[min(edges[f + 1], len(u) - 1)]
        m_ = (days >= lo) & (days <= hi)
        if m_.sum() < 15:
            rows.append(dict(fold=f + 1, span=f"{lo}-{hi}", n=int(m_.sum()), pf=np.nan,
                             sharpe=np.nan, R=np.nan, post_selection=bool(lo >= cut_train)))
            continue
        Rf, df_ = R[m_], days[m_]
        allsess = u[(u >= lo) & (u <= hi)]
        m = V.metrics(Rf, df_, P, all_sess=allsess)
        rows.append(dict(fold=f + 1, span=f"{lo}-{hi}", n=len(Rf),
                         pf=m["pf"] if m else np.nan, sharpe=m["sharpe"] if m else np.nan,
                         R=float(Rf.mean()), post_selection=bool(lo >= cut_train)))
    return pd.DataFrame(rows)


# ---- Monte Carlo -------------------------------------------------------------------------------------
def mc(R, days, draws=4000, seed=11):
    rng = np.random.default_rng(seed)
    _u, inv = np.unique(days, return_inverse=True)
    nd = inv.max() + 1
    by = [np.flatnonzero(inv == j) for j in range(nd)]
    boot_R, boot_pf = np.empty(draws), np.empty(draws)
    for k in range(draws):
        pick = np.concatenate([by[j] for j in rng.integers(0, nd, nd)])
        r = R[pick]
        boot_R[k] = r.mean()
        boot_pf[k] = r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan
    r2 = R.copy()
    perm = np.empty(draws)
    for k in range(draws):
        rng.shuffle(r2)
        eq = np.cumsum(r2)
        perm[k] = np.max(np.maximum.accumulate(eq) - eq)
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(R=float(R.mean()), R_p05=float(np.percentile(boot_R, 5)),
                R_p95=float(np.percentile(boot_R, 95)),
                p_R_negative=float((boot_R <= 0).mean()),
                pf_p05=float(np.nanpercentile(boot_pf, 5)),
                pf_p95=float(np.nanpercentile(boot_pf, 95)),
                p_pf_below1=float(np.nanmean(boot_pf <= 1.0)),
                dd=dd, dd_p50=float(np.percentile(perm, 50)),
                dd_p95=float(np.percentile(perm, 95)),
                dd_p99=float(np.percentile(perm, 99)),
                dd_pctile=float((perm <= dd).mean()))


# ---- cost stress ---------------------------------------------------------------------------------------
def cost_stress(market, p, block_name="valid", mults=(1.0, 1.25, 1.5, 2.0, 3.0)):
    """Re-prep at each cost multiplier. Costs are inside the engine's fill, so this is a re-walk,
    not a subtraction."""
    base = V.NQ_COST_MULT if market == "NQ" else V.US30_COST_MULT
    rows = []
    for mu in mults:
        V._PREP.clear(); V._OUT.clear(); V._SESS.clear()
        if market == "NQ":
            V.NQ_COST_MULT = base * mu
        else:
            V.US30_COST_MULT = base * mu
        blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
        R, days, P, _O, _i = V.trades(market, p, blocks[block_name])
        m = V.metrics(R, days, P, all_sess=V.block_days(P, blocks[block_name], block_name))
        rows.append(dict(cost_mult=mu, n=m["n"] if m else 0, pf=m["pf"] if m else np.nan,
                         sharpe=m["sharpe"] if m else np.nan, R=m["R"] if m else np.nan))
    if market == "NQ":
        V.NQ_COST_MULT = base
    else:
        V.US30_COST_MULT = base
    V._PREP.clear(); V._OUT.clear(); V._SESS.clear()
    return pd.DataFrame(rows)


def read_oos(market, p):
    """THE ONE READ. Nothing may be changed after this is called."""
    blocks = V.splits(V.prep(market, p.tf, p.entry_n, p.exit_n)["sess"])
    R, days, P, _O, _i = V.trades(market, p, blocks["oos"])
    return V.metrics(R, days, P, all_sess=V.block_days(P, blocks["oos"], "oos")), R, days
